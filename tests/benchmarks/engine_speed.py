#!/usr/bin/env python3
"""Decode-speed A/B of one vllm-mlx cell against the oMLX incumbent, through the Pipeline.

The orchestrator runs this. It does not start the production stack. Host prep, engine
launch, readiness, stop, Pipeline health, and the portal_backend pin come from the
existing eval helpers.
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import yaml

from portal.platform.inference.eval_openai import load_bench_engines
from tests.benchmarks import bench_engine_h2h as h2h
from tests.benchmarks import engine_eval_instrument as instrument
from tests.benchmarks import engine_eval_runner as runner

PROMPTS = Path(__file__).with_name("fixtures") / "engine_speed" / "prompts.yaml"
PIPELINE = "http://127.0.0.1:9099"
MAX_TOKENS = 800
WARMUP_PROMPT = "Reply with ok."
WARMUP_MAX_TOKENS = 16
REQUEST_TIMEOUT_S = 1800.0
UNPROVEN = "Unproven — keep oMLX"
ARMS = ("candidate", "incumbent")
_RESIDENT_FIELDS = ("bytes_resident", "resident_bytes", "memory_bytes", "actual_size")


def median(values: list[float]) -> float | None:
    """Upper median, matching bench_engine_h2h.speed_summary."""
    xs = sorted(values)
    if not xs:
        return None
    return float(xs[len(xs) // 2])


def spread(values: list[float]) -> float | None:
    """Run-to-run range. Undefined until two runs exist."""
    if len(values) < 2:
        return None
    return max(values) - min(values)


def decode_tps(
    completion_tokens: int | None, first_s: float | None, last_s: float | None
) -> float | None:
    """Completion tokens divided by the time from the first token to the last."""
    if completion_tokens is None or completion_tokens <= 0 or first_s is None or last_s is None:
        return None
    span = last_s - first_s
    if span <= 0:
        return None
    return completion_tokens / span


def throughput_tok_s(
    completion_tokens: int, ttft_s: float | None, total_s: float | None
) -> float | None:
    """Tokens over (total − TTFT) when that span is positive, else over total."""
    if completion_tokens <= 0 or not _positive(total_s):
        return None
    assert total_s is not None
    if _positive(ttft_s):
        assert ttft_s is not None
        span = float(total_s) - float(ttft_s)
        if span > 0:
            return completion_tokens / span
    return completion_tokens / float(total_s)


def e2e_tok_s(completion_tokens: int, total_s: float | None) -> float | None:
    """Completion tokens divided by the whole request."""
    if completion_tokens <= 0 or not _positive(total_s):
        return None
    assert total_s is not None
    return completion_tokens / float(total_s)


def _positive(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0


def streams_content(content_chunks: object) -> bool:
    """False when the stream delivered two or fewer content or reasoning chunks."""
    if isinstance(content_chunks, bool) or not isinstance(content_chunks, int):
        return True
    return content_chunks > 2


def route_failure(route: str, workspace: str, backend: str, model: str) -> str | None:
    """None when x-portal-route is this workspace, the pinned backend, and the seat model."""
    match = instrument._ROUTE_RE.match(route or "")
    if not match:
        return "missing x-portal-route"
    got = (match.group(1), match.group(2), match.group(3))
    if got[1] != backend:
        return f"route backend {got[1]!r} != pinned {backend!r} ({route})"
    if got != (workspace, backend, model):
        return f"route {route!r} != {workspace};{backend};{model}"
    return None


def judge_measurement(measured: dict[str, Any], expect: dict[str, str]) -> dict[str, Any]:
    """Turn one stream's timings into a valid row or an invalid row with a reason."""
    row = {
        "valid": False,
        "reason": measured.get("error") or "",
        "ttft_s": measured.get("ttft_s"),
        "decode_tps": None,
        "total_s": measured.get("total_s"),
        "completion_tokens": measured.get("completion_tokens"),
        "prompt_tokens": measured.get("prompt_tokens"),
        "route": measured.get("route") or "",
        "http_status": measured.get("http_status"),
        "streaming": streams_content(measured.get("content_chunks")),
        "content_chunks": measured.get("content_chunks"),
        "throughput_tok_s": None,
        "e2e_tok_s": None,
    }
    if row["reason"]:
        return row
    failure = route_failure(
        str(row["route"]), expect["workspace"], expect["backend"], expect["model"]
    )
    if failure:
        row["reason"] = failure
        return row
    if not isinstance(row["ttft_s"], (int, float)):
        row["reason"] = "no content or reasoning delta"
        return row
    tokens = row["completion_tokens"]
    if not isinstance(tokens, int) or isinstance(tokens, bool):
        row["reason"] = "engine usage missing completion_tokens"
        return row
    return _apply_rate(row, measured, tokens)


