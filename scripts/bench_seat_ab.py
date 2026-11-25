#!/usr/bin/env python3
"""Run a trace-verified seat A/B through the production Pipeline."""

from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import os
import re
import statistics
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import httpx
import yaml

from portal.platform.inference.config import effective_workspace
from scripts.bench_security_qat import TASKS as SECURITY_TASKS
from scripts.bench_security_qat import Turn, grade_purple_jndi_sigma, grade_s3_refusal_preservation
from scripts.council_bench import DEFAULT_CASES, build_request, load_cases, score_case
from tests.qat.config import Settings
from tests.qat.models import QATScenario
from tests.qat.owui_client import OWUIClient, artifact_urls, red_square_png
from tests.qat.runner import build_plan
from tests.qat.uat_behavioral import (
    UATCase,
    UATTurn,
    _required_tool_error,
    discover_cases,
    grade_case,
)
from tests.wfe.checkers import CheckContext, apply_checkers

REPO = Path(__file__).resolve().parents[1]
OUTPUT_ROOT = Path("/Volumes/data01/seat_ab")
SUITES = ("research", "vision", "council", "reading", "uncensored")
_LOAD_LINE = re.compile(r"load|loaded|unload|unloaded|evict|evicted", re.IGNORECASE)
_URL_IN_TEXT = re.compile(r"(?:https?://|/api/v1/files/)[^\s\]<>\"']+")


@dataclass
class BenchCase:
    case_id: str
    prompts: tuple[str, ...]
    source: str
    kind: str
    spec: dict[str, Any] = field(default_factory=dict)
    qat: QATScenario | None = None
    uat: UATCase | None = None


def grade_security_probe(scenario: str, answer: str) -> list[str]:
    """Use the security bench's existing refusal and purple-team graders."""
    turns = [Turn(answer=answer)]
    if scenario == "s3-refusal-preservation":
        return grade_s3_refusal_preservation(turns)
    if scenario == "purple_jndi_sigma":
        return grade_purple_jndi_sigma(turns)
    return [f"unknown security probe {scenario}"]


def finalize_verdict(
    row: dict[str, Any], requested_model: str, grader_verdict: str
) -> dict[str, Any]:
    """Invalidate a score unless every recorded served identity matches its arm."""
    served = row.get("served")
    if not isinstance(served, list):
        trace = row.get("trace")
        served = [trace] if isinstance(trace, dict) else []
    invalid = [
        item
        for item in served
        if not isinstance(item, dict)
        or not item.get("backend")
        or not item.get("model")
        or item.get("model") != requested_model
    ]
    if not served:
        invalid.append({"reason": "no served identity in Pipeline trace"})
    result = dict(row)
    result["served"] = served
    result["grader_verdict"] = grader_verdict
    if invalid:
        result["status"] = "INVALID"
        result["grader_verdict"] = None
        result["invalid_reasons"] = invalid
    else:
        result["status"] = grader_verdict
        result["invalid_reasons"] = []
    return result


def _load_wfe(path: Path) -> list[BenchCase]:
    cases = []
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        spec = json.loads(line)
        prompts = tuple(str(turn.get("user") or "") for turn in spec.get("turns") or [])
        if not prompts:
            prompts = (str(spec.get("instruction") or ""),)
        cases.append(
            BenchCase(
                case_id=str(spec["id"]),
                prompts=prompts,
                source=str(path.relative_to(REPO)),
                kind="wfe",
                spec=spec,
            )
        )
    return cases


def _load_cases(suite: str, workspace: str) -> list[BenchCase]:
    if suite == "council":
        return _council_cases()
    settings = Settings.load()
    discovery, plan = build_plan(settings)
    uat = discover_cases(discovery)
    by_id = {scenario.scenario_id: scenario for scenario in plan}
    if suite == "research":
        return _research_cases(by_id, uat)
    if suite == "vision":
        return _vision_cases(by_id, uat)
    if suite == "reading":
        return _reading_cases(workspace, uat)
    if suite == "uncensored":
        return _uncensored_cases(by_id)
    raise ValueError(f"unknown suite {suite!r}")


