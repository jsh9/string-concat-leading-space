from __future__ import annotations

import ast
import warnings
from textwrap import dedent


def dumpAst(source: str) -> str:
    """
    Dump the AST of ``source``, which includes every string's value.

    ``Constant.kind`` (``'u'`` for the ``u`` prefix) is ignored: it has no
    effect at runtime, and on Python 3.12+ it can move between the pieces of an
    f-string concatenation when spaces move.
    """
    with warnings.catch_warnings():
        # Such as "SyntaxWarning: invalid escape sequence"
        warnings.simplefilter('ignore')
        tree = ast.parse(source)

    for node in ast.walk(tree):
        if isinstance(node, ast.Constant):
            node.kind = None

    return ast.dump(tree)


def code(text: str) -> str:
    """Dedent a triple-quoted test case and drop its first newline."""
    return dedent(text).removeprefix('\n')
