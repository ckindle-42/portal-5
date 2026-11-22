#!/usr/bin/env python3
"""Canonical-TA-sourcetype hunt-bed ingestion: label-free, per docs/hunt/SPLUNK_REALISM_AND_SETUP.md 5.1.

Prior native ingest assigned per-day filenames as sourcetypes and shipped stats.log noise plus
Filebeat duplicate re-ships, so no vendor TA or CIM model could bind. This mapper gives every
kept file its canonical TA sourcetype (auth.log -> linux_secure, eve.json -> suricata, ...),
drops metrics noise, Filebeat re-ships and every label file (zero labels may enter Splunk),
flattens CloudTrail {"Records": [...]} into one event per record (eventTime as _time,
recipientAccountId/awsRegion as host), and ships to HEC with a receipt + digest manifest.

    census: python3 scripts/hunt_bed/ingest_canonical.py --root <dir|.tar|.zip> --index <idx> --dry-run
    ship:   python3 scripts/hunt_bed/ingest_canonical.py --root <dir|.tar|.zip> --index <idx> \
                --ship --manifest-out <dir> --default-year <y>

Digest rows reuse ingest_native's shape [host, source, line_no, sha256, path] so scorer keys
join identically; `path` is `<file>` (dir mode) or `<archive>::<member>` (tar/zip mode).
"""

from __future__ import annotations

import argparse
import fnmatch
import gzip
import hashlib
import json
import os
import sys
import tarfile
import time
import zipfile
from collections import Counter
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ingest_native import _post, parse_time  # noqa: E402

ST_CLOUDTRAIL = "aws:cloudtrail"
_MAP = (  # (basename glob, canonical TA sourcetype), first match wins; trailing * eats rotation suffixes
    ("auth.log*", "linux_secure"),
    ("audit.log*", "linux_audit"),
    ("messages*", "syslog"),
    ("syslog*", "syslog"),
    ("kern.log*", "syslog"),
    ("user.log*", "syslog"),
    ("user-*.journal.txt", "syslog"),
    ("*access.log*", "access_combined"),
    ("other_vhosts_access.log*", "access_combined"),
    ("horde-access.log*", "access_combined"),
    ("*error.log*", "apache:error"),
    ("eve.json*", "suricata"),
    ("fast.log*", "suricata:fast"),
    ("dnsmasq.log*", "dnsmasq"),
    ("mail.log*", "postfix_syslog"),
    ("mail.info*", "postfix_syslog"),
    ("mainlog*", "postfix_syslog"),
    ("openvpn.log*", "openvpn"),
)
_LABEL = ("*label*", "*ground_truth*", "*answer*", "*attack_meta*")  # zero labels, ever
_NOISE = ("stats.log*", "*.cpu.log*", "*.mem.log*")
_DUP = (
    "*-system.service.log*",
    "*-system.syslog.log*",
    "*-system.auth.log*",
    "system.journal.txt",
)


def _is_label(rel_path: str) -> bool:
    low = rel_path.lower()
    return any(fnmatch.fnmatchcase(low, g) for g in _LABEL)


def should_drop_path(rel_path: str) -> str | None:
    """Exclusion reason for a corpus path: label | metrics_noise | filebeat_dup, else None."""
    if _is_label(rel_path):
        return "label"
    name = rel_path.rsplit("/", 1)[-1]
    if any(fnmatch.fnmatchcase(name, g) for g in _NOISE):
        return "metrics_noise"
    if any(fnmatch.fnmatchcase(name, g) for g in _DUP):
        return "filebeat_dup"
    return None


def sourcetype_for(rel_path: str) -> str | None:
    """Canonical TA sourcetype by file name, or None when the name maps to nothing."""
    name = rel_path.rsplit("/", 1)[-1]
    if "cloudtrail" in name.lower() and name.lower().endswith((".json", ".json.gz")):
        return ST_CLOUDTRAIL
    return next((st for pat, st in _MAP if fnmatch.fnmatchcase(name, pat)), None)


def _walk(root: Path):
    """Yield (rel_path, host, opener) for every non-empty file under a corpus dir / .tar / .zip."""
    if root.is_file() and root.name.endswith((".tar", ".tar.gz", ".tgz", ".zip")):
        yield from _walk_archive(root)
        return
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.stat().st_size == 0:
            continue
        rel = path.relative_to(root).as_posix()
        yield rel, rel.split("/", 1)[0], (lambda p=path: open(p, "rb"))  # noqa: SIM115


