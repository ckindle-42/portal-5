#!/usr/bin/env python3
"""Build the live plane, regenerate its census, and publish the L.10 gate."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from portal.modules.security.core.bully.live_census import build_live_plane, write_live_census
from portal.modules.security.core.bully.phase0_gate import evaluate_phase0_gate


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--census", type=Path, default=Path("docs/BULLY_DATA_PLANE_CENSUS_LIVE_V1.json")
    )
    parser.add_argument("--output", type=Path, default=Path("docs/BULLY_SA7_P0_GATE_L10.md"))
    parser.add_argument("--sample-limit", type=int, default=16)
    args = parser.parse_args()
    base = Path("/Volumes/data01/portal5_hunt")
    plane, planner = build_live_plane(
        corpora_root=base / "corpora",
        attack_data_root=base / "sources/attack_data/datasets",
        coverage_path=Path("portal/modules/security/core/siem/spl_detections.yaml"),
        store_path=base / "hunt_state.db",
        sample_limit=args.sample_limit,
        corpus_counts={
            "attack_data": 54,
            "flaws_cloud_cloudtrail": 1_939_207,
            "invictus_ir_aws_dataset": 2_900,
        },
    )
    census = write_live_census(
        args.census,
        plane,
        planner,
        findings=[
            {
                "kind": "inventory",
                "status": "unavailable",
                "source": "lab AD/Proxmox",
                "finding": "Proxmox API connection failed; asset context remains derived from live indexed entities",
            }
        ],
    )
    gate = evaluate_phase0_gate(plane, census, planner)
    args.output.write_text(
        "# Bully SA7 Phase 0 Gate — L.10\n\n"
        f"Result: **{'GREEN' if gate['passed'] else 'BLOCKED'}**\n\n"
        "Generated from the live census and planner proof in "
        f"`{args.census}`.\n\n"
        "## Checks\n\n"
        + "\n".join(
            f"- `{name}`: {'PASS' if passed else 'FAIL'}" for name, passed in gate["checks"].items()
        )
        + "\n\n## Evidence\n\n"
        + f"```json\n{json.dumps(gate['evidence'], indent=2, sort_keys=True)}\n```\n\n"
        + "## Named remainder\n\n"
        + "The Proxmox inventory endpoint was unavailable during the live run. "
        "Asset/identity context is nevertheless connected from indexed entities; "
        "the inventory finding remains explicit in the census and is not treated "
        "as observed.\n",
        encoding="utf-8",
    )
    print(json.dumps(gate, sort_keys=True))
    return 0 if gate["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
