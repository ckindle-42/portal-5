#!/usr/bin/env python3
"""Canonical-TA-sourcetype hunt-bed ingestion: label-free, per docs/hunt/SPLUNK_REALISM_AND_SETUP.md 5.1.

Prior native ingest assigned per-day filenames as sourcetypes and shipped stats.log noise plus
Filebeat duplicate re-ships, so no vendor TA or CIM model could bind. This mapper gives every
kept file its canonical TA sourcetype (auth.log -> linux_secure, eve.json -> suricata, ...),
drops metrics noise, Filebeat re-ships and every label sidecar (zero labels may enter Splunk),
flattens CloudTrail {"Records": [...]} into one event per record (eventTime as _time,
recipientAccountId/awsRegion as host), maps Zeek and Sysmon/Security exports to their
canonical TA sourcetypes, strips embedded ground-truth columns from every shipped record,
and ships to HEC with a receipt + digest manifest.

    census: python3 scripts/hunt_bed/ingest_canonical.py --root <dir|.tar|.zip> --index <idx> --dry-run
    ship:   python3 scripts/hunt_bed/ingest_canonical.py --root <dir|.tar|.zip> --index <idx> \
                --ship --manifest-out <dir> --default-year <y>

Digest rows reuse ingest_native's shape [host, source, line_no, sha256, path] so scorer keys
join identically; `path` is `<file>` (dir mode) or `<archive>::<member>` (tar/zip mode).
"""

from __future__ import annotations

import argparse
import csv
import fnmatch
import gzip
import hashlib
import io
import json
import os
import re
import sys
import tarfile
import time
import zipfile
from collections import Counter
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ingest_native import _post, parse_time  # noqa: E402

ST_CLOUDTRAIL = "aws:cloudtrail"
ST_SYSMON = "XmlWinEventLog:Microsoft-Windows-Sysmon/Operational"
ST_SECURITY = "WinEventLog:Security"
# Columns named by the next-wave corpora. Exact match, case-insensitive. Telemetry keys stay.
GROUND_TRUTH_FIELDS = frozenset(
    {
        "label",
        "label_tactic",
        "label_technique",
        "mitre_attack",
        "attack_cat",
        "is_attack",
        "benign",
        "attack",
        "ground_truth",
        "technique",
    }
)
# tls shares bro:ssl:json — TA-bro binds Zeek's TLS log on the ssl sourcetype.
_ZEEK_ST = {
    "s7comm": "bro:s7comm:json",
    "bacnet": "bro:bacnet:json",
    "modbus": "bro:modbus:json",
    "notice": "bro:notice:json",
    "weird": "bro:weird:json",
    "conn": "bro:conn:json",
    "dnp3": "bro:dnp3:json",
    "http": "bro:http:json",
    "dns": "bro:dns:json",
    "ssl": "bro:ssl:json",
    "tls": "bro:ssl:json",
}
_WIN_EXT = (".jsonl", ".json", ".xml", ".csv", ".tsv", ".evtx")
_WIN_HEADER = frozenset({"image", "commandline", "sourceimage", "parentimage", "targetfilename"})
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
# *label* matches column-bearing "*labeled*" extracts; those are kept and stripped below.
_LABEL = ("*label*", "*ground_truth*", "*answer*", "*attack_meta*", "*mission_log*")
_NOISE = ("stats.log*", "*.cpu.log*", "*.mem.log*")
_DUP = (
    "*-system.service.log*",
    "*-system.syslog.log*",
    "*-system.auth.log*",
    "system.journal.txt",
)


def _is_label(rel_path: str) -> bool:
    """True for answer sidecars. A *labeled* telemetry extract is kept and stripped instead."""
    low = rel_path.lower()
    if not any(fnmatch.fnmatchcase(low, g) for g in _LABEL):
        return False
    name = low.rsplit("/", 1)[-1]
    under_labels = "/labels/" in f"/{low}" or low.startswith("labels/")
    if under_labels:
        return True
    return not ("labeled" in name or "labelled" in name)


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


