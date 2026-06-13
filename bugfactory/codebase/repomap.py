"""Build a 'repo map' so an agent can orient in a codebase it has never seen,
without reading every file.

We parse each Python module with `ast` and extract module-level functions AND
class methods, each with a qualified name (`Cart.total`) and exact line span.
This is the dependency-free version of a tree-sitter symbol map; it is enough
to localize bugs and is where richer extraction (call graph, references) grows.
"""
from __future__ import annotations

import ast
import os
from dataclasses import dataclass


@dataclass
class RepoFunction:
    file: str          # path relative to repo root
    abspath: str
    qualname: str      # "subtract" or "Cart.total"
    name: str          # simple name, e.g. "total"
    lineno: int
    kind: str          # "function" | "method"
    is_test: bool

    def source(self) -> str:
        try:
            return get_function_source(self.abspath, self.qualname)
        except Exception:
            return ""

    def snippet(self, max_lines: int = 14) -> str:
        lines = self.source().splitlines()
        if len(lines) > max_lines:
            lines = lines[:max_lines] + ["    ..."]
        return "\n".join(lines)


def _python_files(root: str):
    skip = {".git", "__pycache__", ".venv", "venv", "node_modules", ".pytest_cache"}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in skip]
        for fn in filenames:
            if fn.endswith(".py"):
                yield os.path.join(dirpath, fn)


def _is_test_path(rel: str, name: str) -> bool:
    parts = rel.replace("\\", "/").split("/")
    return "tests" in parts or "test" in parts or name.startswith("test_") or name.endswith("_test")


def build_repo_map(root: str) -> list[RepoFunction]:
    funcs: list[RepoFunction] = []
    for path in _python_files(root):
        rel = os.path.relpath(path, root)
        fname = os.path.basename(path)
        is_test = _is_test_path(rel, fname)
        try:
            with open(path, "r", encoding="utf-8") as fh:
                tree = ast.parse(fh.read())
        except (SyntaxError, UnicodeDecodeError):
            continue

        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                funcs.append(RepoFunction(rel, path, node.name, node.name,
                                          node.lineno, "function", is_test))
            elif isinstance(node, ast.ClassDef):
                for sub in node.body:
                    if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        funcs.append(RepoFunction(rel, path, f"{node.name}.{sub.name}",
                                                  sub.name, sub.lineno, "method", is_test))
    return funcs


from .edit import get_function_source  # noqa: E402  (lazy, avoids circular import)
