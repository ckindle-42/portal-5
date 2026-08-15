#!/usr/bin/env python3
"""Assemble the P7 closeout evidence bundle without inventing proof.

The command reads durable SUB records and existing P6.7/P6.8 artifacts,
hashes every cited file, drills all six rollback switches, and emits a JSON
manifest plus a concise Markdown report. Missing or no-effect evidence is
reported as such and makes the compounding proof fail closed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))

from portal.modules.security.core.bully import config, cutover  # noqa: E402
from portal.modules.security.core.bully.store import Store  # noqa: E402


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _artifact(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.is_file():
        return None
    item: dict[str, Any] = {
        "path": str(path.resolve()),
        "sha256": _sha256(path),
        "bytes": path.stat().st_size,
    }
    if path.suffix == ".json":
        try:
            item["content"] = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            item["parse_error"] = str(exc)
    return item


def _latest(root: Path, pattern: str) -> Path | None:
    matches = [path for path in root.glob(pattern) if path.is_file()]
    return max(matches, key=lambda path: path.stat().st_mtime) if matches else None


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=_REPO_ROOT, check=True, text=True, capture_output=True
    ).stdout.strip()


def _feed_name(explanation: str) -> str | None:
    marker = "cutover proof for "
    if marker not in explanation:
        return None
    return explanation.split(marker, 1)[1].split(";", 1)[0]


def _store_proof(store_path: Path) -> dict[str, Any]:
    with Store(store_path) as store:
        hunts = store.hunts()
        return {
            "hunts": hunts,
            "recalls": store.recall_receipts(),
            "impacts": store.decision_impacts(),
            "events": {
                hunt["hunt_id"]: [
                    event.to_dict() for event in store.decision_events_for_hunt(hunt["hunt_id"])
                ]
                for hunt in hunts
            },
            "costs": {
                hunt["hunt_id"]: store.cost_ledger_for_hunt(hunt["hunt_id"]) for hunt in hunts
            },
        }


def _feed_proofs(impacts: list[dict[str, Any]], cfg: dict[str, Any]) -> dict[str, Any]:
    by_feed: dict[str, list[dict[str, Any]]] = {feed: [] for feed in cutover.FEEDS}
    for impact in impacts:
        feed = _feed_name(impact["explanation"])
        if feed in by_feed:
            by_feed[feed].append(impact)
    proofs = {}
    for feed, records in by_feed.items():
        changed = any(record["change_kind"] != "NO_EFFECT" for record in records)
        proofs[feed] = {
            "mode": cutover.feed_mode(cfg, feed),
            "status": "PASS" if changed else ("NO_EFFECT" if records else "MISSING"),
            "impact_ids": [record["impact_id"] for record in records],
            "change_kinds": [record["change_kind"] for record in records],
            "rollback": cutover.rollback_drill(
                feed,
                replacement={"consumer": "replacement", "records": "retained"},
                baseline={"consumer": "baseline"},
            ),
        }
    return proofs


def _evidence_status(
    calibration_report: Path | None,
    refinement_verdict: Path | None,
    specimen_corpus: Path | None,
    specimen_e2e: Path | None,
    validation_summary: Path | None,
) -> dict[str, Any]:
    artifacts = {
        "calibration": _artifact(calibration_report),
        "refinement": _artifact(refinement_verdict),
        "corpus": _artifact(specimen_corpus),
        "specimen_proof": _artifact(specimen_e2e),
        "validation": _artifact(validation_summary),
    }
    content = {key: (value or {}).get("content") or {} for key, value in artifacts.items()}
    calibration = content["calibration"]
    corpus = content["corpus"]
    proof = content["specimen_proof"]
    artifacts.update(
        {
            "calibration_recorded": bool(artifacts["calibration"])
            and calibration.get("schema") == "BASELINE_CALIBRATION_V1"
            and calibration.get("cold_untuned") is True
            and calibration.get("training_applied") is False
            and calibration.get("threshold_tuning_applied") is False,
            "refinement_recorded": content["refinement"].get("verdict")
            in {"served", "rejected", "rolled_back", "declined_no_gain", "training_failed"},
            "corpus_recorded": corpus.get("schema") == "SPECIMEN_CORPUS_V1"
            and corpus.get("complete") is True
            and all(
                corpus.get("per_lane_counts", {}).get(lane, 0) > 0
                for lane in ("attack_data", "replay_mutation", "live_lab")
            ),
            "specimen_e2e_recorded": proof.get("schema") == "BULLY_P7_SPECIMEN_E2E_V1"
            and proof.get("passed") is True,
            "validation_passed": content["validation"].get("passed") is True,
        }
    )
    return artifacts


def _release_acceptance(
    *,
    all_feeds_changed: bool,
    evidence: dict[str, Any],
    live_lab_recorded: bool,
) -> dict[str, Any]:
    passed = (
        all_feeds_changed
        and evidence["calibration_recorded"]
        and evidence["corpus_recorded"]
        and evidence["specimen_e2e_recorded"]
        and live_lab_recorded
        and evidence["validation_passed"]
    )
    return {
        "six_feeds_changed": all_feeds_changed,
        "calibration_recorded": evidence["calibration_recorded"],
        "refinement_deferred": True,
        "specimen_corpus_recorded": evidence["corpus_recorded"],
        "specimen_e2e_recorded": evidence["specimen_e2e_recorded"],
        "live_lab_recorded": live_lab_recorded,
        "validation_passed": evidence["validation_passed"],
        "status": "PASS" if passed else "FAIL",
        "note": (
            "This manifest proves only cited records. Refinement/tool-call intake is "
            "deferred to the later training pass and is not a P7.2 acceptance input."
        ),
    }


def assemble(
    *,
    store_path: Path,
    calibration_report: Path | None,
    refinement_verdict: Path | None,
    specimen_corpus: Path | None,
    specimen_e2e: Path | None,
    validation_summary: Path | None,
    validation_logs: list[Path],
) -> dict[str, Any]:
    cfg = config.load_hunt_config()
    store_data = _store_proof(store_path)
    hunts, events = store_data["hunts"], store_data["events"]
    feed_proofs = _feed_proofs(store_data["impacts"], cfg)
    evidence = _evidence_status(
        calibration_report,
        refinement_verdict,
        specimen_corpus,
        specimen_e2e,
        validation_summary,
    )
    all_feeds_changed = all(proof["status"] == "PASS" for proof in feed_proofs.values())
    live_lab_recorded = (
        evidence["corpus_recorded"]
        and evidence["specimen_e2e_recorded"]
        and any(
            event.get("data", {}).get("used_synthetic") is False
            and event.get("data", {}).get("source_lane") == "live_lab"
            for hunt_events in events.values()
            for event in hunt_events
        )
        and any(hunt.get("stage") == "CLOSED" for hunt in hunts)
    )

    return {
        "schema": "BULLY_CLOSEOUT_PROOF_V1",
        "recorded_at": datetime.now(UTC).isoformat(),
        "repository": {
            "commit": _git("rev-parse", "HEAD"),
            "tree": _git("rev-parse", "HEAD^{tree}"),
            "branch": _git("branch", "--show-current"),
            "worktree_clean": not bool(_git("status", "--porcelain")),
        },
        "store": {
            "path": str(store_path.resolve()),
            "sha256": _sha256(store_path),
            "hunts": hunts,
            "recall_ids": [row["recall_id"] for row in store_data["recalls"]],
            "events_by_hunt": events,
            "cost_records_by_hunt": store_data["costs"],
            "decision_impacts": store_data["impacts"],
        },
        "feeds": feed_proofs,
        "rollback_all_passed": all(
            proof["rollback"]["rollback_restored_baseline"]
            and proof["rollback"]["records_retained"]
            for proof in feed_proofs.values()
        ),
        "calibration": evidence["calibration"],
        "calibration_recorded": evidence["calibration_recorded"],
        "refinement": evidence["refinement"],
        "refinement_recorded": evidence["refinement_recorded"],
        "refinement_status": "deferred_to_training_pass",
        "specimen_corpus": evidence["corpus"],
        "specimen_corpus_recorded": evidence["corpus_recorded"],
        "specimen_e2e": evidence["specimen_proof"],
        "specimen_e2e_recorded": evidence["specimen_e2e_recorded"],
        "live_lab_recorded": live_lab_recorded,
        "validation_summary": evidence["validation"],
        "validation_passed": evidence["validation_passed"],
        "validation_logs": [item for path in validation_logs if (item := _artifact(path))],
        "release_acceptance": _release_acceptance(
            all_feeds_changed=all_feeds_changed,
            evidence=evidence,
            live_lab_recorded=live_lab_recorded,
        ),
    }


def _markdown(bundle: dict[str, Any]) -> str:
    acceptance = bundle["release_acceptance"]
    lines = [
        "# Defensive Bully closeout proof",
        "",
        f"- Recorded: `{bundle['recorded_at']}`",
        f"- Commit: `{bundle['repository']['commit']}`",
        f"- Release acceptance: **{acceptance['status']}**",
        f"- Store: `{bundle['store']['path']}`",
        f"- Hunts / recalls / impacts: {len(bundle['store']['hunts'])} / "
        f"{len(bundle['store']['recall_ids'])} / {len(bundle['store']['decision_impacts'])}",
        "",
        "## Six-feed compounding proof",
        "",
        "| Feed | Mode | Result | DecisionImpact kinds | Rollback |",
        "|---|---|---|---|---|",
    ]
    for feed, proof in bundle["feeds"].items():
        rollback = "PASS" if proof["rollback"]["rollback_restored_baseline"] else "FAIL"
        kinds = ", ".join(proof["change_kinds"]) or "none"
        lines.append(f"| `{feed}` | {proof['mode']} | {proof['status']} | {kinds} | {rollback} |")
    lines.extend(
        [
            "",
            "## Frozen external evidence",
            "",
            f"- P6.8 calibration recorded: `{bundle['calibration_recorded']}`",
            f"- SPECIMEN_CORPUS_V1 recorded: `{bundle['specimen_corpus_recorded']}`",
            f"- P7 specimen E2E recorded: `{bundle['specimen_e2e_recorded']}`",
            f"- Refinement: `{bundle['refinement_status']}`",
            f"- Non-synthetic closed hunt recorded: `{bundle['live_lab_recorded']}`",
            f"- Validation summary passed: `{bundle['validation_passed']}`",
            f"- Validation logs: {len(bundle['validation_logs'])}",
            "",
            "The JSON manifest contains the complete IDs, before/after records, artifact hashes, "
            "event inventory, and cost records. Missing/no-effect evidence fails closed.",
            "",
        ]
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store", type=Path, default=config.hunt_dir() / "hunt_state.db")
    parser.add_argument("--calibration-report", type=Path)
    parser.add_argument("--refinement-verdict", type=Path)
    parser.add_argument("--specimen-corpus", type=Path)
    parser.add_argument("--specimen-e2e", type=Path)
    parser.add_argument("--validation-summary", type=Path)
    parser.add_argument("--validation-log", type=Path, action="append", default=[])
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args(argv)

    artifact_root = config.hunt_dir() / "artifacts"
    calibration_report = args.calibration_report or _latest(
        artifact_root, "calibration/*/calibration_report.json"
    )
    refinement_verdict = args.refinement_verdict or _latest(
        artifact_root, "trained_models/**/*.verdict.json"
    )
    specimen_corpus = args.specimen_corpus or _latest(
        artifact_root, "specimen_corpus_v1/specimen_corpus_v1.json"
    )
    specimen_e2e = args.specimen_e2e or _latest(
        artifact_root, "p7_specimen_e2e/*/p7_specimen_e2e.json"
    )
    output_dir = args.output_dir or (
        artifact_root / "closeout" / datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    )
    output_dir.mkdir(parents=True, exist_ok=False)

    bundle = assemble(
        store_path=args.store,
        calibration_report=calibration_report,
        refinement_verdict=refinement_verdict,
        specimen_corpus=specimen_corpus,
        specimen_e2e=specimen_e2e,
        validation_summary=args.validation_summary,
        validation_logs=args.validation_log,
    )
    json_path = output_dir / "closeout_manifest.json"
    md_path = output_dir / "closeout_report.md"
    json_path.write_text(json.dumps(bundle, indent=2, sort_keys=True, default=str) + "\n")
    md_path.write_text(_markdown(bundle), encoding="utf-8")
    print(json.dumps({"output_dir": str(output_dir), **bundle["release_acceptance"]}, indent=2))
    return 0 if bundle["release_acceptance"]["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
