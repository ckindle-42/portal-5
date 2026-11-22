#!/usr/bin/env python3
"""Out-of-band scorer key for hb_flaws_aws (flaws.cloud CloudTrail) — scorer plane only.

Bakes the publicly documented flaws.cloud / flaws2.cloud attacker indicators and joins them
against an ingest_canonical digest manifest by re-reading the corpus (its `path` column), or
emits locator SPL for scoring-time search. It is never imported by portal/ — the engine must
not see answers, only the scorer. Exact values that are NOT public (the compromised
AccessKeyId, attacker source IPs) are not baked: they arrive via --extra in the keys_bots.py
shape {"dataset","scenario","value","role","citations"} and are admitted only when the join
or a live audit actually finds them.

    join: python3 scripts/hunt_bed/keys_flaws.py --manifest <ingest_canonical --manifest-out dir>
    spl:  python3 scripts/hunt_bed/keys_flaws.py --splunk hb_flaws_aws [--extra cited.json]
"""

from __future__ import annotations

import argparse
import json
import sys
import tarfile
import zipfile
from collections import defaultdict
from contextlib import contextmanager
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ingest_canonical import _read_records  # noqa: E402

_ACCOUNT = "811596193553"  # the public flaws.cloud challenge account, present in its records
_CHAIN = ("GetCallerIdentity", "ListBuckets", "CreateAccessKey")

# Public, citable indicator table; op: eq | contains (dotted-field substring) | raw (record text).
_IN = [
    {
        "scenario": "flaws_imds_ip",
        "field": "sourceIPAddress",
        "op": "eq",
        "values": ["169.254.169.254"],
        "role": "artefact",
        "cite": ["flaws.cloud level 5; AWS IMDS endpoint docs"],
    },
    {
        "scenario": "flaws_user_backup",
        "field": "userIdentity.userName",
        "op": "eq",
        "values": ["backup"],
        "role": "artefact",
        "cite": ["flaws.cloud level 3 (backup IAM user)"],
    },
    {
        "scenario": "flaws_bucket",
        "field": "requestParameters.bucketName",
        "op": "contains",
        "values": ["flaws"],
        "role": "artefact",
        "cite": ["flaws.cloud levels 1-6; flaws2.cloud bucket names"],
    },
    {
        "scenario": "flaws_level6_marker",
        "field": "_raw",
        "op": "raw",
        "values": ["level6"],
        "role": "artefact",
        "cite": ["flaws.cloud level 6"],
    },
    {
        "scenario": "flaws_persistence",
        "field": "eventName",
        "op": "eq",
        "values": ["CreateUser", "CreateAccessKey", "CreateLoginProfile"],
        "role": "artefact",
        "cite": ["flaws.cloud levels 3-6: account/key creation pivot"],
    },
    {
        "scenario": "flaws_chain",
        "field": "",
        "op": "chain",
        "values": list(_CHAIN),
        "role": "artefact",
        "cite": ["flaws.cloud: GetCallerIdentity -> ListBuckets -> CreateAccessKey chain"],
    },
]


def _field(rec: dict, dotted: str):
    cur: object = rec
    for part in dotted.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def _match(ind: dict, rec: dict, raw: str) -> bool:
    probe = raw if ind["op"] == "raw" else _field(rec, ind["field"])
    if probe is None:
        return False
    text = str(probe).lower()
    return (
        any(v.lower() in text for v in ind["values"])
        if ind["op"] != "eq"
        else str(probe) in ind["values"]
    )


def _chains(recs: list[str]) -> list[tuple[int, int, int]]:
    """Ordinals of ordered GetCallerIdentity -> ListBuckets -> CreateAccessKey runs, by identity."""
    groups: dict[str, list[tuple[int, str]]] = defaultdict(list)
    for n, raw in enumerate(recs, 1):
        try:
            rec = json.loads(raw)
        except json.JSONDecodeError:
            continue
        ident = str(_field(rec, "userIdentity.arn") or _field(rec, "userIdentity.userName") or "")
        groups[f"{ident}|{rec.get('sourceIPAddress')}"].append((n, str(rec.get("eventName"))))
    out = []
    for events in groups.values():
        found: list[int] = []
        rest = iter(events)
        for want in _CHAIN:
            for n, name in rest:
                if name == want:
                    found.append(n)
                    break
        if len(found) == len(_CHAIN):
            out.append(tuple(found))
    return out


