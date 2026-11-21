"""Judge each distinct notable or case once through the Pipeline, cached by its content key."""

from __future__ import annotations

import json
import time
from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import duckdb

from ..judge import (
    JUDGE_ANSWER_TOKENS,
    JUDGE_REASON_TOKENS,
    MODEL_WORK_SECONDS,
    BackpressureClient,
    JudgeClient,
    JudgeResult,
    judge_cell,
)
from .spine import SPINE_FILE, STORE_FILE, event_id

JUDGE_CONCURRENCY = 2  # effort budget: the seat serves one request at a time
JUDGE_PROBE_CALLS = 8  # effort budget: calibration sample that measures the seat's call rate
JUDGE_CACHE_VERSION = 2  # bumped when the parse path changes; older entries are rejudged
JUDGE_MAX_EVIDENCE = 3  # effort budget: example events shown for one notable
JUDGE_MAX_KNOWN_MATCHES = 3  # effort budget: nearest labelled items shown to the judge
JUDGE_EVIDENCE_CHARS = 300  # effort budget: raw characters shown per example
JUDGE_STATEMENT_CHARS = 1200  # effort budget: characters of the notable statement kept
JUDGE_PROMPT_CHARS = 6000  # effort budget: an 8K-context seat
CASE_CACHE_VERSION = 1  # bumped when the case prompt or verification changes
CASE_MAX_MEMBERS = 20  # effort budget: members named to the judge
CASE_MAX_TIMELINE = 30  # effort budget: timeline rows shown to the judge
CASE_MAX_EVIDENCE = 6  # effort budget: raw events shown for one case
CASE_PROMPT_CHARS = 6000  # effort budget: an 8K-context seat
CASE_UNVERIFIED_ANCHOR = "unverified_anchor"  # a deterministic check failed; never a model call

QUESTION = """You are a security analyst. Below is one notable raised from machine-written log data: what
was seen, the entities involved, when it was seen, and up to three example events. Decide whether
it shows an intrusion or abnormal hands-on activity (for example scanning, exploitation, credential
abuse, unauthorized access, command execution, tampering or exfiltration) rather than routine
operation (boot, scheduled jobs, service restarts, log rotation, software updates, ordinary user and
service traffic)."""

CASE_QUESTION = """You are a security analyst. Below is one case built from machine-written log data: an
anchor entity, when it was seen, the sources and entities linked to it, and a bounded timeline of
the case. Decide whether the case shows an intrusion or abnormal hands-on activity (for example
scanning, exploitation, credential abuse, unauthorized access, command execution, tampering or
exfiltration) rather than routine operation (boot, scheduled jobs, service restarts, log rotation,
software updates, ordinary user and service traffic)."""


@dataclass(frozen=True)
class Judged:
    content_key: str
    p_yes: float | None
    served_model: str
    seconds: float
    prompt_tokens: int | None
    reason: str | None
    cached: bool
    answer: str = ""
    decision_index: int | None = None


def _lines(notable: Mapping[str, Any]) -> list[str]:
    evidence = notable.get("evidence")
    if not isinstance(evidence, list):
        return []
    found = []
    for item in evidence[:JUDGE_MAX_EVIDENCE]:
        if isinstance(item, Mapping):
            found.append(str(item.get("line") or "")[:JUDGE_EVIDENCE_CHARS])
    return [line for line in found if line]


def _known_lines(notable: Mapping[str, Any]) -> list[str]:
    """Show the nearest labelled behaviours as a score and family, never the label itself."""
    nearest = notable.get("nearest_known")
    if not isinstance(nearest, list):
        return []
    lines: list[str] = []
    for item in nearest[:JUDGE_MAX_KNOWN_MATCHES]:
        if not isinstance(item, Mapping):
            continue
        raw = item.get("similarity")
        if raw is None:
            continue
        try:
            similarity = float(raw)
        except (TypeError, ValueError):
            continue
        line = f"- matched item {similarity:.3f} ({item.get('family')})"
        if line not in lines:
            lines.append(line)
    return lines


