#!/usr/bin/env python3
"""Swap-sequence UAT: ping-pong, size ladder, the 2026-10-22 order, a concurrent pair, pinned vs long."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx

from portal.platform.inference.cluster_backends import BackendRegistry
from portal.platform.inference.config import load_portal_config
from scripts import host_quiet
from scripts.uat_engines import (
    ONE_WORD,
    answer_text,
    chat_payload,
    make_client,
    pipeline_base,
    post_json,
    route_engine,
    route_model,
    select_shots,
)

#: The sequence that produced three HTTP 502s on 2026-10-22; replayed in this exact order.
INCIDENT_20261022 = (
    "auto-coding::cad",
    "auto-coding::devstral_coder",
    "auto-coding::fast-repair",
    "auto-coding::gemma4-heretic-coder",
    "auto-coding::glm-coder",
)
ENGINES = ("omlx", "ollama")
SEQUENCE_NAMES = ("ping-pong", "ladder", "incident", "concurrent", "pinned")
LONG_PROMPT = (
    "Write a detailed 600-word technical explanation of how unified memory pressure "
    "affects model loading on Apple Silicon. Do not stop early and do not use bullets."
)
_PARAMS = re.compile(r"(?<![A-Za-z0-9_.])(\d+(?:\.\d+)?)\s*[bB](?![A-Za-z0-9_])")
_QUANT = (
    re.compile(r"q(\d+)(?=[^0-9]|$)", re.IGNORECASE),
    re.compile(r"(\d+)\s*bit", re.IGNORECASE),
    re.compile(r"(?:nv|mx)fp(\d+)", re.IGNORECASE),
    re.compile(r"\bfp(\d+)\b", re.IGNORECASE),
)
_NO_WAIT = "with nothing in flight to wait for"
_WAITED = (
    "after waiting",
    "would exceed its wait for another model load",
    "transition still active after waiting",
)


@dataclass(frozen=True)
class Seat:
    """One served workspace id and the model it resolves to on its routed backend."""

    id: str
    engine: str
    backend: str
    model: str
    hint: str
    size_b: float
    quant_bits: float
    context_limit: int
    size_gib: float | None = None
    size_source: str = "estimated"

    @property
    def estimate_gib(self) -> float:
        """Rough weights size from the id's parameter count and quant bits; not measured."""
        return self.size_b * 1e9 * self.quant_bits / 8 / 1024**3

    @property
    def rank_gib(self) -> float:
        """The guard's projected footprint when the Pipeline answered, else the estimate."""
        return self.size_gib if self.size_gib is not None else self.estimate_gib


@dataclass(frozen=True)
class Step:
    workspace_id: str
    seat: Seat | None
    note: str = ""


@dataclass
class Sequence:
    name: str
    mode: str
    steps: list[Step] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Catalog:
    seats: list[Seat]
    unresolved: list[str]
    skipped: list[str]
    stack_down: list[str]
    pinned_id: str | None
    pinned_note: str
    extra: tuple[str, ...]


def _param_count(text: str) -> float:
    counts = [float(match.group(1)) for match in _PARAMS.finditer(text)]
    return max(counts) if counts else 0.0


def _quant_bits(text: str) -> float:
    if re.search(r"bf16", text, re.IGNORECASE):
        return 16.0
    for pattern in _QUANT:
        match = pattern.search(text)
        if match:
            return float(match.group(1))
    return 4.0


def _variant_overrides(spec: Any, name: str) -> dict[str, Any]:
    if not name:
        return {}
    override = spec.variants.get(name) or {}
    return override if isinstance(override, dict) else {}


def resolve_seat(workspace_id: str, config: Any, registry: BackendRegistry) -> Seat | None:
    """Resolve a served id to (engine, native model), using production routing order."""
    base, _sep, name = workspace_id.partition("::")
    spec = config.workspaces.get(base)
    if spec is None:
        return None
    override = _variant_overrides(spec, name)
    hint = str(override.get("model_hint") or spec.model_hint or "")
    if not hint:
        return None
    for backend in registry.get_backend_candidates(workspace_id):
        model = backend.resolve_model(hint)
        if model:
            return Seat(
                id=workspace_id,
                engine=backend.type,
                backend=backend.id,
                model=model,
                hint=hint,
                size_b=_param_count(model) or _param_count(hint),
                quant_bits=_quant_bits(model) or _quant_bits(hint),
                context_limit=int(override.get("context_limit") or spec.context_limit or 0),
            )
    return None


