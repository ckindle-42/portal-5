"""PROVE_THEN_SCALE_V1 §P1.3-bis — the seat-failure attribution controls.

The §P1 verdict ("the failures are the seats, not the harness") rests on three
controls, recorded here because a verdict without its controls is the project's
known failure mode:

1. INSTRUMENT (already recorded in the cells): zero thinking characters on all
   18 cells (the think:false pin held on every seat), no budget-exhaustion stop
   reasons, prompts 22,198–26,282 tokens of the 32,768 window — no truncation
   (an overflowing prompt is HTTP 400 on this runner, not a silent clip), no
   error cells.
2. DELIVERY (in the answers themselves): both disqualified seats quote and cite
   OPERATOR material from deep inside the message — Ling's no_operator_side
   quotes the operator policy's Part 5.2 bullet verbatim; Nemotron's read_check
   names the LSPG procedure's actual sections and its parent cites the
   operator traceability section. Material the model quotes, the model
   received. Delivery is refuted as the cause, per seat, by the cells.
3. SIZE (this probe): the same questions over ONLY the sections each case
   turns on (~2k tokens instead of ~23k). If a disqualified seat succeeds
   small but failed large, its defect is long-material comprehension — a
   different boundary than "cannot read"; if it fails small too, the defect is
   in the reading/judgment itself. Same renderer rules, same instructions,
   same temperature/pin, one call each.

Usage: uv run python scripts/prove_then_scale/p1_seat_failure_controls.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from portal.modules.compliance.core.reading_transport import chat  # noqa: E402
from portal.modules.compliance.core.repository import Repository  # noqa: E402
from portal.modules.compliance.core.section_index import resolve_sections  # noqa: E402

ART_DIR = REPO_ROOT / "reports" / "compliance" / "prove_then_scale" / "p1_controls"

#: The minimal section set each case actually turns on, hand-picked from the
#: case file's derived_from lists — the small-material control.
PROBES = [
    {
        "id": "interval_small",
        "question": "Is our 30-day evaluation cycle stricter than Part 2.2 requires?",
        "sections": [
            "csection-7700dd5499cead0994ec",  # Part 2.2 governing row (35 days)
            "csection-285d8c24551776cb380d",  # GTB 2.2
            "isection-21a30e0d44708f5dfdce",  # operator 3.3.1 (35 days)
            "csection-440a5cdf9a6b65292ef3",  # operator note (30 days, deliberate)
        ],
    },
    {
        "id": "either_or_small",
        "question": "Does our account-lockout setup satisfy Part 5.7?",
        "sections": [
            "csection-98ce4ada99c0ad8c57dd",  # Part 5.7 governing (either/or)
            "csection-f0bda2e1711f7a09b0b8",  # GTB 5.7 (threshold tuning)
            "csection-f5df3655893798a35602",  # Rationale 5.7 (either branch; DoS caution)
            "isection-a9fc0586269cfac4a5c3",  # operator 3.5.3.1 (limit AND/OR alerts)
            "isection-fbc9ce9e2439c4f4af90",  # operator policy 3.4.5.1 (either/or)
        ],
    },
    {
        "id": "read_check_small",
        "question": "Did you read our patch management procedure, or just the standard?",
        "sections": [
            "csection-7700dd5499cead0994ec",  # Part 2.2 governing row
            "isection-21a30e0d44708f5dfdce",  # operator 3.3.1
            "isection-c75f69c881d6a214ff52",  # operator 3.5.1
            "csection-440a5cdf9a6b65292ef3",  # operator note
        ],
    },
]

SEATS = {
    "gemma4": "gemma4:26b-a4b-it-q4_K_M-ctx32k",
    "nemotron": "hf.co/bartowski/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-GGUF:Q4_K_M-ctx32k",
    "ling": "hf.co/inclusionAI/Ling-3.0-tiny-GGUF:Q4_K_M-ctx32k",
}

INSTRUCTIONS = (
    "Answer only from this material; cite section ids in square brackets for "
    "every claim, and quote the text verbatim where the exact words matter. If "
    "the material does not contain the answer, say so plainly."
)


def render_small(repo: Repository, probe: dict) -> str:
    texts = resolve_sections(repo, probe["sections"])
    lines = [f"# Material for one question ({len(probe['sections'])} sections)", ""]
    for section_id in probe["sections"]:
        entry = texts.get(section_id)
        if entry is None:
            lines.append(f"[{section_id}] (did not resolve)")
            continue
        label = (
            "operator"
            if entry.get("jurisdiction") in ("internal", "operator_note")
            else "regulatory"
        )
        lines.append(f"[{section_id}] {label} — {entry.get('headings', '')}")
        lines.append(str(entry.get("text", "")).strip())
        lines.append("")
    lines.append("## The question")
    lines.append("")
    lines.append(probe["question"])
    lines.append("")
    lines.append(INSTRUCTIONS)
    return "\n".join(lines)


def main() -> int:
    ART_DIR.mkdir(parents=True, exist_ok=True)
    repo = Repository()
    try:
        for seat, model in SEATS.items():
            for probe in PROBES:
                path = ART_DIR / f"control_{seat}_{probe['id']}.json"
                if path.exists():
                    print(f"skip existing {path.name}")
                    continue
                message = render_small(repo, probe)
                started = time.time()
                result = chat(
                    model,
                    messages=[{"role": "user", "content": message}],
                    tools=None,
                    fmt=None,
                    think=False,
                    num_ctx=32768,
                    answer_budget=3072,
                    timeout=1800,
                )
                cell = {
                    "control": probe["id"],
                    "seat": seat,
                    "model": model,
                    "question": probe["question"],
                    "material_chars": len(message),
                    "prompt_tokens": result.get("prompt_eval_count"),
                    "wall_s": round(time.time() - started, 2),
                    "thinking_chars": len(result.thinking or ""),
                    "stop_reason": result.get("stop_reason", ""),
                    "answer": (result.content or "").strip(),
                }
                path.write_text(json.dumps(cell, indent=2))
                print(
                    f"{seat:<9} {probe['id']:<16} wall={cell['wall_s']:>6} s "
                    f"prompt={cell['prompt_tokens']:>6} answer={len(cell['answer'])} chars"
                )
    finally:
        repo.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
