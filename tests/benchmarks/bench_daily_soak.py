"""Portal 5 — Daily-Work Fleet Soak (task-centric, tool-driven).

Two modes, one harness:
  --path pipeline            : drive :9099 with workspace ids. Real routing +
                               persona + SERVER-SIDE multi-hop MCP tool execution.
                               This is the full-system "real day" shape (oMLX for
                               the coding group, Ollama for the rest — production
                               routing, not a controlled 1:1).
  --path direct --engine X   : hit :8085 (omlx) or :11434 (ollama) directly with
                               the per-category model, for a true engine 1:1.
                               Tools are forwarded so the tool path is still soaked;
                               the client runs the multi-hop loop.

Selection is by task CATEGORY (day-weighted), each request a real, tool-PROVOKING
task drawn from a deep per-category bank so hours of runtime never go stale and the
MCP tool path is actually exercised (create_word_document, execute_python,
web_search, kb_search, classify_vulnerability, ...). Captures x-portal-route on the
pipeline path. Built on bench_omlx_soak.py's checkpoint/health skeleton.

Unload discipline (2026-08-10 incident fix): every invocation runs a preflight
that unloads stale resident models before starting — see _preflight_unload().
A kernel panic during the first daily-soak run traced to Ollama holding a 54GB
model resident from a finished direct-Ollama leg while the next leg (pipeline)
loaded oMLX models on top of it; combined memory exceeded physical RAM before
either engine's own admission guard could react. This was previously an
operator discipline ("unload between legs") that got skipped at exactly one
transition. It is now enforced by the harness itself so it can't be skipped.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import threading
import time
from datetime import UTC, datetime
from pathlib import Path

import bench_omlx_v3 as base
import httpx

RESULTS_DIR = Path(__file__).parent / "results"
PIPELINE_URL = os.environ.get("PIPELINE_URL", "http://localhost:9099")
OMLX_URL = "http://localhost:8085"
OLLAMA_URL = "http://localhost:11434"
CHECKPOINT_INTERVAL_S = 300
MAX_TOKENS = 1500
MAX_CLIENT_TOOL_HOPS = 4  # direct path only; pipeline runs its own loop server-side

WORKSPACE_WEIGHTS: dict[str, int] = {
    "auto-coding": 22,
    "auto-daily": 16,
    "auto-documents": 10,
    "auto-security": 10,
    "auto-research": 9,
    "auto-reasoning": 8,
    "auto-spl": 7,
    "auto-compliance": 7,
    "auto-data": 6,
    "auto-creative": 5,
}

# Per-category direct model (matched to config/portal.yaml model_hint), for --path direct.
DIRECT_MODELS = {
    "omlx": {
        "auto-coding": "Qwen3-Coder-30B-A3B-Instruct-4bit",
        "auto-daily": "gemma-4-26b-a4b-it-QAT-4bit",
        "auto-documents": "granite-4.1-8b-mxfp8",
        "auto-security": "VulnLLM-R-7B-4bit",
        "auto-research": "Tongyi-DeepResearch-30B-A3B-abliterated-4bit",
        "auto-reasoning": "DeepSeek-R1-0528-Qwen3-8B-4bit",
        "auto-spl": "Qwen3-Coder-30B-A3B-Instruct-4bit",
        "auto-compliance": "granite-4.1-8b-mxfp8",
        "auto-data": "granite-4.1-30b-4bit",
        "auto-creative": "Qwen3.6-35B-A3B-HauhauCS-Aggressive-4bit",
    },
    "ollama": {
        "auto-coding": "qwen3-coder:30b-a3b-q4_K_M-ctx16k",
        "auto-daily": "gemma4:26b-a4b-it-qat-ctx8k",
        "auto-documents": "granite4.1:8b-q8_0-ctx16k",  # Q8_0 to match oMLX mxfp8 (~8-bit) — parity fix
        "auto-security": "hf.co/mradermacher/VulnLLM-R-7B-GGUF:q4_K_M-ctx8k",
        "auto-research": "huihui_ai/tongyi-deepresearch-abliterated:latest-ctx64k",
        "auto-reasoning": "hf.co/unsloth/DeepSeek-R1-0528-Qwen3-8B-GGUF:Q4_K_XL-ctx64k",
        "auto-spl": "qwen3-coder:30b-a3b-q4_K_M-ctx16k",
        "auto-compliance": "granite4.1:8b-q8_0-ctx16k",  # Q8_0 to match oMLX mxfp8 (~8-bit) — parity fix
        "auto-data": "granite4.1:30b-ctx64k",
        "auto-creative": "fredrezones55/Qwen3.6-35B-A3B-Uncensored-HauhauCS-Aggressive:Q4-ctx8k",
    },
}

# Deep, tool-PROVOKING task banks. Each prompt is written to trigger the real MCP
# tools that workspace exposes, so the tool-execution path is soaked, not just chat.
PROMPT_BANKS: dict[str, list[str]] = {
    "auto-coding": [
        "Write a Python function that parses an ISO-8601 duration, then RUN it on 'P3DT4H' and show the output.",
        "Execute this and tell me what it prints, then fix the off-by-one: for i in range(1,10): print(sum(range(i)))",
        "Write and run a quick benchmark comparing list-comprehension vs map for squaring 1e5 ints. Report the timings.",
        "Run a bash one-liner to count .py files under the current dir, then explain what it did.",
        "Implement quickselect, run it on [7,2,9,4,1,8] for k=3, and verify the result against sorted().",
    ],
    "auto-daily": [
        "Draft a friendly email declining a meeting and proposing async notes; keep it under 90 words.",
        "Rewrite less passively and tighten: 'maybe we could possibly look into the routing thing at some point'.",
        "Summarize into one decision + two action items: we compared engines, chose multi-engine, bench due Friday.",
        "Turn these into 3 crisp status bullets: routing works, soak pending, docs behind, deploy Monday.",
        "Write a two-line Slack reply giving a real ETA for a delayed PR review without over-apologizing.",
        "Draft a short standup update covering yesterday, today, and one blocker.",
    ],
    "auto-documents": [
        "Create a Word document titled 'Pipeline Status' with sections Summary, Risks, Next Steps and one bullet each.",
        "Create an Excel sheet with columns Model, Engine, TPS and three example rows, then confirm it saved.",
        "Build a 3-slide PowerPoint outline on migrating to a multi-engine backend; create the file.",
        "Create a Word runbook document: 'Restart the pipeline safely' with numbered steps.",
    ],
    "auto-security": [
        "Search the KB for our SMB enumeration guidance and summarize the authorized-testing steps it lists.",
        "Classify the vulnerability class for: unauthenticated deserialization of user input in a Java service.",
        "Run a Python snippet that checks whether a given port list contains any in the well-known range, on [22,80,8085].",
        "Web-search current guidance on triaging credential-stuffing spikes and give me the top 3 pivots.",
        "Use the sandbox to compute the CIDR range for 10.10.11.0/24 and list the first and last usable host.",
    ],
    "auto-research": [
        "Web-search the tradeoffs of admission-control vs request-queuing for inference servers and cite what you find.",
        "Search the KB for our notes on paged KV cache and summarize how it differs from per-request allocation.",
        "News-search recent developments in Apple-silicon LLM serving and give me two concrete items.",
        "Remember this fact for later: 'oMLX shadow-shift covers the coding group only'. Then recall it back.",
    ],
    "auto-reasoning": [
        "A job arrives 30/hr, 45min avg service, 3 workers. Stable? Show the utilization math and the bottleneck.",
        "Reason step by step why raising a memory ceiling reduces but never eliminates admission failures under a fixed mix.",
        "Given one engine that rejects fast and one that queues, argue which is easier to build retry logic around, and why.",
        "Work through the expected wait time if 5 requests hit a single-slot model each taking 40s.",
    ],
    "auto-spl": [
        "Search the KB for our failed-logon detection and adapt it into an SPL query grouped by src_ip and user.",
        "Classify the technique and write a YARA rule for a PE importing VirtualAllocEx and WriteProcessMemory.",
        "Write an SPL search surfacing rare parent-child process pairs over 24h; explain the stats command choice.",
    ],
    "auto-compliance": [
        "Search the KB for our NERC CIP asset-inventory evidence list, then create a Word doc summarizing it.",
        "Map 'inventory of authorized devices and software' to the CIP requirement and list required evidence.",
        "For HIPAA, summarize the access-control safeguards for an internal AI service producing PHI summaries.",
    ],
    "auto-data": [
        "Run Python to compute p50/p95/p99 of [12,15,9,40,22,18,120,14,16,300] and show the code and result.",
        "Create an Excel sheet from this data: months Jan-Mar, requests 400/520/610, and confirm it saved.",
        "Run Python to fit a simple linear trend to [400,520,610] and report the slope.",
    ],
    "auto-creative": [
        "Write a 120-word launch blurb for a self-hosted AI orchestration platform. Confident, not hypey.",
        "Draft a dry, engineer-to-engineer changelog entry announcing a multi-engine backend.",
        "Write a short, wry internal note that the Friday deploy is slipping to Monday.",
        "Write a two-sentence tagline for a security-lab automation tool, then a punchier alternative.",
    ],
}


def _target(path: str, engine: str, ws: str) -> tuple[str, str]:
    if path == "pipeline":
        return PIPELINE_URL, ws  # model field = workspace id
    return (OMLX_URL if engine == "omlx" else OLLAMA_URL), DIRECT_MODELS[engine][ws]


def _unload_omlx_all() -> None:
    """Unload every currently-loaded oMLX model. Best-effort: a failed check or
    unload is logged and skipped, never fatal — the run should still attempt to
    proceed, but the operator sees exactly what wasn't cleared."""
    try:
        r = httpx.get(f"{OMLX_URL}/v1/models/status", timeout=10)
        loaded = [m["id"] for m in r.json().get("models", []) if m.get("loaded")]
    except Exception as exc:
        print(f"  [preflight] omlx status check failed (non-fatal): {exc}", flush=True)
        return
    for mid in loaded:
        try:
            httpx.post(f"{OMLX_URL}/v1/models/{mid}/unload", timeout=30)
            print(f"  [preflight] unloaded omlx model: {mid}", flush=True)
        except Exception as exc:
            print(f"  [preflight] failed to unload omlx/{mid}: {exc}", flush=True)


