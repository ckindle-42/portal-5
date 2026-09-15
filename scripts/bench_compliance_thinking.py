#!/usr/bin/env python
"""Measure the reasoning confound on the compliance reading suite.

The acceptance cases are run twice on one fixed revision by
``verify_compliance_reading_acceptance.py``: arm A with the production
transports (``think:false``), arm B with thinking enabled and a budget that fits
a reasoning trace. Nothing is promoted. This script supplies the part that arm
A/B execution cannot: **which seats can actually reason**, and the case
inventory the two arms are compared over.

Why this exists: every compliance capability measurement taken before 8ccaa84a
was made by a model that was reasoning despite declaring ``think:false`` (that
commit found the flag was being dropped by the OpenAI-compat layer and names
auto-compliance among the twelve affected workspaces). The live 26-case
qualification ran after it, with reasoning genuinely off. The F2 0.952-1.000
judgment-probe result and the 13/26 live result are therefore not comparable,
and the module's central capability claim currently rests on the earlier one.

The capability probe is not a formality here. On the D0-M roster only
``qwen38`` answers ``think:true``; ``granite4.1:30b`` and
``mistral-small3.2:24b`` return HTTP 400 "does not support thinking". Arm B
therefore restores reasoning to one of three council seats, and any delta it
measures is a *floor*, not the architecture's ceiling. A probe that quietly
substituted a thinking model for a non-thinking seat would report a different
roster's number as this roster's; it does not.
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

OLLAMA = "http://localhost:11434/api/chat"
SUITE = Path("tests/data/compliance_reading_acceptance.json")


def chat(
    model: str,
    system: str,
    user: str,
    *,
    think: bool,
    budget: int,
    fmt: Any = "json",
) -> dict[str, Any]:
    """One /api/chat call. Returns content, thinking and timing.

    Native /api/chat returns ``message.thinking`` separately from
    ``message.content``, so a reasoning trace does not contaminate strict JSON.
    A model without thinking capability answers 400; that is reported, never
    silently downgraded.
    """
    payload: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "stream": False,
        "format": fmt,
        "think": think,
        "options": {"temperature": 0.0, "num_predict": budget},
    }
    req = urllib.request.Request(
        OLLAMA,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    started = time.time()
    try:
        with urllib.request.urlopen(req, timeout=900) as response:  # noqa: S310
            body = json.load(response)
    except urllib.error.HTTPError as exc:
        return {
            "error": f"HTTP {exc.code}",
            "detail": exc.read().decode("utf-8", "replace")[:400],
            "elapsed": time.time() - started,
        }
    except OSError as exc:  # connection refused, timeout — Ollama not up
        return {"error": "UNREACHABLE", "detail": str(exc)[:400], "elapsed": time.time() - started}
    message = body.get("message") or {}
    return {
        "content": message.get("content", "") or "",
        "thinking": message.get("thinking", "") or "",
        "elapsed": time.time() - started,
        "eval_count": body.get("eval_count", 0),
    }


def probe_thinking(model: str) -> dict[str, Any]:
    """Ask one model to reason. Report the verdict with its evidence.

    A capability claim with no evidence attached is the thing this whole task is
    about, so the probe keeps the server's own words for the report.
    """
    result = chat(model, "Reply with {}", "ping", think=True, budget=64, fmt="json")
    if "error" in result:
        return {
            "model": model,
            "thinking_capable": False,
            "evidence": f"{result['error']}: {result.get('detail', '')}".strip(),
            "elapsed": round(result["elapsed"], 1),
        }
    return {
        "model": model,
        "thinking_capable": True,
        "evidence": f"200, message.thinking = {len(result['thinking'])} chars",
        "elapsed": round(result["elapsed"], 1),
    }


def _load_cases() -> dict[str, dict[str, Any]]:
    data = json.loads(SUITE.read_text())
    cases = data["cases"] if isinstance(data, dict) and "cases" in data else data
    return {str(c.get("id")): c for c in cases}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", default="02,04,05,08,10,16,19,20,23,25")
    parser.add_argument(
        "--model",
        action="append",
        default=[],
        help="probe this model; repeatable. Default: the configured council roster.",
    )
    parser.add_argument("--out", default="reports/compliance/THINKING_CONFOUND_V1.json")
    args = parser.parse_args()

    models = args.model
    if not models:
        from portal.modules.compliance.core.runtime_config import seat_roster

        roster = seat_roster()
        models = [s["model"] for s in roster]
        labels = {s["model"]: s["id"] for s in roster}
    else:
        labels = dict.fromkeys(models, "(explicit)")

    probes = [{**probe_thinking(m), "seat": labels.get(m, "?")} for m in models]

    ids = [c.strip() for c in args.cases.split(",") if c.strip()]
    by_id = _load_cases()
    rows: list[dict[str, Any]] = []
    for case_id in ids:
        case = by_id.get(case_id)
        if case is None:
            rows.append({"case": case_id, "status": "NOT_IN_SUITE"})
            continue
        rows.append(
            {
                "case": case_id,
                "requirement_id": case.get("requirement_id", ""),
                # the fixture's expectation field is `expected` (HEAD), not `expect`
                "expected": case.get("expected", {}),
                "notes": case.get("notes", ""),
            }
        )

    capable = [p for p in probes if p["thinking_capable"]]
    payload = {
        "recorded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "seats_probed": probes,
        "seats_thinking_capable": len(capable),
        "seats_total": len(probes),
        "arm_b_reach": (
            f"{len(capable)}/{len(probes)} council seats reason under arm B; "
            "the remainder downgrade and are recorded as downgraded"
        ),
        "cases": rows,
        "note": (
            "arm A/B execution is driven by "
            "scripts/verify_compliance_reading_acceptance.py with the transport "
            "injected; this file records the case inventory and the per-seat "
            "capability probe that bounds what arm B can possibly show"
        ),
    }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2))

    for p in probes:
        mark = "yes" if p["thinking_capable"] else "NO "
        print(f"  [{mark}] {p['seat']:<10} {p['model']}\n           {p['evidence']}")
    print(f"\nthinking-capable seats: {len(capable)}/{len(probes)}   cases: {len(rows)}")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