def _apply_rate(row: dict[str, Any], measured: dict[str, Any], tokens: int) -> dict[str, Any]:
    """Decode tok/s when the stream has many chunks; otherwise throughput_tok_s."""
    total = measured.get("total_s")
    row["e2e_tok_s"] = e2e_tok_s(tokens, total if isinstance(total, (int, float)) else None)
    if row["streaming"] is False:
        rate = throughput_tok_s(
            tokens,
            row["ttft_s"] if isinstance(row["ttft_s"], (int, float)) else None,
            total if isinstance(total, (int, float)) else None,
        )
        if rate is None:
            row["reason"] = "throughput interval is empty"
            return row
        row["throughput_tok_s"] = rate
        row["valid"] = True
        row["reason"] = ""
        return row
    rate = decode_tps(tokens, measured.get("first_s"), measured.get("last_s"))
    if rate is None:
        row["reason"] = "decode interval is empty"
        return row
    row["decode_tps"] = rate
    row["valid"] = True
    row["reason"] = ""
    return row


def _valid(rows: list[dict[str, Any]], arm: str) -> list[dict[str, Any]]:
    return [row for row in rows if row.get("arm") == arm and row.get("valid") is True]


def comparison_metric(rows: list[dict[str, Any]]) -> str:
    """Decode tok/s, or end-to-end throughput when an arm did not stream."""
    valid = [row for row in rows if row.get("valid") is True]
    if any(row.get("streaming") is False for row in valid):
        return "e2e_tok_s"
    return "decode_tps"


def _median_key(metric: str) -> str:
    if metric == "e2e_tok_s":
        return "median_e2e_tok_s"
    return "median_decode_tps"


def _metric_field(metric: str) -> str:
    if metric == "e2e_tok_s":
        return "e2e_tok_s"
    return "decode_tps"


def _e2e_note(metric: str) -> str:
    if metric != "e2e_tok_s":
        return ""
    return "one arm did not stream; compared end-to-end throughput (completion tokens / total_s); "


def run_medians(rows: list[dict[str, Any]], arm: str, field: str = "decode_tps") -> list[float]:
    """One median per repeat that produced a valid row for this rate field."""
    grouped: dict[int, list[float]] = {}
    for row in _valid(rows, arm):
        rate = row.get(field)
        if isinstance(rate, (int, float)) and not isinstance(rate, bool):
            grouped.setdefault(int(row["repeat"]), []).append(float(rate))
    found = []
    for key in sorted(grouped):
        value = median(grouped[key])
        if value is not None:
            found.append(value)
    return found


def _rates(rows: list[dict[str, Any]], field: str) -> list[float]:
    return [
        float(row[field])
        for row in rows
        if isinstance(row.get(field), (int, float)) and not isinstance(row.get(field), bool)
    ]


