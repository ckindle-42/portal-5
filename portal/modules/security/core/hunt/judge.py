"""One-word judgement of one notable or host-hour, asked through the Portal Pipeline."""

from __future__ import annotations

import math
import threading
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

DEFAULT_KEY_ENV = "PIPELINE_API_KEY"  # env var name whose value is the Pipeline credential
JUDGE_SEED = 0
JUDGE_TOP_LOGPROBS = 20  # effort budget: alternatives returned for the answer token
JUDGE_ANSWER_TOKENS = 8  # effort budget: room for a one-word answer, defensively markdown-wrapped
JUDGE_REASON_TOKENS = 40
JUDGE_TIMEOUT_SECONDS = 60  # effort budget: maximum wait for one local judgement
MODEL_CONCURRENCY = 2  # effort budget: the engine behind the seat serves one request at a time
MODEL_WORK_SECONDS = 300.0  # effort budget: wall time one stage may spend asking the Pipeline
RETRY_AFTER_MAX_SECONDS = 30.0  # effort budget: longest wait honoured from Retry-After
BACKOFF_MAX_SECONDS = 8.0  # effort budget: longest deterministic backoff between retries
THROTTLE_STATUSES = frozenset({429, 503})
_CHAT_COMPLETIONS = "/v1/chat/completions"


def chat_completions_endpoint(url: str) -> str:
    """Pipeline chat-completions path. The caller supplies the workspace URL."""
    root = url.rstrip("/")
    if root.endswith(_CHAT_COMPLETIONS):
        return root
    return root + _CHAT_COMPLETIONS


QUESTION = """You are a security analyst. Below are log events from one host during one hour. They were
selected only because their format or volume is unusual for this host. Decide whether they show
an intrusion or abnormal hands-on activity (for example scanning, exploitation, credential abuse,
unauthorized access, command execution, tampering or exfiltration) rather than routine operation
(boot, scheduled jobs, service restarts, log rotation, software updates, ordinary user and
service traffic).
Answer with one word: yes or no.

EVENTS:"""


class JudgeClient(Protocol):
    def complete(self, **request: Any) -> Mapping[str, Any]: ...


class ThrottleBudgetExceededError(RuntimeError):
    """The model-work time budget ran out while the Pipeline was asking for back-pressure."""


def retry_after_seconds(response: httpx.Response) -> float | None:
    """Retry-After in seconds, bounded; an HTTP-date form falls back to deterministic backoff."""
    value = response.headers.get("Retry-After")
    if not value:
        return None
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        return None
    return max(0.0, min(RETRY_AFTER_MAX_SECONDS, seconds))


class BackpressureClient:
    """Honour Pipeline back-pressure: bounded concurrency, bounded waits, one time budget."""

    def __init__(
        self,
        inner: JudgeClient,
        *,
        budget_seconds: float = MODEL_WORK_SECONDS,
        concurrency: int = MODEL_CONCURRENCY,
        sleep: Any = time.sleep,
        clock: Any = time.monotonic,
    ) -> None:
        self.inner = inner
        self.budget_seconds = budget_seconds
        self.concurrency = max(1, concurrency)
        self._sleep = sleep
        self._clock = clock
        self._deadline = clock() + budget_seconds
        self._slots = threading.BoundedSemaphore(self.concurrency)
        self._lock = threading.Lock()
        self.throttles = 0
        self.retries = 0
        self.wait_seconds = 0.0
        self.exhausted = False

    def complete(self, **request: Any) -> Mapping[str, Any]:
        attempt = 0
        while True:
            with self._slots:
                try:
                    return self.inner.complete(**request)
                except httpx.HTTPStatusError as exc:
                    if exc.response.status_code not in THROTTLE_STATUSES:
                        raise
                    response = exc.response
            attempt += 1
            with self._lock:
                self.throttles += 1
                self.retries += 1
            delay = retry_after_seconds(response) or min(
                BACKOFF_MAX_SECONDS, float(2 ** (attempt - 1))
            )
            remaining = self._deadline - self._clock()
            if remaining <= 0:
                with self._lock:
                    self.exhausted = True
                raise ThrottleBudgetExceededError("model_work_budget_exhausted")
            wait = min(delay, remaining)
            with self._lock:
                self.wait_seconds += wait
            self._sleep(wait)

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "concurrency": self.concurrency,
                "budget_seconds": self.budget_seconds,
                "throttles": self.throttles,
                "retries": self.retries,
                "wait_seconds": round(self.wait_seconds, 3),
                "exhausted": self.exhausted,
            }


@dataclass(frozen=True)
class JudgeResult:
    p_yes: float | None
    prompt_tokens: int | None
    seconds: float
    served_model: str
    reason: str | None
    answer: str = ""
    decision_index: int | None = None


