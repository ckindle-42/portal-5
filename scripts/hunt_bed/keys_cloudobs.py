#!/usr/bin/env python3
"""Out-of-band answer key for cloud_obs (DSN'26) runs ingested by ingest_native.py.

Scorer plane only. Each attack script ran with its payload (`-y-`) and without (`-n-`), same
index, back to back. The publisher's own evidence measure is the difference: a record in a `y`
run whose (eventSource, eventName) never appears in its paired `n` run is attack-attributable.
Writes keys.jsonl {"digest", "file", "attack", "run", "action"}; `n` runs and the unpaired
benign captures are not keyed (they are background, not certified benign).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

_RUN = re.compile(r"^(?P<cloud>[a-z]+)-(?P<attack>.+?)-(?P<run>\d+|clean)-(?P<yn>[yn])-logs\.json$")


def _action(raw: str) -> tuple[str, str]:
    rec = json.loads(raw)
    return str(rec.get("eventSource", "")), str(rec.get("eventName", ""))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--ingest", required=True, type=Path)
    args = ap.parse_args()
    # manifest rows: host, source, record_no, digest, file
    by_file: dict[str, list[tuple[int, str]]] = defaultdict(list)
    with open(args.ingest / "digests.jsonl") as fh:
        for raw in fh:
            _h, _s, n, digest, path = json.loads(raw)
            by_file[path].append((n, digest))
    runs: dict[tuple[str, str, str], dict[str, str]] = defaultdict(dict)
    for path in by_file:
        m = _RUN.match(Path(path).name)
        if m:
            stream = Path(path).parent.name
            runs[(stream, m["attack"], m["run"])][m["yn"]] = path

    def records(path: str) -> list[tuple[str, tuple[str, str]]]:
        from ingest_native import _records  # same reader the ingest used

        out = []
        digests = dict(by_file[path])
        for n, rb in _records(Path(path)):
            out.append((digests[n], _action(rb.decode("utf-8", errors="replace"))))
        return out

    keyed = paired = 0
    by_attack: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for (stream, attack, _run), pair in sorted(runs.items()):
        if "y" in pair and "n" in pair:
            by_attack[(stream, attack)].append(pair)
    with open(args.ingest / "keys.jsonl", "w") as out:
        for (stream, attack), pairs in sorted(by_attack.items()):
            paired += len(pairs)
            y_runs = [records(p["y"]) for p in pairs]
            n_actions = [{a for _, a in records(p["n"])} for p in pairs]
            y_actions = [{a for _, a in r} for r in y_runs]
            # attack-attributable: in most payload runs, in no control run of this attack
            signature = {
                a
                for a in set().union(*y_actions)
                if sum(a in ya for ya in y_actions) * 2 >= len(y_actions)
                and not any(a in na for na in n_actions)
            }
            for pair, recs in zip(pairs, y_runs, strict=True):
                for digest, act in recs:
                    if act in signature:
                        keyed += 1
                        out.write(
                            json.dumps(
                                {
                                    "digest": digest,
                                    "file": pair["y"],
                                    "stream": stream,
                                    "attack": attack,
                                    "action": "/".join(act),
                                }
                            )
                            + "\n"
                        )
    print(f"paired runs {paired}; attack-attributable records {keyed}")
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).parent))
    sys.exit(main())