def arm_stats(rows: list[dict[str, Any]], arm: str) -> dict[str, Any]:
    chosen = _valid(rows, arm)
    ttft = [float(row["ttft_s"]) for row in chosen if isinstance(row.get("ttft_s"), (int, float))]
    total = [
        float(row["total_s"]) for row in chosen if isinstance(row.get("total_s"), (int, float))
    ]
    metric = comparison_metric(rows)
    return {
        "median_ttft_s": median(ttft),
        "median_decode_tps": median(_rates(chosen, "decode_tps")),
        "median_throughput_tok_s": median(_rates(chosen, "throughput_tok_s")),
        "median_e2e_tok_s": median(_rates(chosen, "e2e_tok_s")),
        "p90_total_s": h2h.percentile(total, 90),
        "runs": len(chosen),
        "spread": spread(run_medians(rows, arm, _metric_field(metric))),
    }


def _comparison_text(
    metric: str, cand: float, inc: float, margin: float, floor: float, cleared: bool
) -> str:
    name = "e2e" if metric == "e2e_tok_s" else "decode"
    if cleared:
        detail = (
            f"candidate median {name} {cand:.3f} exceeds incumbent {inc:.3f} "
            f"by {margin:.3f} > spread {floor:.3f}"
        )
    else:
        detail = (
            f"candidate median {name} {cand:.3f} vs incumbent {inc:.3f} "
            f"(delta {margin:.3f}) does not exceed spread {floor:.3f}"
        )
    return f"{_e2e_note(metric)}{detail}"


def decide(rows: list[dict[str, Any]]) -> dict[str, str]:
    """FASTER only when the candidate clears the larger arm's run-to-run spread."""
    metric = comparison_metric(rows)
    reasons = [str(row.get("reason") or "invalid") for row in rows if row.get("valid") is not True]
    if not rows:
        return {"verdict": UNPROVEN, "reason": "no measured rows", "metric": metric}
    if reasons:
        return {"verdict": "invalid", "reason": "; ".join(reasons), "metric": metric}
    stats = {arm: arm_stats(rows, arm) for arm in ARMS}
    cand = stats["candidate"][_median_key(metric)]
    inc = stats["incumbent"][_median_key(metric)]
    cand_spread = stats["candidate"]["spread"]
    inc_spread = stats["incumbent"]["spread"]
    if cand is None or inc is None:
        reason = (
            "end-to-end throughput is missing"
            if metric == "e2e_tok_s"
            else "run-to-run spread is undefined"
        )
        return {"verdict": UNPROVEN, "reason": reason, "metric": metric}
    if cand_spread is None or inc_spread is None:
        return {
            "verdict": UNPROVEN,
            "reason": f"{_e2e_note(metric)}run-to-run spread is undefined",
            "metric": metric,
        }
    margin = float(cand) - float(inc)
    floor = max(float(cand_spread), float(inc_spread))
    cleared = margin > floor
    return {
        "verdict": "FASTER" if cleared else UNPROVEN,
        "reason": _comparison_text(metric, float(cand), float(inc), margin, floor, cleared),
        "metric": metric,
    }


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    verdict = decide(rows)
    return {"arms": {arm: arm_stats(rows, arm) for arm in ARMS}, **verdict}


def format_table(summary: dict[str, Any]) -> str:
    lines = [
        "arm | median TTFT | median decode tok/s | median throughput tok/s | "
        "median e2e tok/s | p90 total | runs"
    ]
    for arm in ARMS:
        row = summary["arms"][arm]
        lines.append(
            " | ".join(
                (
                    arm,
                    _num(row["median_ttft_s"]),
                    _num(row["median_decode_tps"]),
                    _num(row["median_throughput_tok_s"]),
                    _num(row["median_e2e_tok_s"]),
                    _num(row["p90_total_s"]),
                    str(row["runs"]),
                )
            )
        )
    metric = summary.get("metric") or "decode_tps"
    if metric == "e2e_tok_s":
        lines.append(
            "compared: end-to-end throughput (completion tokens / total_s) "
            "because an arm did not stream"
        )
    else:
        lines.append("compared: decode tok/s")
    lines.append(f"verdict: {summary['verdict']}")
    if summary.get("reason"):
        lines.append(f"reason: {summary['reason']}")
    return "\n".join(lines)


