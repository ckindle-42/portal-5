"""Transport dialects for the compliance reading call.

Why this exists: ``reading_transport`` spoke exactly one wire protocol —
Ollama's native ``/api/chat`` — at a module-level constant. That is the
endpoint the sweep talks to, and it is NOT the pipeline: ``sweep.map_read``
never consults ``config/backends.yaml`` or the backend registry, so wiring a
new engine into the pipeline changes the conversation lane and leaves the
sweep exactly where it was.

A dialect is the difference between two wire protocols and nothing else. Each
one builds a request body, reads a response body, reports its own metrics, and
says where its context window came from. The judged-call logic in
``reading_transport.chat`` — the answer/reasoning budget split, the empty-answer
retry, the downgrade record — is protocol-independent and stays there.

The load-bearing rule: **every dialect stamps its own name and endpoint onto
the result.** A receipt that does not say which engine served it can be
attributed to the wrong one, which is precisely how a splash measurement can be
taken on Ollama and written into a promotion decision.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any, Protocol

__all__ = [
    "DIALECTS",
    "Dialect",
    "OllamaNative",
    "OpenAICompat",
    "resolve_dialect",
]


class Dialect(Protocol):
    """One wire protocol. Stateless; one instance per engine is enough."""

    name: str
    endpoint: str

    def headers(self) -> dict[str, str]: ...

    def build(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        fmt: Any,
        think: bool | str,
        num_predict: int,
        num_ctx: int,
        temperature: float,
        keep_alive: str,
    ) -> dict[str, Any]: ...

    def unpack(self, body: dict[str, Any]) -> tuple[str, str]: ...

    def metrics(self, body: dict[str, Any]) -> dict[str, Any]: ...

    def seat_ceiling(self, model: str) -> int: ...

    def applied_context_length(self, model: str) -> int: ...

    def classify_400(self, exc: urllib.error.HTTPError) -> str: ...

    def context_source(self) -> str: ...


def _get(url: str, timeout: int, headers: dict[str, str] | None = None) -> Any:
    request = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
        return json.load(response)


class OllamaNative:
    """Ollama's native ``/api/chat`` — the module's original and default path.

    Behaviour here is byte-identical to what ``reading_transport`` did before
    the seam existed: ``options.{temperature,num_predict,num_ctx}``, top-level
    ``keep_alive``, an always-explicit ``think``, ``format`` omitted rather
    than nulled when the caller wants prose.
    """

    name = "ollama-native"

    def __init__(self, base: str = "") -> None:
        self.base = (base or os.environ.get("OLLAMA_BASE", "http://localhost:11434")).rstrip("/")
        self.endpoint = f"{self.base}/api/chat"
        self._ceiling: dict[str, int] = {}

    def headers(self) -> dict[str, str]:
        return {"Content-Type": "application/json"}

    def build(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        fmt: Any,
        think: bool | str,
        num_predict: int,
        num_ctx: int,
        temperature: float,
        keep_alive: str,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": num_predict,
                "num_ctx": num_ctx,
            },
            "keep_alive": keep_alive,
            "think": think,
        }
        if fmt:
            payload["format"] = fmt
        if tools is not None:
            payload["tools"] = tools
        return payload

    def unpack(self, body: dict[str, Any]) -> tuple[str, str]:
        message = body.get("message") or {}
        return (
            str(message.get("content", "") or ""),
            str(message.get("thinking", "") or ""),
        )

    def metrics(self, body: dict[str, Any]) -> dict[str, Any]:
        def _s(key: str) -> float | None:
            val = body.get(key)
            return round(val / 1e9, 3) if isinstance(val, (int, float)) else None

        return {
            "eval_count": body.get("eval_count", 0),
            "prompt_eval_count": body.get("prompt_eval_count", 0),
            "load_duration_s": _s("load_duration"),
            "prompt_eval_duration_s": _s("prompt_eval_duration"),
            "eval_duration_s": _s("eval_duration"),
        }

    def seat_ceiling(self, model: str) -> int:
        if model in self._ceiling:
            return self._ceiling[model]
        ceiling = 0
        try:
            request = urllib.request.Request(
                f"{self.base}/api/show",
                data=json.dumps({"model": model}).encode(),
                headers=self.headers(),
            )
            with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
                info = (json.load(response) or {}).get("model_info") or {}
            ceiling = max(
                (int(v) for k, v in info.items() if k.endswith(".context_length")),
                default=0,
            )
        except Exception:  # noqa: BLE001 - an unreadable ceiling disables the check
            ceiling = 0
        self._ceiling[model] = ceiling
        return ceiling

    def applied_context_length(self, model: str) -> int:
        try:
            models = (_get(f"{self.base}/api/ps", 10) or {}).get("models") or []
        except Exception:  # noqa: BLE001
            return 0
        for entry in models:
            if entry.get("name") == model or entry.get("model") == model:
                return int(entry.get("context_length") or 0)
        return 0

    def classify_400(self, exc: urllib.error.HTTPError) -> str:
        try:
            detail = json.loads(exc.read().decode() or "{}")
        except Exception:  # noqa: BLE001
            return ""
        blob = json.dumps(detail).lower()
        if "exceed_context_size" in blob or "n_prompt_tokens" in blob:
            return "context"
        if "think" in blob or "reasoning" in blob:
            return "think"
        return ""

    def context_source(self) -> str:
        return "request_num_ctx"


class OpenAICompat:
    """An OpenAI-compatible ``/v1/chat/completions`` server — splash 1.0.1.

    The differences that matter, all verified against splash 1.0.1's surface:

    * no ``options`` sub-dict — ``max_tokens`` and ``temperature`` are
      top-level;
    * no ``keep_alive`` — the server holds one model and is operator-run;
    * **no ``num_ctx``** — the window is a serve-line pin
      (``--max-context 32768``), so the request cannot raise or lower it and
      ``context_source`` reports ``serve_line_pin`` so no receipt claims a
      window it did not set;
    * no native ``think`` — reasoning is ``reasoning_effort`` at the top level,
      and ``think: False`` maps to ``"none"``;
    * ``repeat_penalty``/``repetition_penalty`` are not accepted and are never
      sent — a tuning knob the server silently ignores is a debugging trap.
    """

    name = "openai-compat"

    def __init__(self, base: str = "", api_key_env: str = "SPLASH_API_KEY") -> None:
        self.base = (base or os.environ.get("SPLASH_BASE", "http://127.0.0.1:8086")).rstrip("/")
        self.endpoint = f"{self.base}/v1/chat/completions"
        self.api_key_env = api_key_env
        self._ceiling: dict[str, int] = {}

    def headers(self) -> dict[str, str]:
        head = {"Content-Type": "application/json"}
        key = os.environ.get(self.api_key_env)
        if key:
            head["Authorization"] = f"Bearer {key}"
        return head

    @staticmethod
    def _effort(think: bool | str) -> str:
        if think is False or think is None:
            return "none"
        if think is True:
            return "auto"
        return str(think)

    def build(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        fmt: Any,
        think: bool | str,
        num_predict: int,
        num_ctx: int,
        temperature: float,
        keep_alive: str,
    ) -> dict[str, Any]:
        # num_ctx and keep_alive are accepted and DROPPED on purpose: the window
        # is the serve-line pin and the server holds one model. Silently passing
        # them would let a caller believe it set something it did not.
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": False,
            "max_tokens": num_predict,
            "temperature": temperature,
            "reasoning_effort": self._effort(think),
        }
        if fmt:
            payload["response_format"] = {"type": "json_object"} if fmt in ("json", True) else fmt
        if tools is not None:
            payload["tools"] = tools
        return payload

    def unpack(self, body: dict[str, Any]) -> tuple[str, str]:
        choices = body.get("choices") or []
        if not choices:
            return ("", "")
        message = choices[0].get("message") or {}
        content = str(message.get("content", "") or "")
        thinking = str(message.get("reasoning_content") or message.get("reasoning") or "")
        return (content, thinking)

    def metrics(self, body: dict[str, Any]) -> dict[str, Any]:
        usage = body.get("usage") or {}
        timings = body.get("timings") or {}
        # splash 1.0.1 does not populate usage.prompt_tokens (measured: every
        # cell of arms B/C reported prompt_eval_count: 0 against a live
        # prompt_eval_count of 23,119 tokens on the Ollama side of the same
        # material — 40/40 rows). A `0` here was recorded as though it were a
        # measurement; it was the absence of one. Every plausible key splash's
        # OpenAI-compatible surface might use is tried, and an unaccounted
        # cell reports None — never a number nothing backs.
        prompt_tokens = (
            usage.get("prompt_tokens")
            or usage.get("prompt_eval_count")
            or usage.get("prompt_token_count")
            or timings.get("prompt_n")
        )
        eval_tokens = (
            usage.get("completion_tokens")
            or usage.get("eval_count")
            or usage.get("completion_token_count")
            or timings.get("predicted_n")
        )
        return {
            "eval_count": eval_tokens if isinstance(eval_tokens, (int, float)) else None,
            "prompt_eval_count": (
                prompt_tokens if isinstance(prompt_tokens, (int, float)) else None
            ),
            "cached_prompt_tokens": (
                usage.get("prompt_tokens_cached") or usage.get("prompt_cache_hit_tokens") or 0
            ),
            "load_duration_s": timings.get("load_s"),
            "prompt_eval_duration_s": (
                prompt_ms / 1000.0
                if isinstance(prompt_ms := timings.get("prompt_ms"), (int, float))
                else None
            ),
            "eval_duration_s": (
                predicted_ms / 1000.0
                if isinstance(predicted_ms := timings.get("predicted_ms"), (int, float))
                else None
            ),
        }

    def seat_ceiling(self, model: str) -> int:
        """The serve-line window if the server reports it, else 0.

        0 disables the pre-flight check rather than inventing a ceiling — the
        same rule the native dialect follows. The serve-line pin is the real
        constraint and the benchmark records it separately.
        """
        if model in self._ceiling:
            return self._ceiling[model]
        ceiling = 0
        try:
            data = _get(f"{self.base}/v1/models", 15, self.headers()) or {}
            for entry in data.get("data") or []:
                if entry.get("id") != model:
                    continue
                for key in ("max_context", "context_length", "max_model_len", "n_ctx"):
                    val = entry.get(key)
                    if isinstance(val, int) and val > 0:
                        ceiling = val
                        break
        except Exception:  # noqa: BLE001
            ceiling = 0
        self._ceiling[model] = ceiling
        return ceiling

    def applied_context_length(self, model: str) -> int:
        # The applied window is the serve-line pin; there is no /api/ps analogue.
        # Reporting the advertised ceiling would be reporting a request as an
        # applied value, which is the exact confusion this module already fixed
        # once for Ollama. 0 means "unknown here — read the serve line".
        return 0

    def classify_400(self, exc: urllib.error.HTTPError) -> str:
        try:
            detail = json.loads(exc.read().decode() or "{}")
        except Exception:  # noqa: BLE001
            return ""
        blob = json.dumps(detail).lower()
        if "context" in blob and ("exceed" in blob or "longer" in blob or "maximum" in blob):
            return "context"
        if "reasoning" in blob or "think" in blob:
            return "think"
        return ""

    def context_source(self) -> str:
        return "serve_line_pin"


DIALECTS: dict[str, Any] = {
    "ollama-native": OllamaNative,
    "openai-compat": OpenAICompat,
}


def resolve_dialect(dialect: Any = None) -> Any:
    """An explicit dialect wins; then ``COMPLIANCE_TRANSPORT``; then native.

    A name this module does not know is an error, never a silent fallback to
    the default — falling back would serve an Ollama call under a splash label.
    """
    if dialect is not None and not isinstance(dialect, str):
        return dialect
    name = dialect or os.environ.get("COMPLIANCE_TRANSPORT", "ollama-native")
    if name not in DIALECTS:
        raise ValueError(f"unknown transport dialect {name!r}; known: {sorted(DIALECTS)}")
    return DIALECTS[name]()
