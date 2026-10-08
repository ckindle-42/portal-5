#!/usr/bin/env python3
"""Build SPECIMEN_CORPUS_V3: SPECIMEN_CORPUS_V2 plus the behavior values each specimen's own
captured evidence carries.

V2 kept only event codes and field names (``artifacts.observed_fields``); every value was
dropped, so a signature could not tell ``schtasks /create`` from a Splunk forwarder heartbeat.
V3 re-reads each specimen's frozen evidence file (``evidence/<evidence_ref>``, written at V2 build
time) and adds ``artifacts.behavior_values`` from ``bully.behavior_values``. Specimen ids, lanes,
detector outcomes and every other field are carried over unchanged, so V2 and V3 results are
paired probe for probe. No SIEM query is made.

V2 froze only the first ``--event-limit`` (32) events of each source dataset, which is often
background captured before the technique runs. ``--attack-data-root`` + ``--window N`` takes an
attack_data parent's behavior values from the first N events of its full source dataset instead
(the parent is found by recomputing V2's ``sha256(relative_path:content_hash)`` id); every other
dimension still comes from the frozen V2 view, so the only change is the values.

    uv run python scripts/build_specimen_corpus_v3.py \\
        --v2 /Volumes/data01/portal5_hunt/artifacts/specimen_corpus_sa1_v1/specimen_corpus_v2.json
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import itertools
import json
import sys
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))

from portal.modules.security.core.bully.behavior_values import (  # noqa: E402
    MAX_TERMS,
    behavior_values,
)

SPECIMEN_CORPUS_V3 = "SPECIMEN_CORPUS_V3"


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def dataset_records(attack_data_root: Path, window: int) -> dict[str, list[Any]]:
    """attack_data parent specimen id -> the first ``window`` records of its source dataset."""
    from scripts import corpus_ingest

    out: dict[str, list[Any]] = {}
    for ds in corpus_ingest.load_manifest_catalog(attack_data_root):
        if not ds.path.is_file() or corpus_ingest.is_lfs_pointer(ds.path):
            continue
        raw = ds.path.read_bytes()
        rel = str(ds.path.relative_to(attack_data_root))
        ident = hashlib.sha256(f"{rel}:{hashlib.sha256(raw).hexdigest()}".encode()).hexdigest()
        records: list[Any] = []
        for line in itertools.islice(corpus_ingest.iter_events_text(ds.path), window):
            event = corpus_ingest.coerce(line)
            if ds.mapped_sourcetype.startswith("windows:"):  # same flattening as V2's _read_parent
                flat = (
                    corpus_ingest.windows_kv(event)
                    if isinstance(event, dict)
                    else corpus_ingest.windows_xml_kv(str(event))
                )
                event = flat if flat is not None else event
            records.append(event)
        out[f"specimen-parent-{ident[:20]}"] = records
    return out


def build(
    v2: dict[str, Any], evidence_dir: Path, full: dict[str, list[Any]] | None = None
) -> dict[str, Any]:
    v3 = copy.deepcopy(v2)
    missing: list[str] = []
    empty = 0
    from_dataset = 0
    for spec in v3["specimens"]:
        path = evidence_dir / str(spec.get("evidence_ref") or "")
        if not path.is_file():
            missing.append(spec["specimen_id"])
            continue
        if full is not None and spec["specimen_id"] in full:
            records = full[spec["specimen_id"]]
            from_dataset += 1
        else:
            payload = json.loads(path.read_text(encoding="utf-8"))
            records = [e for events in (payload.get("telemetry") or {}).values() for e in events]
        terms = behavior_values(records)
        empty += not terms
        artifacts = spec["engine_view"]["telemetry_view"].setdefault("artifacts", {})
        artifacts["behavior_values"] = terms
    v3["schema"] = SPECIMEN_CORPUS_V3
    v3["derived_from"] = {
        "schema": v2.get("schema"),
        "snapshot_hash": v2.get("snapshot_hash"),
        "added": "engine_view.telemetry_view.artifacts.behavior_values",
        "max_terms": MAX_TERMS,
        "specimens_without_evidence": missing,
        "specimens_without_behavior_terms": empty,
        "values_from_full_dataset": from_dataset,
    }
    v3["snapshot_hash"] = hashlib.sha256(_canonical(v3["specimens"]).encode()).hexdigest()
    return v3


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--v2", type=Path, required=True)
    ap.add_argument("--evidence-dir", type=Path, help="default: <v2 dir>/evidence")
    ap.add_argument("--out", type=Path, help="default: <v2 dir>/specimen_corpus_v3.json")
    ap.add_argument("--attack-data-root", type=Path, help="take parent values from full datasets")
    ap.add_argument("--window", type=int, default=2000, help="records read per source dataset")
    a = ap.parse_args()
    v2 = json.loads(a.v2.read_text(encoding="utf-8"))
    out = a.out or a.v2.with_name("specimen_corpus_v3.json")
    full = dataset_records(a.attack_data_root, a.window) if a.attack_data_root else None
    v3 = build(v2, a.evidence_dir or a.v2.parent / "evidence", full)
    out.write_text(json.dumps(v3, sort_keys=True) + "\n", encoding="utf-8")
    d = v3["derived_from"]
    print(
        f"{out}: {len(v3['specimens'])} specimens, "
        f"{len(d['specimens_without_evidence'])} without evidence, "
        f"{d['specimens_without_behavior_terms']} without behavior terms, "
        f"{d['values_from_full_dataset']} valued from the full dataset, "
        f"snapshot {v3['snapshot_hash'][:16]}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
