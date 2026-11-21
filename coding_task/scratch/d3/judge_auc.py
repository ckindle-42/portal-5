"""Offline: why did the judge's p_yes invert on the _v2 families? Stored runs only."""

from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

from portal.modules.security.core.hunt.notables import scoreboard as sb

RUNS = {
    "santos": (
        Path("/Volumes/data01/portal5_hunt/hunt_proof_r2_santos/v2/santos"),
        Path("/Volumes/data01/portal5_hunt/corpora/ait_lds_v21/santos_ingest/keys.jsonl"),
        Path("/Volumes/data01/portal5_hunt/corpora/ait_lds_v21/santos/gather"),
    ),
    "kyoushi": (
        Path("/Volumes/data01/portal5_hunt/hunt_proof_r2_kyoushi/v2/kyoushi"),
        Path("/Volumes/data01/portal5_hunt/corpora/hunt_bed/kyoushi_s1_ingest/keys.jsonl"),
        Path("/Volumes/data01/portal5_hunt/corpora/hunt_bed/kyoushi_s1/gather"),
    ),
    "russell": (
        Path("/Volumes/data01/portal5_hunt/hunt_proof_r2_russell/v2/russell"),
        Path("/Volumes/data01/portal5_hunt/corpora/ait_lds_v21/russellmitchell_ingest/keys.jsonl"),
        Path("/Volumes/data01/portal5_hunt/corpora/ait_lds_v21/russellmitchell/gather"),
    ),
}


def analyse(name: str, directory: Path, keys_path: Path, logs: Path) -> None:
    rows = sb._read_notables(directory)
    keys = sb._read_keys(keys_path)
    progress = sb.read_json(directory / sb.PROGRESS_FILE)
    year = sb._year(progress, rows)
    steps = sb._steps(keys)
    notables = sb._ranked_notables(rows)
    sb._coverage(steps, notables, keys, logs, year)
    judged = [(n, r) for n, r in zip(notables, rows, strict=True) if n.p_yes is not None]
    bad = [n.p_yes for n, _ in judged if n.covered]
    good = [n.p_yes for n, _ in judged if not n.covered]
    print(f"\n=== {name}: total {len(rows)} judged {len(judged)} bad {len(bad)} good {len(good)}")
    print(f"  AUC overall {sb._auc(bad, good)}  yes_bad {sb._rate(bad)}  yes_good {sb._rate(good)}")
    # position of the judged prefix in the merged file
    first_unjudged = next((i for i, r in enumerate(rows) if r.get("p_yes") is None), None)
    print(f"  judged prefix ends at index {first_unjudged} of {len(rows)}")
    per = defaultdict(
        lambda: {"n": 0, "judged": 0, "bad": 0, "good": 0, "py_bad": [], "py_good": []}
    )
    for rank, (notable, row) in enumerate(zip(notables, rows, strict=True)):
        gen = row.get("generator") or ""
        slot = per[gen]
        slot["n"] += 1
        if rank < (first_unjudged if first_unjudged is not None else len(rows)):
            slot["judged"] += 1
        if notable.p_yes is None:
            continue
        if notable.covered:
            slot["bad"] += 1
            slot["py_bad"].append(notable.p_yes)
        else:
            slot["good"] += 1
            slot["py_good"].append(notable.p_yes)
    for gen, slot in sorted(per.items(), key=lambda kv: -kv[1]["n"]):
        auc = sb._auc(slot["py_bad"], slot["py_good"])
        print(
            f"  {gen:18s} n {slot['n']:4d} judged {slot['judged']:4d} "
            f"bad {slot['bad']:3d} good {slot['good']:4d} "
            f"yes_bad {sb._rate(slot['py_bad'])} yes_good {sb._rate(slot['py_good'])} "
            f"auc {None if auc is None else round(auc, 3)}"
        )
    # which covered steps do the bad judged rows belong to?
    labels = defaultdict(list)
    for line in keys:
        for label in line.labels:
            labels[label].append(line)
    return rows, notables, keys


def main() -> None:
    which = sys.argv[1:] or list(RUNS)
    for name in which:
        directory, keys_path, logs = RUNS[name]
        analyse(name, directory, keys_path, logs)


if __name__ == "__main__":
    main()
