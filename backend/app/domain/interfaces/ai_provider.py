"""Contract every AI inference backend (Ollama, OpenRouter, ...) must satisfy.

`application` code depends only on this `Protocol`, never on a concrete
provider class — the concrete implementation is chosen by
`infrastructure.ai_providers.factory.get_ai_provider()` based on `Settings`.
"""
from typing import Protocol


class AIProvider(Protocol):
    def ask_chat(
        self,
        model: str,
        messages: list[dict],
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> str:
        """Send a chat completion request and return the text response."""
        ...

    def ask_vision(self, model: str, prompt: str, image_path: str) -> str:
        """Send an image + prompt to a vision-capable model and return the text response."""
        ...

    def is_available(self) -> bool:
        """Whether this provider is currently reachable/configured."""
        ...

    @property
    def name(self) -> str:
        """Short provider identifier, e.g. 'ollama' or 'openrouter'."""
        ...
