#!/usr/bin/env python3
"""READING_TRUTH_V1 P6R - every rep reads the same store.

``compliance-reading`` carries tools that write: ``compliance_note``, the review
queue, ``compliance_correct``. B0's store guard could only RECORD a write;
nothing put the store back, so a note written in one rep could be material for
the next rep and the next arm, which breaks the one-variable rule. This module
snapshots the SQLite store once per campaign and restores it before every rep
and arm, through SQLite's online backup API (safe while other connections hold
the database open), and states a logical digest so a rep can refuse to start
on a drifted store.

SQLite only. Any other store a reading tool reads (a vector index the notes
are written into, for instance) must be restored by its own means - the P6R
task names how that is discovered.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import sqlite3
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _local  # noqa: E402


def _tables(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        "SELECT name, sql FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    ).fetchall()
    return [
        name for name, sql in rows if not str(sql or "").upper().startswith("CREATE VIRTUAL TABLE")
    ]


def digest(db: pathlib.Path) -> dict[str, object]:
    """A logical digest: per-table row counts and one sha over every row of
    every ordinary table, in rowid order (virtual tables are covered by their
    shadow tables). Page layout never enters it, so a restore that reproduces
    the data reproduces the digest."""
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        sha = hashlib.sha256()
        counts: dict[str, int] = {}
        for name in _tables(conn):
            quoted = '"' + name.replace('"', '""') + '"'
            try:
                rows = conn.execute(f"SELECT * FROM {quoted} ORDER BY rowid").fetchall()  # noqa: S608
            except sqlite3.OperationalError:
                rows = sorted(conn.execute(f"SELECT * FROM {quoted}").fetchall(), key=repr)  # noqa: S608
            counts[name] = len(rows)
            sha.update(name.encode() + b"\0")
            for row in rows:
                sha.update(repr(row).encode() + b"\n")
        return {"sha256": sha.hexdigest(), "row_counts": counts}
    finally:
        conn.close()


def _copy(src_path: pathlib.Path, dst_path: pathlib.Path) -> None:
    src = sqlite3.connect(str(src_path))
    dst = sqlite3.connect(str(dst_path), timeout=60)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()


def snapshot(db: pathlib.Path, dest: pathlib.Path) -> dict[str, object]:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        dest.unlink()
    _copy(db, dest)
    return {"snapshot": str(dest), **digest(dest)}


def restore(snapshot_path: pathlib.Path, db: pathlib.Path) -> dict[str, object]:
    """Put the live store back to the snapshot and prove it by digest."""
    expected = digest(snapshot_path)
    _copy(snapshot_path, db)
    got = digest(db)
    return {
        "restored": got["sha256"] == expected["sha256"],
        "expected": expected["sha256"],
        "got": got["sha256"],
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("snapshot")
    s.add_argument("--db", type=pathlib.Path, required=True)
    s.add_argument("--out", type=pathlib.Path, required=True)
    r = sub.add_parser("restore")
    r.add_argument("--snapshot", type=pathlib.Path, required=True)
    r.add_argument("--db", type=pathlib.Path, required=True)
    d = sub.add_parser("digest")
    d.add_argument("--db", type=pathlib.Path, required=True)
    args = ap.parse_args(argv)
    if args.cmd == "snapshot":
        refused = _local.refusal(args.out, "the store snapshot")
        if refused:
            print(refused, file=sys.stderr)
            return 2
        print(json.dumps(snapshot(args.db, args.out), indent=2))
        return 0
    if args.cmd == "restore":
        result = restore(args.snapshot, args.db)
        print(json.dumps(result, indent=2))
        return 0 if result["restored"] else 1
    print(json.dumps(digest(args.db), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
