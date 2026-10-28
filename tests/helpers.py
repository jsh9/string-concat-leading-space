from __future__ import annotations

import ast
import warnings
from textwrap import dedent


def dumpAst(source: str) -> str:
    """Dump the AST of ``source``, which includes every string's value."""
    with warnings.catch_warnings():
        # Such as "SyntaxWarning: invalid escape sequence"
        warnings.simplefilter('ignore')
        return ast.dump(ast.parse(source))


def code(text: str) -> str:
    """Dedent a triple-quoted test case and drop its first newline."""
    return dedent(text).removeprefix('\n')
