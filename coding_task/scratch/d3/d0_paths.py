"""D0: what the estate map holds, and what evidence_absent would print with the guard relaxed."""

import json
from pathlib import Path

from portal.modules.security.core.hunt.notables import scoreboard as sb

runs = {
    "santos": (
        Path("/Volumes/data01/portal5_hunt/hunt_proof_r2_santos/v2/santos"),
        Path("/Volumes/data01/portal5_hunt/corpora/ait_lds_v21/santos_ingest/keys.jsonl"),
    ),
    "kyoushi": (
        Path("/Volumes/data01/portal5_hunt/hunt_proof_r2_kyoushi/v2/kyoushi"),
        Path("/Volumes/data01/portal5_hunt/corpora/hunt_bed/kyoushi_s1_ingest/keys.jsonl"),
    ),
    "russell": (
        Path("/Volumes/data01/portal5_hunt/hunt_proof_r2_russell/v2/russell"),
        Path("/Volumes/data01/portal5_hunt/corpora/ait_lds_v21/russellmitchell_ingest/keys.jsonl"),
    ),
}
for name, (d, keys_path) in runs.items():
    rows = []
    for raw in (d / "ledger.jsonl").read_text().splitlines():
        if "by sourcetype source host" not in raw:
            continue
        row = json.loads(raw)
        if row.get("stage") != "cards" or row.get("capped"):
            continue
        rows.append(row)
    paths = {c for r in rows for c in (r.get("values_extracted") or []) if str(c).startswith("/")}
    print(
        f"{name}: estate-map rows {len(rows)} ledger 'rows' {[r['rows'] for r in rows]} "
        f"values_extracted {[len(r['values_extracted']) for r in rows]} distinct paths {len(paths)}"
    )
    keys = sb._read_keys(keys_path)
    absent = sb._evidence_absent(keys, frozenset(paths))
    fully = {label: (gone, total) for label, (gone, total) in absent.items() if gone == total}
    print(
        f"   evidence-absent steps: {fully}  absent lines {sum(a for a, _ in absent.values())}/{sum(b for _, b in absent.values())}"
    )
