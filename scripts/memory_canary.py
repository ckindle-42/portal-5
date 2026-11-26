#!/usr/bin/env python3
"""Memory canary: near-limit back-to-back seat pairs, live memory + load_guard verdict."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

from scripts import prodpath

REPO = Path(__file__).resolve().parents[1]
OWUI = os.environ.get("CANARY_OWUI", "http://localhost:8080")
PIPE = os.environ.get("CANARY_PIPE", "http://localhost:9099")
OLLAMA = os.environ.get("CANARY_OLLAMA", "http://localhost:11434")
OMLX = os.environ.get("CANARY_OMLX", "http://localhost:8085")
CONTAINER = os.environ.get("CANARY_CONTAINER", "portal5-pipeline")
GIB = 1024**3
ENGINE_RSS_PATTERNS = ("omlx-server", "ollama serve", "llama-server")


@dataclass(frozen=True)
class Seat:
    label: str  # workspace id sent to OWUI ("ws" or "ws::variant")
    context_limit: int  # declared window in tokens


@dataclass(frozen=True)
class Pair:
    name: str
    a: Seat
    b: Seat


# Heaviest realistic back-to-back co-residencies across both engines (2026-11-25
# window upgrades). auto-security seats declare no context_limit; Inkling runs
# its native window, capped here at the canary target.
DEFAULT_PAIRS: list[Pair] = [
    Pair(
        "compliance-64k-vs-daily-32k",
        Seat("auto-compliance", 65536),
        Seat(
            "auto-daily",
            32768,
        ),
    ),
    Pair(
        "uncensored-inkling-vs-toolsspecialist-32k",
        Seat("auto-general-uncensored", 131072),
        Seat("tools-specialist", 32768),
    ),
    Pair(
        "purpleteam-deep-inkling-vs-documents-32k",
        Seat("auto-security::purpleteam-deep", 131072),
        Seat("auto-documents", 32768),
    ),
    Pair(
        "daily-inkling-256k-vs-compliance-64k",
        Seat("auto-daily::inkling", 131072),
        Seat("auto-compliance", 65536),
    ),
    Pair(
        "vision-16k-vs-toolsspecialist-32k",
        Seat("auto-vision", 16384),
        Seat("tools-specialist", 32768),
    ),
]


def env(name: str) -> str:
    if os.environ.get(name):
        return os.environ[name]
    dot = REPO / ".env"
    if dot.exists():
        for line in dot.read_text().splitlines():
            k, _, v = line.strip().partition("=")
            if k == name:
                return v.strip().strip("'\"")
    return ""


# ── parsers (unit-tested; no live access) ─────────────────────────────────────

_RE_EVICTED = re.compile(
    r"load_guard: evicted (?P<model>\S+) on (?P<engine>\w+), (?P<gib>[\d.]+) GiB freed \(reason=(?P<reason>[^)]+)\)"
)
_RE_EVICTION_PASS = re.compile(
    r"load_guard: eviction pass for (?P<for>.+?): shortage_gib=(?P<gib>[\d.]+) evicted=(?P<models>\S+)"
)
_RE_NEEDS = re.compile(
    r"load_guard: (?P<model>\S+) needs (?P<need>[\d.]+) GiB, (?P<avail>[\d.]+) available"
)
_RE_REFUSED = re.compile(
    r"Cannot load (?P<model>.+?): projected memory (?P<need>[\d.]+) GiB would exceed host headroom (?P<avail>[\d.]+) GiB"
)
_RE_PROTECT = re.compile(r"load_guard: protecting (?P<engine>\w+):(?P<model>\S+) for")


def parse_load_guard_log(text: str) -> list[dict]:
    """Load-guard admission/eviction events out of raw pipeline log text."""
    events: list[dict] = []
    for line in text.splitlines():
        if "load_guard" not in line and "Cannot load" not in line:
            continue
        for kind, rx in (
            ("evicted", _RE_EVICTED),
            ("eviction_pass", _RE_EVICTION_PASS),
            ("needs_wait", _RE_NEEDS),
            ("refused", _RE_REFUSED),
            ("protect", _RE_PROTECT),
        ):
            m = rx.search(line)
            if m:
                events.append({"kind": kind, **m.groupdict(), "line": line.strip()[:220]})
                break
    return events


_PAGE = re.compile(r"page size of (\d+) bytes")
_WIRED = re.compile(r"Pages wired down:\s+(\d+)")
_FREE = re.compile(r"Pages free:\s+(\d+)")


def parse_vm_stat(text: str) -> dict:
    """vm_stat output → wired/free bytes."""
    page = int((_PAGE.search(text) or [None, 16384])[1])
    wired = int((_WIRED.search(text) or [None, 0])[1])
    free = int((_FREE.search(text) or [None, 0])[1])
    return {"page_size": page, "wired_bytes": wired * page, "free_bytes": free * page}


_SWAP_USED = re.compile(r"used\s*=\s*([\d.]+)([MGT])", re.IGNORECASE)
_SWAP_FREE = re.compile(r"free\s*=\s*([\d.]+)([MGT])", re.IGNORECASE)
_UNITS = {"M": 1024**2, "G": 1024**3, "T": 1024**4}


def parse_swap_usage(text: str) -> dict:
    """`sysctl vm.swapusage` output → used/free bytes."""
    out = {"used_bytes": 0, "free_bytes": 0}
    for key, rx in (("used_bytes", _SWAP_USED), ("free_bytes", _SWAP_FREE)):
        m = rx.search(text)
        if m:
            out[key] = int(float(m.group(1)) * _UNITS[m.group(2).upper()])
    return out


def parse_ps_rss(text: str) -> dict:
    """`ps -axo pid=,rss=,command=` rows → engine RSS totals keyed by pattern."""
    totals = dict.fromkeys(ENGINE_RSS_PATTERNS, 0)
    procs = []
    for line in text.splitlines():
        parts = line.strip().split(None, 2)
        if len(parts) < 3 or not parts[0].isdigit() or not parts[1].isdigit():
            continue
        pid, rss_kib, cmd = int(parts[0]), int(parts[1]), parts[2]
        for pat in ENGINE_RSS_PATTERNS:
            if pat in cmd:
                totals[pat] += rss_kib * 1024
                procs.append({"pid": pid, "rss_bytes": rss_kib * 1024, "match": pat})
    return {"totals": totals, "procs": procs}


def parse_prometheus_counters(text: str, prefix: str) -> dict[str, float]:
    """Sum counter samples by metric name (labels folded) for one prefix."""
    out: dict[str, float] = {}
    for line in text.splitlines():
        if line.startswith("#") or not line.startswith(prefix):
            continue
        name = line.split("{", 1)[0]
        sample = line.rsplit(" ", 1)[-1]
        try:
            out[name] = out.get(name, 0.0) + float(sample)
        except ValueError:
            continue
    return out


def parse_ollama_ps(payload: dict) -> dict[str, int]:
    """/api/ps payload → resident model → size bytes."""
    out = {}
    for m in payload.get("models") or []:
        if isinstance(m, dict) and m.get("name"):
            out[str(m["name"])] = int(m.get("size") or 0)
    return out


def parse_omlx_status(payload: dict) -> dict:
    """/v1/models/status payload → loaded models + final ceiling bytes."""
    loaded = {}
    for m in payload.get("models") or []:
        if isinstance(m, dict) and m.get("loaded") and m.get("id"):
            loaded[str(m["id"])] = float(m.get("estimated_size") or 0)
    ceiling = payload.get("final_ceiling")
    return {"loaded": loaded, "final_ceiling": float(ceiling) if ceiling else None}


def build_filler_prompt(
    target_tokens: int, chars_per_token: float, baseline_tokens: int = 0
) -> str:
    """Build deterministic filler from a seat's measured short-prompt ratio."""
    prefix = "Read this context fill and reply READY after reading it.\n"
    chars = max(int((target_tokens - baseline_tokens) * chars_per_token) - len(prefix), 1)
    return prefix + "context " * ((chars + len("context ") - 1) // len("context "))


def cross_engine_evictions(
    events: list[dict], pre_resident: dict[str, set[str]], pair_models: set[str]
) -> list[dict]:
    """Evictions of models that were resident before the pair and are not its seats."""
    out = []
    for ev in events:
        if ev["kind"] != "evicted":
            continue
        model, engine = ev["model"], ev["engine"]
        if model in pair_models:
            continue
        was = pre_resident.get("omlx" if engine == "omlx" else "ollama", set())
        if any(model in r or r in model for r in was):
            out.append(ev)
    return out


# ── live snapshots (orchestrator-run only) ────────────────────────────────────


def _get_json(url: str, headers: dict | None = None, timeout: int = 30):
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310
        return json.load(r)


def _run(cmd: list[str], timeout: int = 30) -> str:
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    return r.stdout


def snap_host() -> dict:
    vm = parse_vm_stat(_run(["vm_stat"]))
    swap = parse_swap_usage(_run(["sysctl", "vm.swapusage"]))
    rss = parse_ps_rss(_run(["ps", "-axo", "pid=,rss=,command="]))
    return {"vm": vm, "swap": swap, "rss": rss}


def snap_engines() -> dict:
    ollama = {}
    try:
        ollama = parse_ollama_ps(_get_json(f"{OLLAMA}/api/ps"))
    except Exception as e:  # noqa: BLE001
        ollama = {"_error": str(e)[:120]}
    omlx = {"loaded": {}, "final_ceiling": None}
    try:
        headers = {}
        key = env("OMLX_API_KEY")
        if key:
            headers["Authorization"] = f"Bearer {key}"
        omlx = parse_omlx_status(_get_json(f"{OMLX}/v1/models/status", headers))
    except Exception as e:  # noqa: BLE001
        omlx = {"loaded": {}, "final_ceiling": None, "_error": str(e)[:120]}
    return {"ollama": ollama, "omlx": omlx}


def snap_metrics() -> dict[str, float]:
    try:
        req = urllib.request.Request(f"{PIPE}/metrics")
        with urllib.request.urlopen(req, timeout=15) as r:  # noqa: S310
            return parse_prometheus_counters(r.read().decode(), "portal5_load_guard_")
    except Exception:  # noqa: BLE001
        return {}


def docker_logs_since(epoch: float) -> str | None:
    try:
        result = subprocess.run(
            ["docker", "logs", CONTAINER, "--since", f"{epoch:.0f}"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        return result.stdout if result.returncode == 0 else None
    except Exception:  # noqa: BLE001
        return None


# ── turn + pair execution ─────────────────────────────────────────────────────


@dataclass
class TurnResult:
    seat: str
    http_status: int = 0
    prompt_tokens: int = 0
    fill_ratio: float = 0.0
    wall_s: float = 0.0
    outcome: str = "no-trace"
    error: str = ""
    backend: str = ""
    model: str = ""
    trace_matched: bool = False
    valid: bool = False
    validation_errors: list[str] = field(default_factory=list)


def run_turn(seat: Seat, args, chars_per_token: float) -> TurnResult:
    configured = prodpath.configured_target(seat.label)
    prompt = build_filler_prompt(
        int(seat.context_limit * args.fill),
        chars_per_token,
        args.baseline_tokens[seat.label],
    )
    receipt = prodpath.stream_chat(
        configured,
        prodpath.preflight_messages(configured, prompt=prompt),
        owui_url=OWUI,
        pipeline_url=PIPE,
        owui_key=env("OWUI_API_KEY"),
        pipeline_key=env("PIPELINE_API_KEY"),
        timeout=args.timeout,
        body_extra={"max_tokens": args.max_tokens},
    )
    res = TurnResult(
        seat.label,
        http_status=receipt.status,
        prompt_tokens=receipt.prompt_tokens,
        fill_ratio=receipt.prompt_tokens / seat.context_limit if seat.context_limit else 0.0,
        wall_s=round(receipt.wall_s, 1),
        outcome=receipt.outcome,
        error=receipt.error,
        backend=receipt.backend,
        model=receipt.model,
        trace_matched=receipt.trace is not None,
    )
    if receipt.status != 200:
        res.validation_errors.append(f"HTTP {receipt.status}: {receipt.error or 'no response'}")
    if receipt.prompt_tokens <= 0:
        res.validation_errors.append("no measured prompt_tokens")
    if receipt.error:
        res.validation_errors.append(f"stream error: {receipt.error}")
    if not 0.80 <= res.fill_ratio <= 0.95 or receipt.prompt_tokens > seat.context_limit:
        res.validation_errors.append(
            f"measured fill {res.fill_ratio:.3f} is outside 0.80-0.95 of {seat.context_limit} tokens"
        )
    res.validation_errors.extend(prodpath.trace_failures(configured, receipt.trace))
    if receipt.trace and (not receipt.backend or not receipt.model):
        res.validation_errors.append("trace does not name the served backend and model")
    res.valid = not res.validation_errors
    return res


@dataclass
class PairResult:
    pair: str
    turns: list[TurnResult] = field(default_factory=list)
    pre: dict = field(default_factory=dict)
    post: dict = field(default_factory=dict)
    events: list[dict] = field(default_factory=list)
    cross_evictions: list[dict] = field(default_factory=list)
    swap_growth_gib: float = 0.0
    metrics_delta: dict = field(default_factory=dict)
    load_guard_log_parsed: bool = False
    verdict: str = "?"
    reasons: list[str] = field(default_factory=list)


def judge(pr: PairResult, args) -> None:
    invalid = [f"{turn.seat}: {reason}" for turn in pr.turns for reason in turn.validation_errors]
    for turn in pr.turns:
        if turn.http_status != 200:
            invalid.append(f"{turn.seat}: HTTP {turn.http_status}")
        if turn.prompt_tokens <= 0:
            invalid.append(f"{turn.seat}: no measured prompt_tokens")
        if not 0.80 <= turn.fill_ratio <= 0.95:
            invalid.append(f"{turn.seat}: fill {turn.fill_ratio:.3f} is outside 0.80-0.95")
        if turn.outcome not in prodpath.SUCCESS_OUTCOMES:
            invalid.append(f"{turn.seat}: trace outcome {turn.outcome!r} is not successful")
        if not turn.trace_matched:
            invalid.append(f"{turn.seat}: no matched Pipeline trace")
        if not turn.backend or not turn.model:
            invalid.append(f"{turn.seat}: trace has no served backend/model")
        if turn.error:
            invalid.append(f"{turn.seat}: stream error: {turn.error}")
    if not pr.load_guard_log_parsed:
        invalid.append("load_guard log window was not parsed")
    if invalid or any(not turn.valid for turn in pr.turns):
        pr.reasons = invalid or [
            f"{turn.seat}: turn is INVALID" for turn in pr.turns if not turn.valid
        ]
        pr.verdict = "INVALID"
        return
    reasons = []
    for ev in pr.cross_evictions:
        reasons.append(
            f"unplanned eviction of resident {ev['engine']}:{ev['model']} ({ev['gib']} GiB)"
        )
    if pr.swap_growth_gib > args.max_swap_growth_gib:
        reasons.append(f"swap grew {pr.swap_growth_gib:.2f} GiB > {args.max_swap_growth_gib}")
    pr.reasons = reasons
    pr.verdict = "FAIL" if reasons else "PASS"


def run_pair(pair: Pair, args, chars_per_token: dict[str, float]) -> PairResult:
    pr = PairResult(pair.name)
    pre_engines, pre_host, pre_metrics = snap_engines(), snap_host(), snap_metrics()
    pre_resident = {
        "ollama": set(pre_engines["ollama"]),
        "omlx": set(pre_engines["omlx"]["loaded"]),
    }
    t0 = time.time()
    for seat in (pair.a, pair.b):
        if args.pause_s:
            time.sleep(args.pause_s)
        pr.turns.append(run_turn(seat, args, chars_per_token[seat.label]))
    logs = docker_logs_since(t0 - 2)
    pr.load_guard_log_parsed = logs is not None
    pr.events = parse_load_guard_log(logs or "")
    pair_models = {pair.a.model, pair.b.model}
    pr.cross_evictions = cross_engine_evictions(pr.events, pre_resident, pair_models)
    post_engines, post_host, post_metrics = snap_engines(), snap_host(), snap_metrics()
    pr.pre = {"engines": pre_engines, "host": pre_host, "metrics": pre_metrics}
    pr.post = {"engines": post_engines, "host": post_host, "metrics": post_metrics}
    pr.swap_growth_gib = round(
        (post_host["swap"]["used_bytes"] - pre_host["swap"]["used_bytes"]) / GIB, 2
    )
    pr.metrics_delta = {
        k: round(post_metrics.get(k, 0) - pre_metrics.get(k, 0), 3)
        for k in set(pre_metrics) | set(post_metrics)
    }
    judge(pr, args)
    return pr


def render_table(results: list[PairResult]) -> str:
    head = (
        "| pair | seat | HTTP | prompt_tok | fill | wall_s | outcome | served | evictions | "
        "swapΔ GiB | RSS Δ GiB (omlx/ollama-runner) | verdict |"
    )
    sep = "|" + "---|" * 12
    rows = [head, sep]
    for pr in results:
        rss_pre = pr.pre.get("host", {}).get("rss", {}).get("totals", {})
        rss_post = pr.post.get("host", {}).get("rss", {}).get("totals", {})
        d_omlx = (rss_post.get("omlx-server", 0) - rss_pre.get("omlx-server", 0)) / GIB
        d_oll = (
            rss_post.get("llama-server", 0)
            + rss_post.get("ollama serve", 0)
            - rss_pre.get("llama-server", 0)
            - rss_pre.get("ollama serve", 0)
        ) / GIB
        for i, t in enumerate(pr.turns):
            ev = ",".join(f"{e['engine']}:{e['model']}" for e in pr.cross_evictions) or "-"
            rows.append(
                f"| {pr.pair if i == 0 else ''} | {t.seat} | {t.http_status or '-'} | "
                f"{t.prompt_tokens} | {t.fill_ratio:.3f} | {t.wall_s} | {t.outcome} | "
                f"{t.backend}/{t.model} | {ev if i == 0 else ''} | {pr.swap_growth_gib if i == 0 else ''} | "
                f"{d_omlx:+.1f}/{d_oll:+.1f} | {pr.verdict if i == 0 else ''} |"
            )
        for r in pr.reasons:
            rows.append(f"| | ⚠ {r} |{' |' * 10}")
    return "\n".join(rows)


def preflight_pairs(
    pairs: list[Pair], args
) -> tuple[list[prodpath.PreflightResult], dict[str, float], dict[str, int]] | None:
    targets = {}
    try:
        for pair in pairs:
            for seat in (pair.a, pair.b):
                if seat.label not in targets:
                    targets[seat.label] = prodpath.configured_target(seat.label)
    except ValueError as exc:
        print(f"preflight setup failed: {exc}", file=sys.stderr)
        return None
    results = prodpath.preflight(
        list(targets.values()),
        owui_url=OWUI,
        pipeline_url=PIPE,
        owui_key=env("OWUI_API_KEY"),
        pipeline_key=env("PIPELINE_API_KEY"),
        timeout=min(args.timeout, 180),
    )
    if not all(result.ok for result in results):
        print("preflight failed; no canary rows were run", file=sys.stderr)
        return None
    calibration = {}
    for result in results:
        measured = prodpath.calibrate_context_fill(
            result.target,
            result.receipt,
            owui_url=OWUI,
            pipeline_url=PIPE,
            owui_key=env("OWUI_API_KEY"),
            pipeline_key=env("PIPELINE_API_KEY"),
            timeout=min(args.timeout, 180),
        )
        if measured is None:
            return None
        calibration[result.target.workspace] = measured
    ratios = {workspace: values[0] for workspace, values in calibration.items()}
    baselines = {workspace: values[1] for workspace, values in calibration.items()}
    return results, ratios, baselines


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pairs", default="", help="comma-separated pair names (default: all)")
    ap.add_argument("--list", action="store_true", help="list pair names and exit")
    ap.add_argument(
        "--preflight-only", action="store_true", help="run seat checks without canary rows"
    )
    ap.add_argument("--fill", type=float, default=0.85, help="target prompt fill of each window")
    ap.add_argument("--max-tokens", type=int, default=256)
    ap.add_argument("--timeout", type=int, default=900, help="per-turn seconds")
    ap.add_argument("--pause-s", type=int, default=0, help="pause before each turn")
    ap.add_argument("--max-swap-growth-gib", type=float, default=1.0)
    ap.add_argument("--json", default="", help="write full results JSON here")
    args = ap.parse_args(argv)
    pairs = DEFAULT_PAIRS
    if args.pairs:
        want = {p.strip() for p in args.pairs.split(",")}
        pairs = [p for p in DEFAULT_PAIRS if p.name in want]
    if args.list:
        for p in DEFAULT_PAIRS:
            print(
                f"{p.name}\n  A {p.a.label} [{p.a.engine} {p.a.model} @{p.a.context_limit}]\n  B {p.b.label} [{p.b.engine} {p.b.model} @{p.b.context_limit}]"
            )
        return 0
    if not pairs:
        print("no matching pairs", file=sys.stderr)
        return 2
    if not 0.80 <= args.fill <= 0.95:
        ap.error("--fill must be between 0.80 and 0.95")
    preflight = preflight_pairs(pairs, args)
    if preflight is None:
        return 1
    reports, chars_per_token, baseline_tokens = preflight
    if args.preflight_only:
        print(f"preflight passed for {len(reports)} seat(s)")
        return 0
    # Keep tokenization calibration local to each seat, including its system/tool prompt overhead.
    args.baseline_tokens = baseline_tokens
    results = []
    for pair in pairs:
        print(f"== pair {pair.name} ==", flush=True)
        results.append(run_pair(pair, args, chars_per_token))
    print(render_table(results))
    if args.json:
        Path(args.json).write_text(json.dumps([vars(r) for r in results], indent=1, default=str))
    return 0 if all(r.verdict == "PASS" for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
