"""One-token judgement of one host-hour, asked through the Portal Pipeline."""

from __future__ import annotations

import math
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

JUDGE_SEED = 0
JUDGE_TOP_LOGPROBS = 20  # effort budget: alternatives returned for the first token
JUDGE_TIMEOUT_SECONDS = 60  # effort budget: maximum wait for one local judgement

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


@dataclass(frozen=True)
class JudgeResult:
    p_yes: float | None
    prompt_tokens: int | None
    seconds: float
    served_model: str
    reason: str | None


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
        with httpx.Client(transport=self.transport, timeout=self.timeout_seconds) as client:
            response = client.post(self.endpoint, headers=headers, json=request)
            response.raise_for_status()
            payload: Mapping[str, Any] = response.json()
        return payload


def build_prompt(evidence: Sequence[Mapping[str, Any]]) -> str:
    """Append the selected source and raw event lines to the fixed question."""
    return QUESTION + "\n" + "\n".join(str(item["line"]) for item in evidence)


def _token_mass(alternatives: Any) -> tuple[float, float] | None:
    found: dict[str, list[float]] = {"yes": [], "no": []}
    if not isinstance(alternatives, list):
        return None
    for alternative in alternatives:
        if not isinstance(alternative, Mapping):
            continue
        token = str(alternative.get("token", "")).strip().casefold()
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
    evidence: Sequence[Mapping[str, Any]],
) -> JudgeResult:
    """Judge one cell; missing probabilities or transport failures remain unjudged."""
    began = time.monotonic()
    try:
        response = client.complete(
            model=model,
            messages=[{"role": "user", "content": build_prompt(evidence)}],
            temperature=0,
            seed=JUDGE_SEED,
            max_tokens=1,
            logprobs=True,
            top_logprobs=JUDGE_TOP_LOGPROBS,
            reasoning_effort="none",
            stream=False,
        )
    except (httpx.TimeoutException, TimeoutError):
        return JudgeResult(None, None, round(time.monotonic() - began, 3), "", "timeout")
    except httpx.HTTPStatusError:
        return JudgeResult(None, None, round(time.monotonic() - began, 3), "", "http_error")
    except Exception:  # noqa: BLE001 -- failure is per-cell unjudged coverage
        return JudgeResult(None, None, round(time.monotonic() - began, 3), "", "request_failed")
    seconds = round(time.monotonic() - began, 3)
    if not isinstance(response, Mapping):
        return JudgeResult(None, None, seconds, "", "invalid_response")
    served = str(response.get("model", ""))
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], Mapping):
        return JudgeResult(None, _prompt_tokens(response), seconds, served, "missing_logprobs")
    logprobs = choices[0].get("logprobs")
    content = logprobs.get("content") if isinstance(logprobs, Mapping) else None
    if not isinstance(content, list) or not content or not isinstance(content[0], Mapping):
        return JudgeResult(None, _prompt_tokens(response), seconds, served, "missing_logprobs")
    masses = _token_mass(content[0].get("top_logprobs"))
    if masses is None or masses[0] + masses[1] <= 0:
        return JudgeResult(
            None, _prompt_tokens(response), seconds, served, "missing_yes_no_alternatives"
        )
    return JudgeResult(
        masses[0] / (masses[0] + masses[1]),
        _prompt_tokens(response),
        seconds,
        served,
        None,
    )
