"""Build the merge-request artifact (a unified diff + a description). For the
demo we write these to disk; Phase 1 swaps in a GitLab API call behind the same
inputs.
"""
from __future__ import annotations

import difflib


def make_diff(old_source: str, new_source: str, path: str) -> str:
    diff = difflib.unified_diff(
        old_source.splitlines(keepends=True),
        new_source.splitlines(keepends=True),
        fromfile=f"a/{path}",
        tofile=f"b/{path}",
    )
    return "".join(diff)


def make_mr_description(ticket: dict, summary: str, plan: str, diff: str, review_note: str) -> str:
    return f"""# Fix: {ticket.get('title', ticket.get('key', 'bug'))}

**Resolves:** {ticket.get('key', 'N/A')}

## Root cause
{summary}

## Fix
{plan}

## Self-review
{review_note}

## Diff
```diff
{diff}```

---
*Raised automatically by the bug factory.*
"""
