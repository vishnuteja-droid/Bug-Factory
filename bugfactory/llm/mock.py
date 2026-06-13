"""Deterministic provider so the full pipeline runs and can be verified without
any model server (CI, this container, offline dev).

It branches on the [role:NAME] marker each agent puts in its system prompt.
Crucially it does NOT hard-code which bug to fix: for localization it trusts
the deterministic ranker (picks the top candidate), and for coding it inspects
the function it was handed. That makes it a real test of the scaffolding, not a
lookup table — adding a new scenario needs a fix recipe here only because a
stub cannot reason.
"""
from __future__ import annotations

import re

from .base import LLMProvider, LLMResponse

# Known correct fixes for the sample repo's seeded bugs, keyed by a marker in
# the function source the coder is shown.
_FIXES = {
    "def subtract": "def subtract(a, b):\n    return a - b",
    "def total": "def total(self, tax_rate):\n    return self.subtotal() * (1 + tax_rate)",
}


class MockProvider(LLMProvider):
    name = "mock"

    def __init__(self, model: str = "mock"):
        self.model = model

    def complete(self, system: str, prompt: str, **opts) -> LLMResponse:
        s = system.lower()
        if "[role:intake]" in s:
            text = "{}"  # forces the deterministic keyword fallback in intake()
        elif "[role:localize]" in s:
            m = re.search(r"-\s+(\S+)", prompt)  # trust the ranker: take the top candidate
            text = m.group(1) if m else ""
        elif "[role:plan]" in s:
            text = "Correct the function body so it matches the behavior described in the ticket."
        elif "[role:code]" in s:
            fix = next((f for marker, f in _FIXES.items() if marker in prompt), None)
            if fix is None:
                # Unknown function: echo the original unchanged (a harmless no-op),
                # so a wrong suspect is rejected cleanly instead of being mangled.
                orig = re.search(r"```python\s*(.*?)```", prompt, re.DOTALL)
                fix = orig.group(1).strip("\n") if orig else "pass"
            text = f"```python\n{fix}\n```"
        elif "[role:review]" in s:
            text = "PASS: the change addresses the behavior described in the ticket."
        else:
            text = ""
        return LLMResponse(text=text, model=self.model, raw=None)