def _research_cases(by_id: dict[str, QATScenario], uat: tuple[UATCase, ...]) -> list[BenchCase]:
    cases = _load_wfe(REPO / "tests/wfe/suites/research_production.jsonl")
    cases.extend(
        _qat_case(scenario)
        for key, scenario in by_id.items()
        if key.startswith("s4-auto-research-")
    )
    cases.extend(
        _uat_case(case) for case in uat if case.scenario_id.startswith("s5-browser-web-research")
    )
    return cases


def _vision_cases(by_id: dict[str, QATScenario], uat: tuple[UATCase, ...]) -> list[BenchCase]:
    cases = _load_wfe(REPO / "tests/wfe/suites/vision_production.jsonl")
    cases.extend(
        _qat_case(scenario)
        for key, scenario in by_id.items()
        if key.startswith("s4-auto-vision-") or key == "s2-p5-chartanalyst"
    )
    cases.extend(_uat_case(case) for case in uat if "vision" in case.scenario_id)
    return cases


def _reading_cases(workspace: str, uat: tuple[UATCase, ...]) -> list[BenchCase]:
    if "documents" in workspace.split("::", 1)[0]:
        return [_uat_case(case) for case in uat if case.scenario_id.startswith("s5-documents-")]
    cases = _load_wfe(REPO / "tests/wfe/suites/reading_production.jsonl")
    contract = REPO / "tests/wfe/suites/compliance_reading_contract.jsonl"
    if contract.is_file():
        cases.extend(_load_wfe(contract))
    return cases


def _council_cases() -> list[BenchCase]:
    return [
        BenchCase(
            case_id=case.id,
            prompts=(case.submission,),
            source=str(DEFAULT_CASES.relative_to(REPO)),
            kind="council",
            spec={"council_case": case},
        )
        for case in load_cases()
    ]


def _uncensored_cases(by_id: dict[str, QATScenario]) -> list[BenchCase]:
    cases = []
    for task_id, case_id in (
        ("s3_refusal_preservation", "s3-refusal-preservation"),
        ("purple_jndi_sigma", "purple_jndi_sigma"),
    ):
        task = next(task for task in SECURITY_TASKS if task.id == task_id)
        cases.append(
            BenchCase(
                case_id,
                tuple(task.prompts),
                "scripts/bench_security_qat.py",
                "security",
                {"grader_id": case_id},
            )
        )
    for suffix in ("core", "tools", "edge"):
        scenario = by_id.get(f"s4-auto-general-uncensored-{suffix}")
        if scenario:
            cases.append(_qat_case(scenario))
    return cases


def _qat_case(scenario: QATScenario) -> BenchCase:
    return BenchCase(
        scenario.scenario_id,
        tuple(scenario.prompts),
        "tests/qat/scenarios.py + live local discovery",
        "qat",
        {"attachment": scenario.attachment},
        qat=scenario,
    )


def _uat_case(case: UATCase) -> BenchCase:
    return BenchCase(
        case.scenario_id,
        tuple(case.prompts),
        "tests/qat/uat_behavioral.py",
        "uat",
        {},
        uat=case,
    )


def _pipeline_headers(settings: Settings, correlation_id: str) -> dict[str, str]:
    return {
        **settings.auth_headers(),
        "X-Correlation-ID": correlation_id,
        "Accept": "text/event-stream",
    }


def _pipeline_url(settings: Settings, model: str) -> str:
    return f"{settings.pipeline_url}/v1/chat/completions?{urlencode({'model': model})}"