def _strip_gz(name: str) -> str:
    low = name.lower()
    return low[:-3] if low.endswith(".gz") else low


def _zeek_sourcetype(name: str) -> str | None:
    stem = _strip_gz(name)
    for kind, st in _ZEEK_ST.items():
        if re.search(rf"(?:^|[._-]){re.escape(kind)}(?:\.|$)", stem):
            return st
    return None


def _windows_sourcetype(name: str) -> str | None:
    low = _strip_gz(name)
    if not any(low.endswith(ext) for ext in _WIN_EXT):
        return None
    if "sysmon" in low:
        return ST_SYSMON
    stem = low
    for ext in _WIN_EXT:
        if stem.endswith(ext):
            stem = stem[: -len(ext)]
            break
    security = stem in {"security", "winsecurity", "wineventlog-security"}
    if security or stem.endswith(("-security", "_security")):
        return ST_SECURITY
    return None


def sourcetype_for(rel_path: str) -> str | None:
    """Canonical TA sourcetype by file name, or None when the name maps to nothing."""
    name = rel_path.rsplit("/", 1)[-1]
    if "cloudtrail" in name.lower() and _strip_gz(name).endswith(".json"):
        return ST_CLOUDTRAIL
    mapped = next((st for pat, st in _MAP if fnmatch.fnmatchcase(name, pat)), None)
    if mapped is not None:
        return mapped
    return _zeek_sourcetype(name) or _windows_sourcetype(name)


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


def _gt_key(name: str) -> bool:
    """Ground truth is the named set plus any label_* or mitre_* column."""
    key = name.strip().casefold()
    return key in GROUND_TRUTH_FIELDS or key.startswith(("label_", "mitre_"))


def strip_ground_truth_json(raw: str) -> tuple[str, int]:
    """Drop ground-truth keys from one JSON object. Non-objects are returned unchanged."""
    text = raw.strip()
    if not text or text[0] not in "{[":
        return raw, 0
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        return raw, 0
    if not isinstance(obj, dict):
        return raw, 0
    kept = {k: v for k, v in obj.items() if not _gt_key(str(k))}
    removed = len(obj) - len(kept)
    if removed == 0:
        return raw, 0
    return json.dumps(kept, separators=(",", ":")), removed


def _table_delim(name: str, records: list[str]) -> str:
    low = _strip_gz(name)
    if low.endswith(".tsv") or any(
        r.startswith("#separator") or r.startswith("#fields") for r in records[:12]
    ):
        return "\t"
    head = next((r for r in records if r.strip()), "")
    return "\t" if "\t" in head else ","


def _split_cols(line: str, delim: str) -> list[str]:
    if delim == "\t":
        return line.split("\t")
    return next(csv.reader([line]))


def _join_cols(cols: list[str], delim: str) -> str:
    if delim == "\t":
        return "\t".join(cols)
    buf = io.StringIO()
    csv.writer(buf, lineterminator="").writerow(cols)
    return buf.getvalue()


def _split_meta(line: str, delim: str) -> tuple[str, list[str]]:
    if line.startswith("#fields") or line.startswith("#types"):
        prefix, _, body = line.partition(delim if delim in line else " ")
        joiner = delim if delim in line else " "
        return prefix + joiner, _split_cols(body, delim) if body else []
    return "", _split_cols(line, delim)


def _header_index(records: list[str]) -> int | None:
    fallback = None
    for i, line in enumerate(records):
        if line.startswith("#fields"):
            return i
        if fallback is None and line.strip() and not line.startswith("#"):
            fallback = i
    return fallback


def _is_delimited_table(name: str, records: list[str]) -> bool:
    low = _strip_gz(name)
    head = next((r for r in records if r.strip()), "")
    if head.lstrip()[:1] in "{[<":
        return False
    if low.endswith((".csv", ".tsv")):
        return True
    if head.startswith("#fields") or head.startswith("#separator"):
        return True
    if not head or head.lstrip()[:1] in "{[<":
        return False
    return any(_gt_key(c) for c in _split_cols(head, _table_delim(name, records)))


