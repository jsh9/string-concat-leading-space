from __future__ import annotations

import io
import sys
import tokenize

import pytest

from string_concat_leading_space import fixer
from string_concat_leading_space.fixer import (
    FixResult,
    SkippedPair,
    TokenPositionError,
    fixSource,
    splitLines,
)
from tests.helpers import code, dumpAst

requiresPy312 = pytest.mark.skipif(
    sys.version_info < (3, 12),
    reason='Needs PEP 701 f-strings (Python 3.12+)',
)
requiresPy314 = pytest.mark.skipif(
    sys.version_info < (3, 14),
    reason='Needs t-strings (Python 3.14+)',
)


def checkFix(before: str, after: str, lineLength: int = 79) -> FixResult:
    """
    Check that fixing ``before`` gives ``after``.

    Comparing the ASTs checks that every concatenated value is unchanged.
    Fixing ``after`` again must not change anything.
    """
    result = fixSource(before, lineLength=lineLength)
    assert result.source == after
    assert dumpAst(result.source) == dumpAst(before)
    assert fixSource(after, lineLength=lineLength).source == after
    return result


@pytest.mark.parametrize(
    ('before', 'after'),
    [
        pytest.param(
            """
            x = (
                'plain one '
                'two'
            )
            """,
            """
            x = (
                'plain one'
                ' two'
            )
            """,
            id='parenthesized',
        ),
        pytest.param(
            """
            print(
                "double quotes "
                "two",
                end='',
            )
            """,
            """
            print(
                "double quotes"
                " two",
                end='',
            )
            """,
            id='call-argument',
        ),
        pytest.param(
            """
            x = (
                'single quotes '
                "double quotes"
            )
            """,
            """
            x = (
                'single quotes'
                " double quotes"
            )
            """,
            id='mixed-quotes',
        ),
        pytest.param(
            r"""
            x = 'backslash continuation ' \
                'between pieces'
            """,
            r"""
            x = 'backslash continuation' \
                ' between pieces'
            """,
            id='backslash-continuation-between-pieces',
        ),
        pytest.param(
            r"""
            x = (
                'a piece that \
            spans lines '
                'next'
            )
            """,
            r"""
            x = (
                'a piece that \
            spans lines'
                ' next'
            )
            """,
            id='piece-spanning-lines',
        ),
        pytest.param(
            """
            x = (
                'blank lines '

                'between pieces'
            )
            """,
            """
            x = (
                'blank lines'

                ' between pieces'
            )
            """,
            id='blank-line-between-pieces',
        ),
        pytest.param(
            """
            def f():
                return {
                    'key': (
                        'indented '
                        'value'
                    ),
                }
            """,
            """
            def f():
                return {
                    'key': (
                        'indented'
                        ' value'
                    ),
                }
            """,
            id='indented',
        ),
    ],
)
def testMovesTrailingSpacesToTheNextPiece(before: str, after: str) -> None:
    checkFix(code(before), code(after))


@pytest.mark.parametrize(
    'source',
    [
        pytest.param(
            """
            x = ('explicit ' +
                 'concatenation')
            """,
            id='plus-operator',
        ),
        pytest.param(
            """
            x = ['list ',
                 'items']
            """,
            id='comma',
        ),
        pytest.param(
            """
            x = {'key ':
                 'value'}
            """,
            id='colon',
        ),
        pytest.param(
            """
            x = ('conditional ' if x else
                 'expression')
            """,
            id='conditional-expression',
        ),
        pytest.param(
            """
            x = 'separate '
            y = 'statements'
            """,
            id='separate-statements',
        ),
        pytest.param(
            """
            'separate '
            'expression statements'
            """,
            id='separate-expression-statements',
        ),
    ],
)
def testOnlyTouchesImplicitConcatenation(source: str) -> None:
    checkFix(code(source), code(source))


