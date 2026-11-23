#!/usr/bin/env python3
"""Run and score the six held-out Universal Hunt proof corpora."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import duckdb

sys.path.insert(0, str(Path(__file__).resolve().parent))
from score_cases import _digest  # noqa: E402
from score_leads import _hits  # noqa: E402

from portal.modules.security.core.hunt.notables import __main__ as hunt_cli  # noqa: E402
from portal.modules.security.core.hunt.notables.run import (  # noqa: E402
    DEFAULT_GENERATORS,
    default_search,
)
from portal.modules.security.core.hunt.notables.similar import SIMILAR_GENERATOR  # noqa: E402
from portal.modules.security.core.hunt.notables.verdicts import (
    stage4_verdicts_enabled,  # noqa: E402
)

KEY_PATHS = {
    "hb_flaws_aws": ("flaws_manifest/keys.jsonl", "flaws_aws_key.jsonl"),
    "hb_ait_wardbeck": ("ait_wardbeck_key.json",),
    "hb_ait_wilson": ("ait_wilson_key.json",),
    "hb_uwf_zeek24": ("UWF-ZeekData24_key.json",),
    "hb_lmd_2023": ("LMD-2023_key.json",),
    "hb_ics_pcap": ("ICS-pcap_key.json",),
}
PROOF_INDEXES = tuple(KEY_PATHS)
HUNT_STAGES = ("cards", "behaviours", "notables", "relate")
TOP_K = (10, 25, 50, 100)


@dataclass
class KeyData:
    """Out-of-band truth projected into reusable scorer inputs."""

    unit_kind: str
    scoring_method: str
    units: dict[str, str] = field(default_factory=dict)
    unit_hosts: dict[str, str] = field(default_factory=dict)
    windows: dict[str, dict[str, list[float]]] = field(default_factory=dict)
    digest_units: dict[str, set[str]] = field(default_factory=dict)


def canonical_index(index: str) -> str:
    """Return one of the six proof-corpus names."""
    clean = index.strip().casefold()
    if clean not in KEY_PATHS:
        raise ValueError(f"{index!r} is not one of the six Universal Hunt proof indexes")
    return clean


def resolve_key_path(index: str, keys_dir: Path) -> Path:
    """Resolve an index's existing out-of-band key file."""
    canonical = canonical_index(index)
    candidates = [keys_dir / name for name in KEY_PATHS[canonical]]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    tried = ", ".join(str(path) for path in candidates)
    raise FileNotFoundError(f"no key file for {canonical}; checked: {tried}")


def _flag(value: str | None) -> bool:
    return (value or "").strip().casefold() in {"1", "true", "yes", "on"}


def validate_blind_mode(
    *,
    knowledge_store: Path | None = None,
    enabled: Sequence[str] = DEFAULT_GENERATORS,
    environ: Mapping[str, str] | None = None,
) -> bool:
    """Reject any configuration that can attach known-answer material to the hunt."""
    env = os.environ if environ is None else environ
    if knowledge_store is not None:
        raise ValueError("blind proof refuses a knowledge_store argument")
    if SIMILAR_GENERATOR in enabled:
        raise ValueError("blind proof refuses the similar_to_known generator")
    if (env.get("PORTAL_HUNT_KNOWLEDGE_STORE") or "").strip():
        raise ValueError("blind proof refuses PORTAL_HUNT_KNOWLEDGE_STORE")
    if (env.get("PORTAL_HUNT_KNOWLEDGE_FAMILIES") or "").strip():
        raise ValueError("blind proof refuses PORTAL_HUNT_KNOWLEDGE_FAMILIES")
    stage4 = _flag(env.get("PORTAL_HUNT_STAGE4_VERDICTS"))
    if stage4:
        raise ValueError(
            "blind proof refuses Stage 4 verdicts: relate requires PORTAL_HUNT_KNOWLEDGE_STORE"
        )
    return stage4