def _strip_tabular(records: list[str], name: str) -> tuple[list[str], int]:
    delim = _table_delim(name, records)
    header_at = _header_index(records)
    if header_at is None:
        return records, 0
    _prefix, cols = _split_meta(records[header_at], delim)
    drop = {i for i, col in enumerate(cols) if _gt_key(col)}
    if not drop:
        return records, 0
    out: list[str] = []
    removed = 0
    for i, line in enumerate(records):
        meta = line.startswith("#") and not line.startswith(("#fields", "#types"))
        if not line.strip() or meta:
            out.append(line)
            continue
        prefix, row = _split_meta(line, delim)
        removed += sum(1 for j in drop if j < len(row))
        kept = [c for j, c in enumerate(row) if j not in drop]
        out.append(prefix + _join_cols(kept, delim))
    return out, removed


_HEADER_CELL = re.compile(r"[A-Za-z][A-Za-z0-9_.\- ]{0,40}")
_HEADER_BODY_SAMPLE = 200  # effort budget: data rows checked for a header cell recurring as data


def _real_header(records: list[str], name: str) -> tuple[int, list[str]] | None:
    """(index, columns) when the first data row names columns: name-shaped cells that never recur."""
    header_at = _header_index(records)
    if header_at is None or records[header_at].startswith("#"):
        return None
    delim = _table_delim(name, records)
    cols = [cell.strip() for cell in _split_cols(records[header_at], delim)]
    if len(cols) < 2 or not all(_HEADER_CELL.fullmatch(cell) for cell in cols):
        return None
    seen: set[str] = set()
    for line in records[header_at + 1 : header_at + 1 + _HEADER_BODY_SAMPLE]:
        if line.strip() and not line.startswith("#"):
            seen.update(cell.strip() for cell in _split_cols(line, delim))
    if any(cell in seen for cell in cols):
        return None
    return header_at, cols


def _table_records(records: list[str], name: str) -> tuple[list[str], int]:
    """A real header ships one JSON object per row; a headerless table keeps positional stripping."""
    header = _real_header(records, name)
    if header is None:
        return _strip_tabular(records, name)
    header_at, cols = header
    delim = _table_delim(name, records)
    rows = [
        _split_cols(line, delim)
        for line in records[header_at + 1 :]
        if line.strip() and not line.startswith("#")
    ]
    return _emit_json_rows(cols, rows)


def _xml_events(records: list[str], name: str) -> list[str] | None:
    low = _strip_gz(name)
    text = "\n".join(records)
    if not (low.endswith(".xml") or text.lstrip().startswith("<")):
        return None
    found = re.findall(r"<Event\b.*?</Event>", text, flags=re.I | re.S)
    return found or None


def _strip_xml_text(text: str) -> tuple[str, int]:
    removed = 0
    for name in GROUND_TRUTH_FIELDS:
        elem = rf"<{name}\b[^>]*/>|<{name}\b[^>]*>.*?</{name}>"
        attr = rf"\s{name}\s*=\s*(?:\"[^\"]*\"|'[^']*')"
        text, elem_n = re.subn(elem, "", text, flags=re.I | re.S)
        text, attr_n = re.subn(attr, "", text, flags=re.I)
        removed += elem_n + attr_n
    return text, removed


def _strip_json_records(records: list[str]) -> tuple[list[str], int]:
    out: list[str] = []
    removed = 0
    for raw in records:
        cleaned, n = strip_ground_truth_json(raw)
        out.append(cleaned)
        removed += n
    return out, removed


_ZEEK_RENAME = {
    "src_ip_zeek": "id.orig_h",
    "src_port_zeek": "id.orig_p",
    "dest_ip_zeek": "id.resp_h",
    "dest_port_zeek": "id.resp_p",
}
_ZEEK_UNSET = frozenset({"-", "(empty)"})
_UWF_HOST = "uwf-zeek24"
_UWF_SOURCE = "/zeek/conn.log"


