from pathlib import Path

from portal.modules.security.core.hunt.notables import scoreboard as sb

RUNS = {
    "santos": Path("/Volumes/data01/portal5_hunt/hunt_proof_r2_santos/v2/santos"),
    "kyoushi": Path("/Volumes/data01/portal5_hunt/hunt_proof_r2_kyoushi/v2/kyoushi"),
    "russell": Path("/Volumes/data01/portal5_hunt/hunt_proof_r2_russell/v2/russell"),
}

KEY = {
    "santos": Path("/Volumes/data01/portal5_hunt/corpora/ait_lds_v21/santos_ingest/keys.jsonl"),
    "kyoushi": Path("/Volumes/data01/portal5_hunt/corpora/hunt_bed/kyoushi_s1_ingest/keys.jsonl"),
    "russell": Path(
        "/Volumes/data01/portal5_hunt/corpora/ait_lds_v21/russellmitchell_ingest/keys.jsonl"
    ),
}
LOG = {
    "santos": Path("/Volumes/data01/portal5_hunt/corpora/ait_lds_v21/santos/gather"),
    "kyoushi": Path("/Volumes/data01/portal5_hunt/corpora/hunt_bed/kyoushi_s1/gather"),
    "russell": Path("/Volumes/data01/portal5_hunt/corpora/ait_lds_v21/russellmitchell/gather"),
}
for name, d in RUNS.items():
    rows = sb._read_notables(d)
    keys = sb._read_keys(KEY[name])
    p = sb.read_json(d / sb.PROGRESS_FILE)
    steps = sb._steps(keys)
    ns = sb._ranked_notables(rows)
    sb._coverage(steps, ns, keys, LOG[name], sb._year(p, rows))
    dev = [
        (n, r)
        for n, r in zip(ns, rows, strict=True)
        if n.generator == "deviation" and n.p_yes is not None
    ]
    print("=" * 10, name, "deviation judged", len(dev))
    print(" -- covered, lowest p")
    for n, r in sorted((x for x in dev if x[0].covered), key=lambda x: x[0].p_yes)[:4]:
        print(f"   p {n.p_yes:.3f} | {str(r.get('what'))[:80]} | {str(r.get('why'))[:80]}")
    print(" -- uncovered, highest p")
    for n, r in sorted((x for x in dev if not x[0].covered), key=lambda x: -x[0].p_yes)[:4]:
        print(f"   p {n.p_yes:.3f} | {str(r.get('what'))[:80]} | {str(r.get('why'))[:80]}")