def _number(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    return f"{number:.4f}".rstrip("0").rstrip(".") or "0"


def _measure_line(notable: Mapping[str, Any]) -> str:
    """The statistic that made the row rank, with the similar generator's zero threshold."""
    measure = notable.get("measure")
    if not isinstance(measure, Mapping):
        return ""
    name = str(measure.get("name") or "")
    value = measure.get("value")
    if not name or value is None:
        return ""
    if str(notable.get("generator") or "") == "similar_to_known":
        return f"margin = {_number(value)} (threshold 0)"
    return f"measure: {name} = {_number(value)}"


def notable_body(notable: Mapping[str, Any]) -> str:
    """The compact statement plus a few example events, without the question."""
    entities = "; ".join(
        f"{item.get('role')}={item.get('value')}"
        for item in notable.get("entities", [])
        if isinstance(item, Mapping)
    )
    reliability = notable.get("generator_reliability")
    if reliability is None:
        reliability_line = ""
    else:
        try:
            reliability_line = f"generator reliability (measured AUC): {float(reliability):.3f}"
        except (TypeError, ValueError):
            reliability_line = ""
    return "\n".join(
        part
        for part in (
            str(notable.get("what") or "")[:JUDGE_STATEMENT_CHARS],
            f"entities: {entities}" if entities else "",
            f"generator: {notable.get('generator')} / {notable.get('basis')}",
            reliability_line,
            _measure_line(notable),
            f"why raised: {notable.get('why')}",
            "nearest known items:",
            *_known_lines(notable),
            "examples:",
            *[f"- {line}" for line in _lines(notable)],
        )
        if part
    )


def notable_prompt(notable: Mapping[str, Any], *, explain: bool = False) -> str:
    """A compact statement plus a few example events, inside the seat's context."""
    instruction = (
        "Answer yes or no first, followed by a short reason in 12 words or fewer."
        if explain
        else "Answer with one word: yes or no."
    )
    return (QUESTION + "\n" + instruction + "\n\nNOTABLE:\n" + notable_body(notable))[
        :JUDGE_PROMPT_CHARS
    ]


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


def _verdict(key: str, result: JudgeResult, cached: bool) -> Judged:
    return Judged(
        key,
        result.p_yes,
        result.served_model,
        result.seconds,
        result.prompt_tokens,
        result.reason,
        cached,
        result.answer,
        result.decision_index,
    )


def _result(notable: Mapping[str, Any], result: JudgeResult, cached: bool) -> Judged:
    return _verdict(str(notable.get("content_key") or ""), result, cached)


def _cached(
    notable: Mapping[str, Any], cache: JudgeCache, *, explain: bool = False
) -> Judged | None:
    key = str(notable.get("content_key") or "")
    stored = cache.get(key)
    if stored is None or stored.get("p_yes") is None or stored.get("v") != JUDGE_CACHE_VERSION:
        return None
    if explain and stored.get("explain") is not True:
        return None
    return Judged(
        key,
        _float_or_none(stored.get("p_yes")),
        str(stored.get("served_model") or ""),
        float(stored.get("seconds") or 0.0),
        None,
        None,
        True,
        str(stored.get("answer") or ""),
        stored.get("decision_index"),
    )


def _judge_one(
    notable: Mapping[str, Any],
    client: JudgeClient,
    model: str,
    cache: JudgeCache,
    *,
    explain: bool = False,
) -> Judged:
    key = str(notable.get("content_key") or "")
    prompt = notable_prompt(notable, explain=explain)
    result = judge_cell(
        client,
        model=model,
        prompt=prompt,
        max_tokens=JUDGE_REASON_TOKENS if explain else JUDGE_ANSWER_TOKENS,
    )
    if result.p_yes is not None:
        cache.put(
            key,
            {
                "v": JUDGE_CACHE_VERSION,
                "p_yes": result.p_yes,
                "served_model": result.served_model,
                "seconds": result.seconds,
                "prompt_tokens": result.prompt_tokens,
                "reason": result.reason,
                "answer": result.answer,
                "decision_index": result.decision_index,
                "explain": explain,
            },
        )
    return _result(notable, result, False)


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _judge_batch(
    indices: Sequence[int],
    notables: Sequence[dict[str, Any]],
    asker: JudgeClient,
    model: str,
    cache: JudgeCache,
    results: list[Judged | None],
    *,
    explain: bool = False,
) -> None:
    if not indices:
        return
    with ThreadPoolExecutor(max_workers=JUDGE_CONCURRENCY) as pool:
        futures = {
            pool.submit(_judge_one, notables[index], asker, model, cache, explain=explain): index
            for index in indices
        }
        for future in as_completed(futures):
            results[futures[future]] = future.result()


def _rate_budget(
    total: int,
    probe_calls: int,
    run_probe: Callable[[int], None],
    deadline_seconds: float,
) -> tuple[int, dict[str, Any]]:
    """Size the budget from the probe's measured wall rate and the deadline."""
    probe = min(total, max(1, probe_calls))
    began = time.monotonic()
    run_probe(probe)
    probe_seconds = time.monotonic() - began
    rate = probe_seconds / probe
    remaining = max(0.0, deadline_seconds - probe_seconds)
    extra = int(remaining // rate) if rate > 0 else 0
    budget = min(total, probe + extra)
    return budget, {
        "source": "measured_rate",
        "probe_calls": probe,
        "probe_seconds": round(probe_seconds, 3),
        "seconds_per_call": round(rate, 4),
        "deadline_seconds": deadline_seconds,
        "derived_budget": budget,
    }


def _measured_budget(
    pending: Sequence[int],
    notables: Sequence[dict[str, Any]],
    asker: JudgeClient,
    model: str,
    cache: JudgeCache,
    results: list[Judged | None],
    deadline_seconds: float,
    probe_calls: int,
    *,
    explain: bool = False,
) -> tuple[int, dict[str, Any]]:
    """Size the budget from the probe's measured wall rate and the deadline."""

    def run_probe(count: int) -> None:
        _judge_batch(pending[:count], notables, asker, model, cache, results, explain=explain)

    return _rate_budget(len(pending), probe_calls, run_probe, deadline_seconds)


def judge_all(
    notables: Sequence[dict[str, Any]],
    *,
    client: JudgeClient,
    model: str,
    cache_path: Path,
    request_budget: int | None = None,
    deadline_seconds: float = MODEL_WORK_SECONDS,
    probe_calls: int = JUDGE_PROBE_CALLS,
    explain: bool = False,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Cache first, then judge in notable order inside a rate-measured budget."""
    began = time.monotonic()
    cache = JudgeCache(cache_path)
    results: list[Judged | None] = [None] * len(notables)
    pending: list[int] = []
    for index, notable in enumerate(notables):
        found = _cached(notable, cache, explain=explain)
        if found is not None:
            results[index] = found
        else:
            pending.append(index)
    asker = (
        client
        if isinstance(client, BackpressureClient)
        else BackpressureClient(client, budget_seconds=deadline_seconds)
    )
    if request_budget is not None:
        budget = max(0, request_budget)
        basis: dict[str, Any] = {"source": "explicit", "derived_budget": budget}
    elif pending:
        budget, basis = _measured_budget(
            pending,
            notables,
            asker,
            model,
            cache,
            results,
            deadline_seconds,
            probe_calls,
            explain=explain,
        )
    else:
        budget = 0
        basis = {
            "source": "measured_rate",
            "probe_calls": 0,
            "probe_seconds": 0.0,
            "seconds_per_call": None,
            "deadline_seconds": deadline_seconds,
            "derived_budget": 0,
        }
    ask = [index for index in pending[:budget] if results[index] is None]
    unasked = pending[budget:]
    _judge_batch(ask, notables, asker, model, cache, results, explain=explain)
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
            "answer": result.answer,
            "decision_index": result.decision_index,
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
        "budget_basis": basis,
        "unasked": len(unasked),
        "cache": str(cache_path),
        "backpressure": asker.stats() if isinstance(asker, BackpressureClient) else {},
    }


@dataclass(frozen=True)
class CaseFacts:
    """The stored run's own events and episodes: the deterministic check needs no search."""

    raws: Mapping[str, tuple[str, str]]  # event id -> (casefolded raw, source id)
    by_source: Mapping[str, tuple[tuple[str, str], ...]]  # source tail -> (raw, source id)
    episodes: Mapping[str, tuple[str, ...]]  # episode id -> event ids


def _tail(value: str) -> str:
    return value.rsplit(":", 1)[-1].rsplit("/", 1)[-1]


def load_case_facts(out: Path) -> CaseFacts:
    """Read every stored event and spine episode once; the judge never searches for a check."""
    raws: dict[str, tuple[str, str]] = {}
    if (out / STORE_FILE).is_file():
        con = duckdb.connect(str(out / STORE_FILE), read_only=True)
        try:
            rows = con.execute("SELECT source_id, host, ts, raw FROM events").fetchall()
        finally:
            con.close()
        for source_id, host, ts, raw in rows:
            text = str(raw or "")
            key = event_id(str(source_id), str(host or ""), float(ts or 0.0), text)
            raws[key] = (text.casefold(), str(source_id))
    grouped: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for text, source_id in raws.values():
        grouped[_tail(source_id)].append((text, source_id))
    episodes: dict[str, tuple[str, ...]] = {}
    if (out / SPINE_FILE).is_file():
        con = duckdb.connect(str(out / SPINE_FILE), read_only=True)
        try:
            rows = con.execute("SELECT episode_id, event_ids FROM episodes").fetchall()
        finally:
            con.close()
        episodes = {str(row[0]): tuple(json.loads(str(row[1] or "[]"))) for row in rows}
    return CaseFacts(
        raws,
        {key: tuple(value) for key, value in grouped.items()},
        episodes,
    )


def _member_verified(
    member: Mapping[str, Any],
    facts: CaseFacts,
    notables: Mapping[str, Mapping[str, Any]],
) -> tuple[bool, str]:
    """A member is a lead only when its stored evidence holds it; otherwise it is unverified."""
    value = str(member.get("value") or "").casefold()
    kind = str(member.get("type") or "")
    if len(value) < 2:
        return False, "value_too_short"
    if kind == "episode":
        ids = facts.episodes.get(str(member.get("id") or ""))
        if ids is None:
            return False, "episode_missing"
        resolved = [item for item in ids if item in facts.raws]
        if not resolved:
            return False, "no_resolved_event"
        if any(value in facts.raws[item][0] for item in resolved):
            return True, "value_in_raw"
        return False, "value_absent"
    if kind == "signal":
        notable = notables.get(str(member.get("notable_id") or ""))
        if notable is None:
            return False, "notable_missing"
        rows = facts.by_source.get(_tail(str(member.get("source_id") or "")), ())
        for item in notable.get("evidence") or ():
            line = str(item.get("line") or "").casefold() if isinstance(item, Mapping) else ""
            if line and any(raw.startswith(line) and value in raw for raw, _ in rows):
                return True, "notable_line"
        return False, "evidence_not_resolved"
    if kind == "flow":
        endpoints = [str(item) for item in member.get("endpoints") or ()]
        groups = [facts.by_source.get(_tail(item), ()) for item in endpoints]
        groups = groups or [tuple(facts.raws.values())]
        if all(any(value in raw for raw, _ in group) for group in groups):
            return True, "flow_value_in_raw"
        return False, "flow_value_absent"
    return False, "unknown_kind"


def verify_case(
    case: Mapping[str, Any],
    facts: CaseFacts,
    notables: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Check every member deterministically; the anchor's result is the case's result."""
    members: list[dict[str, Any]] = []
    for member in case.get("members") or ():
        item = dict(member) if isinstance(member, Mapping) else {}
        ok, reason = _member_verified(item, facts, notables)
        if not ok:
            item["unverified"] = True
            item["verify_reason"] = reason
        members.append(item)
    anchor = members[0] if members else {}
    verified = bool(anchor) and not anchor.get("unverified")
    out = {**case, "members": members, "verified": verified}
    out["verification"] = "verified" if verified else "unverified"
    if not verified:
        out["verify_reason"] = str(anchor.get("verify_reason") or "no_anchor")
    return out


def _iso(seconds: Any) -> str:
    try:
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(float(seconds)))
    except (TypeError, ValueError):
        return ""


def _case_member_lines(case: Mapping[str, Any]) -> list[str]:
    lines = []
    for member in case.get("members") or ():
        if not isinstance(member, Mapping):
            continue
        where = " ".join(
            part
            for part in (str(member.get("source_id") or ""), str(member.get("host") or ""))
            if part
        )
        lines.append(
            f"- {member.get('type')} {member.get('value')}" + (f" [{where}]" if where else "")
        )
        if len(lines) >= CASE_MAX_MEMBERS:
            break
    return lines


def _case_timeline_lines(case: Mapping[str, Any]) -> list[str]:
    lines = []
    for step in case.get("timeline") or ():
        if not isinstance(step, Mapping):
            continue
        lines.append(f"- {step.get('type')} {step.get('value')} @ {_iso(step.get('start'))}")
        if len(lines) >= CASE_MAX_TIMELINE:
            break
    return lines


def _case_evidence_lines(case: Mapping[str, Any]) -> list[str]:
    lines = []
    for item in case.get("evidence") or ():
        if isinstance(item, Mapping) and item.get("line"):
            lines.append(f"- {str(item['line'])[:JUDGE_EVIDENCE_CHARS]}")
        if len(lines) >= CASE_MAX_EVIDENCE:
            break
    return lines


def case_body(case: Mapping[str, Any]) -> str:
    """The anchor, the linked members, a bounded timeline and a few evidence rows."""
    members = _case_member_lines(case)
    timeline = _case_timeline_lines(case)
    evidence = _case_evidence_lines(case)
    return "\n".join(
        part
        for part in (
            f"anchor: {case.get('anchor_entity')}  why: {case.get('why')}",
            f"window: {_iso(case.get('start'))} .. {_iso(case.get('end'))}  "
            f"evidence pieces: {case.get('pieces')}  sources: {len(case.get('sources') or ())}",
            "evidence:",
            *evidence,
            "members:",
            *members,
            "timeline:",
            *timeline,
        )
        if part
    )


def case_prompt(case: Mapping[str, Any], *, explain: bool = False) -> str:
    """One compact prompt per case, inside the seat's context."""
    instruction = (
        "Answer yes or no first, followed by a short reason in 12 words or fewer."
        if explain
        else "Answer with one word: yes or no."
    )
    return (CASE_QUESTION + "\n" + instruction + "\n\nCASE:\n" + case_body(case))[
        :CASE_PROMPT_CHARS
    ]


def _case_cached(
    case: Mapping[str, Any], cache: JudgeCache, *, explain: bool = False
) -> Judged | None:
    key = str(case.get("case_id") or "")
    stored = cache.get(key)
    if stored is None or stored.get("p_yes") is None or stored.get("v") != CASE_CACHE_VERSION:
        return None
    if explain and stored.get("explain") is not True:
        return None
    return Judged(
        key,
        _float_or_none(stored.get("p_yes")),
        str(stored.get("served_model") or ""),
        float(stored.get("seconds") or 0.0),
        None,
        None,
        True,
        str(stored.get("answer") or ""),
        stored.get("decision_index"),
    )


def _judge_case_one(
    case: Mapping[str, Any],
    client: JudgeClient,
    model: str,
    cache: JudgeCache,
    *,
    explain: bool = False,
) -> Judged:
    key = str(case.get("case_id") or "")
    result = judge_cell(
        client,
        model=model,
        prompt=case_prompt(case, explain=explain),
        max_tokens=JUDGE_REASON_TOKENS if explain else JUDGE_ANSWER_TOKENS,
    )
    if result.p_yes is not None:
        cache.put(
            key,
            {
                "v": CASE_CACHE_VERSION,
                "p_yes": result.p_yes,
                "served_model": result.served_model,
                "seconds": result.seconds,
                "prompt_tokens": result.prompt_tokens,
                "answer": result.answer,
                "decision_index": result.decision_index,
                "explain": explain,
            },
        )
    return _verdict(key, result, False)


def _judge_case_batch(
    indices: Sequence[int],
    cases: Sequence[Mapping[str, Any]],
    asker: JudgeClient,
    model: str,
    cache: JudgeCache,
    results: list[Judged | None],
    *,
    explain: bool = False,
) -> None:
    if not indices:
        return
    with ThreadPoolExecutor(max_workers=JUDGE_CONCURRENCY) as pool:
        futures = {
            pool.submit(_judge_case_one, cases[index], asker, model, cache, explain=explain): index
            for index in indices
        }
        for future in as_completed(futures):
            results[futures[future]] = future.result()


def _case_measured_budget(
    pending: Sequence[int],
    cases: Sequence[Mapping[str, Any]],
    asker: JudgeClient,
    model: str,
    cache: JudgeCache,
    results: list[Judged | None],
    deadline_seconds: float,
    probe_calls: int,
    *,
    explain: bool = False,
) -> tuple[int, dict[str, Any]]:
    def run_probe(count: int) -> None:
        _judge_case_batch(pending[:count], cases, asker, model, cache, results, explain=explain)

    return _rate_budget(len(pending), probe_calls, run_probe, deadline_seconds)


def _notable_index(out: Path) -> dict[str, Mapping[str, Any]]:
    path = out / "notables.jsonl"
    index: dict[str, Mapping[str, Any]] = {}
    if not path.is_file():
        return index
    for line in path.read_text().splitlines():
        if line.strip():
            row = json.loads(line)
            if isinstance(row, dict) and row.get("notable_id"):
                index[str(row["notable_id"])] = row
    return index


def _judge_receipt(
    checked: Sequence[Mapping[str, Any]],
    results: Sequence[Judged],
    *,
    began: float,
    requests: int,
    model_seconds: float,
    served: set[str],
    budget: int,
    basis: Mapping[str, Any],
    unasked: int,
    cache_path: Path,
    asker: BackpressureClient | None,
) -> dict[str, Any]:
    reasons: dict[str, int] = {}
    for result in results:
        if result.p_yes is None:
            reasons[str(result.reason or "unjudged")] = (
                reasons.get(str(result.reason or "unjudged"), 0) + 1
            )
    anchor_reasons: dict[str, int] = {}
    for case in checked:
        if not case.get("verified"):
            key = str(case.get("verify_reason") or "no_anchor")
            anchor_reasons[key] = anchor_reasons.get(key, 0) + 1
    return {
        "cases": len(checked),
        "verified": sum(1 for case in checked if case.get("verified")),
        "unverified": sum(1 for case in checked if not case.get("verified")),
        "unverified_anchors": anchor_reasons,
        "unverified_members": sum(
            1
            for case in checked
            for member in case.get("members") or ()
            if member.get("unverified")
        ),
        "judged": sum(1 for result in results if result.p_yes is not None),
        "unjudged": sum(1 for result in results if result.p_yes is None),
        "unjudged_reasons": reasons,
        "requests": requests,
        "cached": sum(1 for result in results if result.cached),
        "seconds": round(time.monotonic() - began, 3),
        "model_seconds": round(model_seconds, 3),
        "served_models": sorted(served),
        "request_budget": budget,
        "budget_basis": dict(basis),
        "unasked": unasked,
        "cache": str(cache_path),
        "backpressure": asker.stats() if asker is not None else {},
    }


def _case_budget(
    pending: Sequence[int],
    checked: Sequence[Mapping[str, Any]],
    asker: BackpressureClient | None,
    model: str,
    cache: JudgeCache,
    results: list[Judged | None],
    request_budget: int | None,
    deadline_seconds: float,
    probe_calls: int,
    *,
    explain: bool,
) -> tuple[int, dict[str, Any]]:
    """Explicit budget wins; otherwise size it from the probe's measured rate."""
    if request_budget is not None:
        budget = max(0, request_budget)
        return budget, {"source": "explicit", "derived_budget": budget}
    if not pending or asker is None:
        return 0, {
            "source": "no_model" if asker is None else "measured_rate",
            "probe_calls": 0,
            "probe_seconds": 0.0,
            "seconds_per_call": None,
            "deadline_seconds": deadline_seconds,
            "derived_budget": 0,
        }
    return _case_measured_budget(
        pending,
        checked,
        asker,
        model,
        cache,
        results,
        deadline_seconds,
        probe_calls,
        explain=explain,
    )


def judge_cases(
    cases: Sequence[Mapping[str, Any]],
    *,
    out: Path,
    client: JudgeClient | None,
    model: str,
    cache_path: Path | None = None,
    notables: Mapping[str, Mapping[str, Any]] | None = None,
    facts: CaseFacts | None = None,
    request_budget: int | None = None,
    deadline_seconds: float = MODEL_WORK_SECONDS,
    probe_calls: int = JUDGE_PROBE_CALLS,
    explain: bool = False,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Verify first, then one model call per verified case; no case is ever dropped."""
    began = time.monotonic()
    known = facts if facts is not None else load_case_facts(out)
    index = dict(notables) if notables is not None else _notable_index(out)
    checked = [verify_case(case, known, index) for case in cases]
    path = cache_path if cache_path is not None else out / "cache" / "judge_cases.json"
    cache = JudgeCache(path)
    results: list[Judged | None] = [None] * len(checked)
    pending: list[int] = []
    for position, case in enumerate(checked):
        key = str(case.get("case_id") or "")
        if not case.get("verified"):
            results[position] = Judged(key, None, "", 0.0, None, CASE_UNVERIFIED_ANCHOR, False)
            continue
        found = _case_cached(case, cache, explain=explain)
        if found is not None:
            results[position] = found
        else:
            pending.append(position)
    asker = (
        client
        if isinstance(client, BackpressureClient)
        else (BackpressureClient(client, budget_seconds=deadline_seconds) if client else None)
    )
    budget, basis = _case_budget(
        pending,
        checked,
        asker,
        model,
        cache,
        results,
        request_budget,
        deadline_seconds,
        probe_calls,
        explain=explain,
    )
    if asker is None:
        budget = 0
    ask = [position for position in pending[:budget] if results[position] is None]
    unasked = pending[budget:]
    if asker is not None:
        _judge_case_batch(ask, checked, asker, model, cache, results, explain=explain)
    for position in unasked:
        key = str(checked[position].get("case_id") or "")
        results[position] = Judged(key, None, "", 0.0, None, "case_budget_exhausted", False)
    cache.save()
    judged = [result for result in results if result is not None]
    out_cases: list[dict[str, Any]] = []
    requests = 0
    model_seconds = 0.0
    served: set[str] = set()
    for case, result in zip(checked, judged, strict=True):
        item = dict(case)
        item["p_yes"] = result.p_yes
        item["judge"] = {
            "served_model": result.served_model,
            "seconds": result.seconds,
            "prompt_tokens": result.prompt_tokens,
            "reason": result.reason,
            "cached": result.cached,
            "answer": result.answer,
            "decision_index": result.decision_index,
        }
        out_cases.append(item)
        if not result.cached and result.reason not in (
            "model_budget_exhausted",
            "case_budget_exhausted",
            CASE_UNVERIFIED_ANCHOR,
        ):
            requests += 1
            model_seconds += result.seconds
        if result.served_model:
            served.add(result.served_model)
    receipt = _judge_receipt(
        checked,
        judged,
        began=began,
        requests=requests,
        model_seconds=model_seconds,
        served=served,
        budget=budget,
        basis=basis,
        unasked=len(unasked),
        cache_path=path,
        asker=asker,
    )
    return out_cases, receipt