def derive_seats(
    config: Any, extra_ids: tuple[str, ...] = ()
) -> tuple[list[Seat], list[str], list[str], list[str]]:
    """The served catalog as seats, plus any explicit extra ids; unresolved ids and skip classes."""
    run, skipped, stack_down = select_shots(config)
    registry = BackendRegistry()
    seats: list[Seat] = []
    unresolved: list[str] = []
    for workspace_id in list(run) + [wid for wid in extra_ids if wid not in run]:
        seat = resolve_seat(workspace_id, config, registry)
        if seat is None:
            unresolved.append(workspace_id)
        else:
            seats.append(seat)
    return seats, unresolved, skipped, stack_down


def _pipeline_key() -> str:
    return (
        os.environ.get("PIPELINE_API_KEY", "").strip()
        or host_quiet._env_value("PIPELINE_API_KEY", "").strip()
    )


def _projected_gib(row: dict[str, Any]) -> float:
    for key in ("projected_gib", "adds_gib"):
        value = row.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0:
            return float(value)
    return 0.0


def apply_plan_sizes(seats: list[Seat], base: str, key: str) -> tuple[list[Seat], str]:
    """Ask the Pipeline guard for each model's projected footprint; estimate what it cannot see."""
    if not seats:
        return seats, "sizes: no seats"
    if not key:
        return seats, "sizes estimated: PIPELINE_API_KEY is not set"
    payload = {
        "models": [
            {"engine": engine, "model": model}
            for engine, model in sorted({(seat.engine, seat.model) for seat in seats})
        ]
    }
    try:
        data = host_quiet._json_request(
            f"{base.rstrip('/')}/admin/load-plan", method="POST", api_key=key, payload=payload
        )
    except (OSError, ValueError, TimeoutError) as exc:
        return seats, f"sizes estimated: load-plan unavailable ({type(exc).__name__})"
    rows = data.get("models") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        return seats, "sizes estimated: load-plan returned no per-model projections"
    by_model = {
        (str(row.get("engine")), str(row.get("model"))): row
        for row in rows
        if isinstance(row, dict)
    }
    sized = 0
    out: list[Seat] = []
    for seat in seats:
        projection = _projected_gib(by_model.get((seat.engine, seat.model), {}))
        if projection > 0:
            sized += 1
            out.append(replace(seat, size_gib=projection, size_source="load-plan"))
        else:
            out.append(seat)
    source = (
        "guard projection"
        if sized == len(seats)
        else "guard projection where visible, estimate elsewhere"
    )
    return out, f"sizes: {sized}/{len(seats)} from the load-plan ({source})"


def _sized(seats: list[Seat], engine: str = "") -> list[Seat]:
    return [s for s in seats if s.rank_gib > 0 and (not engine or s.engine == engine)]


def unique_models(seats: list[Seat]) -> list[Seat]:
    """One seat per (engine, native model), preferring the widest context."""
    seen: set[tuple[str, str]] = set()
    kept: list[Seat] = []
    for seat in sorted(seats, key=lambda s: (-s.context_limit, s.id)):
        key = (seat.engine, seat.model)
        if key not in seen:
            seen.add(key)
            kept.append(seat)
    return kept


def largest_by_engine(seats: list[Seat]) -> dict[str, Seat]:
    found: dict[str, Seat] = {}
    for engine in ENGINES:
        pool = _sized(seats, engine)
        if pool:
            found[engine] = max(pool, key=lambda s: (s.rank_gib, s.context_limit, s.id))
    return found


def ladder_engine(seats: list[Seat]) -> str:
    counts = {engine: len(_sized(unique_models(seats), engine)) for engine in ENGINES}
    if not any(counts.values()):
        return ""
    return max(ENGINES, key=lambda engine: (counts[engine], engine == "ollama"))


def ping_pong_sequence(seats: list[Seat], cycles: int) -> tuple[list[Step], list[str]]:
    picks = largest_by_engine(seats)
    notes = [f"{engine}: no sized seat" for engine in ENGINES if engine not in picks]
    order = [picks[engine] for engine in ENGINES if engine in picks]
    steps = [Step(seat.id, seat) for _ in range(max(1, cycles)) for seat in order]
    return steps, notes