def _parse_stream(lines: Any) -> tuple[str, list[dict[str, Any]], dict[str, Any], float | None]:
    text: list[str] = []
    calls: list[dict[str, Any]] = []
    usage: dict[str, Any] = {}
    first_token_s: float | None = None
    started = time.perf_counter()
    for line in lines:
        if not line.startswith("data:"):
            continue
        raw = line[5:].strip()
        if raw == "[DONE]":
            break
        event = json.loads(raw)
        if event.get("type") == "exec_audit":
            calls.extend(event.get("tool_calls") or [])
            continue
        if event.get("error"):
            raise RuntimeError(str(event["error"]))
        if event.get("usage"):
            usage = event["usage"]
        choice = (event.get("choices") or [{}])[0]
        delta = choice.get("delta") or {}
        content = delta.get("content") or ""
        if content:
            first_token_s = (
                first_token_s if first_token_s is not None else time.perf_counter() - started
            )
            text.append(content)
    return "".join(text), calls, usage, first_token_s


def _fetch_trace(client: httpx.Client, settings: Settings, correlation_id: str) -> dict[str, Any]:
    response = client.get(
        f"{settings.pipeline_url}/v1/trace/{correlation_id}",
        headers=settings.auth_headers(),
        timeout=30.0,
    )
    response.raise_for_status()
    payload = response.json()
    if isinstance(payload, dict) and isinstance(payload.get("data"), dict):
        return payload["data"]
    return payload if isinstance(payload, dict) else {}


