"""For the lowest-p 'bad' notables, show the labelled line that made them 'bad'."""

from collections import defaultdict
from pathlib import Path

from portal.modules.security.core.hunt.notables import scoreboard as sb

d = Path("/Volumes/data01/portal5_hunt/hunt_proof_r2_santos/v2/santos")
keys = sb._read_keys(
    Path("/Volumes/data01/portal5_hunt/corpora/ait_lds_v21/santos_ingest/keys.jsonl")
)
logs = Path("/Volumes/data01/portal5_hunt/corpora/ait_lds_v21/santos/gather")
rows = sb._read_notables(d)
p = sb.read_json(d / sb.PROGRESS_FILE)
steps = sb._steps(keys)
ns = sb._ranked_notables(rows)
sb._coverage(steps, ns, keys, logs, sb._year(p, rows))

wanted = defaultdict(dict)
for line in keys:
    wanted[(line.host, line.source)][line.number] = line.labels


def first_matches(notable, limit=2):
    out = []
    for (host, source), lines in wanted.items():
        if not sb._on_source(notable.claim, source):
            continue
        path = logs / host / "logs" / source.lstrip("/")
        if not path.is_file():
            continue
        for number, raw in enumerate(path.open(encoding="utf-8", errors="replace"), 1):
            labels = lines.get(number)
            if labels is None:
                continue
            moment = sb.event_time(raw.rstrip("\r\n"), sb._year(p, rows))
            if sb._covers(notable.claim, raw.rstrip("\r\n").casefold(), moment):
                out.append((number, raw.rstrip()[:150], labels))
                if len(out) >= limit:
                    return out
    return out


cands = [(n, r) for n, r in zip(ns, rows, strict=True) if n.covered and n.p_yes is not None]
for n, r in sorted(cands, key=lambda x: x[0].p_yes)[:5]:
    print("=" * 70)
    print(f"rank {n.rank} gen {n.generator} p_yes {n.p_yes:.3f} what={str(r.get('what'))[:90]}")
    print(
        f"claim terms={n.claim.terms} window={n.claim.window} sources={sorted(n.claim.sources)[:3]}"
    )
    for number, line, labels in first_matches(n):
        print(f"  labelled line {number} {labels}: {line}")