def ladder_sequence(seats: list[Seat], size: int) -> tuple[list[Step], list[str]]:
    engine = ladder_engine(seats)
    if not engine:
        return [], ["no engine has a sized seat"]
    pool = sorted(
        _sized(unique_models(seats), engine),
        key=lambda s: (s.rank_gib, s.context_limit, s.id),
    )
    if len(pool) < 2:
        return [], [f"{engine}: fewer than two sized seats"]
    edge = max(1, size)
    ascending = pool[:edge]
    descending = list(reversed(pool[-edge:]))
    if ascending and descending and descending[0].id == ascending[-1].id:
        descending = descending[1:]
    chosen = ascending + descending
    return [Step(seat.id, seat) for seat in chosen], []


def incident_sequence(by_id: dict[str, Seat]) -> tuple[list[Step], list[str]]:
    steps: list[Step] = []
    notes: list[str] = []
    for workspace_id in INCIDENT_20261022:
        seat = by_id.get(workspace_id)
        if seat is None:
            notes.append(f"{workspace_id}: not in the served catalog")
        steps.append(Step(workspace_id, seat, "" if seat else "unresolved"))
    return steps, notes


def concurrent_sequence(seats: list[Seat]) -> tuple[list[Step], list[str]]:
    picks = largest_by_engine(seats)
    notes = [f"{engine}: no sized seat" for engine in ENGINES if engine not in picks]
    if len(picks) < 2:
        notes.append("fewer than two engines have a sized seat; no concurrent pair")
    steps = [Step(picks[engine].id, picks[engine]) for engine in ENGINES if engine in picks]
    return steps, notes


def _router_model() -> str:
    return os.environ.get("LLM_ROUTER_MODEL", "") or host_quiet._env_value("LLM_ROUTER_MODEL", "")


def config_pinned_workspace(config: Any) -> tuple[str | None, str]:
    """The config workspace that pins the guard's router model — the seat the guard protects."""
    router = _router_model()
    if router:
        for workspace_id, spec in config.workspaces.items():
            if str(spec.model_hint or "") == router:
                return workspace_id, f"{workspace_id} model_hint pins the guard's router model"
            for name, override in spec.variants.items():
                if isinstance(override, dict) and str(override.get("model_hint") or "") == router:
                    return (
                        f"{workspace_id}::{name}",
                        f"variant {name} model_hint pins the guard's router model",
                    )
    if "task-router" in config.workspaces:
        return "task-router", "task-router is the config's pinned router seat"
    return None, f"no workspace model_hint pins LLM_ROUTER_MODEL={router or '(unset)'}"


def pinned_sequence(
    seats: list[Seat], pinned_id: str | None, note: str = ""
) -> tuple[list[Step], list[str]]:
    """The pinned seat plus a long-generation request that holds the other engine."""
    by_id = {seat.id: seat for seat in seats}
    if pinned_id is None:
        return [], [note or "no config seat pins a model"]
    pinned = by_id.get(pinned_id)
    if pinned is None:
        reason = f"{pinned_id} is not in the config catalog"
        return [], [f"{reason} ({note})" if note else reason]
    others = [seat for seat in _sized(seats) if seat.engine != pinned.engine]
    if not others:
        return [Step(pinned.id, pinned)], [f"no sized seat on an engine other than {pinned.engine}"]
    long_seat = max(others, key=lambda s: (s.rank_gib, s.context_limit, s.id))
    return [Step(long_seat.id, long_seat), Step(pinned.id, pinned)], []


