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


def assemble(
    *,
    store_path: Path,
    calibration_report: Path | None,
    refinement_verdict: Path | None,
    validation_summary: Path | None,
    validation_logs: list[Path],
) -> dict[str, Any]:
    cfg = config.load_hunt_config()
    with Store(store_path) as store:
        hunts = store.hunts()
        recalls = store.recall_receipts()
        impacts = store.decision_impacts()
        events = {
            hunt["hunt_id"]: [
                event.to_dict() for event in store.decision_events_for_hunt(hunt["hunt_id"])
            ]
            for hunt in hunts
        }
        costs = {hunt["hunt_id"]: store.cost_ledger_for_hunt(hunt["hunt_id"]) for hunt in hunts}

    by_feed: dict[str, list[dict[str, Any]]] = {feed: [] for feed in cutover.FEEDS}
    for impact in impacts:
        feed = _feed_name(impact["explanation"])
        if feed in by_feed:
            by_feed[feed].append(impact)

    feed_proofs: dict[str, Any] = {}
    for feed in cutover.FEEDS:
        records = by_feed[feed]
        changed = any(record["change_kind"] != "NO_EFFECT" for record in records)
        feed_proofs[feed] = {
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

    calibration = _artifact(calibration_report)
    refinement = _artifact(refinement_verdict)
    validation = _artifact(validation_summary)
    calibration_content = (calibration or {}).get("content") or {}
    refinement_content = (refinement or {}).get("content") or {}
    validation_content = (validation or {}).get("content") or {}
    calibration_recorded = bool(calibration) and (
        calibration_content.get("passed") is True
        or bool(calibration_content.get("calibration_proposal"))
    )
    refinement_recorded = refinement_content.get("verdict") in {
        "served",
        "rejected",
        "rolled_back",
        "declined_no_gain",
        "training_failed",
    }
    all_feeds_changed = all(proof["status"] == "PASS" for proof in feed_proofs.values())
    live_lab_recorded = any(
        event.get("data", {}).get("used_synthetic") is False
        and event.get("data", {}).get("episode_id")
        for hunt_events in events.values()
        for event in hunt_events
    ) and any(hunt.get("stage") == "CLOSED" for hunt in hunts)
    validation_passed = validation_content.get("passed") is True

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
            "recall_ids": [row["recall_id"] for row in recalls],
            "events_by_hunt": events,
            "cost_records_by_hunt": costs,
            "decision_impacts": impacts,
        },
        "feeds": feed_proofs,
        "rollback_all_passed": all(
            proof["rollback"]["rollback_restored_baseline"]
            and proof["rollback"]["records_retained"]
            for proof in feed_proofs.values()
        ),
        "calibration": calibration,
        "calibration_recorded": calibration_recorded,
        "refinement": refinement,
        "refinement_recorded": refinement_recorded,
        "live_lab_recorded": live_lab_recorded,
        "validation_summary": validation,
        "validation_passed": validation_passed,
        "validation_logs": [item for path in validation_logs if (item := _artifact(path))],
        "release_acceptance": {
            "six_feeds_changed": all_feeds_changed,
            "calibration_recorded": calibration_recorded,
            "refinement_recorded": refinement_recorded,
            "live_lab_recorded": live_lab_recorded,
            "validation_passed": validation_passed,
            "status": (
                "PASS"
                if all_feeds_changed
                and calibration_recorded
                and refinement_recorded
                and live_lab_recorded
                and validation_passed
                else "FAIL"
            ),
            "note": (
                "This manifest proves only cited records. A synthetic hunt is not labeled as "
                "the live-lab section 15 proof; missing evidence remains a release finding."
            ),
        },
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
            f"- P6.7 refinement verdict recorded: `{bundle['refinement_recorded']}`",
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
    output_dir = args.output_dir or (
        artifact_root / "closeout" / datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    )
    output_dir.mkdir(parents=True, exist_ok=False)

    bundle = assemble(
        store_path=args.store,
        calibration_report=calibration_report,
        refinement_verdict=refinement_verdict,
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