def _walk_archive(root: Path):
    if root.name.endswith(".zip"):
        with zipfile.ZipFile(root) as zf:
            for info in zf.infolist():
                if not info.is_dir() and info.file_size:
                    yield (
                        info.filename,
                        _member_host(info.filename),
                        (lambda n=info.filename: zf.open(n)),
                    )
    else:
        with tarfile.open(root, "r:*") as tf:
            for m in tf:
                if m.isfile() and m.size:
                    yield m.name, _member_host(m.name), (lambda mm=m: tf.extractfile(mm))


def _member_host(member: str) -> str:
    return member.split("/", 1)[0]


def _source_of(rel: str) -> str:
    if "/logs/" in rel:
        rel = rel.split("/logs/", 1)[1]
    elif "/" in rel:
        rel = rel.split("/", 1)[1]
    return "/" + rel


def _doc_records(text: str) -> tuple[list[str], bool] | None:
    """(records, had_records) for one whole JSON document; None when the text is not one."""
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        return None
    recs = obj.get("Records") if isinstance(obj, dict) else obj
    had = isinstance(obj, dict) and isinstance(recs, list)
    if not isinstance(recs, list):
        recs = [obj]
    return [r if isinstance(r, str) else json.dumps(r, separators=(",", ":")) for r in recs], had


def _read_records(opener, name: str) -> tuple[list[str], bool]:
    """(records, had_records): compact record per JSON doc/CloudTrail record, else raw lines."""
    try:
        with opener() as fh:
            carrier = gzip.GzipFile(fileobj=fh) if name.endswith(".gz") else fh
            text = carrier.read().decode("utf-8", errors="replace")
    except OSError:  # broken .gz member: ship the raw bytes as lines, never crash a run
        with opener() as fh:
            text = fh.read().decode("utf-8", errors="replace")
    doc = _doc_records(text) if text.lstrip()[:1] in ("[", "{") else None
    if doc is not None:
        return doc
    return text.splitlines(), False


def classify(rel: str, opener) -> str | None:
    """Canonical sourcetype for a kept path; the Records-array check rescues unmapped CloudTrail."""
    st = sourcetype_for(rel)
    if st is not None:
        return st
    _recs, had = _read_records(opener, rel.rsplit("/", 1)[-1])
    return ST_CLOUDTRAIL if had else None


def census(root: Path) -> dict:
    """File-level census of one corpus: kept by sourcetype, dropped by reason, label check."""
    kept: Counter = Counter()
    dropped: Counter = Counter()
    unmapped: list[str] = []
    kept_rels: list[str] = []
    total = 0
    for rel, _host, opener in _walk(root):
        total += 1
        reason = should_drop_path(rel)
        if reason:
            dropped[reason] += 1
            continue
        st = classify(rel, opener)
        if st is None:
            unmapped.append(rel)
            continue
        kept[st] += 1
        kept_rels.append(rel)
    leaked = [rel for rel in kept_rels if _is_label(rel)]
    return {
        "root": str(root),
        "total_files": total,
        "kept": {"total": sum(kept.values()), "by_sourcetype": dict(sorted(kept.items()))},
        "dropped": {"total": sum(dropped.values()), "by_reason": dict(sorted(dropped.items()))},
        "unmapped": {"total": len(unmapped), "files": unmapped[:20]},
        "labels_dropped": dropped.get("label", 0),
        "labels_included": len(leaked),
        "zero_labels": not leaked,
    }


def _event(args, st: str, host: str, source: str, raw: str, last_t: float | None):
    ev_host, parsed = host, None
    if st == ST_CLOUDTRAIL:
        rec = json.loads(raw)
        ev_host = str(rec.get("recipientAccountId") or rec.get("awsRegion") or host)
        parsed = parse_time(str(rec.get("eventTime") or ""), args.default_year or 1970)
    else:
        parsed = parse_time(raw, args.default_year or 1970)
    t = parsed if parsed is not None else last_t
    event = {"host": ev_host, "source": source, "sourcetype": st, "index": args.index, "event": raw}
    if t is not None:
        event["time"] = f"{t:.6f}"
    return event, parsed, t, ev_host


