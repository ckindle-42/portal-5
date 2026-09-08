#!/usr/bin/env python3
"""Build the compliance_agentic suite from the judgment probe WITHOUT its gold.

The original suite instructed the model to file_read
tests/compliance_probe/judgment_probe_v6.jsonl and then determine the case. Every
record in that file carries gold_label, gold_finding_type, gold_citation AND
rationale inline, and file_read returns 20 000 characters — so the model was
handed the answer key for its own case and for every other case in the file. The
checker then matched the expected label against the whole transcript, which
includes tool-call arguments, so repo_search("CONTRADICTED") alone scored the
task. Neither the task nor the checker measured judgement.

This generator seeds a gold-stripped packet into the sandbox instead, points the
model at the sandbox path, keeps the gold only in the checker, and asserts that
no gold token can reach the model.

  uv run python -m tests.wfe.tools.build_compliance_suite
"""

from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
PROBE = REPO / "tests" / "compliance_probe" / "judgment_probe_v6.jsonl"
OUT = REPO / "tests" / "wfe" / "suites" / "compliance_agentic.jsonl"

GOLD_FIELDS = {"gold_label", "gold_finding_type", "gold_citation", "rationale", "category"}

INSTRUCTION = (
    "You are a compliance council seat. Read the determination packet at "
    "packet.json in your working directory using file_read. Evaluate the "
    "candidate_text against the governing_text, applying the stated premises. "
    "If the packet does not contain what you need to decide, ABSTAIN rather than "
    "guess. Reply with a single JSON object containing the keys determination "
    "(one of SUPPORTED, PARTIAL, CONTRADICTED, ABSENT, ABSTAIN), cited_refs (a "
    "list of governing references) and rationale (two sentences). "
    "End your reply with: DETERMINATION COMPLETE"
)


def strip_gold(rec: dict) -> dict:
    return {k: v for k, v in rec.items() if k not in GOLD_FIELDS}


def build(limit: int | None = None) -> list[dict]:
    tasks = []
    for line in PROBE.read_text().splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        packet = strip_gold(rec)
        gold = rec.get("gold_label")
        if not gold:
            continue
        blob = json.dumps(packet)
        for tok in ("gold_label", "gold_finding_type", "rationale"):
            assert tok not in blob, f"{rec['id']}: gold token {tok} survived stripping"
        tasks.append(
            {
                "id": f"comp-{rec['id'].lower()}",
                "lane": "compliance",
                "agentic": True,
                "instruction": INSTRUCTION,
                "completion_signal": "DETERMINATION COMPLETE",
                "seed": {"packet.json": json.dumps(packet, indent=1)},
                "checkers": [
                    {
                        "type": "answer_contains",
                        "patterns": [rf'"?determination"?\s*[:=]\s*"?{gold}\b', "cited_refs"],
                        # If the answer key ever reaches the model through a tool
                        # result, the run is contaminated and must not be scored
                        # as a model verdict.
                        "forbid_in_tool_output": ["gold_label", "gold_finding_type"],
                    }
                ],
            }
        )
        if limit and len(tasks) >= limit:
            break
    return tasks


def stratify(tasks: list[dict], labels: list[str], k: int) -> list[dict]:
    """Deterministic label-balanced subset: round-robin across gold labels, each
    label's members taken in sorted id order. No RNG, so the campaign suite is
    reproducible and the label mix is stated rather than accidental."""
    buckets: dict[str, list[dict]] = {}
    for t, lab in zip(tasks, labels, strict=True):
        buckets.setdefault(lab, []).append(t)
    for lab in buckets:
        buckets[lab].sort(key=lambda t: t["id"])
    picked, i = [], 0
    order = sorted(buckets)
    while len(picked) < min(k, len(tasks)):
        progressed = False
        for lab in order:
            if i < len(buckets[lab]) and len(picked) < k:
                picked.append(buckets[lab][i])
                progressed = True
        if not progressed:
            break
        i += 1
    return sorted(picked, key=lambda t: t["id"])


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--k", type=int, default=10, help="campaign suite size (label-stratified)")
    args = ap.parse_args()

    tasks, labels = [], []
    for line in PROBE.read_text().splitlines():
        if line.strip():
            rec = json.loads(line)
            if rec.get("gold_label"):
                labels.append(rec["gold_label"])
    tasks = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    full = OUT.with_name("compliance_agentic_full.jsonl")
    full.write_text("\n".join(json.dumps(t) for t in tasks) + "\n")
    subset = stratify(tasks, labels, args.k)
    OUT.write_text("\n".join(json.dumps(t) for t in subset) + "\n")
    mix: dict = {}
    for t, lab in zip(tasks, labels, strict=True):
        if t in subset:
            mix[lab] = mix.get(lab, 0) + 1
    print(f"wrote {len(tasks)} gold-stripped tasks -> {full}")
    print(f"wrote {len(subset)} campaign tasks -> {OUT}  label mix: {mix}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
