"""Build a lightweight 'repo map' so an agent can orient in a codebase it has
never seen, without reading every file. We parse each Python module with `ast`
and extract top-level function definitions (name, file, line).

This is the cheap, dependency-free version of a tree-sitter repo map. It is
enough to localize bugs in the demo and is where we'd grow richer symbol
extraction later.
"""
from __future__ import annotations

import ast
import os
from dataclasses import dataclass


@dataclass
class RepoFunction:
    file: str          # path relative to repo root
    abspath: str
    function: str
    lineno: int

    def snippet(self, max_lines: int = 12) -> str:
        try:
            src = get_function_source(self.abspath, self.function)
        except Exception:
            return ""
        lines = src.splitlines()
        if len(lines) > max_lines:
            lines = lines[:max_lines] + ["    ..."]
        return "\n".join(lines)


def _python_files(root: str):
    skip = {".git", "__pycache__", ".venv", "venv", "node_modules"}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in skip]
        for fn in filenames:
            if fn.endswith(".py"):
                yield os.path.join(dirpath, fn)


def build_repo_map(root: str) -> list[RepoFunction]:
    funcs: list[RepoFunction] = []
    for path in _python_files(root):
        try:
            with open(path, "r", encoding="utf-8") as fh:
                tree = ast.parse(fh.read())
        except (SyntaxError, UnicodeDecodeError):
            continue
        # Only module-level functions for the demo (keeps localization simple).
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                funcs.append(
                    RepoFunction(
                        file=os.path.relpath(path, root),
                        abspath=path,
                        function=node.name,
                        lineno=node.lineno,
                    )
                )
    return funcs


# imported lazily to avoid a circular import at module load
from .edit import get_function_source  # noqa: E402