def _unload_ollama_all() -> None:
    """Unload every currently-loaded Ollama model via keep_alive=0."""
    try:
        r = httpx.get(f"{OLLAMA_URL}/api/ps", timeout=10)
        loaded = [m["name"] for m in r.json().get("models", [])]
    except Exception as exc:
        print(f"  [preflight] ollama ps check failed (non-fatal): {exc}", flush=True)
        return
    for name in loaded:
        try:
            httpx.post(
                f"{OLLAMA_URL}/api/generate", json={"model": name, "keep_alive": 0}, timeout=30
            )
            print(f"  [preflight] unloaded ollama model: {name}", flush=True)
        except Exception as exc:
            print(f"  [preflight] failed to unload ollama/{name}: {exc}", flush=True)


def _preflight_unload(path: str, engine: str) -> None:
    """Clear stale resident models before this leg starts.

    Extends the "unload between legs" discipline into the harness itself so it
    can never again be skipped at a transition (2026-08-10 incident: a kernel
    panic traced to Ollama still holding a 54GB model from a finished direct
    leg while the pipeline leg loaded oMLX on top of it — see
    reports/DAILY_WORK_SOAK_*.md).

      --path direct --engine omlx   -> unload Ollama (isolate the oMLX leg)
      --path direct --engine ollama -> unload oMLX (isolate the Ollama leg)
      --path pipeline                -> unload BOTH (pipeline drives both
                                         engines; this is the exact transition
                                         that crashed the host)
    """
    print("=== preflight: clearing stale resident models ===", flush=True)
    if path == "pipeline":
        _unload_omlx_all()
        _unload_ollama_all()
    elif engine == "omlx":
        _unload_ollama_all()
    else:
        _unload_omlx_all()
    time.sleep(3)  # let Metal/VRAM settle before the run starts


