"""Deterministic provider so the full pipeline runs and can be verified
without any model server (CI, this container, offline dev).

It branches on a keyword in the agent's system prompt — each agent uses a
distinct role marker, so the mock can play every role in the pipeline.
"""
from __future__ import annotations

from .base import LLMProvider, LLMResponse


class MockProvider(LLMProvider):
    name = "mock"

    def __init__(self, model: str = "mock"):
        self.model = model

    def complete(self, system: str, prompt: str, **opts) -> LLMResponse:
        s = system.lower()
        if "[role:intake]" in s:
            text = '{"summary": "subtract() adds instead of subtracting", "keywords": ["subtract", "subtraction"]}'
        elif "[role:localize]" in s:
            text = "subtract"
        elif "[role:plan]" in s:
            text = "Change the body of subtract so it returns a - b instead of a + b."
        elif "[role:code]" in s:
            text = "```python\ndef subtract(a, b):\n    return a - b\n```"
        elif "[role:review]" in s:
            text = "PASS: the fix replaces addition with subtraction, matching the ticket."
        else:
            text = ""
        return LLMResponse(text=text, model=self.model, raw=None)
