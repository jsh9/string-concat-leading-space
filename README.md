# string-concat-leading-space

A pre-commit hook that moves the trailing spaces of implicitly concatenated
strings to the start of the next piece.

<!--TOC-->

______________________________________________________________________

**Table of Contents**

- [1. What it does](#1-what-it-does)
- [2. Installation](#2-installation)
- [3. Usage](#3-usage)
  - [3.1. Pre-commit hook](#31-pre-commit-hook)
  - [3.2. Command line](#32-command-line)
- [4. Options](#4-options)
- [5. Limitations](#5-limitations)

______________________________________________________________________

<!--TOC-->

## 1. What it does

When a long string is split into several string literals across lines, the
space between two words can sit at the end of one piece or at the start of the
next one. This hook moves it to the start of the next piece:

```diff
 msg = (
-    'DOC402: Function has "yield" statements, but the '
-    'docstring does not have a "Yields" section'
+    'DOC402: Function has "yield" statements, but the'
+    ' docstring does not have a "Yields" section'
 )
```

The concatenated value never changes. Only where the space sits changes. A
space at the start of a line is easy to see, so a missing space between two
pieces stands out.

Two string literals form a pair when:

- only line breaks and comments are between them, and
- the second piece starts on a later line than the first piece ends.

For each pair, all space characters at the end of the first piece move to the
start of the second piece. Chains of three or more pieces are handled pair by
pair. It works with plain, raw (`r`), bytes (`b`), and Unicode (`u`) literals,
f-strings, and t-strings (Python 3.14+):

```diff
 y = (
-    f'value {x} is '  # a comment
-    f'{x!r} and '
-    r'raw \d '
-    'tail'
+    f'value {x} is'  # a comment
+    f' {x!r} and'
+    r' raw \d'
+    ' tail'
 )
```

As a safety net, every file is parsed before and after the change. If the two
ASTs differ, the file is not written and an error is reported. The file's
encoding and line endings (`\n`, `\r\n`, or `\r`) are preserved.

## 2. Installation

```bash
pip install string-concat-leading-space
```

## 3. Usage

### 3.1. Pre-commit hook

Add this to your `.pre-commit-config.yaml`:

```yaml
repos:
  - repo: https://github.com/jsh9/string-concat-leading-space
    rev: <LATEST_VERSION>
    hooks:
      - id: string-concat-leading-space
        args: [--line-length=79]
```

pre-commit shows a hook's output only when the hook fails. A pair skipped
because of the line length (see [Limitations](#5-limitations)) does not make
the hook fail by itself, so add `verbose: true` to the hook if you want to see
those messages on every run.

### 3.2. Command line

```bash
string-concat-leading-space path/to/file1.py path/to/file2.py
string-concat-leading-space --line-length=88 path/to/file.py
```

The tool takes file names, rewrites the files in place, and prints
`Rewriting <path>` for each file it changes. Messages go to stderr.

| Exit code | Meaning                                                 |
| --------- | ------------------------------------------------------- |
| `0`       | No file was changed and no error happened               |
| `1`       | At least one file was changed, or an error happened     |
| `2`       | Invalid command-line options, such as `--line-length=0` |

Errors are files that cannot be read, and files whose AST would change (which
would be a bug in this tool). Files that cannot be decoded or parsed are
skipped with a message; they are not errors.

## 4. Options

| Option                  | Default | Description                                                                                                                                       |
| ----------------------- | ------- | ------------------------------------------------------------------------------------------------------------------------------------------------- |
| `--line-length INTEGER` | `79`    | Maximum line length. A pair is skipped, and reported as `path:line`, if moving its spaces would push the line of the next piece over this length. |
| `--version`             | N/A     | Show the version and exit.                                                                                                                        |
| `--help`                | N/A     | Show the help message and exit.                                                                                                                   |

## 5. Limitations

**The hook never rewraps lines.** Moving the spaces makes the line of the next
piece longer, unless that line also loses its own trailing spaces to the piece
after it. If a line that fits within `--line-length` would no longer fit, the
pair is left unchanged and reported, so that you can rewrap it by hand:

```text
path/to/file.py:12: skipped: moving the spaces here would make the line 80 characters long (limit: 79); please rewrap it
```

Lines that are already longer than `--line-length` are not checked.

**These cases are skipped on purpose:**

- Pieces on the same line, such as `'a ' 'b'`
- Triple-quoted pieces, on either side of a pair
- Trailing spaces preceded by an escaping backslash, such as `'abc\ '` (moving
  the space would leave `'abc\'`, which escapes the closing quote)
- A piece that consists only of spaces, such as `'   '`
- Other whitespace, such as tabs, and escape sequences, such as `\x20`; only
  literal space characters are moved
- Strings inside the replacement fields of f-strings and t-strings, such as
  `"inner "` in `f'outer {f"inner "} '`; only the outer piece's trailing spaces
  move

**Files that cannot be parsed are skipped.** The hook parses files with the
Python version that runs it, so it skips, for example, files that use t-strings
when it runs on Python 3.13 or earlier.
