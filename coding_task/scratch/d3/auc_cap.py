"""Quantify the pooled-AUC ceiling: similar_to_known rows are 'good' at p_yes ~ 1.0."""

from __future__ import annotations

from collections import Counter
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


def analyse(name, directory, keys_path, logs):
    rows = sb._read_notables(directory)
    keys = sb._read_keys(keys_path)
    progress = sb.read_json(directory / sb.PROGRESS_FILE)
    steps = sb._steps(keys)
    notables = sb._ranked_notables(rows)
    sb._coverage(steps, notables, keys, logs, sb._year(progress, rows))
    judged = [(n, r) for n, r in zip(notables, rows, strict=True) if n.p_yes is not None]
    bad = [n for n, _ in judged if n.covered]
    good = [n for n, _ in judged if not n.covered]
    sim_good = [n for n in good if n.generator == "similar_to_known"]
    sim_high = [n for n in sim_good if n.p_yes >= 0.99]
    cap = (
        (len(good) - len(sim_high)) / len(good) if good else None
    )  # all bad below every saturated good
    print(
        f"{name}: judged {len(judged)} bad {len(bad)} good {len(good)} "
        f"similar-good {len(sim_good)} (p>=0.99 {len(sim_high)}) "
        f"AUC {round(sb._auc([n.p_yes for n in bad], [n.p_yes for n in good]), 3)} "
        f"pooled-cap-if-saturated {round(cap, 3) if cap else None}"
    )
    # non-similar strata only
    bad2 = [n.p_yes for n in bad if n.generator != "similar_to_known"]
    good2 = [n.p_yes for n in good if n.generator != "similar_to_known"]
    print(f"   non-similar-only AUC {round(sb._auc(bad2, good2), 3) if bad2 and good2 else None}")
    gen_bad = Counter(n.generator for n in bad)
    gen_good = Counter(n.generator for n in good)
    print(f"   bad by generator {dict(gen_bad)}")
    print(f"   good by generator {dict(gen_good)}")
    # similarity distribution of the similar generator's nearest known-bad
    sims = []
    kinds = Counter()
    for r in rows:
        if r.get("generator") != "similar_to_known":
            continue
        nearest = r.get("nearest_known") or []
        for item in nearest:
            kinds[str(item.get("label_kind"))] += 1
        bads = [float(i["similarity"]) for i in nearest if i.get("label_kind") == "known_bad"]
        if bads:
            sims.append(max(bads))
    if sims:
        sims.sort()
        print(
            f"   nearest known-bad cosine: min {round(sims[0], 4)} "
            f"median {round(sims[len(sims) // 2], 4)} max {round(sims[-1], 4)} "
            f"exactly-1.0 {sum(1 for s in sims if s >= 0.9999)}/{len(sims)}"
        )
        print(f"   nearest_known label_kind tally {dict(kinds)}")


for name, (directory, keys_path, logs) in RUNS.items():
    analyse(name, directory, keys_path, logs)
