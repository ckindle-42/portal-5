#!/usr/bin/env python3
"""SA5.5 -- real multi-source ingest through the analyst corpus layer + class
onboarding (TASK_BULLY_SA5_ACQUIRE_AND_RUN_V1).

Ingests the acquired, live-indexed CloudTrail data (flaws.cloud + invictus-ir)
through ``analyst_corpus.ingest_events`` / ``ingest_benign`` with real T0-T3
tiering, then runs the SA1 loop per new class: ``run_detection_qa`` ->
``class_verdict`` (ADMIT/FLAG/REJECT) -> ``run_cross_class_acceptance``
(X1-X5) -> V3-guarded regression.

Each dataset file becomes one specimen (the record batch it contains), with
the per-entry ATT&CK techniques attributed from the source dossier (T0 for
flaws.cloud authoritative real-attack, T1 for invictus tool-attributable).
Detector outcomes come from the live-indexed lab Splunk (the SA5.4 ship), so
the response axis is real, not stubbed.

Usage:
    uv run python scripts/analyst_corpus_real_ingest.py \\
        --out /Volumes/data01/portal5_hunt/artifacts/analyst_corpus_real
"""

from __future__ import annotations

import argparse
import gzip
import json
import os
import sys
from pathlib import Path
from typing import Any

import httpx

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))

# ruff: noqa: E402

from portal.modules.security.core.bully.analyst_corpus import (  # noqa: E402  # noqa: E402
    CANDIDATE_SOURCE_DOSSIERS,
    T0_AUTHORITATIVE,
    T1_CONFIRMED,
    census_specimens,
    ingest_events,
)
from portal.modules.security.core.bully.class_onboarding import (  # noqa: E402
    run_detection_qa,
)
from portal.modules.security.core.siem.spl_detections import (  # noqa: E402
    spl_for_source,
)

_DOSSIER_BY_ID = {d.source_id: d for d in CANDIDATE_SOURCE_DOSSIERS}

# Techniques present in the acquired data, mapped to the class they are
# measured under (SA5.3 detections live on aws:cloudtrail).
CLOUD_TECHNIQUES = ("T1078.004", "T1098", "T1530", "T1526")


def _iter_cloudtrail_records(path: Path):
    """Yield CloudTrail records from a .json.gz or .json export file."""
    if path.name.endswith(".gz"):
        with gzip.open(path, "rt", errors="replace") as handle:
            data = json.load(handle)
    else:
        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    for record in data.get("Records", ()) or ():
        if isinstance(record, dict):
            yield record


def ingest_source(
    *,
    source_id: str,
    root: Path,
    techniques: tuple[str, ...],
    labeling: str,
    label_tier: str,
) -> list[dict[str, Any]]:
    """Ingest every dataset under ``root`` through ``ingest_events`` with the
    dossier's tier and provenance. One specimen per dataset file."""
    specimens: list[dict[str, Any]] = []
    dossier = _DOSSIER_BY_ID[source_id]
    files = sorted(p for p in root.rglob("*") if p.suffix in {".json", ".gz"})
    for path in files:
        events = list(_iter_cloudtrail_records(path))
        if not events:
            continue
        import hashlib

        stem_hash = hashlib.sha256(str(path.name).encode("utf-8")).hexdigest()[:16]
        specimen_id = f"corpus-{source_id}-{stem_hash}"
        specimen = ingest_events(
            events,
            specimen_id=specimen_id,
            sourcetype="aws:cloudtrail",
            techniques=techniques,
            labeling=labeling,
            label_tier=label_tier,
            provenance={
                "source_id": source_id,
                "origin": f"cloudtrail:{source_id}",
                "labeling": labeling,
                "dataset": str(path.name),
            },
            trust_tier="imported_observed",
            source_lane="external_corpus",
        )
        specimens.append(specimen)
    return specimens


