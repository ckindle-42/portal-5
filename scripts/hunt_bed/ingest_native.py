#!/usr/bin/env python3
"""Ingest a directory of native log files into one Splunk index, byte-faithful, label-free.

Hunt-bed rule: an environment's events arrive as the defender would have collected them --
original bytes, original timestamps, original host -- and nothing that names an answer.
Labels never enter Splunk; the scoreboard joins them out of band by record digest.

    host       = the path segment after --root (the dataset's own machine name)
    source     = the file path below the host's log directory (e.g. /apache2/access.log.4)
    sourcetype = the file's basename with rotation suffixes removed (format name, not a label)
    time       = parsed from the line by common timestamp shapes; a line with none carries
                 the previous line's time (counted in the receipt)

Writes a receipt (per file: lines read, events sent, time parse misses) and a digest manifest
(host, source, line number, sha256 of the line) that the key builders join against.
"""

from __future__ import annotations

import argparse
import calendar
import fnmatch
import hashlib
import json
import os
import re
import ssl
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

_MON = {m: i for i, m in enumerate(calendar.month_abbr) if m}
_ISO = re.compile(
    r"(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2}):(\d{2})(\.\d+)?(Z|[+-]\d{2}:?\d{2})?"
)
_CLF = re.compile(r"\[(\d{2})/(\w{3})/(\d{4}):(\d{2}):(\d{2}):(\d{2}) ([+-]\d{4})\]")
_CTIME = re.compile(r"\w{3} (\w{3}) +(\d{1,2}) (\d{2}):(\d{2}):(\d{2})(\.\d+)? (\d{4})")
_SYSLOG = re.compile(r"^(\w{3}) +(\d{1,2}) (\d{2}):(\d{2}):(\d{2})")
_EPOCH = re.compile(r"(?:audit\(|^)(\d{10})(\.\d+)?")
_NUMDATE = re.compile(r"(\d{1,2})/(\d{1,2})/(\d{4})[-\s]+(?:--\s+)?(\d{2}):(\d{2}):(\d{2})(\.\d+)?")
_DAYMON = re.compile(r"\b(\d{1,2}) (\w{3}) (\d{2}):(\d{2}):(\d{2})(\.\d+)?")
_ROTATION = re.compile(r"(\.\d+)+$")


def _tz(text: str | None) -> int:
    if not text or text == "Z":
        return 0
    sign = -1 if text[0] == "-" else 1
    digits = text[1:].replace(":", "")
    return sign * (int(digits[:2]) * 3600 + int(digits[2:4]) * 60)


def _gm(y: int, mo: int, d: int, h: str, mi: str, s: str) -> int:
    return calendar.timegm((y, mo, d, int(h), int(mi), int(s)))


def _iso(m: re.Match, _y: int) -> float | None:
    y, mo, d, h, mi, s, frac, tz = m.groups()
    return _gm(int(y), int(mo), int(d), h, mi, s) - _tz(tz) + float(frac or 0)


def _clf(m: re.Match, _y: int) -> float | None:
    d, mon, y, h, mi, s, tz = m.groups()
    return float(_gm(int(y), _MON[mon], int(d), h, mi, s) - _tz(tz)) if mon in _MON else None


def _ctime(m: re.Match, _y: int) -> float | None:
    mon, d, h, mi, s, frac, y = m.groups()
    return _gm(int(y), _MON[mon], int(d), h, mi, s) + float(frac or 0) if mon in _MON else None


def _syslog(m: re.Match, year: int) -> float | None:
    mon, d, h, mi, s = m.groups()
    return float(_gm(year, _MON[mon], int(d), h, mi, s)) if mon in _MON else None


def _epoch(m: re.Match, _y: int) -> float | None:
    return float(m.group(1)) + float(m.group(2) or 0)


