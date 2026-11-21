"""Re-derive the D5 guard inputs from the stored sources.json (no Splunk)."""

import json
from pathlib import Path

runs = {
    "santos": Path("/Volumes/data01/portal5_hunt/hunt_proof_r2_santos/v2/santos"),
    "kyoushi": Path("/Volumes/data01/portal5_hunt/hunt_proof_r2_kyoushi/v2/kyoushi"),
    "russell": Path("/Volumes/data01/portal5_hunt/hunt_proof_r2_russell/v2/russell"),
}
for name, d in runs.items():
    s = json.loads((d / "sources.json").read_text())
    p = json.loads((d / "progress.json").read_text())
    per_window = p["stages"]["behaviours"].get("per_window")
    cards = s["cards"]
    # behaviour-consuming cards are activity/alert/peer consumers; approximate with kind+consumers
    facts = [c["facts"] for c in cards if c.get("facts")]
    wide = [f for f in facts if (f.get("events") or 0) > per_window]
    firsts = [f["first"] for f in wide if f.get("first")]
    lasts = [f["last"] for f in wide if f.get("last")]
    loc = p["stages"]["behaviours"]["localisation"]["indexes"][0]
    accel = loc.get("accel_window")
    print(f"{name}: per_window {per_window} wide sources {len(wide)}/{len(facts)}")
    print(f"  localise span [{min(firsts):.0f}..{max(lasts) + 0.000001:.0f}]  accel_window {accel}")
    if accel:
        print(
            f"  start short by {accel[0] - min(firsts):.1f}s   end short by {max(lasts) + 0.000001 - accel[1]:.1f}s"
        )
