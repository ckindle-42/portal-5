"""How much of the judge's 'bad' class is window-coincidence rather than content match?"""

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
for name, (d, k, gather) in RUNS.items():
    rows = sb._read_notables(d)
    keys = sb._read_keys(k)
    p = sb.read_json(d / sb.PROGRESS_FILE)
    steps = sb._steps(keys)
    ns = sb._ranked_notables(rows)
    sb._coverage(steps, ns, keys, gather, sb._year(p, rows))
    bad = [(n, r) for n, r in zip(ns, rows, strict=True) if n.covered and n.p_yes is not None]
    window_only = [(n, r) for n, r in bad if not n.claim.folded]
    print(f"{name}: judged bad {len(bad)}  no-literal-claim (window-only) {len(window_only)}")
    for n, r in window_only[:4]:
        print(
            f"   {n.generator:12s} p {n.p_yes:.3f} what={str(r.get('what'))[:70]!r} why={str(r.get('why'))[:70]!r}"
        )
