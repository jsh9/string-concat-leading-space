from __future__ import annotations

import importlib.metadata
import tokenize
import warnings
from pathlib import Path
from typing import Any, NoReturn

import pytest
from click.testing import CliRunner, Result

from string_concat_leading_space import main as mainModule
from string_concat_leading_space.fixer import FixResult, TokenPositionError
from string_concat_leading_space.main import main
from tests.helpers import dumpAst

DATA_DIR = Path(__file__).parent / 'test_data'

NEEDS_FIX = "x = (\n    'a '\n    'b'\n)\n"
FIXED = "x = (\n    'a'\n    ' b'\n)\n"
CLEAN = "x = 'nothing to do'\n"
UNPARSEABLE = "x = (\n    'a '\n    'b'\n"
# The second piece's line would grow from 11 to 12 characters
TOO_LONG = "x = (\n    'abc '\n    'defgh'\n)\n"


def runCli(*args: str) -> Result:
    return CliRunner().invoke(main, list(args))


def writeFile(path: Path, content: str) -> str:
    path.write_bytes(content.encode())
    return str(path)


def runSample(source: str) -> dict[str, Any]:
    """Run the sample code and return the variables it defines."""
    namespace: dict[str, Any] = {}
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')  # "\ " is an invalid escape
        exec(source, namespace)  # noqa: S102

    return {k: v for k, v in namespace.items() if k != '__builtins__'}


def testSampleFile(tmp_path: Path) -> None:
    before = (DATA_DIR / 'sample_before.py').read_bytes()
    after = (DATA_DIR / 'sample_after.py').read_bytes()
    target = tmp_path / 'sample.py'
    target.write_bytes(before)

    result = runCli(str(target))

    assert result.exit_code == 1
    assert result.output == f'Rewriting {target}\n'
    assert target.read_bytes() == after
    assert dumpAst(after.decode()) == dumpAst(before.decode())
    assert runSample(after.decode()) == runSample(before.decode())


@pytest.mark.parametrize(
    ('contents', 'exitCode', 'rewritten'),
    [
        pytest.param([], 0, [], id='no-files'),
        pytest.param([CLEAN], 0, [], id='clean'),
        pytest.param([NEEDS_FIX], 1, [0], id='needs-fix'),
        pytest.param([CLEAN, NEEDS_FIX, CLEAN], 1, [1], id='mixed'),
        pytest.param([NEEDS_FIX, NEEDS_FIX], 1, [0, 1], id='two-fixes'),
        pytest.param([UNPARSEABLE], 0, [], id='unparseable'),
        pytest.param([UNPARSEABLE, NEEDS_FIX], 1, [1], id='unparseable-fix'),
        pytest.param([TOO_LONG], 0, [], id='only-skipped-pairs'),
        pytest.param([''], 0, [], id='empty-file'),
        pytest.param(
            [NEEDS_FIX.removesuffix('\n')], 1, [0], id='no-trailing-newline'
        ),
    ],
)
def testExitCodes(
        tmp_path: Path,
        contents: list[str],
        exitCode: int,
        rewritten: list[int],
) -> None:
    paths = [
        writeFile(tmp_path / f'file{i}.py', content)
        for i, content in enumerate(contents)
    ]

    result = runCli('--line-length=11', *paths)

    assert result.exit_code == exitCode
    rewrittenPaths = [paths[i] for i in rewritten]
    for path in paths:
        isRewritten = f'Rewriting {path}\n' in result.output
        assert isRewritten == (path in rewrittenPaths)


def testMissingFileIsAnError(tmp_path: Path) -> None:
    missing = tmp_path / 'missing.py'
    fixable = writeFile(tmp_path / 'fixable.py', NEEDS_FIX)

    result = runCli(str(missing), fixable)

    assert result.exit_code == 1
    assert f'{missing}: error: cannot read the file' in result.output
    assert Path(fixable).read_text(encoding='utf-8') == FIXED


@pytest.mark.parametrize(
    ('lineLength', 'exitCode', 'expectedOutput', 'expectedContent'),
    [
        pytest.param(
            12,
            1,
            'Rewriting {path}\n',
            "x = (\n    'abc'\n    ' defgh'\n)\n",
            id='fits',
        ),
        pytest.param(
            11,
            0,
            (
                '{path}:3: skipped: moving the spaces here would make the'
                ' line 12 characters long (limit: 11); please rewrap it\n'
            ),
            TOO_LONG,
            id='too-long',
        ),
    ],
)
def testLineLengthOption(
        tmp_path: Path,
        lineLength: int,
        exitCode: int,
        expectedOutput: str,
        expectedContent: str,
) -> None:
    path = writeFile(tmp_path / 'file.py', TOO_LONG)

    result = runCli(f'--line-length={lineLength}', path)

    assert result.exit_code == exitCode
    assert result.output == expectedOutput.format(path=path)
    assert Path(path).read_text(encoding='utf-8') == expectedContent