def _numdate(m: re.Match, _y: int) -> float | None:
    a, b, y, h, mi, s, frac = m.groups()
    mo, d = (int(b), int(a)) if int(a) > 12 else (int(a), int(b))  # d/m only when unambiguous
    if not (1 <= mo <= 12 and 1 <= d <= 31):
        return None
    return _gm(int(y), mo, d, h, mi, s) + float(frac or 0)


def _daymon(m: re.Match, year: int) -> float | None:
    d, mon, h, mi, s, frac = m.groups()
    return _gm(year, _MON[mon], int(d), h, mi, s) + float(frac or 0) if mon in _MON else None


_SHAPES = (
    (_ISO, _iso),
    (_CLF, _clf),
    (_CTIME, _ctime),
    (_SYSLOG, _syslog),
    (_EPOCH, _epoch),
    (_NUMDATE, _numdate),
    (_DAYMON, _daymon),
)


def parse_time(line: str, default_year: int) -> float | None:
    """Earliest timestamp-shaped span in the line -> epoch seconds (naive = UTC)."""
    found = []
    for rx, conv in _SHAPES:
        if (m := rx.search(line)) and (t := conv(m, default_year)) is not None:
            found.append((m.start(), t))
    return min(found)[1] if found else None


def _post(url: str, token: str, body: bytes) -> None:
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    req = urllib.request.Request(
        url, data=body, headers={"Authorization": f"Splunk {token}"}, method="POST"
    )
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, context=ctx, timeout=120) as resp:
                payload = json.loads(resp.read() or b"{}")
                if payload.get("code", 0) != 0:
                    raise RuntimeError(f"HEC error: {payload}")
                return
        except urllib.error.HTTPError as exc:
            body = exc.read()[:300]
            if exc.code == 400 or attempt == 4:
                raise RuntimeError(f"HEC {exc.code}: {body!r}") from exc
            time.sleep(2 * (attempt + 1))
        except Exception:
            if attempt == 4:
                raise
            time.sleep(2 * (attempt + 1))


def iter_files(root: Path, include: list[str], exclude: list[str]) -> list[tuple[str, str, Path]]:
    out = []
    for host_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        for path in sorted(host_dir.rglob("*")):
            if not path.is_file() or path.stat().st_size == 0:
                continue
            rel = path.relative_to(root).as_posix()
            if include and not any(fnmatch.fnmatch(rel, g) for g in include):
                continue
            if any(fnmatch.fnmatch(rel, g) for g in exclude):
                continue
            log_rel = rel.split("/logs/", 1)[1] if "/logs/" in rel else rel.split("/", 1)[1]
            out.append((host_dir.name, "/" + log_rel, path))
    return out


def _unpage(obj):
    """A page of records (an object whose bulk is one list of objects, e.g. a CloudWatch
    `{"events": [...], "nextToken": ...}` response) is its records, not one event."""
    if isinstance(obj, list):
        return [x for item in obj for x in _unpage(item)]
    if isinstance(obj, dict):
        lists = [
            v
            for v in obj.values()
            if isinstance(v, list) and v and all(isinstance(x, dict) for x in v)
        ]
        if len(lists) == 1 and len(json.dumps(lists[0])) > 0.5 * len(json.dumps(obj)):
            return lists[0]
    return [obj]


def _records(path: Path):
    """One raw record per event, by the file's own structure: a JSON array / concatenated JSON
    documents yield one compact record per object (CloudTrail delivers records this way);
    anything else yields lines."""
    with open(path, "rb") as fh:
        head = fh.read(64).lstrip()
    if head[:1] in (b"[", b"{"):
        text = path.read_text(encoding="utf-8", errors="replace")
        dec, i, n, objs = json.JSONDecoder(), 0, len(text), []
        while i < n:
            while i < n and text[i] in " \t\r\n,[]":
                i += 1
            if i >= n:
                break
            try:
                obj, i = dec.raw_decode(text, i)
            except json.JSONDecodeError:
                objs = None
                break
            objs.extend(_unpage(obj))
        if objs is not None:
            for k, obj in enumerate(objs, 1):
                yield k, json.dumps(obj, separators=(",", ":")).encode()
            return
    with open(path, "rb") as fh:
        yield from enumerate(fh, 1)