def _audit_calls(raw_calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    for call in raw_calls:
        args = call.get("arguments") or call.get("args") or {}
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except json.JSONDecodeError:
                pass
        result = str(call.get("output") or "")
        output.append(
            {
                "name": str(call.get("tool") or call.get("name") or ""),
                "args": args,
                "output": result,
                "error": result.startswith("ERROR"),
            }
        )
    return output


def _inline_image(content: str, image: bytes) -> list[dict[str, Any]]:
    return [
        {"type": "text", "text": content},
        {
            "type": "image_url",
            "image_url": {"url": "data:image/png;base64," + base64.b64encode(image).decode()},
        },
    ]


def _upload_descriptor(client: OWUIClient, token: str, name: str, payload: bytes) -> dict[str, Any]:
    item = client.upload_attachment_bytes(token, name, payload)
    file_id = item["id"]
    return {
        "id": file_id,
        "name": name,
        "type": "file",
        "meta": {
            "content_type": mimetypes.guess_type(name)[0] or "application/octet-stream",
            "size": len(payload),
        },
        "size": len(payload),
        "path": f"/workspace/uploads/{file_id}_{name}",
    }


def _attachment_for_turn(
    case: BenchCase,
    index: int,
    prior_turns: list[dict[str, Any]],
    client: OWUIClient | None,
    token: str,
) -> dict[str, Any] | None:
    if case.kind == "qat" and case.spec.get("attachment") == "inline:red-square-png":
        return {"inline_image": red_square_png()}
    if case.kind == "wfe":
        images = case.spec.get("images") or []
        if images:
            path = (REPO / str(images[0])).resolve()
            return {"inline_image": path.read_bytes()}
    if case.kind == "uat" and case.uat and case.uat.attachment and index == 1:
        if case.uat.attachment == "inline:red-square-png":
            return {"inline_image": red_square_png()}
        if client is None:
            raise RuntimeError("Open WebUI attachment upload needs an OWUI client")
        path = Path(case.uat.attachment)
        if not path.is_absolute():
            path = REPO / path
        payload = path.read_bytes()
        if (mimetypes.guess_type(path.name)[0] or "").startswith("image/"):
            return {"inline_image": payload}
        return {"file": _upload_descriptor(client, token, path.name, payload)}
    if case.kind == "uat" and case.uat and index == case.uat.generated_upload_turn:
        if client is None:
            raise RuntimeError("generated document upload needs an OWUI client")
        suffix = str(case.uat.expected.get("upload_kind") or "docx").lower()
        urls = [url for turn in prior_turns for url in turn.get("artifact_urls", [])]
        url = next(
            (value for value in urls if value.lower().split("?")[0].endswith(f".{suffix}")), ""
        )
        if not url:
            raise RuntimeError(f"generated {suffix.upper()} was not surfaced before read-back")
        payload = client.download_artifact(token, url)
        if not payload:
            raise RuntimeError(f"generated {suffix.upper()} download returned no bytes")
        return {"file": _upload_descriptor(client, token, f"uat-generated-note.{suffix}", payload)}
    return None


def _log_paths() -> list[Path]:
    return [
        Path(os.environ.get("OMLX_SERVER_LOG", str(Path.home() / ".omlx/logs/server.log"))),
        Path(os.environ.get("OLLAMA_SERVER_LOG", str(Path.home() / ".ollama/logs/server.log"))),
    ]


def _log_snapshot(paths: list[Path]) -> dict[str, int]:
    return {str(path): path.stat().st_size if path.is_file() else 0 for path in paths}


def _load_eviction_lines(paths: list[Path], snapshot: dict[str, int]) -> list[dict[str, str]]:
    events = []
    for path in paths:
        if not path.is_file():
            continue
        with path.open("rb") as stream:
            stream.seek(min(snapshot.get(str(path), 0), path.stat().st_size))
            lines = stream.read().decode("utf-8", errors="replace").splitlines()
        events.extend({"log": str(path), "line": line} for line in lines if _LOAD_LINE.search(line))
    return events


def _council_override(workspace: str, model: str) -> dict[str, Any]:
    raw = yaml.safe_load((REPO / "config/portal.yaml").read_text())
    config = effective_workspace(raw["workspaces"], workspace).get("council") or {}
    member_ids = [str(member["id"]) for member in config.get("members") or [] if member.get("id")]
    if not member_ids:
        raise ValueError(f"workspace {workspace!r} has no council member roster")
    return {
        "members": {seat_id: {"model": model} for seat_id in member_ids},
        "synthesizer_model": model,
        "single_model_model": model,
    }


def _council_served(trace: dict[str, Any]) -> list[dict[str, str]]:
    timings = trace.get("portal_council_timings") or {}
    stages = timings.get("stages") if isinstance(timings, dict) else []
    if isinstance(stages, list):
        served = [
            {"backend": str(stage.get("backend") or ""), "model": str(stage.get("model") or "")}
            for stage in stages
            if isinstance(stage, dict) and stage.get("called")
        ]
        if served:
            return served
    spans = trace.get("spans") or []
    return [
        {"backend": str(span.get("backend") or ""), "model": str(span.get("model") or "")}
        for span in spans
        if isinstance(span, dict) and span.get("name") == "council.stage" and span.get("called")
    ]


def _request_council(
    client: httpx.Client,
    settings: Settings,
    workspace: str,
    model: str,
    case: BenchCase,
    timeout_s: float,
) -> dict[str, Any]:
    cid = str(uuid.uuid4())
    body = build_request(case.spec["council_case"])
    body["model"] = workspace
    body["portal_council_config"] = _council_override(workspace, model)
    url = _pipeline_url(settings, model)
    started = time.perf_counter()
    response = client.post(
        url,
        json=body,
        headers={**_pipeline_headers(settings, cid), "Accept": "application/json"},
        timeout=timeout_s,
    )
    response.raise_for_status()
    payload = response.json()
    wall = time.perf_counter() - started
    trace = _fetch_trace(client, settings, cid)
    score = score_case(case.spec["council_case"], payload, wall)
    council = payload.get("portal_council") or {}
    stages = council.get("timings", {}).get("stages", []) if isinstance(council, dict) else []
    stage_timings = [
        stage.get("portal_timings") or {} for stage in stages if isinstance(stage, dict)
    ]
    ttft = min(
        (float(t["ttft_s"]) for t in stage_timings if t.get("ttft_s") is not None), default=None
    )
    decode_s = sum(
        float(t.get("answer_s") or 0) + float(t.get("reasoning_s") or 0) for t in stage_timings
    )
    tokens = sum(
        int(t.get("answer_tokens") or 0) + int(t.get("reasoning_tokens") or 0)
        for t in stage_timings
    )
    return {
        "correlation_id": cid,
        "text": (payload.get("choices") or [{}])[0].get("message", {}).get("content", ""),
        "trace": trace,
        "served": _council_served(trace),
        "wall_s": wall,
        "ttft_s": ttft,
        "decode_tps": tokens / decode_s if decode_s else None,
        "tool_calls": [],
        "grader_verdict": "PASS" if score["outcome_ok"] else "FAIL",
        "grader_details": score,
        "score": score,
    }


def _request_turn(
    client: httpx.Client,
    settings: Settings,
    workspace: str,
    model: str,
    case: BenchCase,
    messages: list[dict[str, Any]],
    prompt: str,
    attachment: dict[str, Any] | None,
    timeout_s: float,
) -> dict[str, Any]:
    cid = str(uuid.uuid4())
    user_content: Any = prompt
    if attachment and attachment.get("inline_image") is not None:
        user_content = _inline_image(prompt, attachment["inline_image"])
    messages.append({"role": "user", "content": user_content})
    body: dict[str, Any] = {
        "model": workspace,
        "messages": messages,
        "stream": True,
        "stream_options": {"include_usage": True},
        "exec_audit": True,
    }
    if attachment and attachment.get("file"):
        body["portal_attached_files"] = [attachment["file"]]
    started = time.perf_counter()
    with client.stream(
        "POST",
        _pipeline_url(settings, model),
        json=body,
        headers=_pipeline_headers(settings, cid),
        timeout=timeout_s,
    ) as response:
        response.raise_for_status()
        text, raw_calls, usage, first_token_s = _parse_stream(response.iter_lines())
    wall = time.perf_counter() - started
    trace = _fetch_trace(client, settings, cid)
    calls = _audit_calls(raw_calls)
    artifact_urls_found = list(artifact_urls({"content": text}))
    for call in calls:
        artifact_urls_found.extend(artifact_urls({"content": call.get("output", "")}))
    messages.append({"role": "assistant", "content": text})
    return {
        "correlation_id": cid,
        "text": text,
        "trace": trace,
        "served": [{"backend": trace.get("backend", ""), "model": trace.get("model", "")}],
        "wall_s": wall,
        "first_token_s": first_token_s,
        "usage": usage,
        "portal_timings": trace.get("portal_timings") or {},
        "tool_calls": calls,
        "artifact_urls": list(dict.fromkeys(artifact_urls_found)),
    }


def _timing_summary(turns: list[dict[str, Any]]) -> tuple[float, float | None, float | None]:
    wall = sum(float(turn.get("wall_s") or 0) for turn in turns)
    ttft = next(
        (float(turn["ttft_s"]) for turn in turns if turn.get("ttft_s") is not None),
        next(
            (
                float(turn["portal_timings"]["ttft_s"])
                for turn in turns
                if turn.get("portal_timings", {}).get("ttft_s") is not None
            ),
            next(
                (
                    float(turn["first_token_s"])
                    for turn in turns
                    if turn.get("first_token_s") is not None
                ),
                None,
            ),
        ),
    )
    tokens = 0
    decode_s = 0.0
    for turn in turns:
        timing = turn.get("portal_timings") or {}
        tokens += int(timing.get("answer_tokens") or 0) + int(timing.get("reasoning_tokens") or 0)
        decode_s += float(timing.get("answer_s") or 0) + float(timing.get("reasoning_s") or 0)
    if not tokens:
        for turn in turns:
            usage = turn.get("usage") or {}
            tokens += int(usage.get("completion_tokens") or 0)
    decode_tps = tokens / decode_s if decode_s else None
    if decode_tps is None:
        decode_tps = next(
            (float(turn["decode_tps"]) for turn in turns if turn.get("decode_tps") is not None),
            None,
        )
    return wall, ttft, decode_tps


def _grade(
    case: BenchCase, turns: list[dict[str, Any]], client: OWUIClient | None, token: str
) -> tuple[str, dict[str, Any]]:
    text = "\n".join(str(turn.get("text") or "") for turn in turns)
    tool_calls = [call for turn in turns for call in turn.get("tool_calls", [])]
    if case.kind == "security":
        errors = grade_security_probe(case.spec["grader_id"], text)
        return ("PASS" if not errors else "FAIL"), {"errors": errors}
    if case.kind == "wfe":
        spec = case.spec
        result = apply_checkers(
            spec,
            CheckContext(
                final_text=text,
                assistant_texts=[turn.get("text", "") for turn in turns],
                tool_calls=tool_calls,
                task=spec,
            ),
        )
        return str(result.outcome.value), {"notes": result.notes, "evidence": result.evidence}
    if case.kind == "uat" and case.uat:
        records = [
            UATTurn(
                prompt=case.prompts[index],
                text=str(turn.get("text") or ""),
                trace=turn.get("trace") or {},
                tool_names=tuple(
                    sorted({str(call.get("name") or "") for call in turn.get("tool_calls", [])})
                ),
                artifact_urls=tuple(turn.get("artifact_urls") or []),
            )
            for index, turn in enumerate(turns)
        ]
        payloads: dict[str, list[bytes]] = {}
        download_errors = []
        urls = list(dict.fromkeys(url for record in records for url in record.artifact_urls))
        if urls and client is not None:
            for url in urls:
                payload = client.download_artifact(token, url)
                suffix = Path(url.split("?", 1)[0]).suffix.lower().lstrip(".")
                if payload:
                    payloads.setdefault(suffix, []).append(payload)
                elif suffix:
                    download_errors.append(f"{suffix} artifact download returned no bytes")
        tool_error = _required_tool_error(case.uat, records)
        errors, evidence = grade_case(case.uat, records, payloads)
        if tool_error:
            errors.append(tool_error)
        errors.extend(download_errors)
        return ("PASS" if not errors else "FAIL"), {
            "errors": errors,
            "evidence": evidence,
            "artifact_types": sorted(payloads),
        }
    if case.kind == "qat":
        return "PENDING_REVIEW", {
            "rubric": case.qat.expected if case.qat else "",
            "tool_calls": len(tool_calls),
            "cited_urls": _URL_IN_TEXT.findall(text),
        }
    return "HARNESS_ERROR", {"errors": [f"no grader for {case.kind}"]}


def _run_case(
    client: httpx.Client,
    settings: Settings,
    workspace: str,
    model: str,
    case: BenchCase,
    timeout_s: float,
    owui: OWUIClient | None,
    token: str,
    paths: list[Path],
    warmup: bool,
    repetition: int,
) -> dict[str, Any]:
    before = _log_snapshot(paths)
    turns: list[dict[str, Any]] = []
    messages: list[dict[str, Any]] = []
    error = ""
    try:
        if case.kind == "council":
            turns.append(_request_council(client, settings, workspace, model, case, timeout_s))
            verdict = turns[0]["grader_verdict"]
            details = turns[0]["grader_details"]
        else:
            prior: list[dict[str, Any]] = []
            for index, prompt in enumerate(case.prompts, start=1):
                attachment = _attachment_for_turn(case, index, prior, owui, token)
                turn = _request_turn(
                    client,
                    settings,
                    workspace,
                    model,
                    case,
                    messages,
                    prompt,
                    attachment,
                    timeout_s,
                )
                turns.append(turn)
                prior.append(turn)
            verdict, details = _grade(case, turns, owui, token)
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        verdict, details = "HARNESS_ERROR", {"errors": [error]}
    wall, ttft, decode_tps = _timing_summary(turns)
    served = [identity for turn in turns for identity in turn.get("served", [])]
    row = {
        "case_id": case.case_id,
        "source": case.source,
        "prompts": case.prompts,
        "workspace": workspace,
        "requested_model": model,
        "warmup": warmup,
        "repetition": repetition,
        "wall_s": wall,
        "ttft_s": ttft,
        "decode_tps": decode_tps,
        "tool_calls": [call for turn in turns for call in turn.get("tool_calls", [])],
        "grader_verdict": verdict,
        "grader_details": details,
        "turns": turns,
        "engine_log_lines": _load_eviction_lines(paths, before),
        "error": error,
    }
    if turns and (case.kind == "council" or len(turns) == 1):
        row["trace"] = turns[0].get("trace")
    result = finalize_verdict(row, model, verdict)
    if warmup and result["status"] != "INVALID":
        result["status"] = "WARMUP"
    return result


def _spread(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {"median": None, "min": None, "max": None, "spread": None}
    low, high = min(values), max(values)
    return {"median": statistics.median(values), "min": low, "max": high, "spread": high - low}


def _summaries(rows: list[dict[str, Any]], arms: list[str]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for arm in arms:
        measured = [row for row in rows if row["requested_model"] == arm and not row["warmup"]]
        block: dict[str, Any] = {
            "rows": len(measured),
            "status_counts": {},
            "wall_s": _spread([float(row["wall_s"]) for row in measured]),
            "ttft_s": _spread(
                [float(row["ttft_s"]) for row in measured if row.get("ttft_s") is not None]
            ),
            "decode_tps": _spread(
                [float(row["decode_tps"]) for row in measured if row.get("decode_tps") is not None]
            ),
        }
        by_case: dict[str, Any] = {}
        for case_id in sorted({str(row["case_id"]) for row in measured}):
            repeated = [row for row in measured if row["case_id"] == case_id]
            by_case[case_id] = {
                "rows": len(repeated),
                "wall_s": _spread([float(row["wall_s"]) for row in repeated]),
                "ttft_s": _spread(
                    [float(row["ttft_s"]) for row in repeated if row.get("ttft_s") is not None]
                ),
                "decode_tps": _spread(
                    [
                        float(row["decode_tps"])
                        for row in repeated
                        if row.get("decode_tps") is not None
                    ]
                ),
                "status_counts": {},
            }
            for row in repeated:
                status = str(row["status"])
                counts = by_case[case_id]["status_counts"]
                counts[status] = counts.get(status, 0) + 1
        block["by_case"] = by_case
        for row in measured:
            status = str(row["status"])
            block["status_counts"][status] = block["status_counts"].get(status, 0) + 1
        council_rows = [row for row in measured if "decision" in (row.get("grader_details") or {})]
        if council_rows:
            rejects = [
                row
                for row in council_rows
                if row["grader_details"].get("category") == "clear_reject"
            ]
            supports = [
                row
                for row in council_rows
                if row["grader_details"].get("category") == "clear_support"
            ]
            block["clear_reject_accuracy"] = (
                sum(bool(row["grader_details"].get("outcome_ok")) for row in rejects) / len(rejects)
                if rejects
                else None
            )
            block["revise_false_positive_rate"] = (
                sum(row["grader_details"].get("decision") == "REVISE" for row in supports)
                / len(supports)
                if supports
                else None
            )
        output[arm] = block
    return output


def _markdown(
    suite: str, workspace: str, summaries: dict[str, Any], rows: list[dict[str, Any]]
) -> str:
    def fmt(item: dict[str, Any]) -> str:
        return "n/a" if item["median"] is None else f"{item['median']:.3f} ({item['spread']:.3f})"

    lines = [
        f"# Seat A/B — {suite}",
        "",
        f"Workspace: `{workspace}`",
        "",
        "## Arms",
        "",
        "| Model | Rows | Statuses | Wall median (spread) | TTFT median (spread) | Decode tok/s median (spread) |",
        "|---|---:|---|---:|---:|---:|",
    ]
    for arm, summary in summaries.items():
        wall, ttft, speed = (summary[name] for name in ("wall_s", "ttft_s", "decode_tps"))
        lines.append(
            f"| `{arm}` | {summary['rows']} | {summary['status_counts']} | {fmt(wall)} | {fmt(ttft)} | {fmt(speed)} |"
        )
        if "clear_reject_accuracy" in summary:
            lines.append(
                f"|  |  | Clear reject accuracy: {summary['clear_reject_accuracy']:.3f} · REVISE false-positive rate: {summary['revise_false_positive_rate']:.3f} |  |  |  |"
            )
    lines.extend(
        [
            "",
            "## Per prompt medians and spread",
            "",
            "| Model | Case | Reps | Statuses | Wall median (spread) | TTFT median (spread) | Decode tok/s median (spread) |",
            "|---|---|---:|---|---:|---:|---:|",
        ]
    )
    for arm, summary in summaries.items():
        for case_id, stats in summary["by_case"].items():
            wall, ttft, speed = (stats[name] for name in ("wall_s", "ttft_s", "decode_tps"))
            lines.append(
                f"| `{arm}` | `{case_id}` | {stats['rows']} | {stats['status_counts']} | {fmt(wall)} | {fmt(ttft)} | {fmt(speed)} |"
            )
    lines.extend(
        [
            "",
            "## Measured rows",
            "",
            "| Model | Case | Rep | Status | Wall s | TTFT s | Decode tok/s | Tools |",
            "|---|---|---:|---|---:|---:|---:|---:|",
        ]
    )
    for row in rows:
        if row["warmup"]:
            continue
        tool_names = ", ".join(
            sorted({str(call.get("name") or "") for call in row["tool_calls"] if call.get("name")})
        )
        ttft = "" if row.get("ttft_s") is None else f"{row['ttft_s']:.3f}"
        speed = "" if row.get("decode_tps") is None else f"{row['decode_tps']:.2f}"
        lines.append(
            f"| `{row['requested_model']}` | `{row['case_id']}` | {row['repetition']} | {row['status']} | {row['wall_s']:.3f} | {ttft} | {speed} | {tool_names} |"
        )
    lines.append("")
    return "\n".join(lines)


def run(
    workspace: str, incumbent: str, challenger: str, suite: str, timeout_s: float = 900.0
) -> Path:
    settings = Settings.load()
    cases = _load_cases(suite, workspace)
    if not cases:
        raise ValueError(f"suite {suite!r} discovered no benchmark cases")
    output_dir = OUTPUT_ROOT / f"{suite}_{datetime.now(UTC).strftime('%Y%m%dT%H%M%S%fZ')}"
    output_dir.mkdir(parents=True, exist_ok=False)
    paths = _log_paths()
    rows: list[dict[str, Any]] = []
    owui: OWUIClient | None = None
    token = ""
    needs_upload = any(
        case.uat and (case.uat.attachment or case.uat.generated_upload_turn) for case in cases
    )
    if needs_upload:
        owui = OWUIClient(settings)
        token = owui.signin()
    arms = [incumbent, challenger]
    with httpx.Client() as client:
        for arm in arms:
            for case in cases:
                rows.append(
                    _run_case(
                        client,
                        settings,
                        workspace,
                        arm,
                        case,
                        timeout_s,
                        owui,
                        token,
                        paths,
                        True,
                        0,
                    )
                )
                for repetition in range(1, 4):
                    rows.append(
                        _run_case(
                            client,
                            settings,
                            workspace,
                            arm,
                            case,
                            timeout_s,
                            owui,
                            token,
                            paths,
                            False,
                            repetition,
                        )
                    )
    summaries = _summaries(rows, arms)
    report = {
        "schema": "seat-ab-1",
        "suite": suite,
        "workspace": workspace,
        "arms": arms,
        "created_at": datetime.now(UTC).isoformat(),
        "case_count": len(cases),
        "repetitions": 3,
        "warmups_per_case": 1,
        "engine_log_paths": [str(path) for path in paths],
        "summaries": summaries,
        "rows": rows,
    }
    (output_dir / "rows.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    (output_dir / "report.md").write_text(_markdown(suite, workspace, summaries, rows))
    return output_dir


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workspace", help="production workspace id")
    parser.add_argument("incumbent", help="incumbent model id")
    parser.add_argument("challenger", help="challenger model id")
    parser.add_argument("suite", choices=SUITES)
    parser.add_argument("--timeout", type=float, default=900.0, help="per-turn timeout in seconds")
    args = parser.parse_args()
    output = run(args.workspace, args.incumbent, args.challenger, args.suite, args.timeout)
    print(f"wrote {output / 'rows.json'}")
    print(f"wrote {output / 'report.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
