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

REPO = Path(__file__).resolve().parents[1]
OWUI = os.environ.get("CANARY_OWUI", "http://localhost:8080")
PIPE = os.environ.get("CANARY_PIPE", "http://localhost:9099")
OLLAMA = os.environ.get("CANARY_OLLAMA", "http://localhost:11434")
OMLX = os.environ.get("CANARY_OMLX", "http://localhost:8085")
CONTAINER = os.environ.get("CANARY_CONTAINER", "portal5-pipeline")
GIB = 1024**3
CHARS_PER_TOKEN = 4  # filler is "tokNNNN " words; measured fill ratio is reported per turn
ENGINE_RSS_PATTERNS = ("omlx-server", "ollama serve", "llama-server")


@dataclass(frozen=True)
class Seat:
    label: str  # workspace id sent to OWUI ("ws" or "ws::variant")
    engine: str  # expected serving engine: "ollama" | "omlx"
    model: str  # expected served model id
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
        Seat("auto-compliance", "omlx", "Qwen3.8-27B-oQ4e-mtp", 65536),
        Seat(
            "auto-daily",
            "ollama",
            "hf.co/bartowski/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-GGUF:Q4_K_M-ctx32k",
            32768,
        ),
    ),
    Pair(
        "uncensored-inkling-vs-toolsspecialist-32k",
        Seat("auto-general-uncensored", "omlx", "Inkling-2-Mini-abliterated-oQ4e-mtp", 131072),
        Seat("tools-specialist", "omlx", "unsloth--Qwen3.6-35B-A3B-UD-MLX-4bit", 32768),
    ),
    Pair(
        "purpleteam-deep-inkling-vs-documents-32k",
        Seat(
            "auto-security::purpleteam-deep", "omlx", "Inkling-2-Mini-abliterated-oQ4e-mtp", 131072
        ),
        Seat("auto-documents", "ollama", "gemma4:26b-a4b-it-qat-ctx32k", 32768),
    ),
    Pair(
        "daily-inkling-256k-vs-compliance-64k",
        Seat("auto-daily::inkling", "ollama", "inkling-2-mini:ctx256k", 131072),
        Seat("auto-compliance", "omlx", "Qwen3.8-27B-oQ4e-mtp", 65536),
    ),
    Pair(
        "vision-16k-vs-toolsspecialist-32k",
        Seat("auto-vision", "ollama", "qwen3-vl:32b-ctx16k", 16384),
        Seat("tools-specialist", "omlx", "unsloth--Qwen3.6-35B-A3B-UD-MLX-4bit", 32768),
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


def build_filler_prompt(target_tokens: int) -> str:
    """Deterministic filler aimed at ``target_tokens`` (≈4 chars/token)."""
    words = []
    total = 0
    chars = max(target_tokens, 1) * CHARS_PER_TOKEN
    i = 0
    while total < chars:
        w = f"tok{i % 10000}"
        total += len(w) + (1 if words else 0)
        words.append(w)
        i += 1
    return "Below is a context fill. After reading it, reply with the single word OK.\n" + " ".join(
        words
    )


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


def docker_logs_since(epoch: float) -> str:
    try:
        return _run(["docker", "logs", CONTAINER, "--since", f"{epoch:.0f}"], timeout=60)
    except Exception:  # noqa: BLE001
        return ""


def newest_trace(workspace: str, since: float) -> dict | None:
    headers = {"Authorization": f"Bearer {env('PIPELINE_API_KEY')}"}
    try:
        data = _get_json(f"{PIPE}/v1/trace?limit=8", headers)
        for t in data.get("data") or []:
            if t.get("workspace") == workspace and float(t.get("started_at") or 0) >= since - 1:
                return _get_json(f"{PIPE}/v1/trace/{t['correlation_id']}", headers)
    except Exception:  # noqa: BLE001
        return None
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


def run_turn(seat: Seat, args) -> TurnResult:
    res = TurnResult(seat.label)
    target = int(seat.context_limit * args.fill)
    prompt = build_filler_prompt(target)
    body = json.dumps(
        {
            "model": seat.label,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "max_tokens": args.max_tokens,
        }
    ).encode()
    req = urllib.request.Request(
        f"{OWUI}/api/chat/completions",
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {env('OWUI_API_KEY')}",
            "Content-Type": "application/json",
        },
    )
    t0 = time.time()
    since = t0
    try:
        with urllib.request.urlopen(req, timeout=args.timeout) as r:  # noqa: S310
            res.http_status = r.status
            out = json.load(r)
        usage = out.get("usage") or {}
        res.prompt_tokens = int(usage.get("prompt_tokens") or 0)
        res.fill_ratio = (
            round(res.prompt_tokens / seat.context_limit, 3) if seat.context_limit else 0.0
        )
    except urllib.error.HTTPError as e:
        res.http_status = e.code
        res.error = e.read()[:300].decode("utf-8", "replace").strip()
    except Exception as e:  # noqa: BLE001
        res.error = f"{type(e).__name__}: {e}"[:300]
    res.wall_s = round(time.time() - t0, 1)
    trace = newest_trace(seat.label.split("::")[0], since)
    if trace:
        res.outcome = str(trace.get("outcome") or "?")
        res.prompt_tokens = res.prompt_tokens or int(
            (trace.get("usage") or {}).get("prompt_tokens") or 0
        )
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
    verdict: str = "?"
    reasons: list[str] = field(default_factory=list)


