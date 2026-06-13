from .base import LLMProvider, LLMResponse
from .ollama import OllamaProvider
from .mock import MockProvider

__all__ = ["LLMProvider", "LLMResponse", "OllamaProvider", "MockProvider", "build_provider"]


def build_provider(name: str = "ollama", **kwargs) -> LLMProvider:
    """Factory: pick a provider by name. Adding a new backend is a one-line change here."""
    name = (name or "ollama").lower()
    if name == "ollama":
        return OllamaProvider(**kwargs)
    if name == "mock":
        return MockProvider(**kwargs)
    raise ValueError(f"unknown provider: {name!r} (known: ollama, mock)")
