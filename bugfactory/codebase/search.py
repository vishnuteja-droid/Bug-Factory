"""Localization signals that scale to large repos: stack-trace parsing and
lexical (grep-style) search. These are precise and model-free — the LLM only
chooses among the candidates they surface.
"""
from __future__ import annotations

import os
import re

# `  File "src/orders.py", line 13, in total`
_PY_TRACE = re.compile(r'File "([^"]+)", line (\d+), in (\w+)')
# generic `path/to/file.py:13`
_PATH_LINE = re.compile(r'([\w./\\-]+\.py):(\d+)')


def parse_stack_trace(text: str) -> list[dict]:
    """Extract referenced frames from ticket text. Highest-precision signal."""
    frames = []
    for m in _PY_TRACE.finditer(text or ""):
        frames.append({"file": m.group(1), "line": int(m.group(2)), "func": m.group(3)})
    for m in _PATH_LINE.finditer(text or ""):
        frames.append({"file": m.group(1), "line": int(m.group(2)), "func": None})
    return frames


def lexical_hits(func_source: str, terms: list[str]) -> int:
    """Count how many distinct search terms appear in a function's body."""
    body = (func_source or "").lower()
    return sum(1 for t in {t.lower() for t in terms if t} if t in body)
