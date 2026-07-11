"""Pluggable interfaces — the extraction boundary.

Pure ABCs with ZERO Portal-specific imports.  Portal wiring lives in adapters/.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class InferenceBackend(ABC):
    """Interface for local inference.

    Portal-5 wires this to Ollama (localhost:11434).  A standalone build
    could wire OpenAI/Anthropic/any OpenAI-compatible endpoint.
    """

    @abstractmethod
    def generate(self, prompt: str, **kwargs: Any) -> str:
        """Generate text from a prompt.  Returns the generated text."""
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """Check if the backend is reachable."""
        ...


class SourceConnector(ABC):
    """Interface for knowledge sources.

    Portal-5 wires this to the git repo + docs/.  Generalizes to any repo.
    """

    @abstractmethod
    def iter_sources(self) -> list[dict[str, Any]]:
        """Iterate over available sources.

        Returns list of dicts with at least: {type, path}.
        """
        ...

    @abstractmethod
    def read_source(self, path: str) -> str:
        """Read the content of a source by path."""
        ...
