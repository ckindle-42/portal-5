"""CLI: ``uv run python -m tests.benchmarks.embedding_consumers [--all | --probe ID ...]``."""

from __future__ import annotations

import argparse
import asyncio
import sys

from portal.platform.embedding.client import EmbeddingClient

from . import framework as fw
from . import probes as _probes  # noqa: F401  (registers probes)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--all", action="store_true", help="run every ledger consumer")
    ap.add_argument("--probe", action="append", default=[], help="consumer id (repeatable)")
    ap.add_argument("--list", action="store_true", help="list the ledger and which probes exist")
    ap.add_argument("--live", action="store_true", help="allow probes to call live services")
    ap.add_argument("--opt", action="append", default=[], help="key=value probe option")
    ap.add_argument("--url", default=None, help="EG2 service URL (default EG2_EMBEDDING_URL)")
    a = ap.parse_args(argv)
    reg = fw.registry()
    if a.list:
        for c in fw.CONSUMERS:
            print(
                f"{c.id:24} {'probe' if c.id in reg else 'MISSING':8} {c.area:12} {c.kind:10} {c.title}"
            )
        return 0
    ids = list(fw.CONSUMER_IDS) if a.all else a.probe
    unknown = [i for i in ids if i not in fw.CONSUMER_IDS]
    if unknown or not ids:
        print(f"unknown or no consumers: {unknown or '(none given)'}", file=sys.stderr)
        return 2
    opts = dict(o.split("=", 1) for o in a.opt)
    ctx = fw.ProbeContext(client=EmbeddingClient(a.url), live=a.live, options=opts)
    results = asyncio.run(fw.run(ids, ctx))
    out = fw.write(results)
    print(f"scorecard: {out / 'SCORECARD.md'}")
    if a.all:
        ok = fw.gate_ok(results)
        print(f"phase-3 gate: {'PASS' if ok else 'FAIL'}")
        return 0 if ok else 1
    return 0