def _manifest_path(args, rel: str) -> str:
    return f"{args.root}::{rel}" if args.archive else str(args.root / rel)


def _flush(args, batch: list[bytes], hec: str, token: str) -> None:
    if batch and not args.dry_run:
        _post(hec, token, b"\n".join(batch))


def _ship_file(args, hec, token, manifest, rel: str, host: str, opener, st: str) -> dict:
    source = _source_of(rel)
    records, _had = _read_records(opener, rel.rsplit("/", 1)[-1])
    stats = {
        "host": host,
        "source": source,
        "sourcetype": st,
        "lines": len(records),
        "sent": 0,
        "blank": 0,
        "time_carried": 0,
        "time_none": 0,
    }
    batch: list[bytes] = []
    bbytes = 0
    last_t: float | None = None
    for lineno, raw in enumerate(records, 1):
        raw = raw.rstrip("\r\n")
        if not raw.strip():
            stats["blank"] += 1
            continue
        event, parsed, eff_t, ev_host = _event(args, st, host, source, raw, last_t)
        if parsed is None:
            stats["time_none" if eff_t is None else "time_carried"] += 1
        last_t = eff_t
        digest = hashlib.sha256(f"{ev_host}|{source}|{raw}".encode()).hexdigest()[:24]
        manifest.write(
            json.dumps([ev_host, source, lineno, digest, _manifest_path(args, rel)]) + "\n"
        )
        batch.append(json.dumps(event).encode())
        bbytes += len(batch[-1])
        stats["sent"] += 1
        if len(batch) >= args.batch or bbytes > 512_000:
            _flush(args, batch, hec, token)
            batch, bbytes = [], 0
    _flush(args, batch, hec, token)
    return stats


def _ship(args) -> int:
    hec = os.environ["LAB_SPLUNK_HEC_URL"].rstrip("/") + "/services/collector/event"
    token = os.environ["LAB_SPLUNK_HEC_TOKEN"]
    args.manifest_out.mkdir(parents=True, exist_ok=True)
    receipt = {
        "index": args.index,
        "root": str(args.root),
        "started": time.time(),
        "census": census(args.root),
        "dropped": 0,
        "unmapped": [],
        "files": [],
    }
    with open(args.manifest_out / "digests.jsonl", "w") as manifest:
        for rel, host, opener in _walk(args.root):
            if should_drop_path(rel):
                receipt["dropped"] += 1
            elif (st := classify(rel, opener)) is not None:
                receipt["files"].append(
                    _ship_file(args, hec, token, manifest, rel, host, opener, st)
                )
                print(json.dumps(receipt["files"][-1]), flush=True)
            else:
                receipt["unmapped"].append(rel)
    receipt["finished"] = time.time()
    receipt["sent_total"] = sum(f["sent"] for f in receipt["files"])
    (args.manifest_out / "receipt.json").write_text(json.dumps(receipt, indent=1))
    print(f"sent {receipt['sent_total']} events from {len(receipt['files'])} files", flush=True)
    return 0


def _parse(argv: list[str] | None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument(
        "--root", required=True, type=Path, help="corpus directory, or a .tar/.zip archive"
    )
    ap.add_argument("--index", required=True)
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--dry-run", action="store_true", help="census: counts, distribution, label check"
    )
    mode.add_argument(
        "--ship", action="store_true", help="stream canonical events to HEC + manifest"
    )
    ap.add_argument(
        "--manifest-out", type=Path, help="receipt + digests.jsonl directory (ship mode)"
    )
    ap.add_argument(
        "--default-year", type=int, help="year for yearless syslog timestamps (ship mode)"
    )
    ap.add_argument("--batch", type=int, default=5000)
    args = ap.parse_args(argv)
    if not args.root.exists():
        ap.error(f"--root does not exist: {args.root}")
    args.archive = args.root.is_file() and args.root.name.endswith(
        (".tar", ".tar.gz", ".tgz", ".zip")
    )
    if args.ship and (not args.manifest_out or not args.default_year):
        ap.error("--ship needs --manifest-out DIR and --default-year YEAR")
    return args


def main(argv: list[str] | None = None) -> int:
    args = _parse(argv)
    if args.dry_run:
        report = census(args.root)
        print(json.dumps(report, indent=1))
        return 0 if report["zero_labels"] else 1
    return _ship(args)


if __name__ == "__main__":
    sys.exit(main())