class OpenAICompatibleClient:
    """POST a chat completion to the Portal Pipeline's workspace endpoint."""

    def __init__(
        self,
        endpoint: str,
        api_key: str | None = None,
        *,
        timeout_seconds: float = JUDGE_TIMEOUT_SECONDS,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.endpoint = endpoint
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self.transport = transport

    def complete(self, **request: Any) -> Mapping[str, Any]:
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        timeout = min(
            self.timeout_seconds, float(request.pop("_timeout_seconds", self.timeout_seconds))
        )
        with httpx.Client(transport=self.transport, timeout=timeout) as client:
            # A hunt request is an answer, never a tool call. A workspace that attaches tools
            # otherwise lets the engine's tool-call parser swallow a JSON-object answer.
            body = {"tool_choice": "none", **request}
            response = client.post(self.endpoint, headers=headers, json=body)
            response.raise_for_status()
            payload: Mapping[str, Any] = response.json()
        return payload


def build_prompt(evidence: Sequence[Mapping[str, Any]]) -> str:
    """Append the selected source and raw event lines to the fixed question."""
    return QUESTION + "\n" + "\n".join(str(item["line"]) for item in evidence)


def _clean_token(token: str) -> str:
    """The yes/no inside a token, behind markdown wrap, whitespace or punctuation."""
    cleaned = token.strip().strip("*").strip().casefold()
    return cleaned.rstrip(".!?;:,")


def _token_mass(alternatives: Any) -> tuple[float, float] | None:
    found: dict[str, list[float]] = {"yes": [], "no": []}
    if not isinstance(alternatives, list):
        return None
    for alternative in alternatives:
        if not isinstance(alternative, Mapping):
            continue
        token = _clean_token(str(alternative.get("token", "")))
        if token not in found:
            continue
        try:
            logprob = float(alternative["logprob"])
        except (KeyError, TypeError, ValueError):
            continue
        if math.isfinite(logprob):
            found[token].append(logprob)
    if not found["yes"] or not found["no"]:
        return None
    maximum = max(logprob for values in found.values() for logprob in values)
    return (
        sum(math.exp(value - maximum) for value in found["yes"]),
        sum(math.exp(value - maximum) for value in found["no"]),
    )


def _decision_entry(content: Sequence[Any]) -> tuple[int, Mapping[str, Any]] | None:
    """The first generated token that is the answer itself, not a wrapper like **.

    Defensive: live Stage 2 (receipts_stage2_live1_20261116.log) measured the judge's
    yes-always as model bias — 0 wrapped answers, 31 bare — so the wrapper skip rarely
    fires; the logprob p_yes, not a 0.5 yes/no gate, is the signal.
    """
    for index, entry in enumerate(content):
        if isinstance(entry, Mapping) and _clean_token(str(entry.get("token", ""))) in (
            "yes",
            "no",
        ):
            return index, entry
    # Token-less logprobs entries (no sampled-token text at all): score the first
    # entry carrying yes/no mass, the pre-wrap contract. Never reached when the
    # engine names its tokens, so a ** wrapper is never scored as the answer.
    if any(isinstance(entry, Mapping) and str(entry.get("token") or "") for entry in content):
        return None
    for index, entry in enumerate(content):
        if isinstance(entry, Mapping) and _token_mass(entry.get("top_logprobs")) is not None:
            return index, entry
    return None


def _answer_text(response: Mapping[str, Any]) -> str:
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], Mapping):
        return ""
    message = choices[0].get("message")
    if not isinstance(message, Mapping):
        return ""
    return str(message.get("content") or "")


def _prompt_tokens(response: Mapping[str, Any]) -> int | None:
    usage = response.get("usage")
    if not isinstance(usage, Mapping):
        return None
    value = usage.get("prompt_tokens", usage.get("input_tokens"))
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def judge_cell(
    client: JudgeClient,
    *,
    model: str,
    evidence: Sequence[Mapping[str, Any]] = (),
    prompt: str | None = None,
    max_tokens: int = JUDGE_ANSWER_TOKENS,
) -> JudgeResult:
    """Judge one cell; missing probabilities or transport failures remain unjudged."""
    began = time.monotonic()
    prompt_text = prompt if prompt is not None else build_prompt(evidence)
    try:
        response = client.complete(
            model=model,
            messages=[{"role": "user", "content": prompt_text}],
            temperature=0,
            seed=JUDGE_SEED,
            max_tokens=max_tokens,
            logprobs=True,
            top_logprobs=JUDGE_TOP_LOGPROBS,
            reasoning_effort="none",
            stream=False,
        )
    except (httpx.TimeoutException, TimeoutError):
        return JudgeResult(None, None, round(time.monotonic() - began, 3), "", "timeout")
    except ThrottleBudgetExceededError:
        return JudgeResult(None, None, round(time.monotonic() - began, 3), "", "throttled")
    except httpx.HTTPStatusError:
        return JudgeResult(None, None, round(time.monotonic() - began, 3), "", "http_error")
    except Exception:  # noqa: BLE001 -- failure is per-cell unjudged coverage
        return JudgeResult(None, None, round(time.monotonic() - began, 3), "", "request_failed")
    seconds = round(time.monotonic() - began, 3)
    if not isinstance(response, Mapping):
        return JudgeResult(None, None, seconds, "", "invalid_response")
    served = str(response.get("model", ""))
    answer = _answer_text(response)
    tokens = _prompt_tokens(response)
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], Mapping):
        return JudgeResult(None, tokens, seconds, served, "missing_logprobs", answer)
    logprobs = choices[0].get("logprobs")
    content = logprobs.get("content") if isinstance(logprobs, Mapping) else None
    if not isinstance(content, list) or not content:
        return JudgeResult(None, tokens, seconds, served, "missing_logprobs", answer)
    found = _decision_entry(content)
    if found is None:
        return JudgeResult(None, tokens, seconds, served, "missing_yes_no_alternatives", answer)
    index, entry = found
    masses = _token_mass(entry.get("top_logprobs"))
    if masses is None or masses[0] + masses[1] <= 0:
        return JudgeResult(
            None, tokens, seconds, served, "missing_yes_no_alternatives", answer, index
        )
    return JudgeResult(
        masses[0] / (masses[0] + masses[1]),
        tokens,
        seconds,
        served,
        None,
        answer,
        index,
    )
