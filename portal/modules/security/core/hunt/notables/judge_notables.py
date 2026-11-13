"""Judge each distinct notable once through the Pipeline, cached by the notable's content key."""

from __future__ import annotations

import json
import time
from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..judge import BackpressureClient, JudgeClient, JudgeResult, judge_cell

JUDGE_CONCURRENCY = 2  # effort budget: the seat serves one request at a time
JUDGE_REQUEST_BUDGET = 80  # effort budget: judge's share of ~200 model requests per hunt
JUDGE_MAX_EVIDENCE = 3  # effort budget: example events shown for one notable
JUDGE_EVIDENCE_CHARS = 300  # effort budget: raw characters shown per example
JUDGE_STATEMENT_CHARS = 1200  # effort budget: characters of the notable statement kept
JUDGE_PROMPT_CHARS = 6000  # effort budget: an 8K-context seat

QUESTION = """You are a security analyst. Below is one notable raised from machine-written log data: what
was seen, the entities involved, when it was seen, and up to three example events. Decide whether
it shows an intrusion or abnormal hands-on activity (for example scanning, exploitation, credential
abuse, unauthorized access, command execution, tampering or exfiltration) rather than routine
operation (boot, scheduled jobs, service restarts, log rotation, software updates, ordinary user and
service traffic).
Answer with one word: yes or no.

NOTABLE:"""


@dataclass(frozen=True)
class Judged:
    content_key: str
    p_yes: float | None
    served_model: str
    seconds: float
    prompt_tokens: int | None
    reason: str | None
    cached: bool


def _lines(notable: Mapping[str, Any]) -> list[str]:
    evidence = notable.get("evidence")
    if not isinstance(evidence, list):
        return []
    found = []
    for item in evidence[:JUDGE_MAX_EVIDENCE]:
        if isinstance(item, Mapping):
            found.append(str(item.get("line") or "")[:JUDGE_EVIDENCE_CHARS])
    return [line for line in found if line]


def notable_prompt(notable: Mapping[str, Any]) -> str:
    """A compact statement plus a few example events, inside the seat's context."""
    entities = "; ".join(
        f"{item.get('role')}={item.get('value')}"
        for item in notable.get("entities", [])
        if isinstance(item, Mapping)
    )
    body = "\n".join(
        part
        for part in (
            str(notable.get("what") or "")[:JUDGE_STATEMENT_CHARS],
            f"entities: {entities}" if entities else "",
            f"generator: {notable.get('generator')} / {notable.get('basis')}",
            f"why raised: {notable.get('why')}",
            "examples:",
            *[f"- {line}" for line in _lines(notable)],
        )
        if part
    )
    return (QUESTION + "\n" + body)[:JUDGE_PROMPT_CHARS]


class JudgeCache:
    """One JSON object per notable content key; a rerun asks nothing twice."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.entries: dict[str, dict[str, Any]] = {}
        if path.exists():
            try:
                stored = json.loads(path.read_text())
            except (OSError, ValueError):
                stored = {}
            if isinstance(stored, dict):
                self.entries = {
                    str(key): value for key, value in stored.items() if isinstance(value, dict)
                }

    def get(self, key: str) -> dict[str, Any] | None:
        return self.entries.get(key)

    def put(self, key: str, value: Mapping[str, Any]) -> None:
        self.entries[key] = dict(value)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.entries, sort_keys=True, indent=1))


def _result(notable: Mapping[str, Any], result: JudgeResult, cached: bool) -> Judged:
    return Judged(
        str(notable.get("content_key") or ""),
        result.p_yes,
        result.served_model,
        result.seconds,
        result.prompt_tokens,
        result.reason,
        cached,
    )


def _cached(notable: Mapping[str, Any], cache: JudgeCache) -> Judged | None:
    key = str(notable.get("content_key") or "")
    stored = cache.get(key)
    if stored is None or stored.get("p_yes") is None:
        return None
    return Judged(
        key,
        _float_or_none(stored.get("p_yes")),
        str(stored.get("served_model") or ""),
        float(stored.get("seconds") or 0.0),
        None,
        None,
        True,
    )


def _judge_one(
    notable: Mapping[str, Any], client: JudgeClient, model: str, cache: JudgeCache
) -> Judged:
    key = str(notable.get("content_key") or "")
    prompt = notable_prompt(notable)
    result = judge_cell(client, model=model, prompt=prompt)
    if result.p_yes is not None:
        cache.put(
            key,
            {
                "p_yes": result.p_yes,
                "served_model": result.served_model,
                "seconds": result.seconds,
                "prompt_tokens": result.prompt_tokens,
                "reason": result.reason,
            },
        )
    return _result(notable, result, False)


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def judge_all(
    notables: Sequence[dict[str, Any]],
    *,
    client: JudgeClient,
    model: str,
    cache_path: Path,
    request_budget: int = JUDGE_REQUEST_BUDGET,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Cache first, then judge in notable order inside the model-request budget."""
    began = time.monotonic()
    cache = JudgeCache(cache_path)
    results: list[Judged | None] = [None] * len(notables)
    pending: list[int] = []
    for index, notable in enumerate(notables):
        found = _cached(notable, cache)
        if found is not None:
            results[index] = found
        else:
            pending.append(index)
    budget = max(0, request_budget)
    ask, unasked = pending[:budget], pending[budget:]
    asker = client if isinstance(client, BackpressureClient) else BackpressureClient(client)
    with ThreadPoolExecutor(max_workers=JUDGE_CONCURRENCY) as pool:
        futures = {
            pool.submit(_judge_one, notables[index], asker, model, cache): index for index in ask
        }
        for future in as_completed(futures):
            results[futures[future]] = future.result()
    for index in unasked:
        key = str(notables[index].get("content_key") or "")
        results[index] = Judged(key, None, "", 0.0, None, "model_budget_exhausted", False)
    cache.save()
    judged = [result for result in results if result is not None]
    out: list[dict[str, Any]] = []
    reasons: dict[str, int] = {}
    served: set[str] = set()
    requests = 0
    seconds = 0.0
    for notable, result in zip(notables, judged, strict=True):
        item = dict(notable)
        item["p_yes"] = result.p_yes
        item["judge"] = {
            "served_model": result.served_model,
            "seconds": result.seconds,
            "prompt_tokens": result.prompt_tokens,
            "reason": result.reason,
            "cached": result.cached,
        }
        out.append(item)
        if not result.cached and result.reason != "model_budget_exhausted":
            requests += 1
            seconds += result.seconds
        if result.served_model:
            served.add(result.served_model)
        if result.p_yes is None:
            reasons[str(result.reason or "unjudged")] = (
                reasons.get(str(result.reason or "unjudged"), 0) + 1
            )
    return out, {
        "notables": len(notables),
        "judged": sum(1 for item in judged if item.p_yes is not None),
        "unjudged": sum(1 for item in judged if item.p_yes is None),
        "unjudged_reasons": reasons,
        "requests": requests,
        "cached": sum(1 for item in judged if item.cached),
        "seconds": round(time.monotonic() - began, 3),
        "model_seconds": round(seconds, 3),
        "served_models": sorted(served),
        "request_budget": budget,
        "unasked": len(unasked),
        "cache": str(cache_path),
        "backpressure": asker.stats() if isinstance(asker, BackpressureClient) else {},
    }
