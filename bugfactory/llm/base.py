"""The single narrow interface the whole factory codes against.

Nothing in the pipeline imports a vendor SDK directly. Swapping providers
(Ollama, OpenAI, a hosted model, ...) is a config change, not a code change.
"""
from __future__ import annotations

import abc
from dataclasses import dataclass
from typing import Optional


@dataclass
class LLMResponse:
    text: str
    model: str
    raw: Optional[dict] = None


class LLMProvider(abc.ABC):
    name: str = "base"
    model: str = "unknown"

    @abc.abstractmethod
    def complete(self, system: str, prompt: str, **opts) -> LLMResponse:
        """Return the model's text completion for a system + user prompt."""
        raise NotImplementedError
