#!/usr/bin/env python3
"""Out-of-band answer key for a Kyoushi (AIT-LDS v2) scenario ingested by ingest_native.py.

Scorer plane only. Kyoushi ships `labels/<host>/logs/<path>` as JSON lines
`{"line": N, "labels": [...], "rules": {...}}` mirroring `gather/<host>/logs/<path>`.
Joined to the ingest manifest by (host, source, line) -> record digest. Output is
`keys.jsonl`: {"digest", "host", "source", "line", "labels"}; unlabelled records are benign
by the publisher's definition and are not written. The join rate is printed and must be 100%.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--labels", required=True, type=Path, help="scenario labels/ directory")
    ap.add_argument("--ingest", required=True, type=Path, help="ingest_native --out directory")
    args = ap.parse_args()

    wanted: dict[tuple[str, str, int], list[str]] = {}
    for path in sorted(args.labels.rglob("*")):
        if not path.is_file():
            continue
        host, rest = path.relative_to(args.labels).as_posix().split("/", 1)
        source = "/" + rest.split("logs/", 1)[1]
        for raw in path.read_text().splitlines():
            row = json.loads(raw)
            wanted[(host, source, int(row["line"]))] = sorted(row["labels"])

    joined = 0
    with (
        open(args.ingest / "digests.jsonl") as manifest,
        open(args.ingest / "keys.jsonl", "w") as out,
    ):
        for raw in manifest:
            host, source, line, digest = json.loads(raw)
            labels = wanted.get((host, source, line))
            if labels is not None:
                joined += 1
                out.write(
                    json.dumps(
                        {
                            "digest": digest,
                            "host": host,
                            "source": source,
                            "line": line,
                            "labels": labels,
                        }
                    )
                    + "\n"
                )
    print(
        f"labelled lines {len(wanted)}  joined to ingested records {joined}  "
        f"join {joined / max(len(wanted), 1):.4%}"
    )
    return 0 if joined == len(wanted) else 1


if __name__ == "__main__":
    sys.exit(main())
