"""
Move trailing spaces of implicitly concatenated strings to the next piece.

For two string literals that are implicitly concatenated across lines, such
as::

    "abc"

    'def'

the trailing spaces of the first piece are moved to the start of the next
piece::

    "abc"

    ' def'

The concatenated value does not change; only the place of the spaces does.
"""

from __future__ import annotations

import io
import itertools
import re
import tokenize
from collections import Counter
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator

# The prefix (such as ``rb`` or ``f``) and the opening quote of a literal
PREFIX_AND_QUOTE_RE = re.compile(r'([A-Za-z]*)(\'\'\'|"""|\'|")')
_TRIPLE_QUOTES = frozenset({"'''", '"""'})

# Python 3.12+ splits f-strings into FSTRING_START/MIDDLE/END tokens, and
# Python 3.14+ does the same for t-strings. Earlier versions emit one STRING
# token per f-string.
_START_TYPES = frozenset(
    getattr(tokenize, name)
    for name in ('FSTRING_START', 'TSTRING_START')
    if hasattr(tokenize, name)
)
_END_TYPES = frozenset(
    getattr(tokenize, name)
    for name in ('FSTRING_END', 'TSTRING_END')
    if hasattr(tokenize, name)
)

# Tokens that may sit between two implicitly concatenated pieces
_SKIPPABLE_TYPES = frozenset({tokenize.NL, tokenize.COMMENT})


class TokenPositionError(Exception):
    """Raised when a token position does not point at the token's text."""


@dataclass(frozen=True)
class SkippedPair:
    """
    A pair left unchanged because moving its spaces makes a line too long.

    Attributes
    ----------
    lineNo : int
        The 1-based number of the line that holds the next piece.
    newLength : int
        The length that line would have after moving the spaces.
    """

    lineNo: int
    newLength: int


@dataclass(frozen=True)
class FixResult:
    """
    The outcome of fixing one piece of source code.

    Attributes
    ----------
    source : str
        The fixed source code.
    fixedPairs : int
        The number of pairs whose trailing spaces were moved.
    skippedPairs : tuple[SkippedPair, ...]
        The pairs skipped because of the line length, ordered by line.
    """

    source: str
    fixedPairs: int
    skippedPairs: tuple[SkippedPair, ...]


@dataclass(frozen=True)
class _Piece:
    """One string literal; an f-string or t-string spans several tokens."""

    firstToken: int
    lastToken: int
    start: tuple[int, int]
    end: tuple[int, int]


@dataclass(frozen=True)
class _Move:
    """Moving ``count`` trailing spaces of one piece to the next piece."""

    count: int
    deleteAt: int  # offset of the first trailing space
    deleteLineNo: int
    insertAt: int  # offset right after the next piece's opening quote
    insertLineNo: int


def fixSource(source: str, lineLength: int = 79) -> FixResult:
    """
    Move trailing spaces of implicitly concatenated pieces to the next piece.

    Parameters
    ----------
    source : str
        Python source code. It must be valid Python.
    lineLength : int, default=79
        A pair is skipped if moving its spaces would push the line holding the
        next piece over this length. Lines that are already longer are not
        checked.

    Returns
    -------
    FixResult
        The fixed source code and the pairs that were skipped.
    """
    lines = splitLines(source)

    # Python ends a line at '\r\n', '\r', or '\n', but the pure-Python
    # tokenizer of Python 3.10 and 3.11 does not recognize a lone '\r'.
    # Replacing it with '\n' keeps every line the same length, so token
    # positions stay valid for the original source.
    normalizedLines = [
        line[:-1] + '\n' if line.endswith('\r') else line for line in lines
    ]
    lineIter = iter(normalizedLines)
    tokens = list(tokenize.generate_tokens(lambda: next(lineIter, '')))

    lineStarts = [0, *itertools.accumulate(len(line) for line in lines)]
    moves = _findMoves(''.join(normalizedLines), tokens, lineStarts)
    acceptedMoves, skippedPairs = _selectMoves(moves, lines, lineLength)
    return FixResult(
        source=_applyMoves(source, acceptedMoves),
        fixedPairs=len(acceptedMoves),
        skippedPairs=skippedPairs,
    )


def splitLines(source: str) -> list[str]:
    r"""
    Split source code into physical lines as Python defines them.

    Lines end at ``\r\n``, ``\r``, or ``\n`` only, and keep their line endings.
    Unlike ``str.splitlines()``, this does not split at ``\f``, ``\v``,
    ``\x1c``, ``\u2028``, and similar characters, which tokenize treats as
    ordinary characters within a line.

    Parameters
    ----------
    source : str
        Python source code.

    Returns
    -------
    list[str]
        The lines, each with its line ending (if any).
    """
    return io.StringIO(source, newline='').readlines()