class DailySoak:
    def __init__(self, path: str, engine: str, duration_s: int, concurrency: int, tag: str | None):
        self.path = path
        self.engine = engine
        self.duration_s = duration_s
        self.concurrency = concurrency
        self.tag = tag
        self.api_key = os.environ.get("PIPELINE_API_KEY", "")
        self.names = list(WORKSPACE_WEIGHTS)
        self.weights = [WORKSPACE_WEIGHTS[n] for n in self.names]
        self.samples: list[dict] = []
        self.lock = threading.Lock()
        self._stop = threading.Event()
        self.started_perf = 0.0
        self.stop_at = 0.0

    def _pick(self) -> tuple[str, str]:
        ws = random.choices(self.names, weights=self.weights, k=1)[0]
        return ws, random.choice(PROMPT_BANKS[ws])

    def _one(self, ws: str, prompt: str) -> dict:
        url, model = _target(self.path, self.engine, ws)
        headers = {}
        if self.path == "pipeline" and self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": True,
            "stream_options": {"include_usage": True},
            "max_tokens": MAX_TOKENS,
        }
        t0 = time.perf_counter()
        t_first = None
        toks = 0
        served = ";;"
        try:
            with (
                httpx.Client(timeout=base.REQUEST_TIMEOUT) as c,
                c.stream(
                    "POST", f"{url}/v1/chat/completions", json=payload, headers=headers
                ) as resp,
            ):
                served = resp.headers.get("x-portal-route", ";;")
                if resp.status_code != 200:
                    parts = served.split(";")
                    return {
                        "workspace": ws,
                        "error": f"HTTP {resp.status_code}",
                        "served_backend": parts[1] if len(parts) > 1 and parts[1] else None,
                        "ttft_s": None,
                        "tps": 0.0,
                    }
                for line in resp.iter_lines():
                    if not line or not line.startswith("data: "):
                        continue
                    d = line[6:]
                    if d.strip() == "[DONE]":
                        break
                    try:
                        o = json.loads(d)
                    except json.JSONDecodeError:
                        continue
                    delta = (o.get("choices") or [{}])[0].get("delta", {})
                    if (
                        delta.get("content") or delta.get("reasoning") or delta.get("thinking")
                    ) and t_first is None:
                        t_first = time.perf_counter()
                    if o.get("usage"):
                        toks = o["usage"].get("completion_tokens", toks)
        except Exception as exc:
            return {
                "workspace": ws,
                "error": str(exc),
                "served_backend": None,
                "ttft_s": None,
                "tps": 0.0,
            }
        el = time.perf_counter() - t0
        parts = served.split(";")
        return {
            "workspace": ws,
            "served_backend": parts[1] if len(parts) > 1 and parts[1] else self.engine,
            "ttft_s": round(t_first - t0, 3) if t_first else None,
            "total_s": round(el, 3),
            "tps": round(toks / el, 1) if el > 0 else 0.0,
        }

    def _worker(self) -> None:
        while time.perf_counter() < self.stop_at and not self._stop.is_set():
            ws, prompt = self._pick()
            r = self._one(ws, prompt)
            r["t"] = round(time.perf_counter() - self.started_perf, 1)
            with self.lock:
                self.samples.append(r)

    def _checkpoint(self) -> Path:
        with self.lock:
            snap = list(self.samples)
        by_ws: dict[str, dict] = {}
        by_backend: dict[str, dict] = {}
        for s in snap:
            w = s["workspace"]
            by_ws.setdefault(w, {"ok": 0, "fail": 0})
            by_ws[w]["ok" if "error" not in s else "fail"] += 1
            b = s.get("served_backend") or "unknown"
            by_backend.setdefault(b, {"ok": 0, "fail": 0})
            by_backend[b]["ok" if "error" not in s else "fail"] += 1
        ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        tag = f"_{self.tag}" if self.tag else ""
        label = self.path if self.path == "pipeline" else f"direct_{self.engine}"
        out = RESULTS_DIR / f"daily_soak_{label}{tag}_{ts}.json"
        out.write_text(
            json.dumps(
                {
                    "task": "TASK_DAILY_WORK_FLEET_SOAK_V1",
                    "path": self.path,
                    "engine": self.engine if self.path == "direct" else "pipeline-routed",
                    "duration_s": self.duration_s,
                    "concurrency": self.concurrency,
                    "elapsed_s": round(time.perf_counter() - self.started_perf, 1),
                    "total": len(snap),
                    "ok": sum(1 for s in snap if "error" not in s),
                    "failures": sum(1 for s in snap if "error" in s),
                    "by_workspace": by_ws,
                    "by_served_backend": by_backend,
                    "samples": snap,
                },
                indent=2,
            )
        )
        return out

    def run(self) -> Path:
        RESULTS_DIR.mkdir(exist_ok=True)
        self.started_perf = time.perf_counter()
        self.stop_at = self.started_perf + self.duration_s
        workers = [
            threading.Thread(target=self._worker, daemon=True) for _ in range(self.concurrency)
        ]
        for w in workers:
            w.start()
        next_ck = self.started_perf + CHECKPOINT_INTERVAL_S
        while time.perf_counter() < self.stop_at:
            if time.perf_counter() >= next_ck:
                p = self._checkpoint()
                with self.lock:
                    n = len(self.samples)
                    f = sum(1 for s in self.samples if "error" in s)
                print(f"  [checkpoint] {n} req, {f} fail -> {p.name}", flush=True)
                next_ck += CHECKPOINT_INTERVAL_S
            time.sleep(2)
        self._stop.set()
        for w in workers:
            w.join(timeout=base.REQUEST_TIMEOUT + 5)
        return self._checkpoint()