def build_sequences(
    requested: list[str] | None,
    seats: list[Seat],
    cycles: int,
    ladder_size: int,
    pinned_id: str | None,
    pinned_note: str = "",
    extra_ids: tuple[str, ...] = (),
) -> list[Sequence]:
    catalog = [seat for seat in seats if seat.id not in extra_ids]
    by_id = {seat.id: seat for seat in catalog}
    wanted = requested or list(SEQUENCE_NAMES)
    built: list[Sequence] = []
    for name in SEQUENCE_NAMES:
        if name not in wanted:
            continue
        if name == "ping-pong":
            steps, notes = ping_pong_sequence(catalog, cycles)
            built.append(Sequence(name, "sequential", steps, notes))
        elif name == "ladder":
            steps, notes = ladder_sequence(catalog, ladder_size)
            built.append(Sequence(name, "sequential", steps, notes))
        elif name == "incident":
            steps, notes = incident_sequence(by_id)
            built.append(Sequence(name, "sequential", steps, notes))
        elif name == "concurrent":
            steps, notes = concurrent_sequence(catalog)
            built.append(Sequence(name, "concurrent", steps, notes))
        else:
            steps, notes = pinned_sequence(seats, pinned_id, pinned_note)
            built.append(Sequence(name, "pinned", steps, notes))
    return built


def _payload(model: str, content: str, max_tokens: int | None) -> dict[str, Any]:
    payload = chat_payload(model, content, stream=False)
    if max_tokens:
        payload["max_tokens"] = max_tokens
    return payload


def refusal_excused(lines: list[str], model: str = "") -> tuple[bool, str]:
    """True when a guard line for this model proves in-flight work blocked the free."""
    for line in lines:
        if model and f"Cannot load {model}" not in line and f"cold load of {model}" not in line:
            continue
        if _NO_WAIT in line:
            continue
        if any(marker in line for marker in _WAITED):
            return True, line
    return False, ""


def _detail(payload: dict[str, Any]) -> str:
    error = payload.get("error")
    if isinstance(error, str):
        return error
    if isinstance(error, dict):
        return str(error.get("message") or "")
    detail = payload.get("detail")
    return detail if isinstance(detail, str) else ""


def judge_step(
    status: int,
    route: str,
    answered: bool,
    error: str | None,
    expected_model: str,
    guard_lines: list[str],
    detail: str = "",
    *,
    require_answer: bool = True,
) -> dict[str, Any]:
    if error:
        return {"ok": False, "reason": error, "refusal_excused": False, "guard_evidence": ""}
    served = route_model(route)
    if status == 200:
        if require_answer and not answered:
            return {
                "ok": False,
                "reason": "HTTP 200 with an empty answer",
                "refusal_excused": False,
                "guard_evidence": "",
            }
        if served != expected_model:
            reason = f"served {served or '(none)'} != expected {expected_model}"
            return {"ok": False, "reason": reason, "refusal_excused": False, "guard_evidence": ""}
        return {"ok": True, "reason": "", "refusal_excused": False, "guard_evidence": ""}
    evidence_lines = list(guard_lines)
    if detail:
        evidence_lines.append(detail)
    excused, evidence = refusal_excused(evidence_lines, expected_model)
    if excused:
        reason = f"HTTP {status}; refusal excused: {evidence}"
        return {"ok": True, "reason": reason, "refusal_excused": True, "guard_evidence": evidence}
    return {"ok": False, "reason": f"HTTP {status}", "refusal_excused": False, "guard_evidence": ""}


