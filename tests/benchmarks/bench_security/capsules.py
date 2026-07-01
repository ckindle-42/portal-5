"""Portable proof capsules (Gap 3).

A proof capsule is a self-contained, integrity-hashed JSON the operator can
replay to re-confirm a finding without the original engagement. Follows ptai's
schema: finding + receipt + integrity_sha256.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .oracles import OracleVerdict, verify_finding

CAPSULES_DIR = Path(__file__).resolve().parent / "results" / "capsules"


def _capsule_body(capsule: dict) -> str:
    """Return the deterministically-serialised body for hashing (excludes timestamps + integrity)."""
    exclude = {"integrity_sha256", "created_at", "scored_at"}
    d = {k: v for k, v in capsule.items() if k not in exclude}
    return json.dumps(d, sort_keys=True, default=str).encode()


def compute_integrity(capsule: dict) -> str:
    """Compute integrity_sha256 over the capsule body."""
    return hashlib.sha256(_capsule_body(capsule)).hexdigest()


def build_capsule(
    finding: dict,
    verdict: OracleVerdict,
    replay: dict | None = None,
    engagement: str = "",
) -> dict:
    """Build a proof capsule in ptai's schema.

    Args:
        finding: {id, title, target, severity, bug_class, evidence, oracle, ...}
        verdict: OracleVerdict from verify_finding()
        replay: optional replay recipe dict
        engagement: engagement name for the output path

    Returns the capsule dict with integrity_sha256. Also writes under
    results/capsules/<engagement>/<finding_id>.json if engagement is given.
    """
    from datetime import UTC, datetime

    capsule: dict[str, Any] = {
        "capsule_schema_version": 1,
        "created_at": datetime.now(tz=UTC).isoformat(),
        "finding": {
            "id": finding.get("id", ""),
            "title": finding.get("title", ""),
            "target": finding.get("target", ""),
            "severity": finding.get("severity", "info"),
            "bug_class": finding.get("bug_class", ""),
            "evidence": finding.get("evidence", ""),
            "verification_recipe": {
                "oracle": finding.get("oracle", ""),
                "param": finding.get("param", ""),
            },
        },
        "receipt": {
            "verdict": "verified" if verdict.verified else "rejected",
            "oracle_kind": verdict.oracle_kind,
            "evidence": {
                "raw_output": verdict.evidence,
            },
            "replay": {
                "successes": verdict.reproductions,
                "attempts": verdict.required,
            },
        },
    }

    # Add replay instructions if provided
    if replay:
        capsule["receipt"]["replay"].update(replay)

    # Apply methodology stamp BEFORE computing integrity hash
    try:
        from tests.benchmarks.capability_lib import stamp_result_meta

        capsule = stamp_result_meta(capsule)  # type: ignore[assignment]
    except ImportError:
        pass

    capsule["integrity_sha256"] = compute_integrity(capsule)

    # Write to disk if engagement is provided
    if engagement:
        out_dir = CAPSULES_DIR / engagement
        out_dir.mkdir(parents=True, exist_ok=True)
        fid = finding.get("id", "capsule")
        out_path = out_dir / f"{fid}.json"
        out_path.write_text(json.dumps(capsule, indent=2))
        capsule["_path"] = str(out_path)

    return capsule


def replay_capsule(capsule: dict, dry_run: bool = False) -> OracleVerdict:
    """Verify integrity_sha256, then re-execute the verification recipe.

    A tampered capsule (integrity mismatch) is rejected immediately.
    dry_run prints the plan without touching the network.
    """
    expected_hash = capsule.get("integrity_sha256", "")
    actual_hash = compute_integrity(capsule)
    if expected_hash != actual_hash:
        return OracleVerdict(
            oracle="",
            oracle_kind="",
            verified=False,
            evidence="REJECTION: integrity hash mismatch — capsule may be tampered",
            honesty_claim="",
            reproductions=0,
            required=0,
        )

    if dry_run:
        recipe = capsule.get("finding", {}).get("verification_recipe", {})
        oracle_name = recipe.get("oracle", "")
        return OracleVerdict(
            oracle=oracle_name,
            oracle_kind="dry_run",
            verified=False,
            evidence=f"DRY-RUN: would replay oracle '{oracle_name}'",
            honesty_claim="",
            reproductions=0,
            required=0,
        )

    # Re-execute via lab_dispatch
    recipe = capsule.get("finding", {}).get("verification_recipe", {})
    finding = capsule.get("finding", {})
    oracle_name = recipe.get("oracle", "")

    from .lab import lab_dispatch

    try:
        result = lab_dispatch(
            "check_cve",
            {
                "host": finding.get("target", ""),
                "cve_id": finding.get("bug_class", ""),
            },
        )
    except Exception as exc:
        result = f"replay error: {exc}"

    return verify_finding(
        finding={"oracle": oracle_name, **finding},
        lab_output=result,
        observations={},
    )


def list_capsules(engagement: str = "") -> list[dict]:
    """List capsule paths and their basic metadata for an engagement (or all)."""
    base = CAPSULES_DIR
    if engagement:
        base = base / engagement
    if not base.exists():
        return []
    results: list[dict] = []
    for p in sorted(base.rglob("*.json")):
        try:
            data = json.loads(p.read_text())
            results.append(
                {
                    "path": str(p),
                    "id": data.get("finding", {}).get("id", ""),
                    "verdict": data.get("receipt", {}).get("verdict", "?"),
                    "oracle": data.get("finding", {})
                    .get("verification_recipe", {})
                    .get("oracle", ""),
                    "created": data.get("created_at", ""),
                }
            )
        except Exception:
            pass
    return results
