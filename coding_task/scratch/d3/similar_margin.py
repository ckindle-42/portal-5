"""similar_to_known: does p_yes track the measured margin, or just the 'known_bad' words?"""

import json
from pathlib import Path

for name, d in {
    "santos": Path("/Volumes/data01/portal5_hunt/hunt_proof_r2_santos/v2/santos"),
    "kyoushi": Path("/Volumes/data01/portal5_hunt/hunt_proof_r2_kyoushi/v2/kyoushi"),
    "russell": Path("/Volumes/data01/portal5_hunt/hunt_proof_r2_russell/v2/russell"),
}.items():
    rows = [
        json.loads(line) for line in (d / "notables.jsonl").read_text().splitlines() if line.strip()
    ]
    sim = [r for r in rows if r.get("generator") == "similar_to_known"]
    bins = {"<=0": [], "0..0.05": [], "0.05..0.1": [], ">0.1": []}
    for r in sim:
        v = float((r.get("measure") or {}).get("value") or 0.0)
        p = r.get("p_yes")
        if p is None:
            continue
        key = "<=0" if v <= 0 else "0..0.05" if v < 0.05 else "0.05..0.1" if v < 0.1 else ">0.1"
        bins[key].append(float(p))
    print(name, "similar rows", len(sim), "judged", sum(len(v) for v in bins.values()))
    for k, v in bins.items():
        if v:
            print(
                f"   margin {k:9s} n {len(v):3d} mean p {sum(v) / len(v):.4f} min {min(v):.4f} frac>=0.5 {sum(1 for x in v if x >= 0.5) / len(v):.3f}"
            )
    # negative-margin rows exist?
    neg = [r for r in sim if float((r.get("measure") or {}).get("value") or 0.0) <= 0]
    print(
        "   negative/zero margins:", len(neg), "example why:", (neg[0].get("why") if neg else None)
    )
