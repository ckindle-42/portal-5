#!/usr/bin/env python3
"""One shot per enabled engine and variant, plus the engines-and-roles design checks."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from portal.platform.inference.config import load_persona_map, load_portal_config, variant_module
from portal.platform.wiki.adapters.modules import is_workspace_disabled, served_ids
from scripts import host_quiet

# Another session owns these lanes; this runner does not call them.
SKIP_MODULES = frozenset({"security", "security_redteam"})
ONE_WORD = "Reply with exactly one word."
TIMEOUT_S = 600.0
REPO = Path(__file__).resolve().parents[1]
PRESET_DIR = REPO / "imports" / "openwebui" / "workspaces"
_SLUG = re.compile(r"[A-Za-z0-9_-]+")
_THINK = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


def id_module(config: Any, workspace_id: str) -> str:
    base, _sep, name = workspace_id.partition("::")
    spec = config.workspaces.get(base)
    if spec is None:
        return ""
    if not name:
        return str(spec.module)
    variant = spec.variants.get(name, {})
    return variant_module(spec.module, variant)


def is_stack_down_only(config: Any, workspace_id: str) -> bool:
    """True when the id's variant override, else its engine, declares stack_down_only."""
    base, _sep, name = workspace_id.partition("::")
    spec = config.workspaces.get(base)
    if spec is None:
        return False
    if name:
        override = spec.variants.get(name) or {}
        if isinstance(override, dict) and override.get("stack_down_only") is not None:
            return bool(override["stack_down_only"])
    return bool(getattr(spec, "stack_down_only", None))


def select_shots(
    config: Any, mods: list[str] | None = None
) -> tuple[list[str], list[str], list[str]]:
    """Served ids to call, owned-elsewhere skips, and stack-down-only skips."""
    run: list[str] = []
    skip: list[str] = []
    down: list[str] = []
    for wid in sorted(served_ids(config, mods)):
        if id_module(config, wid) in SKIP_MODULES:
            skip.append(wid)
        elif is_stack_down_only(config, wid):
            down.append(wid)
        else:
            run.append(wid)
    return run, skip, down


def _variant_ids(config: Any) -> list[str]:
    found: list[str] = []
    for ws_id, spec in config.workspaces.items():
        for name in spec.variants:
            found.append(f"{ws_id}::{name}")
    return found


def _disabled_split(config: Any, mods: list[str] | None = None) -> tuple[list[str], list[str]]:
    """Disabled variants to probe, and disabled security variants to list and never call."""
    probe: list[str] = []
    owned: list[str] = []
    for wid in _variant_ids(config):
        if not is_workspace_disabled(wid, mods, config):
            continue
        if id_module(config, wid) in SKIP_MODULES:
            owned.append(wid)
        else:
            probe.append(wid)
    return sorted(probe), sorted(owned)


def disabled_variant_ids(config: Any, mods: list[str] | None = None) -> list[str]:
    """Disabled variants this runner may probe. Security lanes are never included."""
    probe, _owned = _disabled_split(config, mods)
    return probe


def owned_disabled_ids(config: Any, mods: list[str] | None = None) -> list[str]:
    """Disabled security variants. They join 'skipped: owned elsewhere' and get no request."""
    _probe, owned = _disabled_split(config, mods)
    return owned


def route_model(header: str) -> str:
    _engine, sep, rest = header.partition(";")
    _backend, sep2, model = rest.partition(";")
    if not sep or not sep2:
        return ""
    return model.strip()


def route_engine(header: str) -> str:
    """Workspace id in ``x-portal-route`` (``engine;backend;model``)."""
    engine, sep, _rest = header.partition(";")
    return engine.strip() if sep else ""


def compare_route_models(alias_route: str, target_route: str) -> tuple[bool, str]:
    alias_model = route_model(alias_route)
    target_model = route_model(target_route)
    if alias_model and alias_model == target_model:
        return True, alias_model
    return False, f"{alias_model or '(none)'} != {target_model or '(none)'}"