def _ingest_file(host, source, path, args, hec, token, manifest) -> dict:
    sourcetype = _ROTATION.sub("", source.rstrip("/").rsplit("/", 1)[-1])
    last_t: float | None = None
    stats = {
        "host": host,
        "source": source,
        "sourcetype": sourcetype,
        "lines": 0,
        "sent": 0,
        "blank": 0,
        "time_carried": 0,
        "time_none": 0,
    }
    batch: list[bytes] = []
    batch_bytes = 0
    if True:
        for lineno, raw_bytes in _records(path):
            stats["lines"] += 1
            raw = raw_bytes.decode("utf-8", errors="replace").rstrip("\r\n")
            if not raw.strip():
                stats["blank"] += 1
                continue
            t = parse_time(raw, args.default_year)
            if t is None:
                stats["time_none" if last_t is None else "time_carried"] += 1
                t = last_t
            last_t = t
            digest = hashlib.sha256(f"{host}|{source}|{raw}".encode()).hexdigest()[:24]
            manifest.write(json.dumps([host, source, lineno, digest, str(path)]) + "\n")
            event = {
                "host": host,
                "source": source,
                "sourcetype": sourcetype,
                "index": args.index,
                "event": raw,
            }
            if t is not None:
                event["time"] = f"{t:.6f}"
            batch.append(json.dumps(event).encode())
            batch_bytes += len(batch[-1])
            stats["sent"] += 1
            if len(batch) >= args.batch or batch_bytes > 512_000:
                batch_bytes = 0
                if not args.dry_run:
                    _post(hec, token, b"\n".join(batch))
                batch = []
    if batch and not args.dry_run:
        _post(hec, token, b"\n".join(batch))
    return stats


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", required=True, type=Path, help="directory whose children are hosts")
    ap.add_argument("--index", required=True)
    ap.add_argument("--include", action="append", default=[], help="glob relative to root")
    ap.add_argument("--exclude", action="append", default=[], help="glob relative to root")
    ap.add_argument("--default-year", type=int, required=True, help="year for yearless syslog")
    ap.add_argument("--out", required=True, type=Path, help="receipt + digest manifest dir")
    ap.add_argument("--batch", type=int, default=5000)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--host", help="fixed host when the data has no machine (e.g. a cloud trail)")
    ap.add_argument(
        "--source-depth",
        type=int,
        default=0,
        help="keep only the first N path components of source (when file names carry labels)",
    )
    args = ap.parse_args()

    hec = os.environ["LAB_SPLUNK_HEC_URL"].rstrip("/") + "/services/collector/event"
    token = os.environ["LAB_SPLUNK_HEC_TOKEN"]
    args.out.mkdir(parents=True, exist_ok=True)
    files = iter_files(args.root, args.include, args.exclude)
    receipt = {"index": args.index, "root": str(args.root), "started": time.time(), "files": []}
    with open(args.out / "digests.jsonl", "w") as manifest:
        for host, source, path in files:
            if args.host:  # the root's children are streams, not machines
                host, source = args.host, f"/{host}{source}"
            if args.source_depth:
                source = "/" + "/".join(source.strip("/").split("/")[: args.source_depth])
            stats = _ingest_file(host, source, path, args, hec, token, manifest)
            receipt["files"].append(stats)
            print(json.dumps(stats), flush=True)
    receipt["finished"] = time.time()
    receipt["sent_total"] = sum(f["sent"] for f in receipt["files"])
    (args.out / "receipt.json").write_text(json.dumps(receipt, indent=1))
    print(
        f"sent {receipt['sent_total']} events from {len(files)} files "
        f"in {receipt['finished'] - receipt['started']:.0f}s",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
