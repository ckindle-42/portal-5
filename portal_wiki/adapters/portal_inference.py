"""Portal inference adapter — wires InferenceBackend to Ollama (localhost:11434).

Portal-5 specific.  This is the adapter; the interface lives in core/.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

from portal_wiki.core.interfaces import InferenceBackend

logger = logging.getLogger(__name__)

DEFAULT_OLLAMA_URL = "http://localhost:11434"
DEFAULT_MODEL = "gemma3:4b"


class PortalInference(InferenceBackend):
    """Inference backend wired to Ollama at localhost:11434.

    Uses /api/generate for single-turn generation (wiki seeding).
    """

    def __init__(
        self,
        ollama_url: str = "",
        model: str = "",
        timeout_s: float = 120.0,
    ) -> None:
        self.ollama_url = (
            ollama_url
            or os.environ.get("OLLAMA_URL", "")
            or os.environ.get("OLLAMA_BASE_URL", "")
            or DEFAULT_OLLAMA_URL
        )
        self.model = model or os.environ.get("WIKI_INFERENCE_MODEL", DEFAULT_MODEL)
        self.timeout_s = timeout_s

    def generate(self, prompt: str, **kwargs: Any) -> str:
        """Generate text via Ollama /api/generate."""
        model = kwargs.get("model", self.model)
        try:
            r = httpx.post(
                f"{self.ollama_url}/api/generate",
                json={
                    "model": model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": kwargs.get("temperature", 0.3),
                        "num_predict": kwargs.get("max_tokens", 2048),
                    },
                },
                timeout=self.timeout_s,
            )
            r.raise_for_status()
            data = r.json()
            return data.get("response", "")
        except Exception as e:
            logger.warning("Ollama generate failed: %s", e)
            return f"[inference error: {e}]"

    def is_available(self) -> bool:
        """Check if Ollama is reachable."""
        try:
            r = httpx.get(f"{self.ollama_url}/api/tags", timeout=5)
            return r.status_code == 200
        except Exception:
            return False
