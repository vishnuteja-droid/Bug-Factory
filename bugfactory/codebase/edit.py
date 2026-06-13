"""Read and replace a single function OR method by qualified name, using `ast`
to find its exact line span.

Splicing whole functions (rather than parsing fragile diffs) is far more robust
with a tiny model. We also re-indent the model's replacement to the original
symbol's column, so a method returned at column 0 still drops in correctly.
"""
from __future__ import annotations

import ast
import textwrap


def _find_node(source: str, qualname: str):
    """Locate the FunctionDef node for `qualname` ('func' or 'Class.method')."""
    tree = ast.parse(source)
    parts = qualname.split(".")
    if len(parts) == 1:
        candidates = tree.body
        target = parts[0]
    elif len(parts) == 2:
        cls = next((n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == parts[0]), None)
        if cls is None:
            return None
        candidates = cls.body
        target = parts[1]
    else:
        return None
    return next(
        (n for n in candidates
         if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == target),
        None,
    )


def _span(node):
    start = node.lineno - 1
    if node.decorator_list:
        start = min(d.lineno for d in node.decorator_list) - 1
    return start, node.end_lineno, node.col_offset


def get_function_source(path: str, qualname: str) -> str:
    with open(path, "r", encoding="utf-8") as fh:
        source = fh.read()
    node = _find_node(source, qualname)
    if node is None:
        raise ValueError(f"symbol {qualname!r} not found in {path}")
    start, end, _ = _span(node)
    return "\n".join(source.split("\n")[start:end])


def _reindent(block: str, indent: int) -> str:
    pad = " " * indent
    lines = textwrap.dedent(block).split("\n")
    return "\n".join(pad + ln if ln.strip() else ln for ln in lines)


def replace_function(path: str, qualname: str, new_src: str) -> tuple[str, str]:
    """Replace the named symbol's source in `path`. Returns (old_source, new_source)."""
    with open(path, "r", encoding="utf-8") as fh:
        old_source = fh.read()
    node = _find_node(old_source, qualname)
    if node is None:
        raise ValueError(f"symbol {qualname!r} not found in {path}")
    start, end, indent = _span(node)

    new_block = _reindent(new_src.rstrip("\n"), indent)
    lines = old_source.split("\n")
    new_source = "\n".join(lines[:start] + new_block.split("\n") + lines[end:])

    # Never leave broken syntax on disk.
    ast.parse(new_source)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(new_source)
    return old_source, new_source