@pytest.mark.parametrize(
    ('before', 'after'),
    [
        pytest.param(
            """
            x = (
                'several   '
                'spaces'
            )
            """,
            """
            x = (
                'several'
                '   spaces'
            )
            """,
            id='several-spaces',
        ),
        pytest.param(
            """
            x = (
                'tab then space\t '
                'next'
            )
            """,
            """
            x = (
                'tab then space\t'
                ' next'
            )
            """,
            id='only-the-space-after-a-tab',
        ),
        pytest.param(
            """
            x = (
                'trailing tab\t'
                'next'
            )
            """,
            """
            x = (
                'trailing tab\t'
                'next'
            )
            """,
            id='trailing-tab',
        ),
        pytest.param(
            """
            x = (
                'space then tab \t'
                'next'
            )
            """,
            """
            x = (
                'space then tab \t'
                'next'
            )
            """,
            id='space-before-trailing-tab',
        ),
        pytest.param(
            r"""
            x = (
                'escaped tab\t'
                'next'
            )
            """,
            r"""
            x = (
                'escaped tab\t'
                'next'
            )
            """,
            id='escaped-tab',
        ),
        pytest.param(
            r"""
            x = (
                'escaped space\x20'
                'next'
            )
            """,
            r"""
            x = (
                'escaped space\x20'
                'next'
            )
            """,
            id='escaped-space',
        ),
        pytest.param(
            """
            x = (
                'no-break space\u00a0'
                'next'
            )
            """,
            """
            x = (
                'no-break space\u00a0'
                'next'
            )
            """,
            id='no-break-space',
        ),
    ],
)
def testMovesOnlyLiteralSpaces(before: str, after: str) -> None:
    checkFix(code(before), code(after))


@pytest.mark.parametrize(
    ('before', 'after'),
    [
        pytest.param(
            """
            z = 'same line ' 'stays'
            """,
            """
            z = 'same line ' 'stays'
            """,
            id='one-line',
        ),
        pytest.param(
            """
            z = (
                'same line ' 'stays '
                'next line'
            )
            """,
            """
            z = (
                'same line ' 'stays'
                ' next line'
            )
            """,
            id='same-line-pair-then-next-line',
        ),
        pytest.param(
            r"""
            z = (
                'ends on \
            the same line ' 'stays'
            )
            """,
            r"""
            z = (
                'ends on \
            the same line ' 'stays'
            )
            """,
            id='piece-spanning-lines-then-same-line',
        ),
    ],
)
def testSkipsPiecesOnTheSameLine(before: str, after: str) -> None:
    checkFix(code(before), code(after))


@pytest.mark.parametrize(
    'source',
    [
        pytest.param(
            '''
            v = (
                """triple """
                'not touched'
            )
            ''',
            id='first-piece',
        ),
        pytest.param(
            '''
            v = (
                'not touched '
                """triple"""
            )
            ''',
            id='second-piece',
        ),
        pytest.param(
            """
            v = (
                '''both '''
                '''triple'''
            )
            """,
            id='both-pieces',
        ),
        pytest.param(
            '''
            v = (
                f"""{v} triple f-string """
                'not touched'
            )
            ''',
            id='triple-quoted-f-string',
        ),
    ],
)
def testSkipsTripleQuotedPieces(source: str) -> None:
    checkFix(code(source), code(source))


@pytest.mark.parametrize(
    ('before', 'after'),
    [
        pytest.param(
            r"""
            w = (
                'ends with backslash space \ '
                'next'
            )
            """,
            r"""
            w = (
                'ends with backslash space \ '
                'next'
            )
            """,
            id='backslash-space',
        ),
        pytest.param(
            r"""
            w = (
                'escaped backslash then space \\\ '
                'next'
            )
            """,
            r"""
            w = (
                'escaped backslash then space \\\ '
                'next'
            )
            """,
            id='three-backslashes',
        ),
        pytest.param(
            r"""
            w = (
                r'raw backslash space \ '
                'next'
            )
            """,
            r"""
            w = (
                r'raw backslash space \ '
                'next'
            )
            """,
            id='raw-backslash-space',
        ),
        pytest.param(
            r"""
            w = (
                b'bytes backslash space \  '
                b'next'
            )
            """,
            r"""
            w = (
                b'bytes backslash space \  '
                b'next'
            )
            """,
            id='bytes-backslash-two-spaces',
        ),
        pytest.param(
            r"""
            w = (
                'escaped backslash \\ '
                'next'
            )
            """,
            r"""
            w = (
                'escaped backslash \\'
                ' next'
            )
            """,
            id='two-backslashes-are-moved',
        ),
        pytest.param(
            r"""
            w = (
                r'raw escaped backslash \\ '
                'next'
            )
            """,
            r"""
            w = (
                r'raw escaped backslash \\'
                ' next'
            )
            """,
            id='raw-two-backslashes-are-moved',
        ),
    ],
)
def testSkipsSpacesEscapedByBackslash(before: str, after: str) -> None:
    checkFix(code(before), code(after))


