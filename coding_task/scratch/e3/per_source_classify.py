"""Classify each stored-run wide source's own span against the recorded summary window.

Read-only over the R2 run directories. The stored `accel_window` is the only model window a
run records (the Authentication model's), so this is a lower bound on per-source rung 1.
"""

import json
from pathlib import Path

from portal.modules.security.core.hunt.notables.sample import coverage_label

RUNS = {
    "santos": Path("/Volumes/data01/portal5_hunt/hunt_proof_r2_santos/v2/santos"),
    "kyoushi": Path("/Volumes/data01/portal5_hunt/hunt_proof_r2_kyoushi/v2/kyoushi"),
    "russell": Path("/Volumes/data01/portal5_hunt/hunt_proof_r2_russell/v2/russell"),
}

for name, directory in RUNS.items():
    sources = json.loads((directory / "sources.json").read_text())
    progress = json.loads((directory / "progress.json").read_text())
    behaviours = progress["stages"]["behaviours"]
    per_window = behaviours.get("per_window") or 0
    block = behaviours["localisation"]
    entries = block["indexes"]
    facts = [card for card in sources["cards"] if card.get("facts")]
    wide = [card for card in facts if (card["facts"].get("events") or 0) > per_window]
    scheduled = {card["source_id"] for card in wide}
    recorded = entries[0].get("accel_window")
    union = (
        min(c["facts"]["first"] for c in wide),
        max(c["facts"]["last"] for c in wide) + 0.000001,
    )
    union_labels = {coverage_label(recorded, union[0], union[1])}
    per_source = [
        (
            c["source_id"],
            coverage_label(recorded, c["facts"]["first"], c["facts"]["last"] + 1e-6),
        )
        for c in wide
    ]
    counts: dict[str, int] = {}
    for _source, label in per_source:
        counts[label] = counts.get(label, 0) + 1
    print(
        f"{name}: per_window {per_window}  wide cards {len(wide)}/{len(facts)}  distinct sources {len(scheduled)}"
    )
    print(f"  stored receipt entries {len(entries)}  block keys {sorted(block)}")
    print(f"  stored accel_window {recorded}")
    print(f"  union span [{union[0]:.0f} .. {union[1]:.0f}] -> {sorted(union_labels)}")
    print(f"  per-source on that one window: {counts}")
    for source, label in per_source:
        if label != "accelerated":
            print(f"    outside: {source} -> {label}")