def format_invalid(rows: list[dict[str, Any]]) -> str:
    lines = [
        f"invalid | {row.get('arm')} | r{row.get('repeat')} | {row.get('prompt_id')} | {row.get('reason')}"
        for row in rows
        if row.get("valid") is not True
    ]
    return "\n".join(lines)


def _num(value: Any) -> str:
    return (
        f"{float(value):.3f}"
        if isinstance(value, (int, float)) and not isinstance(value, bool)
        else "-"
    )


def load_prompts(seat: str, count: int) -> list[dict[str, str]]:
    data = yaml.safe_load(PROMPTS.read_text(encoding="utf-8")) or {}
    rows = data.get(seat) or []
    if count < 1 or count > len(rows):
        raise runner.Stage3BlockedError(
            f"--prompts {count} but {seat} has {len(rows)} checked-in prompts"
        )
    return [{"id": str(row["id"]), "text": str(row["text"]).strip()} for row in rows[:count]]


def candidate_cell(seat: str) -> dict[str, Any]:
    mode = "plain" if seat == "coding" else "spec"
    matches = [
        cell
        for cell in runner.candidate_cells()
        if cell["seat"] == seat and cell["engine"] == "vllm-mlx" and cell["mode"] == mode
    ]
    if len(matches) != 1:
        raise runner.Stage3BlockedError(f"{seat} vllm-mlx {mode} matched {len(matches)} cells")
    return matches[0]


def incumbent_backend_id() -> str:
    loaded = load_bench_engines(str(runner.REPO / "config" / "backends.yaml"))
    found = [
        str(item["id"])
        for item in loaded.get("backends") or []
        if isinstance(item, dict) and str(item.get("url", "")).rstrip("/").endswith(":8085")
    ]
    if len(found) != 1:
        raise runner.Stage3BlockedError(f"expected one oMLX eval backend, found {found}")
    return found[0]


def host_prepare(cfg: dict[str, Any]) -> dict[str, Any]:
    """Unload oMLX and Ollama, then refuse to start when the swap gate fails."""
    prep = runner._prepare_host(cfg)
    ok, reason = h2h.start_gate(cfg)
    prep["swap_gate_ok"] = ok
    prep["swap_gate_reason"] = reason
    prep["swap_used_mb"] = h2h.swap_now().get("used_mb")
    if not ok:
        text = reason if str(reason).startswith("swap start gate") else f"swap start gate: {reason}"
        raise runner.Stage3BlockedError(text)
    return prep


def request_body(workspace: str, backend: str, prompt: str) -> dict[str, Any]:
    # portal_no_tools keeps the stream one generation. Think and sampling stay unset.
    return {
        "model": workspace,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": MAX_TOKENS,
        "stream": True,
        "stream_options": {"include_usage": True},
        "portal_backend": backend,
        "portal_no_tools": True,
    }


def _completion_tokens(usage: dict[str, Any]) -> int | None:
    raw = usage.get("completion_tokens")
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        return None
    return int(raw)


def _note_delta(delta: dict[str, Any], at_s: float, state: dict[str, Any]) -> None:
    piece = (
        delta.get("content")
        or delta.get("reasoning_content")
        or delta.get("reasoning")
        or delta.get("thinking")
    )
    if not piece:
        return
    state["chunks"] = int(state.get("chunks") or 0) + 1
    if state.get("first") is None:
        state["first"] = at_s
    state["last"] = at_s


def _consume_stream(response: Any, state: dict[str, Any]) -> None:
    for raw in response:
        line = raw.decode("utf-8", "replace").strip()
        if not line.startswith("data:") or line == "data: [DONE]":
            continue
        event = json.loads(line[5:].strip() or "null")
        if not isinstance(event, dict):
            continue
        usage = event.get("usage")
        if isinstance(usage, dict):
            state["usage"] = usage
        for choice in event.get("choices") or []:
            if isinstance(choice, dict):
                _note_delta(choice.get("delta") or {}, time.monotonic() - state["t0"], state)


