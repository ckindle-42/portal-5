"""PROVE_THEN_SCALE_V1 §P1.2 — the proof: hand it the material, ask the question.

Three seats × six case questions, one call each, no tools, no loop, no hop
ceiling, no stop rule. The material is the population of the ref each case
names, rendered shared-body-first by ``reading_material.render`` — the exact
unit the §P4 sweep maps with. Every cell records wall time, prompt tokens,
prompt-eval duration (the cache signal), whether the answer cited both sides,
and the raw answer for the agent to judge by reading.

Live only; writes JSON cells under reports/compliance/prove_then_scale/p1/.

Usage:
    uv run python scripts/prove_then_scale/p1_experiment.py [--seats gemma,nemotron,ling] [--cases all]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from portal.modules.compliance.core import reader, reading_material  # noqa: E402
from portal.modules.compliance.core.reading_transport import ChatResult, chat  # noqa: E402
from portal.modules.compliance.core.repository import Repository  # noqa: E402

ART_DIR = REPO_ROOT / "reports" / "compliance" / "prove_then_scale" / "p1"

#: The six case questions from WINDOW_AND_SEAT_V1 §P6 (config/compliance/cases/
#: cip_007_6.yaml), each with the ref whose population IS its material — the
#: case file's own refs. A question's material is the population of the
#: requirement the question is about, which is the sweep's map unit: the rollup
#: and read_check cases read R2 whole; the Part-level cases read their Part.
CASES = [
    {
        "id": "parent",
        "ref": "CIP-007-6 R2",
        "question": "Where are our gaps in CIP-007-6 R2, and how bad is each one?",
    },
    {
        "id": "choice",
        "ref": "CIP-007-6 R2 Part 2.3",
        "question": "Are we using all the latitude NERC gives us on Part 2.3?",
    },
    {
        "id": "interval",
        "ref": "CIP-007-6 R2 Part 2.2",
        "question": "Is our 30-day evaluation cycle stricter than Part 2.2 requires?",
    },
    {
        "id": "read_check",
        "ref": "CIP-007-6 R2",
        "question": "Did you read our patch management procedure, or just the standard?",
    },
    {
        "id": "either_or",
        "ref": "CIP-007-6 R5 Part 5.7",
        "question": "Does our account-lockout setup satisfy Part 5.7?",
    },
    {
        "id": "no_operator_side",
        "ref": "CIP-007-6 R5 Part 5.2",
        "question": (
            "What does Part 5.2 require, and which of our own documents shows "
            "that we actually do it?"
        ),
    },
]

SEATS = {
    "gemma4": "gemma4:26b-a4b-it-q4_K_M-ctx32k",
    "nemotron": "hf.co/bartowski/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-GGUF:Q4_K_M-ctx32k",
    "ling": "hf.co/inclusionAI/Ling-3.0-tiny-GGUF:Q4_K_M-ctx32k",
}

#: The baked window all three seat tags carry. Nothing here is tuned per seat:
#: the experiment is one message over one material, on the window the product
#: has today. The answer budget is the reader's own default — the worst-case
#: material (the parent R2 population plus the shared fixed body) is ~26k
#: tokens at the conservative 3.0 chars/token estimate, and a larger budget
#: would push it at the window.
NUM_CTX = 32768
ANSWER_BUDGET = 3072

_ID_RE = re.compile(r"\b[ci]section-[0-9a-f]{20}(?:#\d+)?\b")


def cited_sections(repo: Repository, answer: str) -> dict[str, list[str]]:
    """Section ids in the answer, split by SIDE — resolved against the store,
    because the id prefix is not the side: an operator note is an internal
    section and can carry a ``csection-`` id (the 30-day note on R2 Part 2.2
    does exactly that). Jurisdiction is the truth; the prefix is spelling."""
    from portal.modules.compliance.core.section_index import parent_section_id, resolve_sections

    found = list(dict.fromkeys(_ID_RE.findall(answer.translate(reader._DASHES))))
    resolved = resolve_sections(repo, [parent_section_id(s) for s in found])
    regulatory: list[str] = []
    operator: list[str] = []
    for section_id in found:
        entry = resolved.get(parent_section_id(section_id))
        if entry is None:
            continue
        if str(entry.get("jurisdiction")) == "internal":
            operator.append(section_id)
        else:
            regulatory.append(section_id)
    return {
        "regulatory": regulatory,
        "operator": operator,
        "unknown": sorted(set(found) - set(resolved)),
    }


def run_cell(repo: Repository, seat_key: str, case: dict[str, str], fixed: dict) -> dict:
    """One seat, one question, one call. The receipt is the record."""
    material = reading_material.render(repo, case["ref"], question=case["question"], fixed=fixed)
    if "error" in material:
        return {"case": case["id"], "seat": seat_key, "error": material["error"]}
    message = material["text"]
    started = time.time()
    try:
        result: ChatResult = chat(
            SEATS[seat_key],
            messages=[{"role": "user", "content": message}],
            tools=None,
            fmt=None,
            think=False,
            num_ctx=NUM_CTX,
            answer_budget=ANSWER_BUDGET,
            timeout=1800,
        )
    except Exception as exc:  # noqa: BLE001 — a failed cell is a recorded cell
        return {
            "case": case["id"],
            "ref": case["ref"],
            "seat": seat_key,
            "model": SEATS[seat_key],
            "error": f"{type(exc).__name__}: {exc}",
            "wall_s": round(time.time() - started, 2),
        }
    answer = (result.content or "").strip()
    cited = cited_sections(repo, answer)
    return {
        "case": case["id"],
        "ref": case["ref"],
        "seat": seat_key,
        "model": SEATS[seat_key],
        "wall_s": round(time.time() - started, 2),
        "prompt_tokens": result.get("prompt_eval_count"),
        "prompt_eval_duration_s": result.get("prompt_eval_duration_s"),
        "eval_count": result.get("eval_count"),
        "chars_per_token": (
            round(len(message) / result.get("prompt_eval_count"), 2)
            if result.get("prompt_eval_count")
            else None
        ),
        "material_chars": material["chars"],
        "cited_regulatory": cited["regulatory"],
        "cited_operator": cited["operator"],
        "cited_both_sides": bool(cited["regulatory"] and cited["operator"]),
        "thinking_chars": len(result.thinking or ""),
        "stop_reason": result.get("stop_reason", ""),
        "answer": answer,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seats", default="gemma4,nemotron,ling")
    parser.add_argument("--cases", default="all")
    args = parser.parse_args()
    ART_DIR.mkdir(parents=True, exist_ok=True)
    seats = [s.strip() for s in args.seats.split(",") if s.strip()]
    cases = CASES if args.cases == "all" else [c for c in CASES if c["id"] in args.cases.split(",")]

    repo = Repository()
    try:
        fixed = reading_material.fixed_body(repo, "CIP-007-6")
        if "error" in fixed:
            print(f"FIXED BODY ERROR: {fixed['error']}")
            return 1
        print(f"fixed body: {fixed['chars']} chars, sha {fixed['sha']}")
        for seat in seats:
            for case in cases:
                cell_path = ART_DIR / f"cell_{seat}_{case['id']}.json"
                if cell_path.exists():
                    cell = json.loads(cell_path.read_text())
                    if not cell.get("error"):
                        print(f"skip existing {cell_path.name}")
                        continue
                cell = run_cell(repo, seat, case, fixed)
                cell_path.write_text(json.dumps(cell, indent=2, default=str))
                cited = (
                    "both"
                    if cell.get("cited_both_sides")
                    else (
                        f"reg={len(cell.get('cited_regulatory', []))} op={len(cell.get('cited_operator', []))}"
                    )
                )
                print(
                    f"{seat:<9} {case['id']:<16} wall={cell.get('wall_s', 0):>7} s "
                    f"prompt={cell.get('prompt_tokens', '?'):>6} cited={cited} "
                    f"answer={len(cell.get('answer', ''))} chars"
                )
    finally:
        repo.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
