"""Live verification of the P1/P2/P3 pipeline work (PIPELINE_ALIGNMENT_V1).

Three checks, one receipt each:

1. **owned seats** — every council seat called through its production transport
   (``council._ollama_seat``, which addresses the seat's compliance-owned
   workspace) must land on THAT workspace, and the receipt must carry the
   pipeline's APPLIED sampling/thinking (the §P3 options_applied lift):
   qwen38/granite41 at temperature 0.0 + thinking suppressed, deepseek-r1 at
   its vendor 0.6 + thinking enabled.
2. **overflow route** — the census's largest oversized requirement
   (CIP-003-8 R1, priced ~52k tokens over a 32k window) read through
   ``sweep.map_read`` with the §P2 overflow seat must route
   ``overflow_model`` -> ``compliance-reading-overflow`` and complete.
3. **fallback capacity** — the Ollama fallback tag must hold the overflow
   window: one native call at ``num_ctx 65536`` with a ~60k-token prompt,
   all of it evaluated, read back from the runner.

Receipts: p1/owned_workspaces_live.json, p2/overflow_route_live.json.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import time
import urllib.request
from typing import Any

from portal.modules.compliance.core.repository import Repository
from scripts.compliance.truth import _local  # noqa: E402

P1_OUT = _local.RUNS / "pipeline_alignment/p1/owned_workspaces_live.json"
P2_OUT = _local.RUNS / "pipeline_alignment/p2/overflow_route_live.json"
SEAT = "gemma4:26b-a4b-it-q4_K_M-ctx32k"
OVERFLOW_TAG = "gemma4:26b-a4b-it-q4_K_M-ctx64k"
OLLAMA = "http://localhost:11434"

#: What each seat's owned workspace must APPLY (declared in portal.yaml;
#: expected from the qualification/vendor records).
EXPECTED = {
    "qwen38": {
        "workspace": "compliance-council-qwen38",
        "temperature": 0.0,
        "enable_thinking": False,
    },
    "granite41": {
        "workspace": "compliance-council-granite41",
        "temperature": 0.0,
        "enable_thinking": False,
    },
    "deepseek_r1": {
        "workspace": "compliance-council-deepseek-r1",
        "temperature": 0.6,
        "enable_thinking": True,
    },
}


def _seat_check(rows: list[dict[str, Any]]) -> bool:
    import json as _json

    from portal.modules.compliance.core.council import (
        _LAST_TRACE,
        _ollama_seat,
        _seat_address,
    )
    from portal.modules.compliance.core.runtime_config import seat_roster

    roster = {s["id"]: s for s in seat_roster()}
    all_ok = True
    for seat_id, expect in EXPECTED.items():
        seat = roster[seat_id]
        # The seat is addressed EXACTLY as production addresses it — through
        # council._seat_address, which prefers the compliance-owned workspace
        # id (PIPELINE_ALIGNMENT_V1 §P1). A raw tag would resolve through hint
        # first-match and prove nothing about ownership.
        packet = _json.dumps(
            {
                "governing_unit": {"ref": "CIP-002-5.1a R1 Part 1.1"},
                "candidates": [
                    {"commitment_id": "C1", "text": "The operator reviews access annually."}
                ],
                "reference_closure": [],
            }
        )
        started = time.time()
        raw = _ollama_seat(
            _seat_address(seat), "You are a test seat on a compliance council.", packet
        )
        trace = _LAST_TRACE[-1]
        applied = trace.get("applied_options") or {}
        row = {
            "seat": seat_id,
            "model_tag": seat["model"],
            "addressed_as": str(seat.get("workspace") or seat["model"]),
            "expected_workspace": expect["workspace"],
            "trace_workspace": trace.get("workspace"),
            "route_backend": trace.get("route_backend"),
            "served_model": trace.get("served_model"),
            "correlation_id": trace.get("correlation_id"),
            "applied_options": applied,
            "expected": expect,
            "workspace_ok": trace.get("workspace") == expect["workspace"],
            "temperature_ok": applied.get("temperature") == expect["temperature"],
            "thinking_ok": (
                (applied.get("enable_thinking") is expect["enable_thinking"]) if applied else None
            ),
            "raw_is_json_object": str(raw).lstrip().startswith("{"),
            "wall_s": round(time.time() - started, 2),
        }
        row["ok"] = bool(row["workspace_ok"] and row["temperature_ok"] and row["thinking_ok"])
        all_ok &= row["ok"]
        rows.append(row)
        print(
            f"{seat_id:<12} ws={trace.get('workspace')} backend={trace.get('route_backend')} "
            f"temp={applied.get('temperature')} think={applied.get('enable_thinking')} "
            f"ok={row['ok']} ({row['wall_s']}s)",
            flush=True,
        )
    return all_ok


def _overflow_check(repo: Repository) -> dict[str, Any]:
    from portal.modules.compliance.core.sweep import map_read

    started = time.time()
    payload = map_read(
        repo,
        "CIP-003-8 R1",
        model=SEAT,
        write=False,
        overflow_model=OVERFLOW_TAG,
    )
    fit = payload.get("context_fit") or {}
    row = {
        "ref": "CIP-003-8 R1",
        "route": fit.get("route"),
        "seat_window": fit.get("seat_window"),
        "overflow_window": fit.get("num_ctx"),
        "estimated_tokens": fit.get("estimated_tokens"),
        "dialect": payload.get("dialect"),
        "workspace": payload.get("workspace"),
        "route_backend": payload.get("route_backend"),
        "served_model": payload.get("served_model"),
        "correlation_id": payload.get("correlation_id"),
        "applied_options": payload.get("applied_options"),
        "call_error": payload.get("error"),
        "parse_error": (payload.get("determinations") or {}).get("parse_error"),
        "determinations_requested": (payload.get("determinations") or {}).get("requested"),
        "wall_s": round(time.time() - started, 2),
    }
    row["ok"] = bool(
        row["route"] == "overflow_model"
        and row["workspace"] == "compliance-reading-overflow"
        and not row["call_error"]
    )
    print(
        f"overflow: route={row['route']} ws={row['workspace']} backend={row['route_backend']} "
        f"tokens~{row['estimated_tokens']} ok={row['ok']} ({row['wall_s']}s)",
        flush=True,
    )
    return row


def _fallback_capacity_check() -> dict[str, Any]:
    """One native call at num_ctx 65536 with a ~60k-token prompt on the
    ctx64k tag — the fallback must HOLD the window, not just declare it."""
    filler = (
        "The reliability standard requires each responsible entity to maintain "
        "documented evidence of its training program and to review that program "
        "annually against the measured criteria. "
    )
    # Sized against the tokenization the fallback ACTUALLY produced on the
    # first probe (2026-09-26): highly repetitive filler compressed to ~7
    # bytes/token on gemma's tokenizer, so 200KB priced at ~60k by the corpus
    # ratio fed only 28.7k tokens. 450KB at that observed ratio prices at
    # ~64k — inside 65,536 with the answer's room, and the check reads the
    # runner's own prompt_eval_count, never the estimate.
    prompt = filler * (450_000 // len(filler))
    payload = {
        "model": OVERFLOW_TAG,
        "messages": [
            {
                "role": "user",
                "content": prompt
                + "\n\nReply with exactly one word: the last word of the material.",
            }
        ],
        "stream": False,
        "options": {"num_ctx": 65536, "num_predict": 8, "temperature": 0.0},
    }
    request = urllib.request.Request(
        f"{OLLAMA}/api/chat",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    started = time.time()
    try:
        with urllib.request.urlopen(request, timeout=1800) as response:  # noqa: S310
            body = json.load(response)
        prompt_tokens = int(body.get("prompt_eval_count") or 0)
        applied_ctx = _ps_context_length(OVERFLOW_TAG)
        row = {
            "tag": OVERFLOW_TAG,
            "num_ctx_requested": 65536,
            "prompt_bytes": len(prompt),
            "prompt_tokens": prompt_tokens,
            "applied_ctx_from_ps": applied_ctx,
            "answered": bool((body.get("message") or {}).get("content", "").strip()),
            "wall_s": round(time.time() - started, 2),
        }
        row["ok"] = bool(prompt_tokens >= 50_000 and (applied_ctx or 0) >= 65_536)
    except Exception as exc:  # noqa: BLE001 — a failed capacity check is the finding
        row = {
            "tag": OVERFLOW_TAG,
            "ok": False,
            "error": f"{type(exc).__name__}: {exc}",
            "wall_s": round(time.time() - started, 2),
        }
    print(
        f"fallback capacity: tokens={row.get('prompt_tokens')} applied_ctx="
        f"{row.get('applied_ctx_from_ps')} ok={row['ok']}",
        flush=True,
    )
    return row


def _ps_context_length(tag: str) -> int:
    try:
        with urllib.request.urlopen(f"{OLLAMA}/api/ps", timeout=10) as response:  # noqa: S310
            models = (json.load(response) or {}).get("models") or []
        for entry in models:
            if tag in (entry.get("name"), entry.get("model")):
                return int(entry.get("context_length") or 0)
    except Exception:  # noqa: BLE001 — unknown reported as 0
        return 0
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-seats", action="store_true")
    parser.add_argument("--skip-overflow", action="store_true")
    parser.add_argument("--skip-fallback", action="store_true")
    args = parser.parse_args()

    receipts: dict[str, Any] = {}
    if not args.skip_seats:
        rows: list[dict[str, Any]] = []
        ok = _seat_check(rows)
        receipts["seats"] = {"ok": ok, "rows": rows}
        P1_OUT.parent.mkdir(parents=True, exist_ok=True)
        P1_OUT.write_text(
            json.dumps(
                {
                    "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "check": "council seats live through their owned workspaces (P1 + P3)",
                    **receipts["seats"],
                },
                indent=2,
                default=str,
            )
        )
        print(f"written: {P1_OUT}")

    if not (args.skip_overflow and args.skip_fallback):
        # Merge with an existing receipt rather than overwrite it: the checks
        # run independently (--skip-* resume flags) and one receipt must hold
        # both halves.
        p2: dict[str, Any] = {}
        if P2_OUT.is_file():
            with contextlib.suppress(Exception):
                p2 = json.loads(P2_OUT.read_text())
        p2.pop("ok", None)
        p2.pop("generated_at", None)
        if not args.skip_overflow:
            repo = Repository()
            p2["overflow_route"] = _overflow_check(repo)
            repo.close()
        if not args.skip_fallback:
            p2["fallback_capacity"] = _fallback_capacity_check()
        p2["ok"] = all(p2.get(k, {}).get("ok") for k in ("overflow_route", "fallback_capacity"))
        P2_OUT.parent.mkdir(parents=True, exist_ok=True)
        P2_OUT.write_text(
            json.dumps(
                {
                    "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "check": "overflow route end-to-end + fallback window capacity (P2)",
                    **p2,
                },
                indent=2,
                default=str,
            )
        )
        print(f"written: {P2_OUT}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