@pytest.mark.parametrize(
    ('before', 'after'),
    [
        pytest.param(
            """
            s = (
                '   '
                'next'
            )
            """,
            """
            s = (
                '   '
                'next'
            )
            """,
            id='several-spaces',
        ),
        pytest.param(
            """
            s = (
                ' '
                'next'
            )
            """,
            """
            s = (
                ' '
                'next'
            )
            """,
            id='one-space',
        ),
        pytest.param(
            """
            s = (
                ''
                'next'
            )
            """,
            """
            s = (
                ''
                'next'
            )
            """,
            id='empty',
        ),
        pytest.param(
            """
            s = (
                'before '
                '  '
                'after'
            )
            """,
            """
            s = (
                'before'
                '   '
                'after'
            )
            """,
            id='in-a-chain',
        ),
    ],
)
def testSkipsPiecesOfOnlySpaces(before: str, after: str) -> None:
    checkFix(code(before), code(after))


@pytest.mark.parametrize(
    ('before', 'after'),
    [
        pytest.param(
            """
            y = (
                f'value {x} is '  # a comment
                f'{x!r} and '
                'tail'
            )
            """,
            """
            y = (
                f'value {x} is'  # a comment
                f' {x!r} and'
                ' tail'
            )
            """,
            id='f-strings',
        ),
        pytest.param(
            """
            y = (
                'plain '
                f'{x}'
            )
            """,
            """
            y = (
                'plain'
                f' {x}'
            )
            """,
            id='plain-then-f-string',
        ),
        pytest.param(
            """
            y = (
                f'{x:>10} '
                F'{x = } '
                rf'{x!s:{x}} \\d '
                'tail'
            )
            """,
            """
            y = (
                f'{x:>10}'
                F' {x = }'
                rf' {x!s:{x}} \\d'
                ' tail'
            )
            """,
            id='conversion-format-spec-and-debug',
        ),
        pytest.param(
            """
            y = (
                f'{{escaped braces}} '
                'tail'
            )
            """,
            """
            y = (
                f'{{escaped braces}}'
                ' tail'
            )
            """,
            id='escaped-braces',
        ),
        pytest.param(
            """
            y = (
                f'{x }'
                'tail'
            )
            """,
            """
            y = (
                f'{x }'
                'tail'
            )
            """,
            id='space-inside-replacement-field',
        ),
        pytest.param(
            """
            y = (
                'é中 '  # ü
                f'{x}中 '
                'tail'
            )
            """,
            """
            y = (
                'é中'  # ü
                f' {x}中'
                ' tail'
            )
            """,
            id='non-ascii',
        ),
    ],
)
def testHandlesFStrings(before: str, after: str) -> None:
    checkFix(code(before), code(after))


@requiresPy314
@pytest.mark.parametrize(
    ('before', 'after'),
    [
        pytest.param(
            """
            y = (
                t'value {x} is '
                t'{x!r:>10} and '
                rt'raw \\d '
                T'tail'
            )
            """,
            """
            y = (
                t'value {x} is'
                t' {x!r:>10} and'
                rt' raw \\d'
                T' tail'
            )
            """,
            id='t-strings',
        ),
        pytest.param(
            """
            y = (
                t'{f"inner "} outer '
                t'tail'
            )
            """,
            """
            y = (
                t'{f"inner "} outer'
                t' tail'
            )
            """,
            id='f-string-inside-t-string',
        ),
    ],
)
def testHandlesTStrings(before: str, after: str) -> None:
    checkFix(code(before), code(after))


@pytest.mark.parametrize(
    ('before', 'after'),
    [
        pytest.param(
            """
            u = (
                f'nested {f"inner "} '
                'end'
            )
            """,
            """
            u = (
                f'nested {f"inner "}'
                ' end'
            )
            """,
            id='different-quotes',
        ),
        pytest.param(
            """
            u = (
                f'nested {f"inner "}'
                'end'
            )
            """,
            """
            u = (
                f'nested {f"inner "}'
                'end'
            )
            """,
            id='only-the-inner-string-has-a-space',
        ),
        pytest.param(
            """
            u = (
                f'nested {f'inner {f'innermost '} '} '
                'end'
            )
            """,
            """
            u = (
                f'nested {f'inner {f'innermost '} '}'
                ' end'
            )
            """,
            id='same-quotes',
            marks=requiresPy312,
        ),
        pytest.param(
            """
            u = (
                f'{
                    "inner pieces "
                    "are not touched"
                } '
                'end'
            )
            """,
            """
            u = (
                f'{
                    "inner pieces "
                    "are not touched"
                }'
                ' end'
            )
            """,
            id='concatenation-inside-replacement-field',
            marks=requiresPy312,
        ),
    ],
)
def testHandlesNestedFStrings(before: str, after: str) -> None:
    checkFix(code(before), code(after))