def _is_zeek_tsv(records: list[str]) -> bool:
    return any(line.startswith("#separator") or line.startswith("#fields") for line in records[:12])


def _is_uwf_zeek_csv(name: str, records: list[str]) -> bool:
    """UWF-ZeekData24 spark extracts are part-*.csv with src_ip_zeek / dest_ip_zeek."""
    if _is_zeek_tsv(records) or not _strip_gz(name).endswith(".csv"):
        return False
    header_at = _header_index(records)
    if header_at is None:
        return False
    cols = {col.strip().casefold() for col in _split_cols(records[header_at], ",")}
    return "src_ip_zeek" in cols and "dest_ip_zeek" in cols


def _canonical_name(col: str) -> str:
    text = col.strip()
    return _ZEEK_RENAME.get(text.casefold(), text)


def _canonical_value(name: str, raw: str) -> object:
    if name == "ts":
        try:
            return float(raw)
        except ValueError:
            return raw
    if name in {"id.orig_p", "id.resp_p"}:
        try:
            return int(raw)
        except ValueError:
            return raw
    if raw.casefold() in {"true", "false"}:
        return raw.casefold() == "true"
    return raw


def _json_object(cols: list[str], values: list[str]) -> tuple[dict[str, object], int]:
    obj: dict[str, object] = {}
    removed = 0
    for index, col in enumerate(cols):
        if index >= len(values):
            break
        if _gt_key(col):
            removed += 1
            continue
        raw = values[index]
        if raw in _ZEEK_UNSET or raw == "":
            continue
        name = _canonical_name(col)
        obj[name] = _canonical_value(name, raw)
    return obj, removed


def _emit_json_rows(cols: list[str], rows: list[list[str]]) -> tuple[list[str], int]:
    out: list[str] = []
    removed = 0
    for values in rows:
        obj, count = _json_object(cols, values)
        removed += count
        if obj:
            out.append(json.dumps(obj, separators=(",", ":")))
    return out, removed


def _zeek_tsv_records(records: list[str]) -> tuple[list[str], int]:
    """Zeek #fields TSV → one JSON object per data row. Header and unset cells stay out."""
    header_at = next((i for i, line in enumerate(records) if line.startswith("#fields")), None)
    if header_at is None:
        return records, 0
    _prefix, cols = _split_meta(records[header_at], "\t")
    rows = [
        line.split("\t")
        for line in records[header_at + 1 :]
        if line.strip() and not line.startswith("#")
    ]
    return _emit_json_rows(cols, rows)


def _uwf_zeek_records(records: list[str]) -> tuple[list[str], int]:
    """UWF Zeek CSV → bro conn JSON. Label columns and the tactic directory never ship."""
    header_at = _header_index(records)
    if header_at is None:
        return [], 0
    cols = _split_cols(records[header_at], ",")
    rows = [
        _split_cols(line, ",")
        for line in records[header_at + 1 :]
        if line.strip() and not line.startswith("#")
    ]
    return _emit_json_rows(cols, rows)


def prepare_payloads(records: list[str], name: str) -> tuple[list[str], int]:
    """Return shipped records plus how many ground-truth fields were removed."""
    xml = _xml_events(records, name)
    if xml is not None:
        out: list[str] = []
        removed = 0
        for event in xml:
            cleaned, n = _strip_xml_text(event)
            out.append(cleaned)
            removed += n
        return out, removed
    if _is_zeek_tsv(records):
        return _zeek_tsv_records(records)
    if _is_uwf_zeek_csv(name, records):
        return _uwf_zeek_records(records)
    if _is_delimited_table(name, records):
        return _table_records(records, name)
    return _strip_json_records(records)


def _header_keys(records: list[str], name: str) -> set[str]:
    head = next((r for r in records if r.strip() and not r.startswith("#")), "")
    if not head:
        return set()
    if head.lstrip()[:1] == "{":
        try:
            obj = json.loads(head)
        except json.JSONDecodeError:
            return set()
        return {str(k).casefold() for k in obj} if isinstance(obj, dict) else set()
    return {c.strip().casefold() for c in _split_cols(head, _table_delim(name, records))}


