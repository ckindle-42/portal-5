#!/usr/bin/env python3
"""MODULE_COMPLETE_V1 §P3 — the correction loop, demonstrated end to end.

One transcript: read → disagree → correct → re-read → the correction is IN the
material and the re-read ACCOUNTS for it. Plus the module's only proactive
surface, ``compliance_standing_questions(run=True)``, exercised for the first
time.

The loop's bridge (this task's code change): a correction filed through
``compliance_correct`` used to be addressed under the ANSWER's id, while
populations pull notes by REQUIREMENT identity — the two keys never met, so
correcting an answer never changed what the next reading of that requirement
saw. The bridge files the note against the answer's own ``subject_ref``
(requirement side) and keeps ``conversation_answers.correction_of`` (answer
side).

    uv run python scripts/compliance/correction_loop_demo.py \\
        --out-dir reports/compliance/module_complete/p3
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

import httpx  # noqa: E402

#: the demo's subject: a requirement with a real, checkable operator decision.
#: The question invites the reading to state the 35-calendar-day cycle the
#: standard's Measures describe; the operator's correction records their own
#: decision about it — the operator's word, then outranking the reading.
REF = "CIP-007-6 R2 Part 2.2"
QUESTION = (
    "How often must we evaluate security patches and updates for BES Cyber "
    "Systems per CIP-007-6 R2 Part 2.2, and what do our own documents commit to?"
)
CORRECTION = (
    "That answer states our practice as if it were the standard's cycle. The "
    "operator's decision, recorded here: LSPG evaluates applicable security "
    "patches every 30 calendar days — deliberately stricter than the 35 the "
    "Part allows — because the monthly change window is when evaluations are "
    "scheduled. The 35-day figure is the regulatory ceiling only, and answers "
    "about our practice should cite OUR cycle, not the ceiling."
)

#: what "the re-read accounts for it" means, mechanically: the second answer
#: must ENGAGE the correction — quote from the note's text, or state the 30-day
#: figure the note records — not merely coexist with it.
ACCOUNTING_MARKERS = ("30 calendar days", "30-day", "30 day")


def _mcp(base: str, tool: str, args: dict, timeout: float = 900.0) -> dict:
    response = httpx.post(
        f"{base}/tools/{tool}",
        json={"arguments": args},
        timeout=httpx.Timeout(timeout, connect=10.0),
    )
    response.raise_for_status()
    return response.json()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out-dir", required=True, type=pathlib.Path)
    ap.add_argument("--mcp", default="http://127.0.0.1:8937")
    ap.add_argument(
        "--skip-correct",
        action="store_true",
        help="replay only the re-read and standing questions (the correction already recorded)",
    )
    args = ap.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    transcript: dict[str, object] = {
        "run_id": _dt.datetime.now(_dt.UTC).isoformat(),
        "ref": REF,
        "mcp": args.mcp,
        "steps": [],
    }

    def step(name: str, payload: dict) -> None:
        transcript["steps"].append({"step": name, **payload})  # type: ignore[union-attr]
        (args.out_dir / "correction_loop_transcript.json").write_text(
            json.dumps(transcript, indent=2, default=str)
        )
        print(f"[{name}] done")

    # 1. the material BEFORE any correction — proves the note is absent
    material_before = _mcp(args.mcp, "compliance_context", {"ref": REF, "mode": "material"})
    before_notes = (
        [
            n
            for n in (material_before.get("payload", {}).get("sections") or {}).values()
            if n.get("side") == "operator_note"
        ]
        if "payload" in material_before
        else []
    )
    step(
        "material_before",
        {
            "mode": material_before.get("mode"),
            "chars": len(str(material_before.get("text") or material_before.get("note") or "")),
            "window": material_before.get("window"),
            "note_sections_before": 1 if CORRECTION[:40] in str(material_before) else 0,
            "_": before_notes,
        },
    )

    if not args.skip_correct:
        # 2. READ — the deployed tool, stored
        asked = _mcp(
            args.mcp,
            "compliance_ask",
            {"question": QUESTION, "ref": REF, "store": True},
            timeout=1200.0,
        )
        answer_id = str(asked.get("answer_id") or "")
        step(
            "read",
            {
                "question": QUESTION,
                "answer_id": answer_id,
                "answer_head": str(asked.get("answer") or "")[:600],
                "cited": asked.get("citations") or asked.get("verification"),
            },
        )
        if not answer_id:
            (args.out_dir / "correction_loop_transcript.json").write_text(
                json.dumps(transcript, indent=2, default=str)
            )
            print("FAIL: the read produced no stored answer_id")
            return 1

        # 3. DISAGREE → CORRECT — the operator files a correction against the answer
        corrected = _mcp(
            args.mcp,
            "compliance_correct",
            {
                "answer_id": answer_id,
                "correction": CORRECTION,
                "author": "chris (operator, for this demonstration)",
            },
        )
        step("correct", {"correction_receipt": corrected})
        if corrected.get("error"):
            print("FAIL: correction errored:", corrected["error"])
            return 1
    else:
        # replay: find the most recent already-corrected answer on this ref
        asked = {"answer": "(skipped)"}
        step("read", {"skipped": True})
        corrected = {"note_id": "(skipped)"}
        step("correct", {"skipped": True})

    # 4. RE-READ — the correction must now be IN the material
    material_after = _mcp(args.mcp, "compliance_context", {"ref": REF, "mode": "material"})
    text_after = str(material_after.get("text") or "")
    correction_in_material = CORRECTION[:80] in text_after
    step(
        "reread_material",
        {
            "mode": material_after.get("mode"),
            "chars": len(text_after),
            "correction_in_material": correction_in_material,
            "marker_found": CORRECTION[:60] if correction_in_material else "",
        },
    )

    # 5. RE-ASK — the next reading of the requirement should account for it
    reasked = _mcp(
        args.mcp,
        "compliance_ask",
        {"question": QUESTION, "ref": REF, "store": True},
        timeout=1200.0,
    )
    answer2 = str(reasked.get("answer") or "")
    accounts = any(m in answer2 for m in ACCOUNTING_MARKERS)
    step(
        "reask",
        {
            "answer_id": reasked.get("answer_id"),
            "answer_head": answer2[:600],
            "accounts_for_correction": accounts,
            "markers": ACCOUNTING_MARKERS,
        },
    )

    # 6. the proactive surface, exercised for the first time
    standing = _mcp(
        args.mcp,
        "compliance_standing_questions",
        {
            "question": (
                "Has anything we rely on for patch evaluation "
                "changed since our last internal review?"
            ),
            "subject_ref": REF,
        },
    )
    run = _mcp(
        args.mcp, "compliance_standing_questions", {"run": True, "subject_ref": REF}, timeout=1200.0
    )
    step(
        "standing_questions",
        {
            "recorded": standing,
            "run": {
                "ran": run.get("ran"),
                "answers_head": [
                    str(a.get("answer") or "")[:300] for a in (run.get("answers") or [])[:2]
                ],
                "error": run.get("error"),
            },
        },
    )

    loop_ok = bool(correction_in_material and accounts)
    transcript["verdict"] = "LOOP_CLOSED" if loop_ok else "LOOP_OPEN"
    transcript["verdict_rule"] = (
        "LOOP_CLOSED = the correction is present in the next material (bridge works) AND "
        "the re-read accounts for it (the operator's word visibly outranks the reading). "
        "Present-but-ignored is ladder rung 2: the standing instruction needs to say what "
        "a correction outranks — that would be a code change with its own test, not a "
        "silent pass."
    )
    (args.out_dir / "correction_loop_transcript.json").write_text(
        json.dumps(transcript, indent=2, default=str)
    )
    print(f"WROTE transcript; verdict: {transcript['verdict']}")
    return 0 if loop_ok else 1


if __name__ == "__main__":
    sys.exit(main())
