"""Ollama adapter — the real backend for the local demo (default: gemma3:1b)."""
from __future__ import annotations

import requests

from .base import LLMProvider, LLMResponse


class OllamaProvider(LLMProvider):
    name = "ollama"

    def __init__(
        self,
        model: str = "gemma3:1b",
        host: str = "http://localhost:11434",
        temperature: float = 0.0,
        timeout: int = 180,
    ):
        self.model = model
        self.host = host.rstrip("/")
        self.temperature = temperature
        self.timeout = timeout

    def complete(self, system: str, prompt: str, **opts) -> LLMResponse:
        payload = {
            "model": self.model,
            "system": system,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": opts.get("temperature", self.temperature)},
        }
        try:
            resp = requests.post(
                f"{self.host}/api/generate", json=payload, timeout=self.timeout
            )
            resp.raise_for_status()
        except requests.exceptions.ConnectionError as exc:
            raise RuntimeError(
                f"Could not reach Ollama at {self.host}. "
                f"Start it with `ollama serve` and `ollama pull {self.model}`."
            ) from exc
        data = resp.json()
        return LLMResponse(text=(data.get("response") or "").strip(), model=self.model, raw=data)
