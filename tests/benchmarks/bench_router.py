"""Router model benchmark — evaluates LLM intent classifier candidates.

Tests accuracy, latency, and abstention quality for the Layer-1 LLM router
(see portal_pipeline/router/routing.py :: _route_with_llm).

Usage:
    # Compare specific candidates
    python3 tests/benchmarks/bench_router.py

    # Test a specific model only
    python3 tests/benchmarks/bench_router.py --models "hf.co/QuantFactory/Llama-3.2-3B-Instruct-abliterated-GGUF"

    # Show all test cases without running
    python3 tests/benchmarks/bench_router.py --dry-run

    # Save results JSON
    python3 tests/benchmarks/bench_router.py --output results/router_bench_$(date +%Y%m%dT%H%M%S).json

Requirements:
    Ollama running at OLLAMA_URL (default http://localhost:11434).
    Candidate models must already be pulled.

Design notes:
    - Uses /api/generate with format=JSON_SCHEMA (same path as production router)
    - 500ms timeout ceiling matches production default LLM_ROUTER_TIMEOUT_MS
    - Grammar-enforced JSON means models that emit <think> blocks fail gracefully
    - Security queries test whether a model refuses to classify offensive content
      (acceptable: returns "auto" + low confidence; unacceptable: HTTP error / hang)
    - Golden set covers all 29 production workspaces (bench-* excluded by design)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import httpx

# Notification support (same module used by bench_tps / bench_security)
try:
    from tests.benchmarks.bench.notify import _send_bench_notification
except ImportError:
    def _send_bench_notification(message: str, title: str = "Portal 5 Bench") -> None:  # type: ignore[misc]
        pass

# ── Config ────────────────────────────────────────────────────────────────────

OLLAMA_URL: str = os.environ.get("OLLAMA_URL", "http://localhost:11434")
TIMEOUT_MS: int = int(os.environ.get("LLM_ROUTER_TIMEOUT_MS", "500"))
CONFIDENCE_THRESHOLD: float = 0.5

# Resolve routing config (same logic as production router)
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
ROUTING_CONFIG_DIR = Path(os.environ.get("ROUTING_CONFIG_DIR", _REPO_ROOT / "config"))

# ── Candidate models ──────────────────────────────────────────────────────────
#
# Pull commands (run before bench):
#   ollama pull hf.co/QuantFactory/Llama-3.2-3B-Instruct-abliterated-GGUF   # current baseline
#   ollama pull granite3.3:2b        # IBM 2B, 128K ctx, 1.5GB — strong IFEval, no think tokens
#   ollama pull gemma4:e2b-it-qat    # Google 2B, 4.3GB — already in fleet, fast Metal
#   ollama pull llama3.2:1b          # Meta 1B, 1.3GB — smallest/fastest, speed floor
#   ollama pull llama3.2:3b          # Meta 3B, 2.0GB — non-abliterated comparison vs current
#   ollama pull smollm2:1.7b         # HuggingFace 1.7B, 1.8GB — edge-optimised, 8K ctx
#   ollama pull qwen2.5:1.5b         # Alibaba 1.5B, 986MB — tiny, 32K ctx
#   ollama pull qwen2.5:3b           # Alibaba 3B, 1.9GB — stronger, 32K ctx
#   ollama pull phi4-mini            # Microsoft 3.8B, 2.5GB — already in fleet, strong IFEval
#
# Why each candidate:
#   Llama-3.2-3B-abliterated : CURRENT PRODUCTION (Sept 2024). Abliterated = won't refuse
#     security routing queries. Baseline to beat.
#   granite3.3:2b            : IBM Apache 2.0, Jan 2026. IFEval 87+, no thinking tokens,
#     designed for enterprise tool-use + JSON output. Strong candidate for JSON schema routing.
#   gemma4:e2b-it-qat        : Google, May 2026. 2B encoder-free, QAT quality. Fast Metal
#     dispatch. May refuse security routing queries (classification ≠ generation, often works).
#   llama3.2:1b              : Speed floor. If 1B is accurate enough, latency drops by 40%.
#   llama3.2:3b              : Same base as current abliterated — tests whether abliteration
#     actually matters for routing (classifying ≠ generating offensive content).
#   smollm2:1.7b             : HF edge model, Nov 2024. 8K ctx only — prompt fits at 2048
#     num_ctx but context is tight. Tests tiny-model viability.
#   qwen2.5:1.5b             : 986MB — smallest serious candidate. 32K ctx. Alibaba Apache 2.0.
#   qwen2.5:3b               : Qwen2.5 3B, 32K ctx. Strong IFEval for size. No thinking tokens.
#   phi4-mini                : Microsoft 3.8B (largest candidate). Strong IFEval. Already fleet.
#     Tests quality ceiling vs the smaller options.
#
# EXCLUDED:
#   Qwen3 family  — emits <think> blocks that break Ollama grammar decoding from token 1.
#   gemma4:e4b-it-qat (6.1GB) — too large to keep warm alongside 25GB production models.
#   granite4.1:2b — does not exist; granite4.1 starts at 8B (use granite3.3:2b instead).

DEFAULT_CANDIDATES: list[str] = [
    "hf.co/QuantFactory/Llama-3.2-3B-Instruct-abliterated-GGUF",  # current production baseline
    "granite3.3:2b",       # IBM 2B, strong IFEval, no think tokens
    "gemma4:e2b-it-qat",   # Google 2B, already fleet, fast Metal
    "llama3.2:1b",         # Meta 1B, speed floor
    "llama3.2:3b",         # Meta 3B, non-abliterated comparison
    "smollm2:1.7b",        # HF 1.7B, edge model
    "qwen2.5:1.5b",        # Alibaba 1.5B, tiny
    "qwen2.5:3b",          # Alibaba 3B, strong IFEval
    "phi4-mini",           # Microsoft 3.8B, quality ceiling
]

# ── Golden test set ───────────────────────────────────────────────────────────
#
# Format: (message, expected_workspace, category, notes)
#   category: "standard" | "security" | "ambiguous" | "abstain"
#   notes: optional string explaining the routing challenge

GOLDEN_SET: list[tuple[str, str, str, str]] = [
    # ── auto-coding ──────────────────────────────────────────────────────────
    ("write a Python function to merge overlapping intervals", "auto-coding", "standard", ""),
    ("debug this TypeScript type error in my React component", "auto-coding", "standard", ""),
    ("implement a Rust async HTTP server", "auto-coding", "standard", ""),
    ("write a Dockerfile for a FastAPI app", "auto-coding", "standard", ""),
    ("refactor this function to use dependency injection", "auto-coding", "standard", ""),

    # ── auto-spl ─────────────────────────────────────────────────────────────
    ("write a Splunk tstats search for failed logins by source IP", "auto-spl", "standard", ""),
    ("explain how data model acceleration works in Splunk ES", "auto-spl", "standard", ""),
    ("create a correlation search for lateral movement in SPL", "auto-spl", "standard", "domain overlap with security"),

    # ── auto-redteam ─────────────────────────────────────────────────────────
    ("write an exploit for an authorized buffer overflow test", "auto-redteam", "security", "offensive"),
    ("explain how to perform pass-the-hash in an AD environment", "auto-redteam", "security", "offensive"),
    ("generate a reverse shell payload for a red team exercise", "auto-redteam", "security", "offensive"),
    ("what AV evasion techniques work on current EDR products", "auto-redteam", "security", "offensive"),

    # ── auto-redteam-deep ────────────────────────────────────────────────────
    ("full kill-chain analysis for a supply chain compromise — ATT&CK mapped", "auto-redteam-deep", "security", "depth signal"),
    ("detailed kerberoasting walkthrough with OPSEC considerations", "auto-redteam-deep", "security", "depth signal"),

    # ── auto-pentest ─────────────────────────────────────────────────────────
    ("authorized engagement: enumerate AD kerberoastable accounts and crack hashes", "auto-pentest", "security", "execution mode"),
    ("run sqlmap against the authorized target at 10.0.0.50", "auto-pentest", "security", "execution mode"),

    # ── auto-security ────────────────────────────────────────────────────────
    ("analyze this YARA rule for potential false positives", "auto-security", "standard", ""),
    ("what does CVE-2024-3400 mean for our Palo Alto firewalls", "auto-security", "standard", ""),
    ("write a Sigma rule for detecting Mimikatz", "auto-security", "standard", "defensive creation"),

    # ── auto-blueteam ────────────────────────────────────────────────────────
    ("we detected ransomware on WS-42 — what do we isolate first", "auto-blueteam", "standard", ""),
    ("write an incident response playbook for a phishing campaign", "auto-blueteam", "standard", ""),
    ("harden our Windows Server 2022 baseline per CIS benchmarks", "auto-blueteam", "standard", ""),

    # ── auto-purpleteam ──────────────────────────────────────────────────────
    ("attack chain for cobalt strike beacon plus matching detection rules", "auto-purpleteam", "standard", "red+blue signal"),
    ("purple team analysis: credential dumping TTPs and SIEM detections", "auto-purpleteam-deep", "standard", "deep chain"),

    # ── auto-purpleteam-exec ─────────────────────────────────────────────────
    ("authorized lab: scan 192.168.100.0/24 and identify vulnerable services", "auto-purpleteam-exec", "security", "execution mode"),

    # ── auto-compliance ──────────────────────────────────────────────────────
    ("is our patch management process compliant with NERC CIP-007-6 R4", "auto-compliance", "standard", ""),
    ("map our access control logs to CIP-004 R6 evidence requirements", "auto-compliance", "standard", ""),

    # ── auto-bigfix ──────────────────────────────────────────────────────────
    ("query the BigFix REST API for all computers missing KB5034765", "auto-bigfix", "standard", ""),
    ("write a BigFix relevance expression to check .NET 4.8 patch state", "auto-bigfix", "standard", ""),
    ("create a BigFix fixlet to deploy an emergency patch to Windows servers", "auto-bigfix", "standard", ""),

    # ── auto-cad ─────────────────────────────────────────────────────────────
    ("design a parametric mounting bracket in OpenSCAD for M4 screws", "auto-cad", "standard", ""),
    ("generate OpenSCAD code for a hex enclosure with snap-fit lid", "auto-cad", "standard", ""),
    ("create an STL for a spur gear, module 2, 20 teeth", "auto-cad", "standard", ""),

    # ── auto-data ────────────────────────────────────────────────────────────
    ("analyze this CSV for outliers and suggest visualization approaches", "auto-data", "standard", ""),
    ("explain the difference between ANOVA and a t-test for my experiment", "auto-data", "standard", ""),

    # ── auto-research ────────────────────────────────────────────────────────
    ("find recent papers on diffusion models for protein structure prediction", "auto-research", "standard", ""),
    ("what happened with the CrowdStrike outage in July 2024", "auto-research", "standard", ""),

    # ── auto-reasoning ───────────────────────────────────────────────────────
    ("deep dive: pros and cons of event sourcing vs CQRS for this system", "auto-reasoning", "standard", ""),
    ("step by step: how does a transformer's attention mechanism work", "auto-reasoning", "standard", ""),

    # ── auto-math ────────────────────────────────────────────────────────────
    ("solve the differential equation dy/dx = 2xy with initial condition y(0)=1", "auto-math", "standard", ""),
    ("prove by induction that the sum of first n integers is n(n+1)/2", "auto-math", "standard", ""),

    # ── auto-documents ───────────────────────────────────────────────────────
    ("create a Word document with our Q3 financial summary", "auto-documents", "standard", ""),
    ("make a PowerPoint presentation from these 10 bullet points", "auto-documents", "standard", ""),
    ("transcribe this meeting recording with speaker labels", "auto-documents", "standard", ""),

    # ── auto-audio ───────────────────────────────────────────────────────────
    ("summarize the key points from this podcast episode", "auto-audio", "standard", ""),
    ("what topics were discussed in this interview recording", "auto-audio", "standard", ""),

    # ── auto-vision ──────────────────────────────────────────────────────────
    ("what does this network diagram show", "auto-vision", "standard", ""),
    ("analyze the architecture in this screenshot", "auto-vision", "standard", ""),

    # ── auto-creative ────────────────────────────────────────────────────────
    ("write a noir detective short story set in a rainy city", "auto-creative", "standard", ""),
    ("write product copy for a new headphone launch", "auto-creative", "standard", ""),

    # ── auto-music ───────────────────────────────────────────────────────────
    ("generate a 30-second ambient track for a meditation app", "auto-music", "standard", ""),
    ("create an upbeat lo-fi hip hop beat", "auto-music", "standard", ""),

    # ── auto-video ───────────────────────────────────────────────────────────
    ("generate a 5-second video of ocean waves at sunset", "auto-video", "standard", ""),
    ("create a time-lapse video of a city skyline", "auto-video", "standard", ""),

    # ── auto-agentic ─────────────────────────────────────────────────────────
    ("refactor this entire 8000-line monolith to use async/await throughout", "auto-agentic", "standard", "scale signal"),
    ("analyze and document every function in this 200-file codebase", "auto-agentic", "standard", "scale signal"),

    # ── auto-mistral ─────────────────────────────────────────────────────────
    ("use Magistral to walk through this strategic partnership decision", "auto-mistral", "standard", "model-name signal"),
    ("structured Mistral reasoning: evaluate these three architecture options", "auto-mistral", "standard", "model-name signal"),

    # ── auto-phi4 ────────────────────────────────────────────────────────────
    ("use Phi-4 to reason through this STEM problem", "auto-phi4", "standard", "model-name signal"),

    # ── auto-daily ───────────────────────────────────────────────────────────
    ("can you help me draft a quick reply to this email", "auto-daily", "standard", ""),
    ("what's a good way to organize my week", "auto-daily", "standard", ""),

    # ── tools-specialist ─────────────────────────────────────────────────────
    ("read all Python files in this directory recursively", "tools-specialist", "standard", "tool invocation"),
    ("list running Docker containers and show their resource usage", "tools-specialist", "standard", "tool invocation"),

    # ── auto (general / abstain) ─────────────────────────────────────────────
    ("hello, how are you today", "auto", "abstain", "no routing gain"),
    ("what is 2 + 2", "auto", "abstain", "trivial — no workspace needed"),
    ("who invented the telephone", "auto", "abstain", "general knowledge"),
    ("can you help me think through something", "auto", "abstain", "vague intent"),

    # ── Adversarial / hard cases ──────────────────────────────────────────────
    ("write a Splunk search to detect Mimikatz", "auto-spl", "standard", "security + SPL overlap — SPL should win"),
    ("CIP-007 requirements for patching ICS systems", "auto-compliance", "standard", "compliance + security overlap"),
    ("design a bracket that holds a Raspberry Pi", "auto-cad", "standard", "coding vs CAD ambiguity"),
    ("write tests for my OpenSCAD model generator", "auto-coding", "standard", "OpenSCAD but task is coding"),
    ("explain how kerberoasting works", "auto-security", "standard", "explanation vs execution"),
    ("i need to know about lateral movement techniques", "auto-security", "standard", "general vs redteam"),
]


# ── Router infrastructure (mirrors production routing.py) ─────────────────────

def _load_routing_config() -> tuple[dict[str, str], list[dict]]:
    desc_path = ROUTING_CONFIG_DIR / "routing_descriptions.json"
    ex_path = ROUTING_CONFIG_DIR / "routing_examples.json"
    try:
        raw = json.loads(desc_path.read_text())
        descriptions = {k: v for k, v in raw.items() if not k.startswith("_")}
    except Exception as e:
        print(f"  WARNING: could not load routing_descriptions.json: {e}", file=sys.stderr)
        descriptions = {}
    try:
        raw = json.loads(ex_path.read_text())
        examples = raw.get("examples", [])
    except Exception as e:
        print(f"  WARNING: could not load routing_examples.json: {e}", file=sys.stderr)
        examples = []
    return descriptions, examples


def _build_schema(valid_ids: frozenset[str]) -> dict:
    return {
        "type": "object",
        "properties": {
            "workspace": {"type": "string", "enum": sorted(valid_ids)},
            "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        },
        "required": ["workspace", "confidence"],
    }


def _build_prompt(user_message: str, descriptions: dict, examples: list) -> str:
    desc_lines = "\n".join(f"- {ws_id}: {desc}" for ws_id, desc in descriptions.items())
    example_lines = "\n".join(
        f'Message: "{ex["message"]}"\nWorkspace: {ex["workspace"]}\nConfidence: {ex["confidence"]}'
        for ex in examples[:9]
    )
    return (
        "You are an intent router for an AI platform. Classify the user message into exactly one workspace.\n\n"
        f"WORKSPACES:\n{desc_lines}\n\n"
        f"EXAMPLES:\n{example_lines}\n\n"
        f'Now classify this message:\nMessage: "{user_message}"\n\n'
        'Respond ONLY with a JSON object: {"workspace": "<workspace_id>", "confidence": <0.0-1.0>}\n'
        "The workspace must be one of the valid IDs listed above."
    )


def route_one(
    client: httpx.Client,
    model: str,
    message: str,
    schema: dict,
    prompt: str,
    valid_ids: frozenset[str],
    timeout_s: float,
) -> tuple[str | None, float, float, str]:
    """Route one message. Returns (workspace, confidence, elapsed_ms, error)."""
    t0 = time.monotonic()
    try:
        resp = client.post(
            f"{OLLAMA_URL}/api/generate",
            json={
                "model": model,
                "prompt": prompt,
                "stream": False,
                "keep_alive": "-1",
                "options": {"temperature": 0, "num_predict": 40, "num_ctx": 2048},
                "format": schema,
            },
            timeout=httpx.Timeout(timeout_s + 2.0, connect=5.0),
        )
        elapsed_ms = (time.monotonic() - t0) * 1000
        resp.raise_for_status()
        raw = resp.json().get("response", "").strip()
        parsed = json.loads(raw)
        workspace = str(parsed.get("workspace", "")).strip()
        confidence = float(parsed.get("confidence", 0.0))
        if workspace not in valid_ids:
            return None, 0.0, elapsed_ms, f"unknown workspace '{workspace}'"
        if confidence < CONFIDENCE_THRESHOLD:
            return None, confidence, elapsed_ms, f"low confidence {confidence:.2f}"
        return workspace, confidence, elapsed_ms, ""
    except httpx.TimeoutException:
        elapsed_ms = (time.monotonic() - t0) * 1000
        return None, 0.0, elapsed_ms, "TIMEOUT"
    except Exception as exc:
        elapsed_ms = (time.monotonic() - t0) * 1000
        return None, 0.0, elapsed_ms, str(exc)[:80]


# ── Scoring ───────────────────────────────────────────────────────────────────

def score_results(rows: list[dict]) -> dict[str, Any]:
    total = len(rows)
    correct = sum(1 for r in rows if r["result"] == "correct")
    correct_abstain = sum(1 for r in rows if r["category"] == "abstain" and r["result"] == "correct")
    total_abstain = sum(1 for r in rows if r["category"] == "abstain")
    total_security = sum(1 for r in rows if r["category"] == "security")
    correct_security = sum(1 for r in rows if r["category"] == "security" and r["result"] == "correct")
    security_refused = sum(1 for r in rows if r["category"] == "security" and "refused" in r.get("error", "").lower())
    security_timeout = sum(1 for r in rows if r["category"] == "security" and r.get("error") == "TIMEOUT")
    latencies = [r["elapsed_ms"] for r in rows if r.get("elapsed_ms", 0) > 0]
    return {
        "accuracy": correct / total if total else 0,
        "accuracy_pct": f"{correct}/{total}",
        "security_accuracy": correct_security / total_security if total_security else 0,
        "security_pct": f"{correct_security}/{total_security}",
        "security_refused": security_refused,
        "security_timeout": security_timeout,
        "abstain_accuracy": correct_abstain / total_abstain if total_abstain else 0,
        "p50_ms": sorted(latencies)[len(latencies) // 2] if latencies else 0,
        "p95_ms": sorted(latencies)[int(len(latencies) * 0.95)] if latencies else 0,
        "timeout_count": sum(1 for r in rows if r.get("error") == "TIMEOUT"),
    }


# ── Runner ────────────────────────────────────────────────────────────────────

def run_bench(
    models: list[str],
    dry_run: bool = False,
) -> dict[str, list[dict]]:
    descriptions, examples = _load_routing_config()
    if not descriptions:
        print("ERROR: routing_descriptions.json empty — check ROUTING_CONFIG_DIR", file=sys.stderr)
        sys.exit(1)

    # Build valid_ids from production workspaces (bench-* excluded)
    try:
        sys.path.insert(0, str(_REPO_ROOT))
        from portal_pipeline.router.workspaces import WORKSPACES  # type: ignore[import]
        valid_ids = frozenset(k for k in WORKSPACES if not k.startswith("bench-"))
    except ImportError:
        # Fallback to descriptions keys
        valid_ids = frozenset(descriptions.keys())

    schema = _build_schema(valid_ids)

    # Pre-build prompts per test case
    prompts = [
        _build_prompt(msg, descriptions, examples)
        for msg, _, _, _ in GOLDEN_SET
    ]

    if dry_run:
        print(f"DRY RUN — {len(GOLDEN_SET)} test cases × {len(models)} models\n")
        for i, (msg, expected, cat, note) in enumerate(GOLDEN_SET):
            note_str = f"  [{note}]" if note else ""
            print(f"  {i+1:2d}. [{cat:10s}] → {expected:30s}  {msg[:60]!r}{note_str}")
        return {}

    all_results: dict[str, list[dict]] = {}

    _send_bench_notification(
        f"Router bench started — {len(models)} candidates × {len(GOLDEN_SET)} tests\n"
        f"Models: {', '.join(m.split('/')[-1] for m in models)}",
        title="🔀 Router Bench — START",
    )
    bench_start = time.monotonic()

    with httpx.Client() as client:
        for model in models:
            print(f"\n{'─'*70}")
            print(f"MODEL: {model}")
            print(f"{'─'*70}")

            rows: list[dict] = []
            timeout_s = TIMEOUT_MS / 1000.0
            n = len(GOLDEN_SET)

            for i, (msg, expected, cat, note) in enumerate(GOLDEN_SET):
                prompt = prompts[i]
                workspace, confidence, elapsed_ms, error = route_one(
                    client, model, msg, schema, prompt, valid_ids, timeout_s
                )

                # Determine result
                if workspace == expected:
                    result = "correct"
                elif workspace is None and expected == "auto":
                    result = "correct"  # abstained on ambiguous = correct
                elif workspace is None:
                    result = "abstained"  # fell back to keyword layer
                else:
                    result = "wrong"

                symbol = "✓" if result == "correct" else ("·" if result == "abstained" else "✗")
                latency_flag = " ⚠️ SLOW" if elapsed_ms > TIMEOUT_MS else ""
                ws_display = workspace or f"(none/fallback){' TIMEOUT' if error == 'TIMEOUT' else ''}"
                print(
                    f"  {i+1:2d}/{n} {symbol} [{cat[:3]:3s}] {expected:28s}"
                    f"  → {ws_display:28s}  {elapsed_ms:5.0f}ms{latency_flag}"
                )
                if error and error != "TIMEOUT":
                    print(f"       error: {error}")

                rows.append({
                    "message": msg,
                    "expected": expected,
                    "got": workspace,
                    "confidence": confidence,
                    "elapsed_ms": round(elapsed_ms, 1),
                    "result": result,
                    "category": cat,
                    "error": error,
                    "notes": note,
                })

            stats = score_results(rows)
            all_results[model] = rows

            print(f"\n  SUMMARY  accuracy={stats['accuracy_pct']}  ({stats['accuracy']*100:.1f}%)")
            print(f"           security={stats['security_pct']}  ({stats['security_accuracy']*100:.1f}%)")
            print(f"           abstain_acc={stats['abstain_accuracy']*100:.1f}%")
            print(f"           p50={stats['p50_ms']:.0f}ms  p95={stats['p95_ms']:.0f}ms")
            print(f"           timeouts={stats['timeout_count']}  security_refused={stats['security_refused']}")

            short_name = model.split("/")[-1][:40]
            _send_bench_notification(
                f"{short_name}\n"
                f"acc={stats['accuracy_pct']} ({stats['accuracy']*100:.1f}%)  "
                f"sec={stats['security_accuracy']*100:.1f}%\n"
                f"p50={stats['p50_ms']:.0f}ms  p95={stats['p95_ms']:.0f}ms  "
                f"TO={stats['timeout_count']}",
                title="🔀 Router Bench — model done",
            )

    elapsed_total = time.monotonic() - bench_start
    # Build summary for final notification
    lines = []
    for model, rows in all_results.items():
        s = score_results(rows)
        lines.append(
            f"{model.split('/')[-1][:30]:30s}  "
            f"acc={s['accuracy']*100:.0f}%  sec={s['security_accuracy']*100:.0f}%  "
            f"p50={s['p50_ms']:.0f}ms"
        )
    _send_bench_notification(
        f"{len(all_results)} models  {len(GOLDEN_SET)} tests  {elapsed_total/60:.1f}min\n\n"
        + "\n".join(lines),
        title="🔀 Router Bench — DONE",
    )

    return all_results


def print_comparison(all_results: dict[str, list[dict]]) -> None:
    if len(all_results) < 2:
        return
    print(f"\n{'━'*80}")
    print("COMPARISON")
    print(f"{'━'*80}")
    header = f"{'Model':<55} {'Acc':>6} {'Sec':>6} {'Abs':>6} {'p50ms':>6} {'p95ms':>6} {'TO':>4}"
    print(header)
    print("─" * 80)
    for model, rows in all_results.items():
        stats = score_results(rows)
        short = model.split("/")[-1][:52]
        print(
            f"{short:<55} {stats['accuracy']*100:>5.1f}% "
            f"{stats['security_accuracy']*100:>5.1f}% "
            f"{stats['abstain_accuracy']*100:>5.1f}% "
            f"{stats['p50_ms']:>5.0f} "
            f"{stats['p95_ms']:>5.0f} "
            f"{stats['timeout_count']:>4}"
        )

    # Per-workspace breakdown for cases where models disagree
    print(f"\n{'DISAGREEMENTS':}")
    print("─" * 80)
    model_names = list(all_results.keys())
    for i, (msg, expected, cat, _) in enumerate(GOLDEN_SET):
        verdicts = [all_results[m][i]["result"] for m in model_names]
        if len(set(verdicts)) > 1:
            print(f"  [{cat[:3]:3s}] → {expected:25s}  {msg[:45]!r}")
            for m, verdict in zip(model_names, verdicts):
                got = all_results[m][i].get("got") or "(fallback)"
                print(f"    {'✓' if verdict=='correct' else '✗'} {m.split('/')[-1][:30]:30s} → {got}")


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Bench LLM router model candidates",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--models",
        nargs="+",
        default=DEFAULT_CANDIDATES,
        metavar="MODEL",
        help="Ollama model IDs to evaluate (default: 4 candidates)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print test cases only, don't run")
    parser.add_argument("--output", metavar="FILE", help="Save full results as JSON")
    parser.add_argument(
        "--timeout-ms",
        type=int,
        default=TIMEOUT_MS,
        help=f"Per-request timeout ms (default: {TIMEOUT_MS})",
    )
    args = parser.parse_args()

    global TIMEOUT_MS
    TIMEOUT_MS = args.timeout_ms

    print(f"Portal 5 — Router Model Bench")
    print(f"Candidates : {len(args.models)} models")
    print(f"Test cases : {len(GOLDEN_SET)}")
    print(f"Timeout    : {TIMEOUT_MS}ms per request")
    print(f"Ollama     : {OLLAMA_URL}")
    print(f"Config dir : {ROUTING_CONFIG_DIR}")

    all_results = run_bench(args.models, dry_run=args.dry_run)

    if all_results:
        print_comparison(all_results)

    if args.output and all_results:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "timeout_ms": TIMEOUT_MS,
            "models": {
                model: {
                    "stats": score_results(rows),
                    "rows": rows,
                }
                for model, rows in all_results.items()
            },
        }
        out_path.write_text(json.dumps(payload, indent=2))
        print(f"\nResults saved → {out_path}")


if __name__ == "__main__":
    main()
