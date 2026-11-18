#!/usr/bin/env python3
"""Build the R2 entity-level botsv2 key (scenario -> step -> artefact) plus its live-audit SPL.

Reads an out-of-band cited source JSON (a list of {"dataset", "scenario", "step", "value",
"entity", "role", "citations", "locator"?, "locator_fallback"?, "note"?}) and optionally the
R1 audited key (hunt_bed/bots_keys/bots_key.jsonl), whose live audit counts are carried
forward as provenance. Writes keys.jsonl and keys_audit_queries.spl under --out-dir.

A value audited live in R1 keeps admitted=true with its counts and audit date; every other
value stays admitted=null (pending) until the orchestrator runs keys_audit_queries.spl
against the lab — the intake rule (R2 statement §4) says the family does not count until
each locator finds real events. A value whose NFC and NFD spellings differ is located in
both forms (same eval trailer), because the index stores one spelling and Splunk matches
bytes.
"""

from __future__ import annotations

import argparse
import datetime
import json
import sys
import unicodedata
from pathlib import Path
from typing import Any


def _spl_quote(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _forms(value: str) -> tuple[str, ...]:
    """The value's NFC and NFD spellings when they differ, else the value alone."""
    nfc, nfd = unicodedata.normalize("NFC", value), unicodedata.normalize("NFD", value)
    return (value,) if nfc == nfd else (nfc, nfd)


def _form_locators(row: dict[str, Any], form: str) -> tuple[str, str]:
    """The row's locators retargeted at one normalization form of its value."""
    value = str(row["value"])
    if form == value:
        return str(row["locator"]), str(row.get("locator_fallback") or "")
    return (
        str(row["locator"]).replace(value, form),
        str(row.get("locator_fallback") or "").replace(value, form),
    )


def _default_locators(dataset: str, value: str) -> tuple[str, str]:
    quoted = _spl_quote(value)
    primary = (
        f"| tstats count dc(sourcetype) as sourcetypes dc(host) as hosts "
        f"where index={dataset} TERM({quoted})"
    )
    fallback = (
        f"search index={dataset} {quoted} | head 1000 "
        f"| stats count dc(sourcetype) as sourcetypes dc(host) as hosts"
    )
    return primary, fallback


def _load_prior(path: Path | None) -> tuple[dict[tuple[str, str], dict[str, Any]], str]:
    if path is None:
        return {}, ""
    audited = datetime.date.fromtimestamp(path.stat().st_mtime).isoformat()
    prior: dict[tuple[str, str], dict[str, Any]] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        row = json.loads(raw)
        key = (str(row["dataset"]), str(row["value"]))
        audit = dict(row.get("audit") or {})
        audit.update({"audited": audited, "source": str(path)})
        prior[key] = {"audit": audit, "admitted": bool(row.get("admitted"))}
    return prior, audited


def _key_row(entry: dict[str, Any], prior: dict[tuple[str, str], dict[str, Any]]) -> dict[str, Any]:
    dataset, value = str(entry["dataset"]), str(entry["value"])
    default_primary, default_fallback = _default_locators(dataset, value)
    carried = prior.get((dataset, value))
    row: dict[str, Any] = {
        "dataset": dataset,
        "scenario": entry["scenario"],
        "step": entry["step"],
        "value": value,
        "entity": entry.get("entity") or "",
        "role": entry["role"],
        "citations": list(entry["citations"]),
        "locator": entry.get("locator") or default_primary,
        "locator_fallback": entry.get("locator_fallback") or default_fallback,
        "audit": (carried or {}).get("audit"),
        "admitted": (carried or {}).get("admitted"),
    }
    if entry.get("note"):
        row["note"] = entry["note"]
    return row


def _audit_line(query: str, row: dict[str, Any], probe: str) -> str:
    trailer = " | eval scenario={}, step={}, artefact={}, role={}, probe={}".format(
        *(_spl_quote(str(row[name])) for name in ("scenario", "step", "value", "role")),
        _spl_quote(probe),
    )
    return query + trailer


def _write_spl(path: Path, rows: list[dict[str, Any]]) -> int:
    lines = 0
    with path.open("w", encoding="utf-8") as handle:
        for role in ("artefact", "asset"):
            for row in rows:
                if row["role"] != role:
                    continue
                for form in _forms(str(row["value"])):
                    primary, fallback = _form_locators(row, form)
                    handle.write(_audit_line(primary, row, "primary") + "\n")
                    lines += 1
                    if fallback:
                        handle.write(_audit_line(fallback, row, "fallback") + "\n")
                        lines += 1
    return lines


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--source", required=True, type=Path, help="cited entity values (out of band)")
    ap.add_argument("--prior-audit", type=Path, help="R1 bots_key.jsonl to carry audit provenance")
    ap.add_argument("--out-dir", required=True, type=Path)
    args = ap.parse_args()
    source = json.loads(args.source.read_text(encoding="utf-8"))
    prior, audited = _load_prior(args.prior_audit)
    rows = sorted(
        (_key_row(entry, prior) for entry in source),
        key=lambda row: (
            str(row["scenario"]),
            str(row["step"]),
            0 if row["role"] == "artefact" else 1,
            str(row["value"]),
        ),
    )
    args.out_dir.mkdir(parents=True, exist_ok=True)
    keys_path = args.out_dir / "keys.jsonl"
    with keys_path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    spl_path = args.out_dir / "keys_audit_queries.spl"
    queries = _write_spl(spl_path, rows)
    artefacts = [row for row in rows if row["role"] == "artefact"]
    pending = [row for row in artefacts if row["admitted"] is None]
    carried = [row for row in artefacts if row["admitted"] is not None]
    print(
        f"{keys_path}: {len(rows)} rows  scenarios={len({r['scenario'] for r in rows})}  "
        f"steps={len({(r['scenario'], r['step']) for r in rows})}  "
        f"artefacts={len(artefacts)}  assets={len(rows) - len(artefacts)}"
    )
    print(
        f"artefact audits: carried from R1 ({audited or 'n/a'}) {len(carried)}  "
        f"pending live audit {len(pending)}"
    )
    for row in pending:
        print(f"  pending {row['scenario']}/{row['step']} {row['value'][:60]}")
    print(f"{spl_path}: {queries} locator queries (primary + fallback per entry)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