def classify_disabled_response(status: int, payload: Any) -> tuple[bool, str]:
    """True when the body is the disabled-workspace 404 and carries no completion."""
    if not isinstance(payload, dict):
        return False, f"HTTP {status} body is not JSON"
    detail = payload.get("detail")
    text = detail if isinstance(detail, str) else ""
    if status == 404 and "disabled" in text.lower() and not payload.get("choices"):
        return True, text
    return False, f"HTTP {status} detail {text!r}"


def _assistant_message(payload: dict[str, Any]) -> dict[str, Any]:
    choices = payload.get("choices") or []
    if not choices or not isinstance(choices[0], dict):
        return {}
    message = choices[0].get("message") or {}
    return message if isinstance(message, dict) else {}


def answer_text(payload: dict[str, Any]) -> str:
    content = _content_str(_assistant_message(payload).get("content"))
    return _THINK.sub("", content).strip()


def reasoning_text(payload: dict[str, Any]) -> str:
    return _content_str(_assistant_message(payload).get("reasoning_content")).strip()


def _content_str(content: Any) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for part in content:
        if isinstance(part, str):
            parts.append(part)
        elif isinstance(part, dict) and isinstance(part.get("text"), str):
            parts.append(part["text"])
    return "".join(parts)


def judge_shot(
    status: int, route: str, answered: bool, error: str | None
) -> tuple[bool, str | None]:
    if error:
        return False, error
    if status == 200 and answered and route_model(route):
        return True, None
    bits: list[str] = []
    if status != 200:
        bits.append(f"HTTP {status}")
    if not route_model(route):
        bits.append("missing route model")
    if not answered:
        bits.append("empty answer")
    return False, "; ".join(bits)


def make_check(name: str, ok: bool, reason: str) -> dict[str, Any]:
    return {"name": name, "ok": ok, "reason": reason}


def skip_check(name: str, reason: str) -> dict[str, Any]:
    return {"name": name, "ok": False, "reason": reason, "skipped": True}


def sse_status(lines: list[str]) -> tuple[bool, str]:
    chunks = 0
    done = False
    for line in lines:
        text = line.strip()
        if not text.startswith("data:"):
            continue
        payload = text[5:].strip()
        if payload == "[DONE]":
            done = True
        elif payload:
            chunks += 1
    if chunks and done:
        return True, f"{chunks} SSE chunks and [DONE]"
    return False, f"chunks={chunks} done={done}"


def prompt_needle(prompt: str) -> str:
    lines = [line.strip() for line in prompt.splitlines() if line.strip()]
    if not lines:
        return ""
    if len(lines[0]) >= 24:
        return lines[0][:80]
    return "\n".join(lines[:2])[:80]


def _strings(node: Any) -> list[str]:
    if isinstance(node, str):
        return [node]
    if isinstance(node, dict):
        found: list[str] = []
        for value in node.values():
            found.extend(_strings(value))
        return found
    if isinstance(node, list):
        found = []
        for item in node:
            found.extend(_strings(item))
        return found
    return []


def prompt_in_trace(trace: dict[str, Any], prompt: str) -> tuple[bool, str]:
    needle = prompt_needle(prompt)
    if not needle:
        return False, "persona prompt is empty"
    if any(needle in text for text in _strings(trace.get("bodies"))):
        return True, "persona prompt in trace messages"
    if trace.get("_error"):
        return False, f"trace request failed: {trace['_error']}"
    if "_status" in trace:
        return False, f"trace HTTP {trace['_status']}"
    if trace.get("bodies_dropped"):
        return False, "trace dropped message bodies"
    if trace.get("bodies_captured") is False:
        return False, "trace did not capture message bodies"
    return False, "persona prompt absent from trace messages"


def pick_role(personas: dict[str, Any]) -> Any | None:
    """Shortest production role, so the prompt still fits in a trace record."""
    eligible = []
    for spec in personas.values():
        if spec.delivery != "role" or spec.module in SKIP_MODULES | {"eval"}:
            continue
        if spec.slug.startswith("bench") or not _SLUG.fullmatch(spec.slug):
            continue
        if not str(spec.system_prompt).strip():
            continue
        eligible.append(spec)
    eligible.sort(key=lambda spec: (len(spec.system_prompt), spec.slug))
    return eligible[0] if eligible else None


