"""Multi-model soak test for the oMLX rip-and-replace capacity question
(2026-08-05/06). Answers the question the short bursts in bench_omlx_v3.py
and bench_omlx_stress_extras.py can't: does oMLX hold up when the models
actually driving most production traffic are mixed together for hours, not
seconds?

Model matrix: the 10 models representing the highest-traffic production
workspaces, derived from persona-count-weighted workspace routing (see
reports/ for the derivation — live Prometheus telemetry had too little
history to trust). 3 already existed as MLX builds; 7 were located on HF and
pulled this session (see git-ignored pull log).

Unlike bench_omlx_v3.py's shootout gate (fixed short duration, uniform
round-robin), this:
  - weights model selection by the same persona-count proxy, so the model
    mix approximates a real traffic day, not an even split
  - runs for hours, not 2 minutes
  - polls oMLX's own /health endpoint every 60s for engine_pool memory/
    loaded-model state, not just request-level success/failure, so eviction
    thrashing or slow leaks are visible even if every request still succeeds
  - writes an incremental checkpoint every snapshot interval (not just at
    the end) so a killed or crashed run still leaves usable data
  - treats oMLX process downtime (health polling failures) as a first-class
    finding, not a script-ending error — it retries with backoff and records
    the outage window

Usage:
  python3 tests/benchmarks/bench_omlx_soak.py --duration 10800 --concurrency 5
"""

from __future__ import annotations

import argparse
import json
import random
import threading
import time
from datetime import UTC, datetime
from pathlib import Path

import bench_omlx_v3 as base
import httpx

RESULTS_DIR = Path(__file__).parent / "results"
OMLX_URL = "http://localhost:8085"
OLLAMA_URL = "http://localhost:11434"
HEALTH_POLL_INTERVAL_S = 60
CHECKPOINT_INTERVAL_S = 300
MAX_TOKENS = 800

# name -> (oMLX model id, weight). Weight = persona count routed to the
# production workspace this model serves (compliance+documents combined for
# granite-4.1-8b since both route there) — the best available traffic proxy
# given live telemetry only covers ~7h of mostly-test traffic.
MODEL_WEIGHTS: dict[str, tuple[str, int]] = {
    "coder": ("Qwen3-Coder-30B-A3B-Instruct-4bit", 34),
    # oQ4 (unsloth "optimized quant") conversion HTTP 409'd on this oMLX
    # version: "Received 2 parameters not in model: lm_head.biases,
    # lm_head.scales" — a real format incompatibility, not a fluke (live
    # verified). mxfp8 from a different uploader loads and answers cleanly.
    "granite-8b": ("granite-4.1-8b-mxfp8", 11),
    "vulnllm": ("VulnLLM-R-7B-4bit", 10),
    "deepseek-r1": ("DeepSeek-R1-0528-Qwen3-8B-4bit", 9),
    "qwen-vl": ("Qwen3-VL-32B-Instruct-4bit", 8),
    "tongyi-research": ("Tongyi-DeepResearch-30B-A3B-abliterated-4bit", 8),
    "granite-30b": ("granite-4.1-30b-4bit", 7),
    "gemma-daily": ("gemma-4-26b-a4b-it-QAT-4bit", 4),
    "hauhaucs-creative": ("Qwen3.6-35B-A3B-HauhauCS-Aggressive-4bit", 4),
    "qwen35-9b": ("huihui-ai--Huihui-Qwen3.5-9B-abliterated-mlx-4bit", 3),
}

# Same names/weights, production Ollama GGUF tags (the real model_hint values
# from config/portal.yaml for each of the same 10 workspaces) — for a direct
# apples-to-apples soak against the oMLX run above.
OLLAMA_MODEL_WEIGHTS: dict[str, tuple[str, int]] = {
    "coder": ("qwen3-coder:30b-a3b-q4_K_M-ctx16k", 34),
    "granite-8b": ("granite4.1:8b-ctx16k", 11),
    "vulnllm": ("hf.co/mradermacher/VulnLLM-R-7B-GGUF:q4_K_M-ctx8k", 10),
    "deepseek-r1": ("hf.co/unsloth/DeepSeek-R1-0528-Qwen3-8B-GGUF:Q4_K_XL-ctx64k", 9),
    "qwen-vl": ("qwen3-vl:32b-ctx8k", 8),
    "tongyi-research": ("huihui_ai/tongyi-deepresearch-abliterated:latest-ctx64k", 8),
    "granite-30b": ("granite4.1:30b-ctx64k", 7),
    "gemma-daily": ("gemma4:26b-a4b-it-qat-ctx8k", 4),
    "hauhaucs-creative": (
        "fredrezones55/Qwen3.6-35B-A3B-Uncensored-HauhauCS-Aggressive:Q4-ctx8k",
        4,
    ),
    "qwen35-9b": ("huihui_ai/qwen3.5-abliterated:9b-ctx8k", 3),
}