def main() -> None:
    p = argparse.ArgumentParser(description="Portal 5 daily-work fleet soak")
    p.add_argument("--path", choices=["pipeline", "direct"], default="pipeline")
    p.add_argument("--engine", choices=["omlx", "ollama"], default="omlx")
    p.add_argument("--duration", type=int, default=10800)
    p.add_argument("--concurrency", type=int, default=3)
    p.add_argument("--tag", default=None)
    p.add_argument(
        "--no-preflight-unload",
        action="store_true",
        help="Skip the stale-model unload preflight (default: on). Only for debugging"
        " a specific leg's transition behavior — leave enabled for real runs.",
    )
    args = p.parse_args()
    if args.path == "pipeline" and not os.environ.get("PIPELINE_API_KEY"):
        print("WARNING: PIPELINE_API_KEY unset — :9099 will 401.", flush=True)
    if not args.no_preflight_unload:
        _preflight_unload(args.path, args.engine)
    tgt = (
        PIPELINE_URL
        if args.path == "pipeline"
        else (OMLX_URL if args.engine == "omlx" else OLLAMA_URL)
    )
    print(
        f"=== daily soak [{args.path}"
        f"{'/' + args.engine if args.path == 'direct' else ''}]: {args.duration}s "
        f"@ c={args.concurrency}, {len(WORKSPACE_WEIGHTS)} categories, {tgt} ===",
        flush=True,
    )
    soak = DailySoak(args.path, args.engine, args.duration, args.concurrency, args.tag)
    print(f"=== done -> {soak.run()} ===", flush=True)


if __name__ == "__main__":
    main()