def run_hunt(
    index: str,
    out: Path,
    search: Any,
    *,
    start: float = 0.0,
    end: float | None = None,
    knowledge_store: Path | None = None,
    stage_runner: Any = None,
) -> None:
    """Run the supported discovery-first stages without judge or knowledge feedback."""
    canonical = canonical_index(index)
    validate_blind_mode(knowledge_store=knowledge_store, enabled=DEFAULT_GENERATORS)
    end_time = time.time() + 1.0 if end is None else end
    runner = hunt_cli.main if stage_runner is None else stage_runner
    args = [
        "--index",
        canonical,
        "--out",
        str(out),
        "--start",
        str(start),
        "--end",
        str(end_time),
        "--generators",
        ",".join(DEFAULT_GENERATORS),
    ]
    for stage in HUNT_STAGES:
        stage_args = [*args, "--stage", stage]
        if stage == "relate":
            stage_args.append("--allow-proof")
        if runner(stage_args, search=search) != 0:
            raise RuntimeError(f"hunt stage {stage} failed for {canonical}")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def _epoch(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        text = str(value).strip().replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.timestamp()


def _step_window(step: Mapping[str, Any], source: Mapping[str, Any]) -> tuple[float, float] | None:
    window = source.get("time_window") or step.get("time_window") or {}
    if not isinstance(window, Mapping):
        return None
    start = _epoch(window.get("start_epoch"))
    end = _epoch(window.get("end_epoch"))
    if start is None:
        start = _epoch(window.get("start"))
    if end is None:
        end = _epoch(window.get("end"))
    if start is None or end is None:
        return None
    return min(start, end), max(start, end)


def _load_json_key(path: Path) -> KeyData:
    payload = json.loads(path.read_text(encoding="utf-8"))
    result = KeyData(
        unit_kind="attack_windows",
        scoring_method="host/time midpoint via score_leads._hits; source paths are not compared",
    )
    for step_no, step in enumerate(payload.get("attack_steps") or ()):
        if not isinstance(step, Mapping):
            continue
        name = str(step.get("step") or f"step-{step_no + 1}")
        sources = step.get("sources") or ()
        if not sources:
            sources = [{"host": host} for host in step.get("affected_hosts") or ()]
        for source_no, source in enumerate(sources):
            if not isinstance(source, Mapping):
                continue
            host = str(source.get("host") or "")
            source_name = str(source.get("log_path") or source.get("source") or "")
            unit = f"{name}|{host}|{source_name}|{source_no}"
            result.units[unit] = name
            result.unit_hosts[unit] = host
            bounds = _step_window(step, source)
            if host and bounds is not None:
                midpoint = (bounds[0] + bounds[1]) / 2.0
                result.windows.setdefault(unit, {}).setdefault(host.replace("-", "_"), []).append(
                    midpoint
                )
    return result


def _load_flaws_key(path: Path) -> KeyData:
    result = KeyData(
        unit_kind="keyed_events",
        scoring_method="retained-line digest via score_cases._digest; excerpts can miss long rows",
    )
    for row in _read_jsonl(path):
        digest = str(row.get("digest") or "")
        scenario = str(row.get("scenario") or "")
        if not digest or not scenario:
            continue
        unit = f"{digest}|{scenario}"
        result.units[unit] = scenario
        result.unit_hosts[unit] = str(row.get("host") or "")
        result.digest_units.setdefault(digest, set()).add(unit)
    return result


def load_key(index: str, path: Path) -> KeyData:
    """Load FLAWS JSONL or AIT/next-wave JSON truth without exposing it to hunt code."""
    return (
        _load_flaws_key(path) if canonical_index(index) == "hb_flaws_aws" else _load_json_key(path)
    )


def _record_signature(row: Mapping[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(row.get("event_id") or ""),
        str(row.get("host") or ""),
        str(row.get("source") or ""),
        str(row.get("time") or row.get("earliest") or row.get("line") or ""),
    )


def evidence_records(payload: Any) -> list[Mapping[str, Any]]:
    """Collect distinct event references from a notable or case payload."""
    found: list[Mapping[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()
    pending = [payload]
    while pending:
        current = pending.pop()
        if isinstance(current, Mapping):
            if (
                current.get("host")
                and current.get("source")
                and any(
                    current.get(key) is not None
                    for key in ("line", "raw", "_raw", "time", "earliest")
                )
            ):
                signature = _record_signature(current)
                if signature not in seen:
                    seen.add(signature)
                    found.append(current)
            pending.extend(current.values())
        elif isinstance(current, list):
            pending.extend(current)
    return found


def _record_interval(row: Mapping[str, Any]) -> tuple[float, float] | None:
    start = next(
        (
            _epoch(row.get(key))
            for key in ("earliest", "first_seen", "time", "hour", "start")
            if _epoch(row.get(key)) is not None
        ),
        None,
    )
    end = next(
        (
            _epoch(row.get(key))
            for key in ("latest", "last_seen", "time", "hour", "end")
            if _epoch(row.get(key)) is not None
        ),
        start,
    )
    if start is None:
        return None
    last = start if end is None else end
    return min(start, last), max(start, last)


def _row_hits(row: Mapping[str, Any], key: KeyData) -> set[str]:
    events = evidence_records(row)
    hits: set[str] = set()
    if key.unit_kind == "keyed_events":
        for event in events:
            raw = event.get("raw") or event.get("_raw") or event.get("line")
            if raw is None:
                continue
            digest = _digest(str(event.get("host") or ""), str(event.get("source") or ""), str(raw))
            hits.update(key.digest_units.get(digest, set()))
        return hits
    for event in events:
        bounds = _record_interval(event)
        host = str(event.get("host") or "")
        if bounds is None or not host:
            continue
        hits.update(
            _hits(
                {"host": host, "hour": bounds[0], "span": bounds[1] - bounds[0]},
                key.windows,
            )
        )
    return hits


def _ratio(hits: int, total: int) -> float | None:
    return round(hits / total, 6) if total else None


def score_rows(rows: Sequence[Mapping[str, Any]], key: KeyData) -> dict[str, Any]:
    """Score ranked hunt rows with the existing digest and time-window hit primitives."""
    row_hits = [_row_hits(row, key) for row in rows]
    total_units = len(key.units)
    total_steps = len(set(key.units.values()))
    total_entities = len({host for host in key.unit_hosts.values() if host})

    def summary(limit: int) -> dict[str, Any]:
        units = set().union(*row_hits[:limit]) if row_hits[:limit] else set()
        steps = {key.units[unit] for unit in units}
        entities = {key.unit_hosts[unit] for unit in units if key.unit_hosts.get(unit)}
        return {
            "keyed_unit_recall": _ratio(len(units), total_units),
            "attack_step_recall": _ratio(len(steps), total_steps),
            "entity_recall": _ratio(len(entities), total_entities),
        }

    all_units = set().union(*row_hits) if row_hits else set()
    all_steps = {key.units[unit] for unit in all_units}
    all_entities = {key.unit_hosts[unit] for unit in all_units if key.unit_hosts.get(unit)}
    return {
        "rows_scored": len(rows),
        "evidence_events": sum(len(evidence_records(row)) for row in rows),
        "keyed_units": {
            "kind": key.unit_kind,
            "detected": len(all_units),
            "total": total_units,
            "recall": _ratio(len(all_units), total_units),
        },
        "attack_steps": {
            "detected": len(all_steps),
            "total": total_steps,
            "recall": _ratio(len(all_steps), total_steps),
        },
        "entities": {
            "detected": len(all_entities),
            "total": total_entities,
            "recall": _ratio(len(all_entities), total_entities),
        },
        "top_k_recall": {str(k): summary(k) for k in TOP_K},
    }


def _event_count(run_dir: Path) -> int:
    store = run_dir / "behaviours.duckdb"
    if not store.is_file():
        raise FileNotFoundError(f"hunt behaviour store missing: {store}")
    connection = duckdb.connect(str(store), read_only=True)
    try:
        row = connection.execute("SELECT COUNT(*) FROM events").fetchone()
    finally:
        connection.close()
    return int(row[0] if row else 0)


def score_corpus(index: str, key_path: Path, run_dir: Path, elapsed: float) -> dict[str, Any]:
    """Score one completed hunt directory and return its receipt row."""
    key = load_key(index, key_path)
    notables = _read_jsonl(run_dir / "notables.jsonl")
    cases_payload = json.loads((run_dir / "cases.json").read_text(encoding="utf-8"))
    cases = cases_payload.get("cases") or []
    return {
        "index": canonical_index(index),
        "key_file": str(key_path),
        "run_dir": str(run_dir),
        "events": _event_count(run_dir),
        "events_basis": "row count from behaviours.duckdb events table",
        "notables": len(notables),
        "cases": len(cases),
        "scoring_method": key.scoring_method,
        "notables_score": score_rows(notables, key),
        "cases_score": score_rows(cases, key),
        "zero_knowledge": True,
        "zero_labels_in_splunk": True,
        "zero_labels_in_splunk_basis": (
            "key data stays out of hunt inputs; live index label absence requires operator verification"
        ),
        "stage4_verdicts_enabled": stage4_verdicts_enabled(),
        "elapsed_seconds": round(elapsed, 3),
    }


def build_receipt(
    corpora: Sequence[Mapping[str, Any]], *, status: str = "completed"
) -> dict[str, Any]:
    """Build the machine-readable consolidated receipt."""
    return {
        "schema_version": 1,
        "status": status,
        "created_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "zero_knowledge": True,
        "knowledge_store": None,
        "similar_to_known_enabled": False,
        "zero_labels_in_splunk": True,
        "zero_labels_in_splunk_basis": (
            "key data stays out of hunt inputs; live index label absence requires operator verification"
        ),
        "stage4_verdicts_enabled": stage4_verdicts_enabled(),
        "corpora": [dict(row) for row in corpora],
    }


def render_markdown(receipt: Mapping[str, Any]) -> str:
    """Render the short operator-facing proof receipt."""
    lines = [
        "# Universal Hunt zero-knowledge proof receipt",
        "",
        f"- Status: `{receipt.get('status')}`",
        f"- Created: `{receipt.get('created_at_utc')}`",
        f"- Zero knowledge: `{receipt.get('zero_knowledge')}`",
        f"- `knowledge_store`: `{receipt.get('knowledge_store')}`",
        f"- `similar_to_known_enabled`: `{receipt.get('similar_to_known_enabled')}`",
        f"- Stage 4 verdicts enabled: `{receipt.get('stage4_verdicts_enabled')}`",
        f"- Zero labels in Splunk: `{receipt.get('zero_labels_in_splunk')}`",
        f"- Label basis: {receipt.get('zero_labels_in_splunk_basis')}",
        "- Scoring: FLAWS hashes retained excerpts; JSON keys use host/time window midpoints.",
        "",
        "| Corpus | Events read | Notables | Cases | Notable top-10 unit recall | Case top-10 unit recall | Seconds |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in receipt.get("corpora", []):
        notable = row.get("notables_score", {}).get("top_k_recall", {}).get("10", {})
        case = row.get("cases_score", {}).get("top_k_recall", {}).get("10", {})
        lines.append(
            "| {index} | {events} | {notables} | {cases} | {nr} | {cr} | {elapsed} |".format(
                index=row.get("index"),
                events=row.get("events"),
                notables=row.get("notables"),
                cases=row.get("cases"),
                nr=notable.get("keyed_unit_recall"),
                cr=case.get("keyed_unit_recall"),
                elapsed=row.get("elapsed_seconds"),
            )
        )
    lines.extend(
        ("", "Live index label absence and the served hunt path require operator verification.", "")
    )
    return "\n".join(lines)


def write_receipt(out_dir: Path, receipt: Mapping[str, Any]) -> None:
    """Write both consolidated receipt formats."""
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "proof_receipt.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (out_dir / "PROOF_RECEIPT.md").write_text(render_markdown(receipt), encoding="utf-8")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--index", action="append", choices=PROOF_INDEXES)
    selection.add_argument("--all-proof", action="store_true")
    parser.add_argument("--keys-dir", type=Path, default=Path("/Volumes/data01/hunt_keys"))
    parser.add_argument("--out-dir", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    return parser


def _default_out_dir() -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return Path("results/hunt_proofs") / stamp


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    indexes = PROOF_INDEXES if args.all_proof else tuple(args.index or ())
    try:
        validate_blind_mode()
        resolved = {index: resolve_key_path(index, args.keys_dir) for index in indexes}
    except (FileNotFoundError, ValueError) as error:
        print(f"proof preflight: {error}", file=sys.stderr)
        return 2
    out_dir = args.out_dir or _default_out_dir()
    if args.dry_run:
        print(
            json.dumps(
                {
                    "status": "dry_run_ok",
                    "indexes": list(indexes),
                    "keys": {name: str(path) for name, path in resolved.items()},
                    "knowledge_store": None,
                    "similar_to_known_enabled": False,
                    "stage4_verdicts_enabled": False,
                    "out_dir": str(out_dir),
                    "splunk_contacted": False,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    out_dir.mkdir(parents=True, exist_ok=True)
    receipt: dict[str, Any] = build_receipt([], status="running")
    write_receipt(out_dir, receipt)
    search = default_search()
    corpora: list[dict[str, Any]] = []
    for index in indexes:
        run_dir = out_dir / index
        started = time.monotonic()
        try:
            run_hunt(index, run_dir, search)
            row = score_corpus(index, resolved[index], run_dir, time.monotonic() - started)
        except Exception as error:
            receipt["status"] = "failed"
            receipt["error"] = f"{type(error).__name__}: {error}"
            receipt["corpora"] = corpora
            write_receipt(out_dir, receipt)
            print(receipt["error"], file=sys.stderr)
            return 1
        corpora.append(row)
        receipt = build_receipt(corpora, status="running")
        write_receipt(out_dir, receipt)
    receipt = build_receipt(corpora)
    write_receipt(out_dir, receipt)
    print(f"proof receipt: {out_dir / 'PROOF_RECEIPT.md'}")
    print(f"proof receipt: {out_dir / 'proof_receipt.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