def _findMoves(
        source: str,
        tokens: list[tokenize.TokenInfo],
        lineStarts: list[int],
) -> list[_Move]:
    """Find every pair of pieces whose trailing spaces can be moved."""
    pieces = list(_iterPieces(tokens))
    moves: list[_Move] = []
    for piece, nextPiece in itertools.pairwise(pieces):
        if nextPiece.start[0] == piece.end[0]:
            continue  # same line, such as 'a ' 'b'

        between = tokens[piece.lastToken + 1 : nextPiece.firstToken]
        if any(token.type not in _SKIPPABLE_TYPES for token in between):
            continue  # not implicitly concatenated, such as 'a ', 'b'

        text = _getPieceText(source, tokens, piece, lineStarts)
        nextText = _getPieceText(source, tokens, nextPiece, lineStarts)
        match = PREFIX_AND_QUOTE_RE.match(text)
        nextMatch = PREFIX_AND_QUOTE_RE.match(nextText)
        if match is None or nextMatch is None:
            continue

        quote = match.group(2)
        if quote in _TRIPLE_QUOTES or nextMatch.group(2) in _TRIPLE_QUOTES:
            continue

        body = text[match.end() : -len(quote)]
        stripped = body.rstrip(' ')
        count = len(body) - len(stripped)
        if count == 0 or stripped == '':
            continue  # no trailing spaces, or only spaces

        if (len(stripped) - len(stripped.rstrip('\\'))) % 2 == 1:
            continue  # a backslash escapes the first trailing space

        closingQuoteAt = _toOffset(piece.end, lineStarts) - len(quote)
        moves.append(
            _Move(
                count=count,
                deleteAt=closingQuoteAt - count,
                deleteLineNo=piece.end[0],
                insertAt=_toOffset(nextPiece.start, lineStarts)
                + nextMatch.end(),
                insertLineNo=nextPiece.start[0],
            )
        )

    return moves


def _iterPieces(tokens: list[tokenize.TokenInfo]) -> Iterator[_Piece]:
    """Yield every string literal, with an f-string or t-string as one."""
    i = 0
    while i < len(tokens):
        token = tokens[i]
        if token.type == tokenize.STRING:
            yield _Piece(i, i, token.start, token.end)
        elif token.type in _START_TYPES:
            # Skip to the matching end token. Nested f-strings and the
            # strings inside replacement fields belong to this piece.
            depth = 0
            j = i
            while True:
                if tokens[j].type in _START_TYPES:
                    depth += 1
                elif tokens[j].type in _END_TYPES:
                    depth -= 1
                    if depth == 0:
                        break

                j += 1

            yield _Piece(i, j, token.start, tokens[j].end)
            i = j

        i += 1


def _getPieceText(
        source: str,
        tokens: list[tokenize.TokenInfo],
        piece: _Piece,
        lineStarts: list[int],
) -> str:
    """
    Return the source text of a piece, checking it against its tokens.

    The check guards against offsets that drift from token positions. Such a
    drift could move spaces inside comments, which the AST comparison would not
    catch.
    """
    text = source[
        _toOffset(piece.start, lineStarts) : _toOffset(piece.end, lineStarts)
    ]
    first = tokens[piece.firstToken]
    last = tokens[piece.lastToken]
    if piece.firstToken == piece.lastToken:
        isConsistent = text == first.string
    else:
        isConsistent = text.startswith(first.string) and text.endswith(
            last.string
        )

    if not isConsistent:
        raise TokenPositionError(
            f'line {piece.start[0]}: token positions do not match the source'
        )

    return text


def _toOffset(position: tuple[int, int], lineStarts: list[int]) -> int:
    """Convert a 1-based row and a 0-based column into an offset."""
    return lineStarts[position[0] - 1] + position[1]


def _selectMoves(
        moves: list[_Move],
        lines: list[str],
        lineLength: int,
) -> tuple[list[_Move], tuple[SkippedPair, ...]]:
    """
    Keep the moves that do not push a line over the line length.

    A line can gain spaces at its first piece and lose spaces at its last
    piece, and the net change decides its new length. Whether it loses spaces
    depends on a later pair, so the pairs are checked from the last one
    backwards.
    """
    lengths = [len(line.rstrip('\r\n')) for line in lines]
    change: Counter[int] = Counter()
    acceptedMoves: list[_Move] = []
    skippedPairs: list[SkippedPair] = []
    for move in reversed(moves):
        oldLength = lengths[move.insertLineNo - 1]
        newLength = oldLength + change[move.insertLineNo] + move.count
        if oldLength <= lineLength < newLength:
            skippedPairs.append(SkippedPair(move.insertLineNo, newLength))
            continue

        change[move.insertLineNo] += move.count
        change[move.deleteLineNo] -= move.count
        acceptedMoves.append(move)

    return acceptedMoves, tuple(reversed(skippedPairs))


def _applyMoves(source: str, moves: list[_Move]) -> str:
    """Delete the trailing spaces and insert them after the next quote."""
    edits = sorted(
        [(move.deleteAt, move.count, '') for move in moves]
        + [(move.insertAt, 0, ' ' * move.count) for move in moves]
    )
    parts: list[str] = []
    position = 0
    for offset, deleteCount, insertText in edits:
        parts.extend((source[position:offset], insertText))
        position = offset + deleteCount

    parts.append(source[position:])
    return ''.join(parts)
