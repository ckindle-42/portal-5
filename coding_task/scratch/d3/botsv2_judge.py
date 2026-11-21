"""botsv2 run C: which notables cover an artefact, by generator (offline, stored run only)."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from portal.modules.security.core.hunt.notables import scoreboard as sb

RUN = Path(
    "/Users/chris/projects/portal-5-hunt-proof-r2-botsv2/coding_task/scratch/"
    "hunt_proof_r2_botsv2/run_c/botsv2"
)
KEYS = Path("/Volumes/data01/portal5_hunt/corpora/botsv2_keys/keys.jsonl")

rows = sb._read_notables(RUN)
keys = sb._read_entity_keys(KEYS)
artefacts, assets, rejected = sb._entity_split(keys)
owners = sb._entity_ownership(artefacts)
hays = [sb._haystack(row) for row in rows]
notables, firsts, by_generator, steps, scenarios = sb._entity_pass(artefacts, rows, hays, owners)
judged = [(n, r) for n, r in zip(notables, rows, strict=True) if n.p_yes is not None]
bad = [n for n, _ in judged if n.covered]
good = [n for n, _ in judged if not n.covered]
print(
    f"judged {len(judged)} bad {len(bad)} good {len(good)} auc {sb._auc([n.p_yes for n in bad], [n.p_yes for n in good])}"
)
print("bad by generator", dict(Counter(n.generator for n in bad)))
print("bad p_yes", sorted(round(n.p_yes, 3) for n in bad))
for n, r in judged:
    if not n.covered:
        continue
    print(
        "COVERED", n.generator, n.p_yes, "|", str(r.get("what"))[:90], "|", str(r.get("why"))[:100]
    )