PROMPTS = list(base.SHOOTOUT_PROMPTS.values()) + [
    "Explain the CAP theorem and give a concrete example of a system that "
    "chooses availability over consistency, and why that's the right choice "
    "for it.",
    "Write a short incident postmortem for a service that returned 500s for "
    "10 minutes because a downstream cache expired all keys simultaneously. "
    "Include root cause, impact, and two concrete prevention items.",
]


class Soak:
    def __init__(self, duration_s: int, concurrency: int, tag: str | None, engine: str = "omlx"):
        self.duration_s = duration_s
        self.concurrency = concurrency
        self.tag = tag
        self.engine = engine
        self.url = OMLX_URL if engine == "omlx" else OLLAMA_URL
        self.model_weights = MODEL_WEIGHTS if engine == "omlx" else OLLAMA_MODEL_WEIGHTS
        self.names = list(self.model_weights)
        self.weights = [self.model_weights[n][1] for n in self.names]
        self.stop_at = 0.0
        self.lock = threading.Lock()
        self.samples: list[dict] = []
        self.health_snapshots: list[dict] = []
        self.outages: list[dict] = []
        self.started = datetime.now(UTC)
        self.started_perf = 0.0
        self._stop_event = threading.Event()

    def _pick_model(self) -> tuple[str, str]:
        name = random.choices(self.names, weights=self.weights, k=1)[0]
        return name, self.model_weights[name][0]

    def _request_worker(self) -> None:
        while time.perf_counter() < self.stop_at and not self._stop_event.is_set():
            name, model_id = self._pick_model()
            prompt = random.choice(PROMPTS)
            r = base.one_request(
                self.url, model_id, [{"role": "user", "content": prompt}], max_tokens=MAX_TOKENS
            )
            r["model_name"] = name
            r["model_id"] = model_id
            r["t"] = time.perf_counter() - self.started_perf
            with self.lock:
                self.samples.append(r)

    def _poll_omlx_health(self) -> dict:
        resp = httpx.get(f"{self.url}/health", timeout=10)
        resp.raise_for_status()
        data = resp.json()
        return {**data.get("engine_pool", {}), "status": data.get("status")}

    def _poll_ollama_health(self) -> dict:
        # No /health or memory-ceiling concept on Ollama — /api/ps lists
        # currently loaded models; sum their VRAM footprint as the memory
        # proxy and treat "ceiling" as unknown (Ollama evicts/queues rather
        # than enforcing an admission-control cap the way oMLX does).
        resp = httpx.get(f"{self.url}/api/ps", timeout=10)
        resp.raise_for_status()
        models = resp.json().get("models", [])
        mem = sum(m.get("size_vram") or m.get("size") or 0 for m in models)
        return {
            "loaded_count": len(models),
            "current_model_memory": mem,
            "final_ceiling": None,
            "status": "healthy",
            "loaded_models": [m.get("name") for m in models],
        }

    def _health_poll(self) -> None:
        in_outage = False
        outage_start = None
        poll = self._poll_omlx_health if self.engine == "omlx" else self._poll_ollama_health
        while not self._stop_event.is_set():
            try:
                engine_pool = poll()
                snap = {
                    "t": round(time.perf_counter() - self.started_perf, 1),
                    "wall": datetime.now(UTC).isoformat(),
                    **engine_pool,
                }
                with self.lock:
                    self.health_snapshots.append(snap)
                ceiling = snap.get("final_ceiling")
                print(
                    f"    [health] t={snap['t']:.0f}s loaded={snap.get('loaded_count')} "
                    f"mem={snap.get('current_model_memory', 0) / 1e9:.1f}GB "
                    + (f"ceiling={ceiling / 1e9:.1f}GB" if ceiling else "ceiling=n/a"),
                    flush=True,
                )
                if in_outage:
                    with self.lock:
                        self.outages.append(
                            {
                                "start_t": outage_start,
                                "end_t": snap["t"],
                                "duration_s": round(snap["t"] - outage_start, 1),
                            }
                        )
                    print(
                        f"    [health] RECOVERED after {snap['t'] - outage_start:.0f}s outage",
                        flush=True,
                    )
                    in_outage = False
            except Exception as exc:
                if not in_outage:
                    outage_start = time.perf_counter() - self.started_perf
                    in_outage = True
                    print(f"    [health] OUTAGE START at t={outage_start:.0f}s: {exc}", flush=True)
            self._stop_event.wait(HEALTH_POLL_INTERVAL_S)
        if in_outage:
            with self.lock:
                self.outages.append(
                    {"start_t": outage_start, "end_t": None, "duration_s": None, "ongoing": True}
                )

    def _checkpoint(self) -> Path:
        import statistics as st

        with self.lock:
            samples = list(self.samples)
            health = list(self.health_snapshots)
            outages = list(self.outages)

        ok = [r for r in samples if "error" not in r]
        fails = [r for r in samples if "error" in r]
        per_model: dict[str, dict] = {}
        for name in self.names:
            m_ok = [r for r in ok if r["model_name"] == name]
            m_fail = [r for r in fails if r["model_name"] == name]
            per_model[name] = {
                "ok": len(m_ok),
                "fail": len(m_fail),
                "tps_mean": round(st.mean([r["tps"] for r in m_ok if r.get("tps")]), 1)
                if any(r.get("tps") for r in m_ok)
                else None,
            }

        result = {
            "task": "omlx-fleet-soak-v1",
            "engine": self.engine,
            "started": self.started.isoformat(),
            "elapsed_s": round(time.perf_counter() - self.started_perf, 1),
            "duration_s": self.duration_s,
            "concurrency": self.concurrency,
            "model_weights": self.model_weights,
            "total_requests": len(samples),
            "ok": len(ok),
            "failures": len(fails),
            "failure_samples": [
                {"model": r["model_name"], "error": r.get("error"), "t": r.get("t")}
                for r in fails[-20:]
            ],
            "per_model": per_model,
            "health_snapshots": health,
            "outages": outages,
            "peak_memory_bytes": max((h.get("current_model_memory", 0) for h in health), default=0),
            "ceiling_bytes": health[-1].get("final_ceiling") if health else None,
        }

        ts = self.started.strftime("%Y%m%dT%H%M%SZ")
        tag = f"_{self.tag}" if self.tag else ""
        out = RESULTS_DIR / f"{self.engine}_fleet_soak{tag}_{ts}.json"
        out.write_text(json.dumps(result, indent=2))
        return out

    def run(self) -> Path:
        self.started_perf = time.perf_counter()
        self.stop_at = self.started_perf + self.duration_s

        health_thread = threading.Thread(target=self._health_poll, daemon=True)
        health_thread.start()

        workers = [threading.Thread(target=self._request_worker) for _ in range(self.concurrency)]
        for w in workers:
            w.start()

        out_path = RESULTS_DIR / "unwritten"
        next_checkpoint = self.started_perf + CHECKPOINT_INTERVAL_S
        while any(w.is_alive() for w in workers):
            time.sleep(5)
            if time.perf_counter() >= next_checkpoint:
                out_path = self._checkpoint()
                with self.lock:
                    n = len(self.samples)
                    f = sum(1 for r in self.samples if "error" in r)
                print(f"  [checkpoint] {n} requests, {f} failures -> {out_path.name}", flush=True)
                next_checkpoint += CHECKPOINT_INTERVAL_S

        self._stop_event.set()
        health_thread.join(timeout=15)
        out_path = self._checkpoint()
        return out_path


def main() -> None:
    p = argparse.ArgumentParser(description="Multi-model fleet soak test (oMLX or Ollama)")
    p.add_argument("--engine", choices=["omlx", "ollama"], default="omlx")
    p.add_argument("--duration", type=int, default=10800, help="seconds (default 3h)")
    p.add_argument("--concurrency", type=int, default=5)
    p.add_argument("--tag", default=None)
    args = p.parse_args()

    soak = Soak(args.duration, args.concurrency, args.tag, engine=args.engine)
    print(
        f"=== soak start [{args.engine}]: {args.duration}s @ concurrency={args.concurrency}, "
        f"{len(soak.model_weights)} models weighted ===",
        flush=True,
    )
    out = soak.run()
    print(f"\nFinal results -> {out}")


if __name__ == "__main__":
    main()