@contextmanager
def _member_stream(path_col: str):
    if "::" in path_col:  # archive::member as written by ingest_canonical
        archive, member = path_col.split("::", 1)
        if archive.endswith(".zip"):
            with zipfile.ZipFile(archive) as zf, zf.open(member) as fh:
                yield fh
        else:
            with tarfile.open(archive, "r:*") as tf:
                fh = tf.extractfile(member)
                if fh is None:
                    raise FileNotFoundError(f"{archive}::{member}")
                with fh:
                    yield fh
    else:
        with open(path_col, "rb") as fh:
            yield fh


def build(manifest_dir: Path, inds: list[dict]) -> int:
    rows: dict[str, list[tuple[int, str, str, str]]] = defaultdict(list)
    with open(manifest_dir / "digests.jsonl") as fh:
        for line in fh:
            host, source, n, digest, path = json.loads(line)
            rows[path].append((n, digest, host, source))
    keyed = 0
    with open(manifest_dir / "keys.jsonl", "w") as out:
        for path, file_rows in sorted(rows.items()):
            name = path.rsplit("::", 1)[-1].rsplit("/", 1)[-1]
            with _member_stream(path) as fh:
                recs, _had = _read_records(lambda fh=fh: fh, name)
            by_n = {n: (digest, host, source) for n, digest, host, source in file_rows}
            for n, digest, host, source in file_rows:
                if n > len(recs):
                    continue
                raw = recs[n - 1].rstrip("\r\n")
                try:
                    rec = json.loads(raw)
                except json.JSONDecodeError:
                    rec = {}
                for ind in inds:
                    if ind["op"] == "chain" or not _match(ind, rec, raw):
                        continue
                    out.write(
                        json.dumps(
                            {
                                "digest": digest,
                                "host": host,
                                "source": source,
                                "line": n,
                                "scenario": ind["scenario"],
                                "role": ind["role"],
                                "cite": ind["cite"],
                            }
                        )
                        + "\n"
                    )
                    keyed += 1
            for chain in _chains(recs):
                if not all(n in by_n for n in chain):
                    continue
                digest, host, source = by_n[chain[-1]]  # the CreateAccessKey record is the pivot
                out.write(
                    json.dumps(
                        {
                            "digest": digest,
                            "host": host,
                            "source": source,
                            "line": chain[-1],
                            "scenario": "flaws_chain",
                            "role": "artefact",
                            "chain": [by_n[n][0] for n in chain],
                            "cite": _IN[-1]["cite"],
                        }
                    )
                    + "\n"
                )
                keyed += 1
    print(f"keyed {keyed} rows across {len(rows)} files -> {manifest_dir / 'keys.jsonl'}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--manifest", type=Path, help="ingest_canonical --manifest-out dir (join mode)")
    ap.add_argument("--splunk", help="emit locator SPL for this index instead of joining")
    ap.add_argument(
        "--extra", type=Path, help="cited exact values (keys_bots.py shape), found-only"
    )
    args = ap.parse_args(argv)
    inds = [dict(i) for i in _IN]
    if args.extra:
        for row in json.loads(args.extra.read_text()):
            inds.append(
                {
                    "scenario": row["scenario"],
                    "field": "_raw",
                    "op": "raw",
                    "values": [row["value"]],
                    "role": row.get("role", "artefact"),
                    "cite": row.get("citations", []),
                }
            )
    if args.splunk:
        for ind in inds:
            v = ind["values"][0]
            print(f'search index={args.splunk} "{v}"  # {ind["scenario"]} ({ind["role"]})')
        return 0
    if not args.manifest:
        ap.error("one of --manifest / --splunk is required")
    return build(args.manifest, inds)


if __name__ == "__main__":
    sys.exit(main())
