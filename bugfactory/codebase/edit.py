"""Read and replace a single top-level function by name, using `ast` to find
its exact line span. Splicing whole functions (rather than parsing fragile
diffs) is far more robust with a tiny model that may not emit clean patches.
"""
from __future__ import annotations

import ast


def _find_span(source: str, func_name: str):
    """Return (start_idx, end_idx_exclusive) line indices for the function, or None."""
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == func_name:
            start = node.lineno - 1
            if node.decorator_list:
                start = min(d.lineno for d in node.decorator_list) - 1
            return start, node.end_lineno
    return None


def get_function_source(path: str, func_name: str) -> str:
    with open(path, "r", encoding="utf-8") as fh:
        source = fh.read()
    span = _find_span(source, func_name)
    if span is None:
        raise ValueError(f"function {func_name!r} not found in {path}")
    start, end = span
    return "\n".join(source.split("\n")[start:end])


def replace_function(path: str, func_name: str, new_func_src: str) -> tuple[str, str]:
    """Replace the named function's body in `path`. Returns (old_source, new_source)."""
    with open(path, "r", encoding="utf-8") as fh:
        old_source = fh.read()
    span = _find_span(old_source, func_name)
    if span is None:
        raise ValueError(f"function {func_name!r} not found in {path}")
    start, end = span

    lines = old_source.split("\n")
    new_lines = lines[:start] + new_func_src.rstrip("\n").split("\n") + lines[end:]
    new_source = "\n".join(new_lines)

    # Validate the result still parses before writing — never leave broken syntax.
    ast.parse(new_source)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(new_source)
    return old_source, new_source
