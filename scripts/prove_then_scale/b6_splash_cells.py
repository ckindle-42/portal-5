#!/usr/bin/env python3
"""A2's six cases re-run on splash (TASK_COMPLIANCE_DELIVER_AND_SETTLE_ENGINE_V1 §B6, Coupling 2).

Same material, same one-call/no-tools shape, same judged-by-reading protocol
as p1_experiment.py — different ENGINE: the call goes to the splash forwarder
(:8086, OpenAI surface, Bearer key, reasoning_effort none). The question B6
answers is not "is splash fast" but "does the engine change what the model
says": flat 4-bit weights, an 8-bit KV cache and speculative decoding are
three reasons it might.

Live only; writes JSON cells under reports/compliance/prove_then_scale/b6/.

Usage:
    uv run python scripts/prove_then_scale/b6_splash_cells.py --seat qwen38   # on Qwen3.8-27B-Splash
    uv run python scripts/prove_then_scale/b6_splash_cells.py --seat qwen36   # on Qwen3.6-35B-A3B-Splash
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

import httpx  # noqa: E402

from portal.modules.compliance.core import reading_material  # noqa: E402
from portal.modules.compliance.core.cip_register import Register  # noqa: E402
from portal.modules.compliance.core.repository import Repository  # noqa: E402
from scripts.prove_then_scale.p1_experiment import CASES, cited_sections  # noqa: E402

ART_DIR = REPO_ROOT / "reports" / "compliance" / "prove_then_scale" / "b6"

SPLASH_MODELS = {
    "qwen38": "incoai/Qwen3.8-27B-Splash",
    "qwen36": "incoai/Qwen3.6-35B-A3B-Splash",
}
BASE_URL = os.environ.get("BENCH_SPLASH_URL", "http://localhost:8086")


def run_cell(repo: Repository, seat: str, case: dict[str, str], fixed: dict) -> dict:
    material = reading_material.render(repo, case["ref"], question=case["question"], fixed=fixed)
    if "error" in material:
        return {"case": case["id"], "seat": seat, "error": material["error"]}
    started = time.time()
    try:
        with httpx.Client(timeout=3600.0) as client:
            resp = client.post(
                f"{BASE_URL}/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {os.environ['SPLASH_API_KEY']}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": SPLASH_MODELS[seat],
                    "messages": [{"role": "user", "content": material["text"]}],
                    "max_tokens": 3072,
                    "temperature": 0.0,
                    "reasoning_effort": "none",
                },
            )
        if resp.status_code != 200:
            return {
                "case": case["id"],
                "seat": seat,
                "error": f"HTTP {resp.status_code}: {resp.text[:300]}",
                "wall_s": round(time.time() - started, 2),
            }
        payload = resp.json()
    except Exception as exc:  # noqa: BLE001 — a failed cell is a recorded cell
        return {
            "case": case["id"],
            "seat": seat,
            "error": f"{type(exc).__name__}: {exc}",
            "wall_s": round(time.time() - started, 2),
        }
    choice = (payload.get("choices") or [{}])[0]
    answer = str((choice.get("message") or {}).get("content") or "").strip()
    usage = payload.get("usage") or {}
    cited = cited_sections(repo, answer)
    return {
        "case": case["id"],
        "ref": case["ref"],
        "seat": seat,
        "engine": "splash",
        "model": SPLASH_MODELS[seat],
        "wall_s": round(time.time() - started, 2),
        "prompt_tokens": usage.get("prompt_tokens"),
        "completion_tokens": usage.get("completion_tokens"),
        "cached_tokens": (usage.get("prompt_tokens_details") or {}).get("cached_tokens"),
        "material_chars": material["chars"],
        "cited_regulatory": cited["regulatory"],
        "cited_operator": cited["operator"],
        "cited_both_sides": bool(cited["regulatory"] and cited["operator"]),
        "finish_reason": choice.get("finish_reason", ""),
        "recorded_at": datetime.now(UTC).isoformat(),
        "answer": answer,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seat", required=True, choices=sorted(SPLASH_MODELS))
    args = parser.parse_args()
    if not os.environ.get("SPLASH_API_KEY"):
        print("SPLASH_API_KEY missing (source ~/.portal5/splash.env)")
        return 1
    ART_DIR.mkdir(parents=True, exist_ok=True)
    reg = Register.load()
    repo = Repository()
    try:
        fixed = reading_material.fixed_body(repo, "CIP-007-6")
        if "error" in fixed:
            print(f"FIXED BODY ERROR: {fixed['error']}")
            return 1
        for case in CASES:
            cell_path = ART_DIR / f"cell_splash_{args.seat}_{case['id']}.json"
            if cell_path.exists():
                cell = json.loads(cell_path.read_text())
                if not cell.get("error"):
                    print(f"skip existing {cell_path.name}")
                    continue
            cell = run_cell(repo, args.seat, case, fixed)
            cell_path.write_text(json.dumps(cell, indent=2, default=str))
            cited = (
                "both"
                if cell.get("cited_both_sides")
                else f"reg={len(cell.get('cited_regulatory', []))} op={len(cell.get('cited_operator', []))}"
            )
            print(
                f"splash/{args.seat} {case['id']:<16} wall={cell.get('wall_s', 0):>7} s "
                f"prompt={cell.get('prompt_tokens', '?'):>6} cited={cited} err={str(cell.get('error', ''))[:60]}"
            )
    finally:
        repo.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