def stream_once(
    pipeline: str, body: dict[str, Any], timeout_s: float = REQUEST_TIMEOUT_S
) -> dict[str, Any]:
    """One pinned Pipeline stream. Timings are seconds from the request start."""
    url = f"{pipeline.rstrip('/')}/v1/chat/completions"
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers=instrument._pipeline_headers(),
    )
    t0 = time.monotonic()
    state: dict[str, Any] = {"t0": t0, "first": None, "last": None, "usage": {}, "chunks": 0}
    try:
        with urllib.request.urlopen(request, timeout=timeout_s) as response:
            route = response.headers.get("x-portal-route", "")
            status = getattr(response, "status", 200)
            _consume_stream(response, state)
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")[:500]
        header = exc.headers.get("x-portal-route", "") if exc.headers else ""
        return _stream_error(f"HTTP {exc.code}: {raw}", header, exc.code)
    except (OSError, TimeoutError, json.JSONDecodeError, ValueError) as exc:
        return _stream_error(f"{type(exc).__name__}: {exc}", "", None)
    usage = state["usage"] if isinstance(state["usage"], dict) else {}
    return {
        "error": None,
        "route": route,
        "http_status": status,
        "ttft_s": state["first"],
        "first_s": state["first"],
        "last_s": state["last"],
        "total_s": time.monotonic() - t0,
        "completion_tokens": _completion_tokens(usage),
        "prompt_tokens": usage.get("prompt_tokens"),
        "content_chunks": int(state.get("chunks") or 0),
    }


def _stream_error(error: str, route: str, status: int | None) -> dict[str, Any]:
    return {
        "error": error,
        "route": route,
        "http_status": status,
        "ttft_s": None,
        "first_s": None,
        "last_s": None,
        "total_s": None,
        "completion_tokens": None,
        "prompt_tokens": None,
        "content_chunks": 0,
    }


def resident_from_row(row: dict[str, Any], source: str) -> dict[str, Any]:
    """Engine-reported residency only. A missing field stays unavailable."""
    for field in _RESIDENT_FIELDS:
        value = row.get(field)
        if isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0:
            return {"available": True, "field": field, "bytes": value, "source": source}
    return {
        "available": False,
        "reason": "engine did not report a resident-memory field",
        "source": source,
    }


def omlx_resident(cfg: dict[str, Any], model: str) -> dict[str, Any]:
    snap = instrument._omlx_resident_snapshot(h2h.base_url(cfg, "omlx"))
    if not isinstance(snap, dict) or model not in snap:
        return {
            "available": False,
            "reason": "oMLX /v1/models/status did not report actual_size for this model",
            "source": "GET /v1/models/status actual_size",
            "snapshot": snap,
        }
    return {
        "available": True,
        "field": "actual_size",
        "bytes": snap[model],
        "source": "GET /v1/models/status actual_size",
    }


def managed_resident(base: str, model: str) -> dict[str, Any]:
    try:
        payload = runner._models_payload(base)
    except (
        OSError,
        TimeoutError,
        runner.CandidateHTTPError,
        json.JSONDecodeError,
        ValueError,
    ) as exc:
        return {
            "available": False,
            "reason": f"model list unread: {exc}",
            "source": "GET /v1/models",
        }
    body = payload.get("json") if isinstance(payload, dict) else {}
    return resident_from_row(
        runner._model_row(body if isinstance(body, dict) else {}, model), "GET /v1/models"
    )