def judge(pr: PairResult, args) -> None:
    reasons = []
    for t in pr.turns:
        if t.http_status == 507 or "would exceed" in t.error:
            reasons.append(f"{t.seat}: load-guard refusal (507)")
        elif t.http_status not in (0, 200):
            reasons.append(f"{t.seat}: HTTP {t.http_status} {t.error[:80]}")
        elif t.outcome not in ("complete", "?"):
            reasons.append(f"{t.seat}: trace outcome {t.outcome}")
    for ev in pr.cross_evictions:
        reasons.append(
            f"unplanned eviction of resident {ev['engine']}:{ev['model']} ({ev['gib']} GiB)"
        )
    if pr.swap_growth_gib > args.max_swap_growth_gib:
        reasons.append(f"swap grew {pr.swap_growth_gib:.2f} GiB > {args.max_swap_growth_gib}")
    pr.reasons = reasons
    pr.verdict = "FAIL" if reasons else "PASS"


def run_pair(pair: Pair, args) -> PairResult:
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
        pr.turns.append(run_turn(seat, args))
    logs = docker_logs_since(t0 - 2)
    pr.events = parse_load_guard_log(logs)
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
        "| pair | seat | HTTP | prompt_tok | fill | wall_s | outcome | evictions | "
        "swapΔ GiB | RSS Δ GiB (omlx/ollama-runner) | verdict |"
    )
    sep = "|" + "---|" * 11
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
                f"{t.prompt_tokens} | {t.fill_ratio} | {t.wall_s} | {t.outcome} | "
                f"{ev if i == 0 else ''} | {pr.swap_growth_gib if i == 0 else ''} | "
                f"{d_omlx:+.1f}/{d_oll:+.1f} | {pr.verdict if i == 0 else ''} |"
            )
        for r in pr.reasons:
            rows.append(f"| | ⚠ {r} |{' |' * 9}")
    return "\n".join(rows)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pairs", default="", help="comma-separated pair names (default: all)")
    ap.add_argument("--list", action="store_true", help="list pair names and exit")
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
    results = []
    for pair in pairs:
        print(f"== pair {pair.name} ==", flush=True)
        results.append(run_pair(pair, args))
    print(render_table(results))
    if args.json:
        Path(args.json).write_text(json.dumps([vars(r) for r in results], indent=1, default=str))
    return 0 if all(r.verdict == "PASS" for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
