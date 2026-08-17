#!/usr/bin/env python3
"""Generate the SA7 live data-plane census.

The caller supplies live Splunk credentials through the environment (normally
by sourcing the workspace .env); this script never serializes credential values.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from portal.modules.security.core.bully.live_census import build_live_plane, write_live_census


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output", type=Path, default=Path("docs/BULLY_DATA_PLANE_CENSUS_LIVE_V1.json")
    )
    parser.add_argument("--sample-limit", type=int, default=32)
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
    payload = write_live_census(
        args.output,
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
    print(
        json.dumps(
            {
                "output": str(args.output),
                "sources": len(payload["census"]["sources"]),
                "blind_spots": len(payload["census"]["blind_spots"]),
                "planner_proof": payload["planner_proof"]["proof_hash"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
