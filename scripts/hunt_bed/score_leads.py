#!/usr/bin/env python3
"""Score a hunt run's leads against any hunt-bed key (scorer plane; the engine never sees it).

Joins keys.jsonl (digest -> label fields) to the ingest manifest (digest -> host, file, record)
and reads each keyed record's own time from the source file with the ingest's own reader and
time parser. Truth is grouped into episodes (`--episode` = a key field such as `attack`, or
`day`). A lead hits an episode when it is on the episode's host and its bucket
[start, start + span) contains one of the episode's keyed records.

Reports recall of episodes in the top N leads and how many of those leads hold no keyed record.
Host spellings differ by source in real Splunk (`intranet_server` / `intranet-server`); '-' and
'_' are treated as one host here, never in the engine.
"""

from __future__ import annotations

import argparse
import bisect
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from ingest_native import _records, parse_time  # noqa: E402


def _h(host: str) -> str:
    return host.replace("-", "_")


def keyed_times(
    keys: Path, manifest: Path, year: int, episode: str, root: Path | None = None
) -> dict[str, dict[str, list[float]]]:
    """episode -> host -> sorted keyed record times."""
    with open(keys) as fh:
        key = {(k := json.loads(raw))["digest"]: k for raw in fh}
    where: dict[str, list[tuple[int, str, str]]] = defaultdict(list)
    with open(manifest) as fh:
        for raw in fh:
            row = json.loads(raw)
            host, _src, n, digest = row[:4]
            if digest in key:
                path = row[4] if len(row) > 4 else f"{root}/{host}/logs{_src}"
                where[path].append((n, digest, host))
    out: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for path, items in where.items():
        wanted = {n: (d, h) for n, d, h in items}
        for n, rb in _records(Path(path)):
            if n in wanted:
                digest, host = wanted[n]
                t = parse_time(rb.decode("utf-8", errors="replace"), year)
                if t is None:
                    continue
                ep = (
                    time.strftime("%Y-%m-%d", time.gmtime(t))
                    if episode == "day"
                    else str(key[digest].get(episode, ""))
                )
                out[ep][_h(host)].append(t)
    for hosts in out.values():
        for ts in hosts.values():
            ts.sort()
    return out


def _hits(lead: dict, truth: dict[str, dict[str, list[float]]]) -> set[str]:
    lo, hi, host = lead["hour"], lead["hour"] + lead.get("span", 3600), _h(lead["host"])
    found = set()
    for ep, hosts in truth.items():
        ts = hosts.get(host, [])
        i = bisect.bisect_left(ts, lo)
        if i < len(ts) and ts[i] < hi:
            found.add(ep)
    return found


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--leads", required=True)
    ap.add_argument("--keys", required=True, type=Path)
    ap.add_argument("--manifest", required=True, type=Path)
    ap.add_argument("--year", type=int, required=True)
    ap.add_argument("--episode", default="day")
    ap.add_argument("--root", type=Path, help="host-dir root, for manifests without file paths")
    args = ap.parse_args()
    truth = keyed_times(args.keys, args.manifest, args.year, args.episode, args.root)
    with open(args.leads) as fh:
        leads = json.load(fh)["leads"]
    hits = [_hits(lead, truth) for lead in leads]
    print(f"episodes {len(truth)}; leads {len(leads)}")
    first: dict[str, int] = {}
    for rank, hs in enumerate(hits, 1):
        for ep in hs:
            first.setdefault(ep, rank)
    for n in (10, 25, 50, 100):
        found = {ep for hs in hits[:n] for ep in hs}
        false = sum(1 for hs in hits[:n] if not hs)
        print(f"top {n:3}: episodes found {len(found)}/{len(truth)}  false leads {false}/{n}")
    ranks = sorted(first.values())
    print("first-hit ranks:", ranks[:30], "| never surfaced:", len(truth) - len(first))
    return 0


if __name__ == "__main__":
    sys.exit(main())
