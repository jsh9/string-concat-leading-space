# Change Log

All notable changes to this project will be documented in this file.

The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-10-28

- Added
  - Initial release: a pre-commit hook and command-line tool that moves the
    trailing spaces of implicitly concatenated strings to the start of the next
    piece
  - Support for f-strings, t-strings (Python 3.14+), nested f-strings, raw and
    bytes literals, comments between pieces, and chains of pieces
  - A `--line-length` option: pairs that would push a line over the limit are
    skipped and reported as `path:line`
  - A safety net that does not write a file if its AST would change
  - Preservation of each file's encoding and line endings
- Full diff
  - N/A