def capture_guard_logs(
    container: str, started: datetime, ended: datetime
) -> tuple[list[str], str | None]:
    """Read the pipeline's load_guard lines for one step's window (docker logs is read-only)."""
    since = (started - timedelta(seconds=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    until = (ended + timedelta(seconds=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
    command = ["docker", "logs", container, "--timestamps", "--since", since, "--until", until]
    try:
        done = subprocess.run(command, capture_output=True, text=True, check=False, timeout=30)
    except (OSError, subprocess.SubprocessError) as exc:
        return [], f"{type(exc).__name__}: {exc}"
    if done.returncode:
        return [], f"docker logs exited {done.returncode}: {done.stderr.strip()[:200]}"
    lines = [
        line.strip() for line in (done.stdout + done.stderr).splitlines() if "load_guard" in line
    ]
    return lines[-12:], None


def _base_record(step: Step, sequence: str, index: int) -> dict[str, Any]:
    seat = step.seat
    return {
        "sequence": sequence,
        "index": index,
        "workspace_id": step.workspace_id,
        "engine": seat.engine if seat else "",
        "backend": seat.backend if seat else "",
        "expected_model": seat.model if seat else "",
        "size_b": seat.size_b if seat else 0.0,
        "size_gib": round(seat.rank_gib, 1) if seat else 0.0,
        "size_source": seat.size_source if seat else "",
        "context_limit": seat.context_limit if seat else 0,
        "note": step.note,
    }


def fire_step(
    client: httpx.Client,
    base: str,
    key: str,
    step: Step,
    sequence: str,
    index: int,
    *,
    container: str = "",
    prompt: str = ONE_WORD,
    max_tokens: int | None = None,
    require_answer: bool = True,
) -> dict[str, Any]:
    record = _base_record(step, sequence, index)
    if step.seat is None:
        record.update(
            http_status=0,
            route="",
            route_model="",
            route_engine="",
            seconds=0.0,
            answered=False,
            answer_excerpt="",
            correlation_id="",
            ok=False,
            refusal_excused=False,
            guard_evidence="",
            guard_log_lines=[],
            guard_error="",
            error_detail="",
            pressure=not require_answer,
            reason=step.note or "seat unresolved from config",
        )
        return record
    cid = f"p5-swap-{uuid.uuid4().hex[:12]}"
    started_wall = datetime.now(UTC)
    started = time.monotonic()
    status, payload, route, seen, error = post_json(
        client,
        f"{base}/v1/chat/completions",
        key,
        _payload(step.seat.id, prompt, max_tokens),
        cid,
    )
    seconds = round(time.monotonic() - started, 1)
    ended_wall = datetime.now(UTC)
    text = answer_text(payload)
    guard_lines, guard_error = (
        capture_guard_logs(container, started_wall, ended_wall) if container else ([], "disabled")
    )
    verdict = judge_step(
        status,
        route,
        bool(text),
        error,
        step.seat.model,
        guard_lines,
        _detail(payload),
        require_answer=require_answer,
    )
    record.update(
        http_status=status,
        route=route,
        route_model=route_model(route),
        route_engine=route_engine(route),
        seconds=seconds,
        answered=bool(text),
        answer_excerpt=text[:60],
        error_detail=_detail(payload)[:500],
        pressure=not require_answer,
        correlation_id=seen,
        guard_log_lines=guard_lines,
        guard_error=guard_error or "",
        **verdict,
    )
    return record


def _note(line: str) -> None:
    print(line, file=sys.stderr)


def _verdict_label(record: dict[str, Any]) -> str:
    if record.get("ok") and record.get("refusal_excused"):
        return "PASS (refused; guard waited)"
    if record.get("ok") and record.get("pressure"):
        return "PASS (pressure request)"
    return "PASS" if record.get("ok") else "FAIL"


def run_sequential(
    client: httpx.Client, base: str, key: str, sequence: Sequence, container: str
) -> list[dict[str, Any]]:
    records = []
    for index, step in enumerate(sequence.steps, 1):
        record = fire_step(client, base, key, step, sequence.name, index, container=container)
        records.append(record)
        _note(
            f"{sequence.name} {index}/{len(sequence.steps)} {step.workspace_id} "
            f"{record['http_status']} {record['seconds']}s {_verdict_label(record)}"
        )
    return records


def run_concurrent(
    client: httpx.Client, base: str, key: str, sequence: Sequence, container: str
) -> list[dict[str, Any]]:
    with ThreadPoolExecutor(max_workers=max(1, len(sequence.steps))) as pool:
        futures = [
            pool.submit(
                fire_step, client, base, key, step, sequence.name, index, container=container
            )
            for index, step in enumerate(sequence.steps, 1)
        ]
        records = []
        for index, (step, future) in enumerate(zip(sequence.steps, futures, strict=True), 1):
            record = future.result()
            record["concurrent_with"] = [
                other.workspace_id for other in sequence.steps if other is not step
            ]
            records.append(record)
            _note(
                f"{sequence.name} {index}/{len(sequence.steps)} {step.workspace_id} "
                f"{record['http_status']} {record['seconds']}s {_verdict_label(record)}"
            )
    return records


def run_pinned(
    client: httpx.Client,
    base: str,
    key: str,
    sequence: Sequence,
    container: str,
    *,
    lead_s: float,
    max_tokens: int,
) -> list[dict[str, Any]]:
    if len(sequence.steps) < 2:
        return []
    long_step, pinned_step = sequence.steps[0], sequence.steps[1]
    with ThreadPoolExecutor(max_workers=1) as pool:
        long_future = pool.submit(
            fire_step,
            client,
            base,
            key,
            long_step,
            sequence.name,
            1,
            container=container,
            prompt=LONG_PROMPT,
            max_tokens=max_tokens,
            require_answer=False,
        )
        time.sleep(max(0.0, lead_s))
        in_flight = long_future.running()
        pinned = fire_step(client, base, key, pinned_step, sequence.name, 2, container=container)
        long_record = long_future.result()
    long_record["concurrent_with"] = [pinned_step.workspace_id]
    long_record["long_request_in_flight_at_pin"] = in_flight
    pinned["concurrent_with"] = [long_step.workspace_id]
    pinned["long_request_in_flight_at_pin"] = in_flight
    pinned["lead_seconds"] = lead_s
    for record in (long_record, pinned):
        _note(
            f"{sequence.name} {record['index']}/2 {record['workspace_id']} "
            f"{record['http_status']} {record['seconds']}s {_verdict_label(record)}"
        )
    return [long_record, pinned]


def run_sequence(
    client: httpx.Client,
    base: str,
    key: str,
    sequence: Sequence,
    container: str,
    *,
    lead_s: float,
    long_max_tokens: int,
) -> list[dict[str, Any]]:
    if not sequence.steps:
        return []
    if sequence.mode == "concurrent":
        return run_concurrent(client, base, key, sequence, container)
    if sequence.mode == "pinned":
        return run_pinned(
            client, base, key, sequence, container, lead_s=lead_s, max_tokens=long_max_tokens
        )
    return run_sequential(client, base, key, sequence, container)


def render_plan(
    seats: list[Seat],
    sequences: list[Sequence],
    unresolved: list[str],
    skipped: list[str],
    stack_down: list[str],
    size_note: str,
) -> str:
    lines = [
        "SWAP UAT PLAN — dry run, no inference requests",
        (
            f"catalog: {len(seats)} served seats resolved, {len(_sized(seats))} sized, "
            f"{len(unresolved)} unresolved, {len(skipped)} skipped (owned elsewhere), "
            f"{len(stack_down)} stack-down only"
        ),
        size_note,
    ]
    if unresolved:
        lines.append("unresolved: " + ", ".join(unresolved))
    unsized = sorted(
        {
            step.seat.id
            for sequence in sequences
            for step in sequence.steps
            if step.seat and step.seat.rank_gib <= 0
        }
    )
    if unsized:
        lines.append("size n/a (excluded from ping-pong/ladder picks): " + ", ".join(unsized))
    for sequence in sequences:
        lines.extend(["", f"sequence {sequence.name} ({len(sequence.steps)} steps)"])
        for index, step in enumerate(sequence.steps, 1):
            if step.seat is None:
                lines.append(f"  {index}. {step.workspace_id} — UNRESOLVED ({step.note})")
                continue
            seat = step.seat
            size = (
                f"~{seat.rank_gib:.1f} GiB ({seat.size_source})"
                if seat.rank_gib > 0
                else "size n/a"
            )
            lines.append(
                f"  {index}. {seat.id}  {seat.engine}  {seat.model}  "
                f"{size}  ctx {seat.context_limit}"
            )
        for note in sequence.notes:
            lines.append(f"  note: {note}")
        if not sequence.steps:
            lines.append("  SKIP")
    return "\n".join(lines) + "\n"


def _summary_table(report: dict[str, Any]) -> list[str]:
    lines = [
        "| sequence | # | seat | engine | ~GiB | HTTP | served model | seconds | verdict |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for sequence in report["sequences"]:
        if not sequence["steps"]:
            lines.append(f"| {sequence['name']} | - | SKIP | - | - | - | - | - | SKIP |")
            for note in sequence["notes"]:
                lines.append(f"| {sequence['name']} | - | note: {note} | - | - | - | - | - | - |")
            continue
        for record in sequence["steps"]:
            size = f"{record['size_gib']:.1f}" if record.get("size_gib") else "n/a"
            lines.append(
                f"| {sequence['name']} | {record['index']} | {record['workspace_id']} | "
                f"{record.get('route_engine') or record['engine']} | {size} | "
                f"{record['http_status']} | {record.get('route_model') or '(none)'} | "
                f"{record['seconds']:.1f} | {_verdict_label(record)} |"
            )
    return lines


def _evidence_lines(report: dict[str, Any]) -> list[str]:
    evidence = [
        (record, sequence["name"])
        for sequence in report["sequences"]
        for record in sequence["steps"]
        if record.get("guard_log_lines") or (not record.get("ok") and record.get("error_detail"))
    ]
    if not evidence:
        return []
    lines = ["", "## Guard evidence"]
    for record, name in evidence:
        for line in record["guard_log_lines"]:
            lines.append(f"- {name} #{record['index']} {record['workspace_id']}: {line}")
        if not record.get("ok") and record.get("error_detail"):
            lines.append(
                f"- {name} #{record['index']} {record['workspace_id']} "
                f"body: {record['error_detail']}"
            )
    return lines


def _totals_lines(report: dict[str, Any]) -> list[str]:
    totals = report["totals"]
    lines = [
        "",
        "## Totals",
        (
            f"- steps: {totals['pass']} pass ({totals['excused']} excused refusals), "
            f"{totals['fail']} fail, {totals['skip']} skip"
        ),
    ]
    lines.extend(f"- note: {note}" for note in report.get("notes", []))
    catalog = report.get("catalog") or {}
    if catalog.get("size_note"):
        lines.append(f"- {catalog['size_note']}")
    if catalog.get("pinned_seat"):
        lines.append(
            f"- pinned seat: {catalog['pinned_seat']} ({catalog.get('pinned_seat_source', '')})"
        )
    return lines


def render_summary(report: dict[str, Any]) -> str:
    lines = [*_summary_table(report), *_evidence_lines(report), *_totals_lines(report)]
    return "\n".join(lines) + "\n"


def compute_totals(sequences: list[dict[str, Any]]) -> dict[str, int]:
    records = [record for sequence in sequences for record in sequence["steps"]]
    return {
        "pass": sum(1 for record in records if record["ok"]),
        "fail": sum(1 for record in records if not record["ok"]),
        "excused": sum(1 for record in records if record.get("refusal_excused")),
        "skip": sum(1 for sequence in sequences if not sequence["steps"]),
    }


def write_report(report: dict[str, Any]) -> Path:
    root = Path(os.environ.get("PORTAL_DATA_ROOT", str(Path.home() / "AI_Output" / "portal-data")))
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    path = root / "uat" / f"{stamp}-swap.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _blocked_report(base: str, key: str, context: dict[str, Any]) -> dict[str, Any]:
    host_quiet.finish_run(context, base, key)
    reason = host_quiet.refusal(context)
    return {
        "started_at": datetime.now(UTC).isoformat(),
        "pipeline": base,
        "sequences": [],
        "notes": [reason],
        "host_quiet": context,
        "totals": {"pass": 0, "fail": 1, "excused": 0, "skip": 0},
    }


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Swap-sequence UAT for the Portal pipeline.")
    parser.add_argument(
        "--dry-run", action="store_true", help="print the sequences and send nothing"
    )
    parser.add_argument(
        "--sequence",
        action="append",
        choices=SEQUENCE_NAMES,
        help="run only these sequences (repeatable; default all)",
    )
    parser.add_argument("--ping-pong-cycles", type=int, default=2, help="engine alternations")
    parser.add_argument("--ladder-size", type=int, default=3, help="seats at each ladder end")
    parser.add_argument(
        "--pinned-seat",
        metavar="ID",
        help="config seat to treat as pinned (default: the workspace whose model_hint pins LLM_ROUTER_MODEL)",
    )
    parser.add_argument(
        "--pinned-lead-seconds",
        type=float,
        default=3.0,
        help="wait after starting the long request before firing the pinned seat",
    )
    parser.add_argument(
        "--long-max-tokens", type=int, default=600, help="the long request's budget"
    )
    parser.add_argument(
        "--container",
        default="portal5-pipeline",
        help="pipeline container for docker logs (empty disables guard logs)",
    )
    parser.add_argument("--force", action="store_true", help="override host-quiet blockers")
    parser.add_argument(
        "--wait-for-quiet",
        action="store_true",
        help="poll transient host blockers until they clear or the wait expires",
    )
    parser.add_argument("--quiet-poll-seconds", type=float, default=host_quiet.DEFAULT_QUIET_POLL_S)
    parser.add_argument(
        "--quiet-max-wait-seconds", type=float, default=host_quiet.DEFAULT_QUIET_MAX_WAIT_S
    )
    return parser.parse_args(argv)


def _sequences_for(args: argparse.Namespace, catalog: Catalog, seats: list[Seat]) -> list[Sequence]:
    return build_sequences(
        args.sequence,
        seats,
        args.ping_pong_cycles,
        args.ladder_size,
        catalog.pinned_id,
        catalog.pinned_note,
        catalog.extra,
    )


def _dry_run(args: argparse.Namespace, catalog: Catalog, base: str, key: str) -> int:
    seats, size_note = apply_plan_sizes(catalog.seats, base, key)
    sequences = _sequences_for(args, catalog, seats)
    plan = render_plan(
        seats, sequences, catalog.unresolved, catalog.skipped, catalog.stack_down, size_note
    )
    print(plan, end="")
    return 0


def _execute_sequences(
    args: argparse.Namespace, sequences: list[Sequence], base: str, key: str
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    with make_client() as client:
        for sequence in sequences:
            records = run_sequence(
                client,
                base,
                key,
                sequence,
                args.container,
                lead_s=args.pinned_lead_seconds,
                long_max_tokens=args.long_max_tokens,
            )
            results.append(
                {
                    "name": sequence.name,
                    "mode": sequence.mode,
                    "notes": sequence.notes,
                    "steps": records,
                }
            )
    return results


def _build_report(
    base: str,
    catalog: Catalog,
    seats: list[Seat],
    size_note: str,
    sequences: list[Sequence],
    results: list[dict[str, Any]],
    context: dict[str, Any],
) -> dict[str, Any]:
    return {
        "started_at": datetime.now(UTC).isoformat(),
        "pipeline": base,
        "catalog": {
            "seats": len(seats),
            "sized": len(_sized(seats)),
            "size_note": size_note,
            "pinned_seat": catalog.pinned_id or "",
            "pinned_seat_source": catalog.pinned_note,
            "unresolved": catalog.unresolved,
            "skipped_owned_elsewhere": catalog.skipped,
            "stack_down_only": catalog.stack_down,
        },
        "sequences": results,
        "notes": [note for sequence in sequences for note in sequence.notes],
        "host_quiet": context,
    }


def _live_run(args: argparse.Namespace, catalog: Catalog, base: str, key: str) -> int:
    context = host_quiet.start_run(
        base,
        key,
        force=args.force,
        wait=args.wait_for_quiet,
        poll_s=args.quiet_poll_seconds,
        max_wait_s=args.quiet_max_wait_seconds,
    )
    if not context["allowed"]:
        report = _blocked_report(base, key, context)
        path = write_report(report)
        print(host_quiet.refusal(context), file=sys.stderr)
        print(f"json: {path}")
        return 1
    if context["override_reason"]:
        print(f"HOST-QUIET OVERRIDE: {context['override_reason']}", file=sys.stderr)
    seats, size_note = apply_plan_sizes(catalog.seats, base, key)
    sequences = _sequences_for(args, catalog, seats)
    results = _execute_sequences(args, sequences, base, key)
    report = _build_report(base, catalog, seats, size_note, sequences, results, context)
    host_quiet.finish_run(context, base, key)
    report["totals"] = compute_totals(results)
    path = write_report(report)
    print(render_summary(report), end="")
    print(f"json: {path}")
    return 1 if report["totals"]["fail"] else 0


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    config = load_portal_config()
    pinned_id, pinned_note = (
        (args.pinned_seat, "explicit --pinned-seat")
        if args.pinned_seat
        else config_pinned_workspace(config)
    )
    extra = (pinned_id,) if pinned_id else ()
    seats, unresolved, skipped, stack_down = derive_seats(config, extra)
    catalog = Catalog(seats, unresolved, skipped, stack_down, pinned_id, pinned_note, extra)
    base = pipeline_base()
    key = _pipeline_key()
    if args.dry_run:
        return _dry_run(args, catalog, base, key)
    if not key:
        print("PIPELINE_API_KEY is not set", file=sys.stderr)
        return 1
    return _live_run(args, catalog, base, key)


if __name__ == "__main__":
    raise SystemExit(main())
