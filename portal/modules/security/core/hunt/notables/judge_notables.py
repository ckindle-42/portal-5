"""Judge each distinct notable once through the Pipeline, cached by the notable's content key."""

from __future__ import annotations

import json
import time
from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..judge import JudgeClient, JudgeResult, judge_cell

JUDGE_CONCURRENCY = 4  # effort budget: concurrent model requests, well inside the seat's capacity
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
            f"source: {notable.get('source_id')}",
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


def _judge_one(
    notable: Mapping[str, Any], client: JudgeClient, model: str, cache: JudgeCache
) -> Judged:
    key = str(notable.get("content_key") or "")
    stored = cache.get(key)
    if stored is not None and stored.get("p_yes") is not None:
        return Judged(
            key,
            _float_or_none(stored.get("p_yes")),
            str(stored.get("served_model") or ""),
            float(stored.get("seconds") or 0.0),
            None,
            None,
            True,
        )
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
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Judge every distinct notable once, bounded concurrency, failures left unjudged."""
    began = time.monotonic()
    cache = JudgeCache(cache_path)
    judged: list[Judged] = []
    with ThreadPoolExecutor(max_workers=JUDGE_CONCURRENCY) as pool:
        futures = [pool.submit(_judge_one, notable, client, model, cache) for notable in notables]
        for future in futures:
            judged.append(future.result())
    cache.save()
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
        if not result.cached:
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
        "cache": str(cache_path),
    }