def _sniff_windows(records: list[str], name: str) -> str | None:
    """LMD-2023 CSV/JSON often has no 'sysmon' in the filename; the header names the sensor."""
    keys = _header_keys(records, name)
    if "eventid" in keys and keys & _WIN_HEADER:
        return ST_SYSMON
    return None


def classify(rel: str, opener) -> str | None:
    """Canonical sourcetype for a kept path; content rescues unmapped CloudTrail and Sysmon."""
    st = sourcetype_for(rel)
    if st is not None:
        return st
    name = rel.rsplit("/", 1)[-1]
    records, had = _read_records(opener, name)
    if had:
        return ST_CLOUDTRAIL
    sniffed = _sniff_windows(records, name)
    if sniffed is not None:
        return sniffed
    if _is_uwf_zeek_csv(name, records):
        return "bro:conn:json"
    return None


def _stripped_count(opener, rel: str) -> int:
    name = rel.rsplit("/", 1)[-1]
    records, _had = _read_records(opener, name)
    _payloads, removed = prepare_payloads(records, name)
    return removed


def census(root: Path) -> dict:
    """File-level census of one corpus: kept by sourcetype, dropped by reason, label check."""
    kept: Counter = Counter()
    dropped: Counter = Counter()
    unmapped: list[str] = []
    kept_rels: list[str] = []
    total = 0
    stripped = 0
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
        stripped += _stripped_count(opener, rel)
    leaked = [rel for rel in kept_rels if _is_label(rel)]
    return {
        "root": str(root),
        "total_files": total,
        "kept": {"total": sum(kept.values()), "by_sourcetype": dict(sorted(kept.items()))},
        "dropped": {"total": sum(dropped.values()), "by_reason": dict(sorted(dropped.items()))},
        "unmapped": {"total": len(unmapped), "files": unmapped[:20]},
        "labels_dropped": dropped.get("label", 0),
        "labels_included": len(leaked),
        "label_fields_stripped": stripped,
        "zero_labels": not leaked,
    }


_JSON_TIME = ("ts", "timestamp", "utctime", "timecreated", "systemtime")


def _json_field_time(raw: str, default_year: int) -> float | None:
    """Zeek `ts` and Sysmon time fields sit inside the JSON object, not at column 0."""
    if not raw.lstrip().startswith("{"):
        return None
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(obj, dict):
        return None
    folded = {str(key).casefold(): value for key, value in obj.items()}
    for key in _JSON_TIME:
        value = folded.get(key)
        if value is None or isinstance(value, bool):
            continue
        if isinstance(value, (int, float)):
            return float(value)
        parsed = parse_time(str(value), default_year)
        if parsed is not None:
            return parsed
    return None


def _event(args, st: str, host: str, source: str, raw: str, last_t: float | None):
    ev_host, parsed = host, None
    if st == ST_CLOUDTRAIL:
        rec = json.loads(raw)
        ev_host = str(rec.get("recipientAccountId") or rec.get("awsRegion") or host)
        parsed = parse_time(str(rec.get("eventTime") or ""), args.default_year or 1970)
    else:
        parsed = parse_time(raw, args.default_year or 1970)
        if parsed is None:
            parsed = _json_field_time(raw, args.default_year or 1970)
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
    name = rel.rsplit("/", 1)[-1]
    records, _had = _read_records(opener, name)
    uwf = _is_uwf_zeek_csv(name, records)
    records, stripped = prepare_payloads(records, name)
    source = _UWF_SOURCE if uwf else _source_of(rel)
    if uwf:
        host = _UWF_HOST
    stats = {
        "host": host,
        "source": source,
        "sourcetype": st,
        "lines": len(records),
        "sent": 0,
        "blank": 0,
        "time_carried": 0,
        "time_none": 0,
        "label_fields_stripped": stripped,
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
    receipt["label_fields_stripped"] = sum(f["label_fields_stripped"] for f in receipt["files"])
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