def _chat_engines(config: Any, ids: list[str]) -> list[str]:
    """Exposed general engines that can answer without a forced tool call. auto re-routes, so it is left out."""
    found: list[str] = []
    for wid in ids:
        if "::" in wid or wid == "auto":
            continue
        spec = config.workspaces.get(wid)
        if spec is None or not spec.expose_to_owui or spec.module != "general":
            continue
        if getattr(spec, "tool_choice", None) == "required":
            continue
        found.append(wid)
    return found


def pick_engine(config: Any, ids: list[str], avoid: str) -> str | None:
    """Chat engine other than the role's workspace, else the first concrete engine."""
    for wid in _chat_engines(config, ids):
        if wid != avoid:
            return wid
    concrete = [wid for wid in ids if "::" not in wid and wid not in {"auto", avoid}]
    return concrete[0] if concrete else None


def pick_stream_engine(config: Any, ids: list[str]) -> str | None:
    engines = _chat_engines(config, ids)
    return engines[0] if engines else pick_engine(config, ids, "")


def internal_ids(config: Any, run: list[str]) -> list[str]:
    return sorted(
        wid for wid in run if "::" not in wid and not config.workspaces[wid].expose_to_owui
    )


def preset_ids(directory: Path) -> set[str]:
    found: set[str] = set()
    if not directory.is_dir():
        return found
    for path in sorted(directory.glob("*.json")):
        found.update(_ids_in_preset(path))
    return found


def _ids_in_preset(path: Path) -> set[str]:
    found: set[str] = set()
    name = path.name
    if name.startswith("workspace_") and name.endswith(".json"):
        stem = name[len("workspace_") : -len(".json")]
        if stem:
            found.add(stem.replace("_", "-"))
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return found
    rows = data if isinstance(data, list) else [data]
    for row in rows:
        if isinstance(row, dict) and isinstance(row.get("id"), str):
            found.add(row["id"])
    return found


def check_bench(ids: set[str]) -> dict[str, Any]:
    hits = sorted(wid for wid in ids if wid.startswith("bench-"))
    if hits:
        return make_check("bench-presets", False, "present: " + ", ".join(hits))
    return make_check("bench-presets", True, "no bench-* preset")


def check_internals(
    ids: list[str], shots: dict[str, dict[str, Any]], presets: set[str]
) -> dict[str, Any]:
    if not ids:
        return make_check("internals", False, "no expose_to_owui false workspace in the served set")
    missing = [wid for wid in ids if wid not in shots or not shots[wid]["ok"]]
    leaked = [wid for wid in ids if wid in presets]
    if not missing and not leaked:
        return make_check("internals", True, f"{len(ids)} callable and absent from presets")
    parts: list[str] = []
    if missing:
        parts.append("not callable: " + ", ".join(missing))
    if leaked:
        parts.append("present in presets: " + ", ".join(leaked))
    return make_check("internals", False, "; ".join(parts))


def alias_target(spec: Any) -> str:
    if isinstance(spec, dict):
        return str(spec.get("to", ""))
    return str(getattr(spec, "to", ""))


def compute_totals(
    shots: list[dict[str, Any]], skipped: list[str], checks: list[dict[str, Any]]
) -> dict[str, int]:
    return {
        "shots_ok": sum(1 for shot in shots if shot["ok"]),
        "shots_failed": sum(1 for shot in shots if not shot["ok"]),
        "skipped": len(skipped),
        "checks_ok": sum(1 for item in checks if item["ok"] and not item.get("skipped")),
        "checks_failed": sum(1 for item in checks if not item["ok"] and not item.get("skipped")),
    }


