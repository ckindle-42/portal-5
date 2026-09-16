#!/usr/bin/env python3
"""Choose the reading seat by reading its answers (BILATERAL_CORPUS_V1 P6.8).

Put the **same real neighbourhood** in front of each candidate seat, ask the
**same real questions**, and keep the transcripts so a person can read them.

There is deliberately no rubric and no score. A rubric that could capture
"did it understand the material" would make the reading model unnecessary, and
selecting on a number is the prescriptive move at one remove. What this script
produces is transcripts, citation-resolution facts, and latency. The judgement
is written by hand, into the report, from reading them.

    uv run python scripts/compliance_reading_seat_probe.py
    uv run python scripts/compliance_reading_seat_probe.py --effort-probe granite4.1:30b-ctx64k
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from portal.modules.compliance.core.reader import read  # noqa: E402
from portal.modules.compliance.core.repository import Repository  # noqa: E402

OUT_ROOT = REPO_ROOT / "reports" / "compliance" / "seat_probe"

#: candidate seats. Each must hold the assembly plus an answer; the transport
#: sets num_ctx per call and Ollama honours it (measured — see the report), so a
#: tag's own baked context only has to not be *smaller* than what we ask for.
SEATS = (
    "hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M-ctx32k",
    "granite4.1:30b-ctx64k",
    "mistral-small3.2:24b-instruct-2506-q4_K_M",
    "glm-4.7-flash:Q4_K_M-ctx64k",
)

#: The second pass. What this workload actually costs is PREFILL over a
#: 16k-25k-token neighbourhood, and prefill compute scales with ACTIVE
#: parameters, not total — so a sparse mixture with ~3B active reads a long
#: document for a fraction of what a dense 24-27B pays. Measured on a 12k-token
#: prompt: glm-4.7-flash (MoE) 244 tok/s prefill against 126 for dense Mistral
#: Small 3.2, 112 for dense Qwen3.8-27B and 95 for hybrid-Mamba granite4.1. The
#: two slowest seats are the two non-MoE ones, which is the whole argument.
#: Small, purpose-fit seats, probed on a SCOPED packet rather than the whole
#: neighbourhood. Two reasons, and the second is the product reason:
#:
#: 1. 55% of the full packet is the implementation plan and the compliance
#:    section, while the requirement itself is 2%. A question about what a
#:    requirement is FOR does not need either, and the `intent` profile is
#:    ~6,500 tokens against ~29,900.
#: 2. The module ships inside the running product. A seat that needs the Docker
#:    stack down is not a seat. granite4.1:30b at 32k context is 36.4 GB
#:    resident and cannot co-exist with 22 containers on this machine; a 5-9 GB
#:    seat can, with room to spare.
#:
#: Foundation-Sec-8B-Reasoning is here because it is the only model in the
#: catalog actually trained for this domain.
SMALL_SEATS = (
    "hf.co/fdtn-ai/Foundation-Sec-8B-Reasoning-Q8_0-GGUF:Q8_0",
    "granite4.1:8b-ctx16k",
    "huihui_ai/qwen3.5-abliterated:9b-ctx64k",
    "qwen3-vl:8b-instruct-q4_K_M",
)

MOE_SEATS = (
    "hf.co/unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q4_K_XL-ctx32k",
    "qwen3-coder:30b-a3b-q4_K_M-ctx256k",
    "gemma4:26b-a4b-it-q4_K_M",
    "huihui_ai/tongyi-deepresearch-abliterated:latest-ctx64k",
)

REF = "CIP-007-6 R2 Part 2.2"

#: real questions, not probes. Each one is something an analyst actually asks,
#: and each one can only be answered well by reading a different part of the
#: neighbourhood.
QUESTIONS = (
    "What is this requirement actually for? What outcome does it exist to achieve, "
    "and what does it deliberately leave to us?",
    "Our own procedure evaluates security patches every thirty calendar days, not "
    "thirty-five. Are we stricter than we need to be, and does that matter?",
    "What would an auditor ask us to produce for this Part, and what in our own "
    "material would satisfy them? Be specific about what is missing.",
)


def _unload(model: str) -> None:
    import urllib.request

    body = json.dumps({"model": model, "messages": [], "keep_alive": 0}).encode()
    request = urllib.request.Request(
        "http://localhost:11434/api/chat", data=body, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(request, timeout=120):  # noqa: S310
            pass
    except Exception:  # noqa: BLE001 - unloading is best effort
        pass


def probe_seats(
    seats: tuple[str, ...],
    questions: tuple[str, ...],
    ref: str,
    effort: bool | str | None,
    profile: str = "",
) -> dict[str, Any]:
    repo = Repository()
    out: dict[str, Any] = {
        "ran_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "ref": ref,
        "questions": list(questions),
        "reasoning_effort": str(effort),
        "profile": profile or "full",
        "seats": [],
    }
    try:
        for model in seats:
            record: dict[str, Any] = {"model": model, "answers": []}
            started = time.time()
            for question in questions:
                payload = read(
                    repo,
                    question,
                    ref,
                    model=model,
                    reasoning_effort=effort,
                    answer_tokens=1600,
                    profile=profile,
                    store=False,
                    timeout=1800,
                )
                record["answers"].append(payload)
                print(
                    f"  {model[:46]:48s} {payload['latency']['elapsed_s']:7.1f}s  "
                    f"eval {payload['latency']['eval_count']:5d}  "
                    f"cited {payload['verification']['num_cited']:3d}  "
                    f"unresolvable {len(payload['verification']['unresolvable']):2d}",
                    flush=True,
                )
            record["total_s"] = round(time.time() - started, 1)
            out["seats"].append(record)
            _unload(model)
    finally:
        repo.close()
    return out


def probe_effort(model: str, ref: str, question: str) -> dict[str, Any]:
    """Reasoning effort measured on THIS call site, not inherited.

    ``DEFAULT_EFFORT`` was settled on a different packet answering a different
    question (a JSON alignment verdict). A prose reading over a 16k-token
    bilateral neighbourhood is not that call, and the earlier measurement says
    nothing about it.
    """
    repo = Repository()
    out: dict[str, Any] = {"model": model, "ref": ref, "question": question, "levels": []}
    try:
        for effort in (False, "low", "medium"):
            payload = read(
                repo,
                question,
                ref,
                model=model,
                reasoning_effort=effort,
                answer_tokens=1600,
                store=False,
                timeout=2400,
            )
            payload["effort_requested"] = str(effort)
            out["levels"].append(payload)
            print(
                f"  effort={str(effort):7s} {payload['latency']['elapsed_s']:7.1f}s  "
                f"thinking {payload['thinking_chars']:6d} chars  "
                f"eval {payload['latency']['eval_count']:5d}  "
                f"cited {payload['verification']['num_cited']:3d}",
                flush=True,
            )
        _unload(model)
    finally:
        repo.close()
    return out


def probe_prefix_cache(model: str, ref: str) -> dict[str, Any]:
    """Does a second question over the SAME neighbourhood reuse the prefix?

    Every turn of a session ships the identical ~16k-token material. If the
    runner's slot cache holds it, turn two costs the delta rather than the whole
    prefill — which is a larger latency win than any seat swap buys, and free.
    Measured rather than assumed: this asks the same question twice, then a
    different question over the same material, and reports prompt_eval_count
    each time. A cache hit shows as a collapsed prompt_eval_count.
    """
    repo = Repository()
    out: dict[str, Any] = {"model": model, "ref": ref, "turns": []}
    try:
        for label, question in (
            ("turn 1 — cold", QUESTIONS[0]),
            ("turn 2 — same question", QUESTIONS[0]),
            ("turn 3 — new question, same material", QUESTIONS[1]),
        ):
            payload = read(
                repo,
                question,
                ref,
                model=model,
                reasoning_effort=False,
                answer_tokens=400,
                store=False,
                timeout=2400,
            )
            latency = payload["latency"]
            out["turns"].append({"label": label, **latency})
            print(
                f"  {label:38s} {latency['elapsed_s']:7.1f}s  "
                f"prompt_eval {latency['prompt_eval_count']:6d} tok in "
                f"{latency['prompt_eval_duration_s']:6.1f}s",
                flush=True,
            )
    finally:
        repo.close()
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seat", action="append", default=None)
    parser.add_argument("--ref", default=REF)
    parser.add_argument("--effort-probe", default="", help="run the effort grid on this model")
    parser.add_argument("--effort", default="false", help="false | low | medium | high")
    parser.add_argument("--moe", action="store_true", help="probe the sparse-mixture seats")
    parser.add_argument("--small", action="store_true", help="probe the small purpose-fit seats")
    parser.add_argument("--profile", default="", help="full | intent | conformance | audit")
    parser.add_argument(
        "--prefix-cache",
        action="store_true",
        help="measure whether a second turn over the SAME neighbourhood reuses the prefix",
    )
    args = parser.parse_args(argv)

    effort: bool | str = False if args.effort.lower() == "false" else args.effort
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")

    if args.prefix_cache:
        out = probe_prefix_cache(args.seat[0] if args.seat else SEATS[3], args.ref)
        target = OUT_ROOT / f"{stamp}-prefix-cache.json"
        target.write_text(json.dumps(out, indent=2, default=str) + "\n", encoding="utf-8")
        print(f"\ntranscripts: {target}")
        return 0
    if args.effort_probe:
        out = probe_effort(args.effort_probe, args.ref, QUESTIONS[1])
        target = OUT_ROOT / f"{stamp}-effort.json"
    else:
        if args.seat:
            chosen = tuple(args.seat)
        elif args.small:
            chosen = SMALL_SEATS
        elif args.moe:
            chosen = MOE_SEATS
        else:
            chosen = SEATS
        out = probe_seats(chosen, QUESTIONS, args.ref, effort, args.profile)
        target = OUT_ROOT / f"{stamp}-seats.json"
    target.write_text(json.dumps(out, indent=2, default=str) + "\n", encoding="utf-8")
    print(f"\ntranscripts: {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
