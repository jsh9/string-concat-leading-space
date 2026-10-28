# AGENTS.md

This guide briefs coding agents working on `string-concat-leading-space`. Use
it to get oriented before making changes.

## 1. Quick Snapshot

- A pre-commit hook and CLI (`string-concat-leading-space`) that moves the
  trailing spaces of implicitly concatenated strings to the start of the next
  piece, without changing any string's value.
- Minimum Python 3.10, packaged via `setuptools`; the only dependency is
  `click`. CI runs on Python 3.10 to 3.14, because f-string tokenization
  changed in 3.12 and t-strings arrived in 3.14.

## 2. Repository Layout

- `string_concat_leading_space/fixer.py` – Core logic. `fixSource()` takes
  source code and returns the fixed source plus the pairs skipped for line
  length. It does no file I/O.
- `string_concat_leading_space/main.py` – Click CLI. `fixFile()` reads a file
  (keeping its encoding and line endings), parses it, calls `fixSource()`,
  compares the ASTs, writes the file, and prints messages.
- `tests/test_fixer.py` – One parametrized test per rule; `checkFix()` also
  compares ASTs and checks that a second run changes nothing.
- `tests/test_main.py` – CLI tests: exit codes, messages, line endings,
  encodings, unparseable files, and the AST safety net.
- `tests/test_data/` – The sample input and its expected output. Excluded from
  pre-commit and muff, because the hook would rewrite the input.

## 3. Implementation Notes

- Python 3.12+ tokenizes f-strings as `FSTRING_START`/`MIDDLE`/`END` (and 3.14+
  t-strings as `TSTRING_*`); earlier versions emit one `STRING` token.
  `_iterPieces()` treats a whole f-string or t-string, including nested ones,
  as one piece.
- Offsets come from `splitLines()`, which splits at `\r\n`, `\r`, and `\n`
  only. `str.splitlines()` also splits at `\f`, `\x1c`, `\u2028`, and so on,
  which would make offsets drift. The same lines are fed to tokenize, with a
  lone `\r` replaced by `\n` (same length) for the pure-Python tokenizer of
  3.10 and 3.11.
- `_getPieceText()` checks each piece's text against its tokens and raises
  `TokenPositionError` on a mismatch, because the AST comparison would not
  catch spaces moved inside comments.
- The AST comparison (`_dumpAst()` in `main.py`, `dumpAst()` in
  `tests/helpers.py`) ignores `Constant.kind`. On Python 3.12+, an f-string
  concatenation takes `kind='u'` from its first piece of literal text, so
  moving the spaces out of `f'{x} '` into `u'b'` changes `kind` but not the
  value.
- `_selectMoves()` checks the line length from the last pair backwards: a line
  can gain spaces at its first piece and lose spaces at its last piece, and the
  loss depends on the next pair. Only lines that go from within the limit to
  over it are skipped.

## 4. Development Workflow

- Install: `pip install -e .` and `pip install -r requirements.dev`.
- Tests: `pytest`.
- Lint and format:
  `muff check --config=muff.toml string_concat_leading_space tests` and
  `muff format --config=muff.toml string_concat_leading_space tests`.
- Type checking: `ty check string_concat_leading_space/`.
- Docstrings:
  `pydoclint --check-arg-defaults=True ./string_concat_leading_space`.
- Everything: `tox`. Pre-commit: `pre-commit run -a`.

## 5. Style Guidance

- camelCase for function and variable names; type hints wherever possible;
  NumPy-style docstrings.
- Tests are flat functions with `pytest.mark.parametrize`. Stack parametrize
  decorators instead of using `itertools.product`.
- Lines are at most 79 characters; single quotes (see `muff.toml`).
- Commit messages and PR titles use the imperative mood ("Add", not "Added").
