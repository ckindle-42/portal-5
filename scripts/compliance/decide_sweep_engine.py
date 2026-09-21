#!/usr/bin/env python3
"""SPLASH_SWEEP_ACCELERATION_V1 P5 - the promotion decision, made by the data.

Reads the four-arm receipt and applies the criteria pre-committed in the task
file. No operator step. Deterministic: anyone can re-run it against the same
receipt and get the same answer.

Promotion means ONE thing: the compliance SWEEP entry point defaults to the
splash dialect. It does not touch the conversation lane, the workspace seat,
config/portal.yaml, or PROMOTE_POLICY. The conversation lane already has x157
append reuse on the incumbent and no measurement here says otherwise.

Exit codes:
    0 - decision made and written (promoted or not; both are outcomes)
    2 - the receipt is present but an arm is missing or mislabeled
    3 - the receipt is absent or unreadable
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import pathlib
import sys
from typing import Any

# Pre-committed criteria. Every one must hold for promotion.
MIN_ENGINE_SPEEDUP = 2.0  # arm C vs arm D - the ENGINE's own contribution
MIN_WALL_SPEEDUP = 2.0  # arm C vs arm A - the end-to-end change being bought
MIN_JACCARD = 0.80  # arm C's determination set vs arm A's
MAX_PARSE_FAIL_DELTA = 0.05  # arm C's parse-failure rate minus arm A's
MIN_OK_RATE = 0.95  # arm C cells that completed without error


def _rate(num: int, den: int) -> float:
    return round(num / den, 4) if den else 0.0


def _arm_endpoint_error(name: str, arm: dict[str, Any]) -> str:
    """Endpoint integrity: the human-readable reason an arm cannot be scored.

    Refuse to score an arm whose rows came from more than one endpoint, or
    from an endpoint that does not match its dialect — an empty string means
    the arm is attributable."""
    eps = arm.get("endpoints_observed") or []
    if len(eps) > 1:
        return (
            f"arm {name} saw multiple endpoints {eps}; the measurement "
            f"cannot be attributed to one engine"
        )
    if eps:
        ep = eps[0]
        if arm["dialect"] == "openai-compat" and "/v1/chat/completions" not in ep:
            return f"arm {name} declares splash but was served by {ep}"
        if arm["dialect"] == "ollama-native" and "/api/chat" not in ep:
            return f"arm {name} declares ollama but was served by {ep}"
    return ""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arms", required=True, type=pathlib.Path)
    ap.add_argument("--out", required=True, type=pathlib.Path)
    ap.add_argument(
        "--apply",
        action="store_true",
        help="write the promotion into config when the data says promote",
    )
    args = ap.parse_args()

    if not args.arms.exists():
        print(f"FAIL: no arms receipt at {args.arms}", file=sys.stderr)
        return 3
    data = json.loads(args.arms.read_text())
    arms = data.get("arms") or {}

    missing = [a for a in ("A", "C", "D") if a not in arms]
    if missing:
        print(
            f"FAIL: arms {missing} absent; A (incumbent), C (proposal) and "
            f"D (concurrency control) are all required to attribute the result",
            file=sys.stderr,
        )
        return 2

    # Endpoint integrity: refuse to score an arm whose rows came from more than
    # one endpoint, or from an endpoint that does not match its dialect.
    for name, arm in arms.items():
        err = _arm_endpoint_error(name, arm)
        if err:
            print(f"FAIL: {err}", file=sys.stderr)
            return 2

    # An unearned measurement is an error, not a value: 40/40 splash cells
    # once reported prompt_eval_count: 0 against a live 23,119 on the same
    # material, and that zero was scored as though it were a number. A cell
    # with no prompt-token count was not measured; refuse to decide on an arm
    # that contains one.
    for name, arm in arms.items():
        unaccounted = arm.get("unaccounted") or []
        if unaccounted:
            print(
                f"FAIL: arm {name} has {len(unaccounted)} unaccounted cell(s) "
                f"(completed with no prompt-token count): {unaccounted[:10]}",
                file=sys.stderr,
            )
            return 2

    # arm_a/arm_c/arm_d are the receipt's arms A/C/D: the task's criteria
    # table speaks of C-over-D (the engine's contribution) and C-over-A (the
    # end-to-end change).
    arm_a, arm_c, arm_d = arms["A"], arms["C"], arms["D"]
    cmp_c = (data.get("comparison_vs_A") or {}).get("C") or {}

    wall_speedup = (
        round(arm_a["total_wall_s"] / arm_c["total_wall_s"], 3) if arm_c["total_wall_s"] else 0.0
    )
    engine_speedup = (
        round(arm_d["total_wall_s"] / arm_c["total_wall_s"], 3) if arm_c["total_wall_s"] else 0.0
    )
    jaccard = cmp_c.get("jaccard_vs_A")
    a_parse_fail = _rate(arm_a.get("n_parse_failed", 0), arm_a.get("n_refs", 0))
    c_parse_fail = _rate(arm_c.get("n_parse_failed", 0), arm_c.get("n_refs", 0))
    c_ok_rate = _rate(arm_c.get("n_ok", 0), arm_c.get("n_refs", 0))

    checks = []
    checks.append(
        {
            "name": "engine_speedup_C_over_D",
            "value": engine_speedup,
            "floor": MIN_ENGINE_SPEEDUP,
            "ok": engine_speedup >= MIN_ENGINE_SPEEDUP,
            "why": "the engine's own contribution, with concurrency held constant",
        }
    )
    checks.append(
        {
            "name": "wall_speedup_C_over_A",
            "value": wall_speedup,
            "floor": MIN_WALL_SPEEDUP,
            "ok": wall_speedup >= MIN_WALL_SPEEDUP,
            "why": "the end-to-end change actually being bought",
        }
    )
    checks.append(
        {
            "name": "reading_agreement_jaccard",
            "value": jaccard,
            "floor": MIN_JACCARD,
            "ok": jaccard is not None and jaccard >= MIN_JACCARD,
            "why": "a faster sweep that determines different things is a different sweep",
        }
    )
    checks.append(
        {
            "name": "parse_failure_delta",
            "value": round(c_parse_fail - a_parse_fail, 4),
            "ceiling": MAX_PARSE_FAIL_DELTA,
            "ok": (c_parse_fail - a_parse_fail) <= MAX_PARSE_FAIL_DELTA,
            "why": "a too-small window corrupts determination JSON before it slows anything",
        }
    )
    checks.append(
        {
            "name": "completion_rate",
            "value": c_ok_rate,
            "floor": MIN_OK_RATE,
            "ok": c_ok_rate >= MIN_OK_RATE,
            "why": "cells that error under concurrency are not a faster sweep",
        }
    )

    promote = all(c["ok"] for c in checks)

    decision = {
        "run_id": _dt.datetime.now(_dt.UTC).isoformat(),
        "arms_receipt": str(args.arms),
        "standard": data.get("standard"),
        "measured": {
            "A_wall_s": arm_a["total_wall_s"],
            "B_wall_s": (arms.get("B") or {}).get("total_wall_s"),
            "C_wall_s": arm_c["total_wall_s"],
            "D_wall_s": arm_d["total_wall_s"],
            "wall_speedup_C_over_A": wall_speedup,
            "engine_speedup_C_over_D": engine_speedup,
            "concurrency_speedup_D_over_A": (
                round(arm_a["total_wall_s"] / arm_d["total_wall_s"], 3)
                if arm_d["total_wall_s"]
                else None
            ),
            "jaccard_C_vs_A": jaccard,
        },
        "checks": checks,
        "decision": "PROMOTE_SPLASH_FOR_SWEEP" if promote else "KEEP_OLLAMA_FOR_SWEEP",
        "scope_note": (
            "This decision governs the compliance SWEEP lane only. The conversation "
            "lane keeps its seat: the incumbent already reuses the append prefix x157 "
            "and nothing measured here speaks to conversation quality or latency."
        ),
        "verdict": "PASS",
    }

    if promote and args.apply:
        cfg = pathlib.Path("config/compliance/sweep_engine.json")
        cfg.parent.mkdir(parents=True, exist_ok=True)
        cfg.write_text(
            json.dumps(
                {
                    "dialect": "openai-compat",
                    "model": arm_c["model"],
                    "concurrency": arm_c["concurrency"],
                    "decided_by": str(args.out),
                    "decided_at": decision["run_id"],
                },
                indent=2,
            )
        )
        decision["applied_to"] = str(cfg)
        print(f"APPLIED: {cfg}")
    elif promote:
        decision["applied_to"] = None
        print("PROMOTE decided but --apply not passed; config unchanged")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(decision, indent=2, default=str))
    print(f"WROTE {args.out}")
    print(f"DECISION: {decision['decision']}")
    for c in checks:
        bound = c.get("floor", c.get("ceiling"))
        print(f"  [{'OK ' if c['ok'] else 'NO '}] {c['name']}: {c['value']} (bound {bound})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