def render_summary(report: dict[str, Any]) -> str:
    lines = [
        "| id | status | route model | seconds |",
        "| --- | --- | --- | --- |",
    ]
    for shot in report["shots"]:
        status = shot["http_status"]
        if shot.get("reasoning_only"):
            status = f"{status}; answer only in reasoning"
        lines.append(f"| {shot['id']} | {status} | {shot['route_model']} | {shot['seconds']:.1f} |")
    lines.extend(["", "## Design checks"])
    for item in report["checks"]:
        if item.get("skipped"):
            lines.append(f"- SKIP: {item['reason']}")
            continue
        mark = "PASS" if item["ok"] else "FAIL"
        lines.append(f"- {mark} {item['name']}: {item['reason']}")
    totals = report["totals"]
    lines.extend(
        [
            "",
            "## Totals",
            (
                f"- shots: {totals['shots_ok']} ok, {totals['shots_failed']} failed, "
                f"{totals['skipped']} skipped"
            ),
            f"- checks: {totals['checks_ok']} pass, {totals['checks_failed']} fail",
            "",
            "## skipped: owned elsewhere",
        ]
    )
    skipped = report["skipped"]
    lines.extend(f"- {wid}" for wid in skipped)
    if not skipped:
        lines.append("- (none)")
    lines.extend(["", "## stack-down only, not tested"])
    down = report.get("stack_down_only") or []
    lines.extend(f"- {wid}" for wid in down)
    if not down:
        lines.append("- (none)")
    return "\n".join(lines) + "\n"


def render_plan(
    run: list[str],
    skip: list[str],
    down: list[str],
    aliases: list[tuple[str, str, bool]],
    role: Any,
    engine: str | None,
    stream_engine: str | None,
    disabled: list[str],
    internals: list[str],
    *,
    design: bool,
) -> str:
    lines = [f"shots ({len(run)}):", *[f"  {wid}" for wid in run]]
    lines.append(f"skipped: owned elsewhere ({len(skip)}):")
    lines.extend(f"  {wid}" for wid in skip)
    lines.append(f"stack-down only, not tested ({len(down)}):")
    lines.extend(f"  {wid}" for wid in down)
    if not design:
        lines.append("checks: not run (--only)")
        return "\n".join(lines)
    lines.append("checks:")
    if aliases:
        for alias_id, target, owned in aliases:
            suffix = " (skipped: owned elsewhere)" if owned else ""
            lines.append(f"  alias {alias_id} -> {target}{suffix}")
    else:
        lines.append("  alias: none configured")
    if role is not None and engine:
        lines.append(f"  role /{role.slug} on {engine}")
    else:
        lines.append("  role: unavailable")
    lines.append(f"  disabled variants ({len(disabled)}):")
    lines.extend(f"    {wid}" for wid in disabled)
    lines.append("  internals: " + (", ".join(internals) if internals else "(none)"))
    lines.append("  bench presets: imports/openwebui/workspaces/")
    lines.append(f"  stream: {stream_engine or '(none)'}")
    return "\n".join(lines)


def chat_payload(model: str, content: str, *, stream: bool) -> dict[str, Any]:
    return {"model": model, "messages": [{"role": "user", "content": content}], "stream": stream}