def testLineLengthDefaultsTo79(tmp_path: Path) -> None:
    longLine = "    '" + 'x' * 73 + "'"  # 79 characters
    content = f"y = (\n    'a '\n{longLine}\n)\n"
    path = writeFile(tmp_path / 'file.py', content)

    result = runCli(path)

    assert result.exit_code == 0
    assert f'{path}:3: skipped' in result.output
    assert '(limit: 79)' in result.output


def testFixAndSkipInOneFile(tmp_path: Path) -> None:
    content = (
        "x = (\n    'abc '\n    'defgh'\n)\ny = (\n    'a '\n    'b'\n)\n"
    )
    path = writeFile(tmp_path / 'file.py', content)

    result = runCli('--line-length=11', path)

    assert result.exit_code == 1
    assert result.output.splitlines() == [
        f'Rewriting {path}',
        (
            f'{path}:3: skipped: moving the spaces here would make the line'
            ' 12 characters long (limit: 11); please rewrap it'
        ),
    ]
    assert Path(path).read_text(encoding='utf-8') == (
        "x = (\n    'abc '\n    'defgh'\n)\ny = (\n    'a'\n    ' b'\n)\n"
    )


@pytest.mark.parametrize('lineLength', ['0', '-1', 'abc'])
def testRejectsInvalidLineLength(tmp_path: Path, lineLength: str) -> None:
    path = writeFile(tmp_path / 'file.py', NEEDS_FIX)

    result = runCli(f'--line-length={lineLength}', path)

    assert result.exit_code == 2
    assert Path(path).read_text(encoding='utf-8') == NEEDS_FIX


@pytest.mark.parametrize('newline', ['\n', '\r\n', '\r'])
@pytest.mark.parametrize(
    ('header', 'encoding'),
    [
        pytest.param('', 'utf-8', id='utf-8'),
        pytest.param('', 'utf-8-sig', id='utf-8-with-bom'),
        pytest.param('# -*- coding: latin-1 -*-\n', 'latin-1', id='latin-1'),
    ],
)
def testPreservesLineEndingsAndEncoding(
        tmp_path: Path,
        newline: str,
        header: str,
        encoding: str,
) -> None:
    before = header + "x = (\n    'café '\n    'crème'\n)\n"
    after = header + "x = (\n    'café'\n    ' crème'\n)\n"
    path = tmp_path / 'file.py'
    path.write_bytes(before.replace('\n', newline).encode(encoding))

    result = runCli(str(path))

    assert result.exit_code == 1
    assert path.read_bytes() == after.replace('\n', newline).encode(encoding)


@pytest.mark.parametrize(
    'content',
    [
        pytest.param(UNPARSEABLE.encode(), id='syntax-error'),
        pytest.param(b"x = 'a\x00'\n" + NEEDS_FIX.encode(), id='null-byte'),
        pytest.param(b"x = '\xff'\n" + NEEDS_FIX.encode(), id='invalid-utf-8'),
        pytest.param(
            b'# -*- coding: no-such-codec -*-\n' + NEEDS_FIX.encode(),
            id='unknown-encoding',
        ),
        pytest.param(
            b'\xef\xbb\xbf# -*- coding: latin-1 -*-\n' + NEEDS_FIX.encode(),
            id='bom-and-other-encoding',
        ),
    ],
)
def testSkipsFilesThatCannotBeParsed(tmp_path: Path, content: bytes) -> None:
    path = tmp_path / 'file.py'
    path.write_bytes(content)

    result = runCli(str(path))

    assert result.exit_code == 0
    assert result.output == f'{path}: cannot parse, skipped\n'
    assert path.read_bytes() == content