@pytest.mark.parametrize(
    ('before', 'after'),
    [
        pytest.param(
            r"""
            y = (
                r'raw \d '
                'tail'
            )
            """,
            r"""
            y = (
                r'raw \d'
                ' tail'
            )
            """,
            id='raw-then-plain',
        ),
        pytest.param(
            r"""
            y = (
                'plain '
                R'raw \d'
            )
            """,
            r"""
            y = (
                'plain'
                R' raw \d'
            )
            """,
            id='plain-then-raw',
        ),
        pytest.param(
            """
            b = (
                rb'raw bytes '
                Rb'tail'
            )
            """,
            """
            b = (
                rb'raw bytes'
                Rb' tail'
            )
            """,
            id='raw-bytes',
        ),
        pytest.param(
            """
            b = (
                b'bytes '
                B'tail'
            )
            """,
            """
            b = (
                b'bytes'
                B' tail'
            )
            """,
            id='bytes',
        ),
    ],
)
def testHandlesRawAndBytes(before: str, after: str) -> None:
    checkFix(code(before), code(after))


@pytest.mark.parametrize(
    'prefix',
    ['', 'r', 'R', 'u', 'U', 'b', 'B', 'br', 'Rb', 'f', 'F', 'rf', 'fR'],
)
@pytest.mark.parametrize('quote', ["'", '"'])
def testHandlesEveryPrefixAndQuote(prefix: str, quote: str) -> None:
    before = (
        f'x = (\n    {prefix}{quote}abc {quote}\n'
        f'    {prefix}{quote}def{quote}\n)\n'
    )
    after = (
        f'x = (\n    {prefix}{quote}abc{quote}\n'
        f'    {prefix}{quote} def{quote}\n)\n'
    )
    checkFix(before, after)


@pytest.mark.parametrize(
    ('before', 'after'),
    [
        pytest.param(
            """
            x = (
                'a comment '  # 'not a piece '
                'after'
            )
            """,
            """
            x = (
                'a comment'  # 'not a piece '
                ' after'
            )
            """,
            id='trailing-comment',
        ),
        pytest.param(
            """
            x = (
                'comment lines '
                # 'not a piece '

                # another comment
                'between'  # trailing
            )
            """,
            """
            x = (
                'comment lines'
                # 'not a piece '

                # another comment
                ' between'  # trailing
            )
            """,
            id='comment-lines',
        ),
    ],
)
def testHandlesCommentsBetweenPieces(before: str, after: str) -> None:
    checkFix(code(before), code(after))


@pytest.mark.parametrize(
    ('before', 'after'),
    [
        pytest.param(
            """
            msg = (
                'DOC402: Function has "yield" statements, but the '
                'docstring does not have a "Yields" section; '
                'please add one '
                'or remove the yield'
            )
            """,
            """
            msg = (
                'DOC402: Function has "yield" statements, but the'
                ' docstring does not have a "Yields" section;'
                ' please add one'
                ' or remove the yield'
            )
            """,
            id='four-pieces',
        ),
        pytest.param(
            """
            msg = (
                'first '
                'second'
                'third  '
                'fourth'
            )
            """,
            """
            msg = (
                'first'
                ' second'
                'third'
                '  fourth'
            )
            """,
            id='middle-piece-without-trailing-space',
        ),
        pytest.param(
            """
            msg = foo(
                'a ', 'b '
                'c ' 'd '
                'e'
            )
            """,
            """
            msg = foo(
                'a ', 'b'
                ' c ' 'd'
                ' e'
            )
            """,
            id='several-pieces-per-line',
        ),
    ],
)
def testHandlesChains(before: str, after: str) -> None:
    checkFix(code(before), code(after))


