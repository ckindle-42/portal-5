import json
from pathlib import Path

from portal.modules.security.core.hunt.notables import scoreboard as sb
from portal.modules.security.core.hunt.notables.judge_notables import notable_prompt

DIR = Path("/Volumes/data01/portal5_hunt/hunt_proof_r2_santos/v2/santos")
KEYS = Path("/Volumes/data01/portal5_hunt/corpora/ait_lds_v21/santos_ingest/keys.jsonl")
LOGS = Path("/Volumes/data01/portal5_hunt/corpora/ait_lds_v21/santos/gather")
rows = sb._read_notables(DIR)
keys = sb._read_keys(KEYS)
progress = sb.read_json(DIR / sb.PROGRESS_FILE)
steps = sb._steps(keys)
notables = sb._ranked_notables(rows)
sb._coverage(steps, notables, keys, LOGS, sb._year(progress, rows))


def show(label, pred):
    for n, r in zip(notables, rows, strict=True):
        if pred(n, r):
            print(
                "=" * 20,
                label,
                "rank",
                n.rank,
                "gen",
                n.generator,
                "p",
                n.p_yes,
                "covered",
                n.covered,
            )
            print("MEASURE", json.dumps(r.get("measure")))
            print("WHY", r.get("why"))
            print(notable_prompt(r)[:2400])
            print()
            return
    print("no match", label)


show("similar uncovered", lambda n, r: n.generator == "similar_to_known" and not n.covered)
show(
    "deviation covered",
    lambda n, r: n.generator == "deviation" and n.covered and (n.p_yes or 0) < 0.5,
)
show(
    "deviation uncovered high-p",
    lambda n, r: n.generator == "deviation" and not n.covered and (n.p_yes or 0) >= 0.5,
)