def _auth(key: str, cid: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {key}", "X-Correlation-ID": cid}


def payload_of(response: httpx.Response) -> dict[str, Any]:
    try:
        data = response.json()
    except (json.JSONDecodeError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def post_json(
    client: httpx.Client, url: str, key: str, payload: dict[str, Any], cid: str
) -> tuple[int, dict[str, Any], str, str, str | None]:
    try:
        response = client.post(url, json=payload, headers=_auth(key, cid))
    except httpx.HTTPError as exc:
        return 0, {}, "", cid, str(exc)
    seen = response.headers.get("x-correlation-id", cid)
    return (
        response.status_code,
        payload_of(response),
        response.headers.get("x-portal-route", ""),
        seen,
        None,
    )


def fire_shot(
    client: httpx.Client,
    base: str,
    key: str,
    model: str,
    content: str = ONE_WORD,
) -> dict[str, Any]:
    cid = f"p5-uat-{uuid.uuid4().hex[:12]}"
    started = time.monotonic()
    status, payload, route, seen, error = post_json(
        client, f"{base}/v1/chat/completions", key, chat_payload(model, content, stream=False), cid
    )
    text = answer_text(payload)
    reasoned = bool(reasoning_text(payload))
    ok, reason = judge_shot(status, route, bool(text), error)
    reasoning_only = not text and reasoned
    if reasoning_only and reason:
        reason = f"{reason}; answer only in reasoning"
    return {
        "id": model,
        "http_status": status,
        "route": route,
        "route_model": route_model(route),
        "seconds": round(time.monotonic() - started, 1),
        "answered": bool(text),
        "answer_excerpt": text[:60],
        "reasoning_only": reasoning_only,
        "correlation_id": seen,
        "ok": ok,
        "error": reason,
    }


def fire_stream(client: httpx.Client, base: str, key: str, model: str) -> dict[str, Any]:
    cid = f"p5-uat-{uuid.uuid4().hex[:12]}"
    url = f"{base}/v1/chat/completions"
    try:
        with client.stream(
            "POST", url, json=chat_payload(model, ONE_WORD, stream=True), headers=_auth(key, cid)
        ) as response:
            lines = list(response.iter_lines())
            status = response.status_code
    except httpx.HTTPError as exc:
        return make_check("streaming", False, str(exc))
    ok, reason = sse_status(lines)
    if status != 200:
        return make_check("streaming", False, f"HTTP {status}; {reason}")
    return make_check("streaming", ok, reason)


def fetch_trace(client: httpx.Client, base: str, key: str, cid: str) -> dict[str, Any]:
    try:
        response = client.get(f"{base}/v1/trace/{cid}", headers={"Authorization": f"Bearer {key}"})
    except httpx.HTTPError as exc:
        return {"_error": str(exc)}
    if response.status_code != 200:
        return {"_status": response.status_code}
    return payload_of(response)


def _note(line: str) -> None:
    print(line, file=sys.stderr)


def run_shots(client: httpx.Client, base: str, key: str, ids: list[str]) -> list[dict[str, Any]]:
    shots: list[dict[str, Any]] = []
    for wid in ids:
        shot = fire_shot(client, base, key, wid)
        shots.append(shot)
        _note(f"shot {wid} {shot['http_status']} {shot['seconds']}s")
    return shots


def alias_checks(
    client: httpx.Client,
    base: str,
    key: str,
    config: Any,
    shots: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    if not config.aliases:
        return [make_check("alias", False, "no aliases configured")]
    checks: list[dict[str, Any]] = []
    for alias_id, spec in sorted(config.aliases.items()):
        target = alias_target(spec)
        name = f"alias:{alias_id}"
        if id_module(config, target) in SKIP_MODULES:
            checks.append(make_check(name, False, "target owned elsewhere"))
            continue
        target_shot = shots.get(target)
        if target_shot is None and is_workspace_disabled(target, None, config):
            checks.append(skip_check(name, f"target {target} disabled, not tested"))
            continue
        if target_shot is None:
            checks.append(make_check(name, False, f"target {target} was not shot"))
            continue
        if not route_model(target_shot.get("route", "")):
            checks.append(skip_check(name, f"target {target} did not produce a route model"))
            continue
        alias_shot = fire_shot(client, base, key, alias_id)
        _note(f"alias {alias_id} {alias_shot['http_status']} {alias_shot['seconds']}s")
        ok, reason = compare_route_models(alias_shot["route"], target_shot["route"])
        checks.append(make_check(name, ok, reason))
    return checks


def judge_role(
    plain_route: str, role_route: str, trace: dict[str, Any], prompt: str
) -> dict[str, Any]:
    """Engine field of x-portal-route must hold. The prompt check skips when bodies are off."""
    plain_engine = route_engine(plain_route)
    role_engine = route_engine(role_route)
    if not plain_engine or role_engine != plain_engine:
        shown = role_engine or "(none)"
        expected = plain_engine or "(none)"
        return make_check("role", False, f"engine {shown} != {expected}")
    if trace.get("bodies_captured") is False:
        return skip_check("role", "set PORTAL_TRACE_BODIES=1")
    present, prompt_reason = prompt_in_trace(trace, prompt)
    if present:
        return make_check("role", True, f"engine {role_engine}; {prompt_reason}")
    return make_check("role", False, prompt_reason)


def role_check(
    client: httpx.Client,
    base: str,
    key: str,
    role: Any,
    engine: str | None,
    shots: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    if role is None or not engine:
        return make_check("role", False, "no role persona or no engine")
    plain = shots.get(engine)
    if plain is None or not plain.get("route"):
        return make_check("role", False, f"{engine} has no route to compare")
    shot = fire_shot(client, base, key, engine, content=f"/{role.slug} {ONE_WORD}")
    _note(f"role /{role.slug} on {engine} {shot['http_status']} {shot['seconds']}s")
    trace = fetch_trace(client, base, key, shot["correlation_id"])
    return judge_role(plain["route"], shot["route"], trace, str(role.system_prompt))


def disabled_check(client: httpx.Client, base: str, key: str, ids: list[str]) -> dict[str, Any]:
    if not ids:
        return make_check("disabled-variants", True, "no disabled variant")
    failed: list[str] = []
    for wid in ids:
        _status, payload, _route, _cid, error = post_json(
            client,
            f"{base}/v1/chat/completions",
            key,
            chat_payload(wid, ONE_WORD, stream=False),
            f"p5-uat-{uuid.uuid4().hex[:12]}",
        )
        status = 0 if error else _status
        ok, reason = (False, error) if error else classify_disabled_response(status, payload)
        _note(f"disabled {wid} {status}")
        if not ok:
            failed.append(f"{wid} ({reason})")
    if failed:
        return make_check("disabled-variants", False, "; ".join(failed))
    return make_check(
        "disabled-variants", True, f"{len(ids)} returned the disabled-workspace error"
    )


def execute(
    client: httpx.Client,
    base: str,
    key: str,
    config: Any,
    run: list[str],
    skip: list[str],
    down: list[str],
    role: Any,
    engine: str | None,
    stream_engine: str | None,
    disabled: list[str],
    *,
    design: bool,
    host_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    shots = run_shots(client, base, key, run)
    by_id = {shot["id"]: shot for shot in shots}
    checks: list[dict[str, Any]] = []
    if host_context is not None:
        checks.append(
            make_check(
                "host-quiet",
                True,
                host_context["override_reason"] or "host preflight passed",
            )
        )
    if design:
        presets = preset_ids(PRESET_DIR)
        checks.extend(alias_checks(client, base, key, config, by_id))
        checks.append(role_check(client, base, key, role, engine, by_id))
        checks.append(disabled_check(client, base, key, disabled))
        checks.append(check_internals(internal_ids(config, run), by_id, presets))
        checks.append(check_bench(presets))
        checks.append(
            fire_stream(client, base, key, stream_engine)
            if stream_engine
            else make_check("streaming", False, "no engine")
        )
    if host_context is not None:
        host_quiet.finish_run(host_context, base, key)
    report = {
        "started_at": datetime.now(UTC).isoformat(),
        "pipeline": base,
        "design_checks_run": design,
        "shots": shots,
        "skipped": skip,
        "stack_down_only": down,
        "checks": checks,
    }
    if host_context is not None:
        report["host_quiet"] = host_context
    report["totals"] = compute_totals(shots, skip, checks)
    return report


def write_report(report: dict[str, Any]) -> Path:
    root = Path(os.environ.get("PORTAL_DATA_ROOT", str(Path.home() / "AI_Output" / "portal-data")))
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    path = root / "uat" / f"{stamp}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def pipeline_base() -> str:
    return os.environ.get("PIPELINE_URL", "http://localhost:9099").rstrip("/")


def make_client() -> httpx.Client:
    return httpx.Client(timeout=httpx.Timeout(TIMEOUT_S, connect=10.0))


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="One shot per enabled engine and variant.")
    parser.add_argument("--dry-run", action="store_true", help="list the plan and send nothing")
    parser.add_argument("--only", metavar="ID", help="run one served id and skip design checks")
    parser.add_argument("--force", action="store_true", help="override host-quiet blockers")
    parser.add_argument(
        "--wait-for-quiet",
        action="store_true",
        help="poll transient host blockers until they clear or the wait expires",
    )
    parser.add_argument(
        "--quiet-poll-seconds",
        type=float,
        default=host_quiet.DEFAULT_QUIET_POLL_S,
        help="seconds between host-quiet re-checks when waiting",
    )
    parser.add_argument(
        "--quiet-max-wait-seconds",
        type=float,
        default=host_quiet.DEFAULT_QUIET_MAX_WAIT_S,
        help="stop waiting for a quiet host after this many seconds",
    )
    return parser.parse_args(argv)


def resolve_only(
    only: str, run: list[str], skip: list[str], down: list[str]
) -> tuple[list[str], list[str], list[str], str | None]:
    if only in skip:
        return [], [only], [], None
    if only in down:
        return [], [], [only], None
    if only in run:
        return [only], [], [], None
    return [], [], [], f"{only} is not a served id"


def alias_rows(config: Any) -> list[tuple[str, str, bool]]:
    rows = []
    for alias_id, spec in sorted(config.aliases.items()):
        target = alias_target(spec)
        rows.append((alias_id, target, id_module(config, target) in SKIP_MODULES))
    return rows


def _blocked_host_report(base: str, key: str, context: dict[str, Any]) -> dict[str, Any]:
    host_quiet.finish_run(context, base, key)
    reason = host_quiet.refusal(context)
    return {
        "started_at": datetime.now(UTC).isoformat(),
        "pipeline": base,
        "design_checks_run": False,
        "shots": [],
        "skipped": [],
        "stack_down_only": [],
        "checks": [make_check("host-quiet", False, reason)],
        "host_quiet": context,
        "totals": compute_totals([], [], [make_check("host-quiet", False, reason)]),
    }


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    config = load_portal_config()
    run, skip, down = select_shots(config)
    design = not args.only
    if args.only:
        run, skip, down, error = resolve_only(args.only, run, skip, down)
        if error:
            print(error, file=sys.stderr)
            return 1
    role = pick_role(load_persona_map(config=config)) if design else None
    avoid = role.workspace_model if role is not None else ""
    engine = pick_engine(config, run, avoid) if design else None
    stream_engine = pick_stream_engine(config, run) if design else None
    disabled: list[str] = []
    if design:
        disabled = disabled_variant_ids(config)
        skip = sorted(set(skip).union(owned_disabled_ids(config)))
    if args.dry_run:
        print(
            render_plan(
                run,
                skip,
                down,
                alias_rows(config) if design else [],
                role,
                engine,
                stream_engine,
                disabled,
                internal_ids(config, run) if design else [],
                design=design,
            )
        )
        return 0
    key = os.environ.get("PIPELINE_API_KEY", "").strip()
    if not key:
        print("PIPELINE_API_KEY is not set", file=sys.stderr)
        return 1
    base = pipeline_base()
    host_context = host_quiet.start_run(
        base,
        key,
        force=args.force,
        wait=args.wait_for_quiet,
        poll_s=args.quiet_poll_seconds,
        max_wait_s=args.quiet_max_wait_seconds,
    )
    if not host_context["allowed"]:
        report = _blocked_host_report(base, key, host_context)
        path = write_report(report)
        print(host_quiet.refusal(host_context), file=sys.stderr)
        print(f"json: {path}")
        return 1
    if host_context["override_reason"]:
        print(f"HOST-QUIET OVERRIDE: {host_context['override_reason']}", file=sys.stderr)
    with make_client() as client:
        report = execute(
            client,
            base,
            key,
            config,
            run,
            skip,
            down,
            role,
            engine,
            stream_engine,
            disabled,
            design=design,
            host_context=host_context,
        )
    path = write_report(report)
    print(render_summary(report), end="")
    print(f"json: {path}")
    totals = report["totals"]
    return 1 if totals["shots_failed"] or totals["checks_failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