@pytest.mark.parametrize(
    'char',
    ['\f', '\v', '\x1c', '\x1d', '\x1e', '\x85', '\u2028', '\u2029'],
)
@pytest.mark.parametrize('place', ['comment', 'string'])
def testOffsetsFollowTokenizeLineSplitting(char: str, place: str) -> None:
    # str.splitlines() splits at all these characters, but tokenize does
    # not, so offsets based on str.splitlines() would drift.
    if place == 'comment':
        before = f"x = 1  # a{char}b\ny = (\n    'c '\n    'd'\n)\n"
        after = f"x = 1  # a{char}b\ny = (\n    'c'\n    ' d'\n)\n"
    else:
        before = f"y = (\n    'a{char}b '\n    'c '\n    'd'\n)\n"
        after = f"y = (\n    'a{char}b'\n    ' c'\n    ' d'\n)\n"

    assert len(before.splitlines()) > len(splitLines(before))
    checkFix(before, after)


@pytest.mark.parametrize('newline', ['\n', '\r\n', '\r'])
def testPreservesLineEndings(newline: str) -> None:
    before = code("""
        x = (
            'plain one '
            'two'
        )
        """).replace('\n', newline)
    after = code("""
        x = (
            'plain one'
            ' two'
        )
        """).replace('\n', newline)
    checkFix(before, after)


def testPreservesMixedLineEndings() -> None:
    before = "x = (\r\n    'a '\n    'b '\r    'c'\r\n)\n"
    after = "x = (\r\n    'a'\n    ' b'\r    ' c'\r\n)\n"
    checkFix(before, after)


@pytest.mark.parametrize(
    ('before', 'lineLength', 'after', 'skippedPairs'),
    [
        pytest.param(
            """
            x = (
                'abc '
                'defgh'
            )
            """,
            12,
            """
            x = (
                'abc'
                ' defgh'
            )
            """,
            (),
            id='reaches-the-limit',
        ),
        pytest.param(
            """
            x = (
                'abc '
                'defgh'
            )
            """,
            11,
            """
            x = (
                'abc '
                'defgh'
            )
            """,
            (SkippedPair(lineNo=3, newLength=12),),
            id='exceeds-the-limit',
        ),
        pytest.param(
            """
            x = (
                'abc '
                'defg '
                'hi'
            )
            """,
            11,
            """
            x = (
                'abc'
                ' defg'
                ' hi'
            )
            """,
            (),
            id='line-also-loses-its-trailing-space',
        ),
        pytest.param(
            """
            x = (
                'abc '
                'defg '
                'hijkl'
            )
            """,
            11,
            """
            x = (
                'abc '
                'defg '
                'hijkl'
            )
            """,
            (
                SkippedPair(lineNo=3, newLength=12),
                SkippedPair(lineNo=4, newLength=12),
            ),
            id='skipped-pair-makes-the-previous-pair-skipped',
        ),
        pytest.param(
            """
            x = (
                'abc '
                'already too long'
            )
            """,
            10,
            """
            x = (
                'abc'
                ' already too long'
            )
            """,
            (),
            id='line-already-too-long',
        ),
        pytest.param(
            """
            x = (
                'abc '
                'de '
                'fghij'
            )
            """,
            11,
            """
            x = (
                'abc'
                ' de '
                'fghij'
            )
            """,
            (SkippedPair(lineNo=4, newLength=12),),
            id='only-the-last-pair-skipped',
        ),
    ],
)
@pytest.mark.parametrize('newline', ['\n', '\r\n', '\r'])
def testSkipsPairsThatMakeLinesTooLong(
        before: str,
        lineLength: int,
        after: str,
        skippedPairs: tuple[SkippedPair, ...],
        newline: str,
) -> None:
    result = checkFix(
        code(before).replace('\n', newline),
        code(after).replace('\n', newline),
        lineLength=lineLength,
    )
    assert result.skippedPairs == skippedPairs


def testCountsFixedPairs() -> None:
    before = "x = (\n    'a '\n    'b '\n    'c'\n)\ny = 'd ' 'e'\n"
    assert fixSource(before).fixedPairs == 2


def testRaisesWhenOffsetsDoNotMatchTokens() -> None:
    source = "x = (\n    'a '\n    'b'\n)\n"
    tokens = list(tokenize.generate_tokens(io.StringIO(source).readline))
    pieces = list(fixer._iterPieces(tokens))
    wrongLineStarts = [0, 7, 16, 24, 26]  # off by one from line 2 on
    with pytest.raises(TokenPositionError, match='line 2'):
        fixer._getPieceText(source, tokens, pieces[0], wrongLineStarts)
