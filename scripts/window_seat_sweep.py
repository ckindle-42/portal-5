#!/usr/bin/env python3
"""WINDOW_AND_SEAT_V1 §P3.2 — per candidate per window, live.

Reuses `tests/benchmarks/bench/lifecycle.py`'s unload/idle discipline
(`_unload_all_running_ollama_models`, `_wait_ollama_idle`); what it could not
reuse: lifecycle benchmarks TPS on short prompts through /v1, while this needs
the per-architecture numbers the seat decision turns on — KV cost of the
window (resident after a ~20k-token prefill minus resident at load), prefill
tok/s at that size, decode tok/s at length, the two-turn cache ratio (the
P2.2 runnability gate), and host free/swap with the model loaded.

Emits reports/compliance/window_and_seat/p3_measurements.json.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tests.benchmarks.bench.lifecycle import (  # noqa: E402
    _unload_all_running_ollama_models,
    _wait_ollama_idle,
)

OLLAMA = "http://localhost:11434"
OUT = (
    Path(__file__).resolve().parents[1] / "reports/compliance/window_and_seat/p3_measurements.json"
)

#: ~20.5k tokens of requirement-shaped filler — the §P1.4 high-water region.
FILLER_UNIT = (
    "The operator shall evaluate security patches and maintain dated records of the evaluation. "
)
FILLER = FILLER_UNIT * 1480  # ≈ 20.6k tokens at ~4.7 chars/tok regulatory prose


def post(path: str, payload: dict, timeout: int = 1800) -> dict:
    req = urllib.request.Request(
        f"{OLLAMA}{path}",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def ps() -> list[dict]:
    req = urllib.request.Request(f"{OLLAMA}/api/ps")  # GET — POST is a 405 here
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.load(r).get("models", [])


def host_free_mb() -> int:
    out = subprocess.check_output(["vm_stat"], text=True)
    page = 16384
    for line in out.splitlines():
        if line.startswith("Pages free"):
            free = int(line.split(":")[1].strip().rstrip("."))
            return free * page // (1024 * 1024)
    return -1


def swap_mb() -> float:
    out = subprocess.check_output(["sysctl", "vm.swapusage"], text=True)
    # "total = 512.00M used = 12.25M free = 499.75M (encrypted)"
    for part in out.split():
        if part.startswith("used"):
            continue
    try:
        used = out.split("used = ")[1].split("M")[0].strip()
        return float(used)
    except (IndexError, ValueError):
        return -1.0


def measure(tag: str, num_ctx: int) -> dict:
    row: dict = {"tag": tag, "num_ctx": num_ctx}
    _unload_all_running_ollama_models()
    _wait_ollama_idle(timeout_s=90)
    row["swap_before_mb"] = swap_mb()

    t0 = time.monotonic()
    post(
        "/api/chat",
        {
            "model": tag,
            "messages": [{"role": "user", "content": "hi"}],
            "stream": False,
            "options": {"temperature": 0.0, "num_predict": 1, "num_ctx": num_ctx},
        },
    )
    row["cold_load_s"] = round(time.monotonic() - t0, 1)

    models = {m["name"]: m for m in ps()}
    row["resident_loaded_gb"] = round(models.get(tag, {}).get("size", 0) / 1e9, 2)
    row["free_mb_loaded"] = host_free_mb()

    # decode at length
    r = post(
        "/api/chat",
        {
            "model": tag,
            "messages": [
                {"role": "user", "content": "Count from 1 to 80, comma separated, no other text."}
            ],
            "stream": False,
            "think": False,
            "options": {"temperature": 0.0, "num_predict": 400, "num_ctx": num_ctx},
        },
    )
    ev, ed = r.get("eval_count", 0), max(r.get("eval_duration", 1), 1) / 1e9
    row["decode_tok_s"] = round(ev / ed, 1)

    # prefill at the high-water mark; KV cache cost = resident delta
    r = post(
        "/api/chat",
        {
            "model": tag,
            "messages": [{"role": "user", "content": FILLER + "\n\nReply with: READ."}],
            "stream": False,
            "think": False,
            "options": {"temperature": 0.0, "num_predict": 8, "num_ctx": num_ctx},
        },
    )
    pc, pd = r.get("prompt_eval_count", 0), max(r.get("prompt_eval_duration", 1), 1) / 1e9
    row["prefill_tokens"] = pc
    row["prefill_tok_s"] = round(pc / pd, 1) if pd else None
    models = {m["name"]: m for m in ps()}
    row["resident_after_prefill_gb"] = round(models.get(tag, {}).get("size", 0) / 1e9, 2)
    row["kv_cost_at_high_water_gb"] = round(
        row["resident_after_prefill_gb"] - row["resident_loaded_gb"], 2
    )
    row["free_mb_after_prefill"] = host_free_mb()

    # two-turn cache ratio on the same material
    msgs = [{"role": "user", "content": FILLER + "\n\nReply with the single word: TURN-ONE."}]
    r1 = post(
        "/api/chat",
        {
            "model": tag,
            "messages": msgs,
            "stream": False,
            "think": False,
            "options": {"temperature": 0.0, "num_predict": 8, "num_ctx": num_ctx},
        },
    )
    p1 = r1.get("prompt_eval_count")
    msgs.append({"role": "assistant", "content": str(r1["message"].get("content", ""))})
    msgs.append({"role": "user", "content": "Reply with the single word: TURN-TWO."})
    r2 = post(
        "/api/chat",
        {
            "model": tag,
            "messages": msgs,
            "stream": False,
            "think": False,
            "options": {"temperature": 0.0, "num_predict": 8, "num_ctx": num_ctx},
        },
    )
    p2 = r2.get("prompt_eval_count")
    row["turn1_prompt"] = p1
    row["turn2_prompt"] = p2
    row["cache_holds"] = bool(p1 and p2 and p2 < p1 * 0.6)

    row["swap_after_mb"] = swap_mb()
    row["swap_grew"] = row["swap_after_mb"] > row["swap_before_mb"] + 512

    _unload_all_running_ollama_models()
    return row


CANDIDATES = [
    ("hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M-ctx32k", 32768, "incumbent"),
    (
        "hf.co/bartowski/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-GGUF:q4_K_M-ctx32k",
        32768,
        "mamba2-moe",
    ),
    ("hf.co/unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q4_K_XL-ctx48k", 49152, "gdn-moe"),
    ("hf.co/unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q4_K_XL-ctx32k", 32768, "gdn-moe"),
    ("gemma4:26b-a4b-it-q4_K_M-ctx32k", 32768, "sliding-global"),
    ("granite4:tiny-h-ctx32k", 32768, "granitehybrid"),
    ("granite4:small-h-ctx32k", 32768, "granitehybrid"),
    ("ling30-tiny-test", 32768, "kda-mla"),
]


def main() -> int:
    rows = []
    for tag, ctx, family in CANDIDATES:
        print(f"== measuring {tag} @ {ctx} ==", flush=True)
        try:
            row = measure(tag, ctx)
        except Exception as exc:  # noqa: BLE001 - a candidate that cannot run is a recorded row
            _unload_all_running_ollama_models()
            row = {"tag": tag, "num_ctx": ctx, "error": f"{type(exc).__name__}: {exc}"}
        row["family"] = family
        rows.append(row)
        OUT.write_text(json.dumps(rows, indent=1))
        print(json.dumps(row, indent=1), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