@pytest.mark.parametrize(
    'brokenSource',
    [
        pytest.param("x = (\n    'a'\n    'b'\n)\n", id='different-value'),
        pytest.param("x = (\n    'a'\n    ' b'\n", id='syntax-error'),
    ],
)
def testDoesNotWriteWhenAstChanges(
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        brokenSource: str,
) -> None:
    def brokenFixSource(*_args: object, **_kwargs: object) -> FixResult:
        return FixResult(source=brokenSource, fixedPairs=1, skippedPairs=())

    monkeypatch.setattr(mainModule, 'fixSource', brokenFixSource)
    path = writeFile(tmp_path / 'file.py', NEEDS_FIX)

    result = runCli(path)

    assert result.exit_code == 1
    assert result.output == (
        f'{path}: error: the rewrite would change the AST;'
        ' file left unchanged\n'
    )
    assert Path(path).read_text(encoding='utf-8') == NEEDS_FIX


@pytest.mark.parametrize(
    ('exception', 'exitCode', 'message'),
    [
        pytest.param(
            TokenPositionError('line 2: token positions differ'),
            1,
            'error: line 2: token positions differ; file left unchanged',
            id='token-position-error',
        ),
        pytest.param(
            tokenize.TokenError('EOF in multi-line statement'),
            0,
            'cannot tokenize, skipped',
            id='tokenize-error',
        ),
    ],
)
def testHandlesFixerExceptions(
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        exception: Exception,
        exitCode: int,
        message: str,
) -> None:
    def raisingFixSource(*_args: object, **_kwargs: object) -> FixResult:
        raise exception

    monkeypatch.setattr(mainModule, 'fixSource', raisingFixSource)
    path = writeFile(tmp_path / 'file.py', NEEDS_FIX)

    result = runCli(path)

    assert result.exit_code == exitCode
    assert result.output == f'{path}: {message}\n'
    assert Path(path).read_text(encoding='utf-8') == NEEDS_FIX


def testVersionOption() -> None:
    result = runCli('--version')

    assert result.exit_code == 0
    version = importlib.metadata.version('string-concat-leading-space')
    assert result.output.endswith(f'version {version}\n')


@pytest.mark.parametrize(
    ('before', 'after'),
    [
        pytest.param(
            "v = 1\nx = (\n    f'{v} '\n    u'b'\n)\n",
            "v = 1\nx = (\n    f'{v}'\n    u' b'\n)\n",
            id='f-string-then-u-string',
        ),
        pytest.param(
            "v = 1\nx = (\n    u'a '\n    f'{v} '\n    U'c'\n)\n",
            "v = 1\nx = (\n    u'a'\n    f' {v}'\n    U' c'\n)\n",
            id='u-string-f-string-u-string',
        ),
    ],
)
def testIgnoresUnicodePrefixWhenComparingAsts(
        tmp_path: Path,
        before: str,
        after: str,
) -> None:
    # On Python 3.12+, Constant.kind ('u') moves to another piece here
    path = writeFile(tmp_path / 'file.py', before)

    result = runCli(path)

    assert result.exit_code == 1
    assert result.output == f'Rewriting {path}\n'
    assert Path(path).read_text(encoding='utf-8') == after


def testReportsWriteErrors(
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
) -> None:
    def failingWriteText(*_args: object, **_kwargs: object) -> NoReturn:
        raise PermissionError('read-only file')

    path = writeFile(tmp_path / 'file.py', NEEDS_FIX)
    monkeypatch.setattr(Path, 'write_text', failingWriteText)

    result = runCli(path)

    assert result.exit_code == 1
    assert result.output == (
        f'{path}: error: cannot write the file: read-only file\n'
    )
    assert Path(path).read_text(encoding='utf-8') == NEEDS_FIX


def testSkipsFilesTooDeeplyNestedToCompare(tmp_path: Path) -> None:
    # ast.parse() handles this, but the recursive ast.dump() does not
    content = NEEDS_FIX + 'y = ' + ' + '.join(['1'] * 1500) + '\n'
    path = writeFile(tmp_path / 'file.py', content)

    result = runCli(path)

    assert result.exit_code == 0
    assert result.output == (
        f'{path}: too deeply nested to compare ASTs, skipped\n'
    )
    assert Path(path).read_text(encoding='utf-8') == content


def testSkipsFilesTooDeeplyNestedToParse(
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Such as a 100,000-term expression on Python 3.14
    def recursingParse(*_args: object, **_kwargs: object) -> NoReturn:
        raise RecursionError('maximum recursion depth exceeded')

    monkeypatch.setattr(mainModule, '_parse', recursingParse)
    path = writeFile(tmp_path / 'file.py', NEEDS_FIX)

    result = runCli(path)

    assert result.exit_code == 0
    assert result.output == f'{path}: cannot parse, skipped\n'
    assert Path(path).read_text(encoding='utf-8') == NEEDS_FIX