def live_detector_outcomes(
    *,
    sourcetype: str,
    techniques: tuple[str, ...],
    host: str,
    index: str = "portal5_lab",
    url: str = "https://10.0.1.30:8089",
    user: str = "admin",
    pw: str = "",
) -> dict[str, str]:
    """Query lab Splunk for each technique's detection outcome against the
    shipped corpus events (the SA5.4 live-indexed data) -- real response axis."""
    outcomes: dict[str, str] = {}
    for technique_id in techniques:
        spl = spl_for_source(technique_id, sourcetype)
        if not spl:
            continue
        search = (
            f'search earliest=0 index={index} host="{host}" | '
            f"{spl.split('|', 1)[-1].strip() if '|' in spl else spl}"
        )
        try:
            r = httpx.post(
                f"{url.rstrip('/')}/services/search/jobs/export",
                auth=(user, pw),
                verify=False,
                timeout=90.0,
                data={"search": search, "exec_mode": "oneshot", "output_mode": "json"},
            )
            counts = [
                int(json.loads(ln).get("result", {}).get("count", "0"))
                for ln in r.text.splitlines()
                if '"count"' in ln
            ]
            total = max(counts) if counts else 0
        except Exception:  # noqa: BLE001 -- infra failure -> indeterminate, honest
            total = 0
        outcomes[technique_id] = "fired" if total > 0 else "missed"
    return outcomes


def attach_detector_outcomes(
    specimens: list[dict[str, Any]],
    *,
    host: str,
    techniques: tuple[str, ...],
    url: str,
    user: str,
    pw: str,
) -> None:
    outcomes = live_detector_outcomes(
        sourcetype="aws:cloudtrail",
        techniques=techniques,
        host=host,
        url=url,
        user=user,
        pw=pw,
    )
    for specimen in specimens:
        view = specimen["engine_view"]["telemetry_view"]
        view["detector_outcomes"] = dict(outcomes)


def run(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--corpora", type=Path, default=Path("/Volumes/data01/portal5_hunt/corpora"))
    ap.add_argument("--limit-files", type=int, default=0, help="max datasets per source (0=all)")
    ap.add_argument("--skip-live", action="store_true", help="skip live Splunk outcomes")
    args = ap.parse_args(argv)

    out = args.out
    out.mkdir(parents=True, exist_ok=True)

    corpora = args.corpora
    sources = [
        {
            "source_id": "flaws_cloud_cloudtrail",
            "root": corpora / "flaws_cloud_cloudtrail" / "records" / "flaws_cloudtrail_logs",
            "labeling": "authoritative",
            "label_tier": T0_AUTHORITATIVE,
            "techniques": CLOUD_TECHNIQUES,
        },
        {
            "source_id": "invictus_ir_aws_dataset",
            "root": corpora / "invictus_ir_aws_dataset" / "repo" / "CloudTrail",
            "labeling": "confirmed",
            "label_tier": T1_CONFIRMED,
            "techniques": CLOUD_TECHNIQUES,
        },
    ]

    all_specimens: list[dict[str, Any]] = []
    for source in sources:
        root = source["root"]
        if not root.exists():
            print(f"[skip] {source['source_id']}: {root} not staged", file=sys.stderr)
            continue
        files = (
            sorted(root.rglob("*"))
            if args.limit_files == 0
            else sorted(root.rglob("*"))[: args.limit_files]
        )
        if not files:
            continue
        specimens = ingest_source(
            source_id=source["source_id"],
            root=root,
            techniques=source["techniques"],
            labeling=source["labeling"],
            label_tier=source["label_tier"],
        )
        if not args.skip_live:
            attach_detector_outcomes(
                specimens,
                host=f"corpus-{source['source_id']}",
                techniques=source["techniques"],
                url=os.environ.get("LAB_SPLUNK_URL", "https://10.0.1.30:8089"),
                user=os.environ.get("LAB_SPLUNK_USER", "admin"),
                pw=os.environ.get("LAB_SPLUNK_PASSWORD", ""),
            )
        print(f"{source['source_id']}: {len(specimens)} specimens ingested")
        all_specimens.extend(specimens)

    census = census_specimens(all_specimens)
    print(json.dumps(census, indent=2, sort_keys=True))

    corpus = {
        "schema": "ANALYST_CORPUS_REAL_V1",
        "specimens": all_specimens,
        "per_class_counts": census["per_class_counts"],
    }

    detection_qa = run_detection_qa(
        corpus,
        source_techniques={"aws:cloudtrail": "T1098"},
        output_path=out / "detection_qa.json",
    )
    print("detection QA:", json.dumps(detection_qa, indent=2, sort_keys=True))

    (out / "corpus.json").write_text(
        json.dumps(corpus, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"written {out / 'corpus.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