def _blank_row(arm: str, repeat: int, prompt_id: str, reason: str) -> dict[str, Any]:
    return {
        "arm": arm,
        "repeat": repeat,
        "prompt_id": prompt_id,
        "valid": False,
        "reason": reason,
        "ttft_s": None,
        "decode_tps": None,
        "throughput_tok_s": None,
        "e2e_tok_s": None,
        "streaming": None,
        "total_s": None,
        "completion_tokens": None,
        "route": "",
    }


def one_request(
    pipeline: str,
    expect: dict[str, str],
    prompt: dict[str, str],
    arm: str,
    repeat: int,
) -> dict[str, Any]:
    measured = stream_once(
        pipeline, request_body(expect["workspace"], expect["backend"], prompt["text"])
    )
    row = judge_measurement(measured, expect)
    row.update(arm=arm, repeat=repeat, prompt_id=prompt["id"])
    state = "valid" if row["valid"] else "invalid"
    print(
        f"{arm} | r{repeat} | {prompt['id']} | {state} | streaming={row.get('streaming')} | "
        f"ttft={_num(row['ttft_s'])} | tps={_num(row['decode_tps'])} | "
        f"throughput={_num(row.get('throughput_tok_s'))} | e2e={_num(row.get('e2e_tok_s'))} | "
        f"tokens={row['completion_tokens']} | {row['reason']}",
        flush=True,
    )
    return row


def _stop_candidate(cfg: dict[str, Any], engine: str) -> str | None:
    try:
        h2h.stop_managed(cfg, engine)
    except (OSError, SystemExit, TimeoutError) as exc:
        return f"{type(exc).__name__}: {exc}"
    return None


def measure_arm(
    cfg: dict[str, Any],
    pipeline: str,
    expect: dict[str, str],
    prompts: list[dict[str, str]],
    arm: str,
    repeat: int,
    log_dir: Path | None,
) -> dict[str, Any]:
    """Host prep, optional launch, untimed warm-up, pinned prompts, and memory."""
    record: dict[str, Any] = {
        "arm": arm,
        "repeat": repeat,
        "backend": expect["backend"],
        "rows": [],
        "error": None,
        "stop_error": None,
        "swap_before_mb": h2h.swap_now().get("used_mb"),
        "swap_after_mb": None,
    }
    try:
        record["host_prep"] = host_prepare(cfg)
        if arm == "candidate":
            _measure_candidate(cfg, pipeline, expect, prompts, repeat, log_dir, record)
        else:
            _measure_loaded(cfg, pipeline, expect, prompts, arm, repeat, record)
    except (
        runner.Stage3BlockedError,
        OSError,
        TimeoutError,
        SystemExit,
        urllib.error.URLError,
    ) as exc:
        record["error"] = f"{type(exc).__name__}: {exc}"
        if not record["rows"]:
            record["rows"] = [_blank_row(arm, repeat, "-", record["error"])]
        print(f"{arm} | r{repeat} | invalid | {record['error']}", flush=True)
    finally:
        record["swap_after_mb"] = h2h.swap_now().get("used_mb")
    return record


def warmup_body(workspace: str, backend: str) -> dict[str, Any]:
    """Same seat as the timed run, with a short untimed generation."""
    body = request_body(workspace, backend, WARMUP_PROMPT)
    body["max_tokens"] = WARMUP_MAX_TOKENS
    return body


def judge_warmup(measured: dict[str, Any], expect: dict[str, str]) -> dict[str, Any]:
    """Warm-up wall time. A transport or route failure is an error, not a sample."""
    failure = measured.get("error") or route_failure(
        str(measured.get("route") or ""), expect["workspace"], expect["backend"], expect["model"]
    )
    total = measured.get("total_s")
    return {
        "warmup_s": float(total) if _non_negative(total) else None,
        "ttft_s": measured.get("ttft_s"),
        "error": failure or None,
        "route": measured.get("route") or "",
        "http_status": measured.get("http_status"),
        "completion_tokens": measured.get("completion_tokens"),
        "max_tokens": WARMUP_MAX_TOKENS,
    }


