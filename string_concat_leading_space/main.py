from __future__ import annotations

import ast
import io
import sys
import tokenize
import warnings
from pathlib import Path

import click

from string_concat_leading_space.fixer import TokenPositionError, fixSource


@click.command()
@click.version_option(package_name='string-concat-leading-space')
@click.argument('filenames', nargs=-1, type=click.Path())
@click.option(
    '--line-length',
    'lineLength',
    type=click.IntRange(min=1),
    default=79,
    show_default=True,
    help=(
        'Maximum line length. A pair is skipped (and reported as path:line)'
        ' if moving its spaces would push a line over this length.'
    ),
)
def main(filenames: tuple[str, ...], lineLength: int) -> None:
    """
    Move trailing spaces of implicitly concatenated strings to the next piece.

    Exit with 1 if any file is rewritten or any error happens, otherwise 0.
    """
    status = 0
    for filename in filenames:
        status |= fixFile(filename, lineLength=lineLength)

    if status != 0:
        raise SystemExit(status)


def fixFile(filename: str, *, lineLength: int = 79) -> int:
    """
    Fix one file in place, keeping its encoding and line endings.

    Files that cannot be decoded or parsed are skipped. The file is not written
    if the fixed source would parse into a different AST.

    Parameters
    ----------
    filename : str
        The file to fix.
    lineLength : int, default=79
        The maximum line length.

    Returns
    -------
    int
        1 if the file is rewritten or an error happens, otherwise 0.
    """
    path = Path(filename)
    try:
        # detect_encoding() only knows '\n', but Python also ends a line
        # at a lone '\r', so line endings are normalized for it
        data = path.read_bytes().replace(b'\r\n', b'\n').replace(b'\r', b'\n')
        encoding, _ = tokenize.detect_encoding(io.BytesIO(data).readline)

        # newline='' keeps '\r\n' and '\r' line endings as they are
        with path.open(encoding=encoding, newline='') as f:
            source = f.read()

        tree = _parse(source)
    except OSError as exc:
        _report(f'{filename}: error: cannot read the file: {exc}')
        return 1
    except (SyntaxError, ValueError):
        # Such as invalid bytes, an invalid encoding declaration, null bytes,
        # or invalid syntax. Depending on the Python version, the same
        # problem can come from detect_encoding(), decoding, or parsing.
        _report(f'{filename}: cannot parse, skipped')
        return 0

    try:
        result = fixSource(source, lineLength=lineLength)
    except (SyntaxError, tokenize.TokenError):
        _report(f'{filename}: cannot tokenize, skipped')
        return 0
    except TokenPositionError as exc:
        _report(f'{filename}: error: {exc}; file left unchanged')
        return 1

    status = 0
    if result.source != source:
        if not _hasSameAst(tree, result.source):
            _report(
                f'{filename}: error: the rewrite would change the AST;'
                ' file left unchanged'
            )
            return 1

        _report(f'Rewriting {filename}')
        path.write_text(result.source, encoding=encoding, newline='')
        status = 1

    for pair in result.skippedPairs:
        _report(
            f'{filename}:{pair.lineNo}: skipped: moving the spaces here'
            f' would make the line {pair.newLength} characters long'
            f' (limit: {lineLength}); please rewrap it'
        )

    return status


def _parse(source: str) -> ast.Module:
    """Parse source code without printing warnings about its content."""
    with warnings.catch_warnings():
        # Such as "SyntaxWarning: invalid escape sequence"
        warnings.simplefilter('ignore')
        return ast.parse(source)


def _hasSameAst(tree: ast.Module, newSource: str) -> bool:
    """Check whether ``newSource`` parses into the same AST as ``tree``."""
    try:
        newTree = _parse(newSource)
    except (SyntaxError, ValueError):
        return False

    return ast.dump(newTree) == ast.dump(tree)


def _report(message: str) -> None:
    print(message, file=sys.stderr)


if __name__ == '__main__':
    main()