def _non_negative(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0


def _warmup(pipeline: str, expect: dict[str, str], arm: str, repeat: int) -> dict[str, Any]:
    measured = stream_once(pipeline, warmup_body(expect["workspace"], expect["backend"]))
    row = judge_warmup(measured, expect)
    print(
        f"warmup | {arm} | r{repeat} | {_num(row['warmup_s'])}s | {row['error'] or 'ok'}",
        flush=True,
    )
    return row


def _measure_loaded(
    cfg: dict[str, Any],
    pipeline: str,
    expect: dict[str, str],
    prompts: list[dict[str, str]],
    arm: str,
    repeat: int,
    record: dict[str, Any],
) -> None:
    """Time prompts after one untimed warm-up on this seat."""
    health = runner.wait_pipeline_eval_backend(pipeline, expect["backend"])
    record["pipeline_health"] = {"ready": True, "backend_id": health.get("backend", {}).get("id")}
    warmup = _warmup(pipeline, expect, arm, repeat)
    record["warmup"] = warmup
    if warmup.get("error"):
        record["rows"] = [_blank_row(arm, repeat, "warmup", f"warm-up failed: {warmup['error']}")]
    else:
        record["rows"] = [one_request(pipeline, expect, prompt, arm, repeat) for prompt in prompts]
    record["resident_memory"] = _resident(cfg, expect, arm)


def _measure_candidate(
    cfg: dict[str, Any],
    pipeline: str,
    expect: dict[str, str],
    prompts: list[dict[str, str]],
    repeat: int,
    log_dir: Path | None,
    record: dict[str, Any],
) -> None:
    port = int(expect["port"])
    if h2h.pid_on_port(port):
        raise runner.Stage3BlockedError(f"candidate port {port} is already occupied")
    try:
        _start_candidate(cfg, expect, log_dir, record)
        _measure_loaded(cfg, pipeline, expect, prompts, "candidate", repeat, record)
    finally:
        if h2h._state_file(expect["engine"]).exists():
            record["stop_error"] = _stop_candidate(cfg, expect["engine"])


def _start_candidate(
    cfg: dict[str, Any], expect: dict[str, str], log_dir: Path | None, record: dict[str, Any]
) -> None:
    logs = None
    if log_dir is not None:
        logs = (log_dir / "engine.stdout.log", log_dir / "engine.stderr.log")
    started = h2h.start_managed(
        cfg, expect["engine"], expect["model_key"], expect["mode"], log_paths=logs
    )
    record["ready_s"] = started.get("ready_s")
    record["argv"] = started.get("argv")


def _resident(cfg: dict[str, Any], expect: dict[str, str], arm: str) -> dict[str, Any]:
    if arm == "incumbent":
        return omlx_resident(cfg, expect["model"])
    return managed_resident(expect["base"], expect["model"])


def _expects(cell: dict[str, Any], incumbent: str) -> dict[str, dict[str, str]]:
    shared = {"workspace": cell["workspace"], "model": cell["model_hint"]}
    return {
        "candidate": {
            **shared,
            "backend": cell["backend"],
            "engine": cell["engine"],
            "mode": cell["mode"],
            "model_key": cell["model"],
            "port": str(cell["port"]),
            "base": cell["base"],
        },
        "incumbent": {**shared, "backend": incumbent, "engine": "omlx", "mode": "incumbent"},
    }


def run_seat(seat: str, prompts_n: int, repeats: int, pipeline: str) -> dict[str, Any]:
    """Interleave candidate then incumbent, once per repeat, and write nothing itself."""
    root = runner.data_root()
    runner._configure_results(root)
    cfg = h2h.load_config()
    cell = candidate_cell(seat)
    prompts = load_prompts(seat, prompts_n)
    expects = _expects(cell, incumbent_backend_id())
    build = runner.current_build()
    rows: list[dict[str, Any]] = []
    arms: list[dict[str, Any]] = []
    stop_error = None
    with h2h.single_flight():
        for repeat in range(repeats):
            rows, arms, stop_error = _one_repeat(
                rows, arms, repeat, expects, prompts, pipeline, cfg, root, build, seat
            )
            if stop_error:
                break
    summary = summarize(rows)
    return _receipt(
        build,
        seat,
        cell,
        expects,
        pipeline,
        prompts_n,
        repeats,
        prompts,
        rows,
        arms,
        summary,
        stop_error,
    )


def _one_repeat(
    rows: list[dict[str, Any]],
    arms: list[dict[str, Any]],
    repeat: int,
    expects: dict[str, dict[str, str]],
    prompts: list[dict[str, str]],
    pipeline: str,
    cfg: dict[str, Any],
    root: Path,
    build: str,
    seat: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str | None]:
    stop_error = None
    for arm in ARMS:
        log_dir = root / "engine_eval" / "speed" / build / "logs" / seat / arm / f"r{repeat}"
        measured = measure_arm(cfg, pipeline, expects[arm], prompts, arm, repeat, log_dir)
        arms.append({key: value for key, value in measured.items() if key != "rows"})
        rows.extend(measured["rows"])
        if measured.get("stop_error"):
            stop_error = str(measured["stop_error"])
            rows.append(_blank_row(arm, repeat, "-", f"stop failed: {stop_error}"))
            break
    return rows, arms, stop_error


def _receipt(
    build: str,
    seat: str,
    cell: dict[str, Any],
    expects: dict[str, dict[str, str]],
    pipeline: str,
    prompts_n: int,
    repeats: int,
    prompts: list[dict[str, str]],
    rows: list[dict[str, Any]],
    arms: list[dict[str, Any]],
    summary: dict[str, Any],
    stop_error: str | None,
) -> dict[str, Any]:
    return {
        "build": build,
        "seat": seat,
        "workspace": cell["workspace"],
        "model": cell["model_hint"],
        "candidate": {
            "engine": cell["engine"],
            "mode": cell["mode"],
            "backend": expects["candidate"]["backend"],
            "port": cell["port"],
        },
        "incumbent": {"engine": "omlx", "backend": expects["incumbent"]["backend"]},
        "pipeline": pipeline,
        "prompts": prompts_n,
        "repeats": repeats,
        "prompt_ids": [item["id"] for item in prompts],
        "max_tokens": MAX_TOKENS,
        "arms": arms,
        "rows": rows,
        "summary": summary,
        "metric": summary.get("metric"),
        "verdict": summary["verdict"],
        "reason": summary["reason"],
        "stop_error": stop_error,
    }


def receipt_path(root: Path, build: str, seat: str) -> Path:
    return root / "engine_eval" / "speed" / build / f"{seat}.json"


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Pipeline decode-speed A/B against the oMLX incumbent"
    )
    parser.add_argument("--seat", required=True, choices=("coding", "daily-moe"))
    parser.add_argument("--prompts", type=int, required=True)
    parser.add_argument("--repeats", type=int, required=True)
    parser.add_argument("--pipeline", default=PIPELINE)
    args = parser.parse_args(argv)
    if args.prompts < 1 or args.repeats < 1:
        parser.error("--prompts and --repeats must be >= 1")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        receipt = run_seat(args.seat, args.prompts, args.repeats, args.pipeline)
    except (runner.Stage3BlockedError, OSError, SystemExit, urllib.error.URLError) as exc:
        print(f"invalid | {exc}", flush=True)
        return 1
    root = runner.data_root()
    path = receipt_path(root, str(receipt["build"]), args.seat)
    runner._write_json(path, receipt)
    invalid = format_invalid(receipt["rows"])
    if invalid:
        print(invalid, flush=True)
    print(format_table(receipt["summary"]), flush=True)
    print(f"receipt: {path}", flush=True)
    if receipt.get("stop_error"):
        print(f"stop failed: {receipt['stop_error']}", flush=True)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
