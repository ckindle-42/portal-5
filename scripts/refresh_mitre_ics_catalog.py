#!/usr/bin/env python3
"""Regenerate the compact ATT&CK-for-ICS technique catalog used by mitre_mcp.

Fetches MITRE's official ics-attack STIX bundle from
``mitre-attack/attack-stix-data`` and distils it to
``portal/modules/security/core/siem/mitre_ics_techniques.json`` —
``{technique_id: {name, tactic, tactics, platforms, data_sources, detection,
description}}`` — the same lightweight shape mitre_mcp merges into its in-memory
index (with ``matrix: "ics"``).

Additive to the Enterprise catalog; run when MITRE ships a new ICS release.
"""

from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

_STIX_URL = (
    "https://raw.githubusercontent.com/mitre-attack/attack-stix-data/"
    "master/ics-attack/ics-attack.json"
)
_OUT = (
    Path(__file__).resolve().parents[1]
    / "portal"
    / "modules"
    / "security"
    / "core"
    / "siem"
    / "mitre_ics_techniques.json"
)


def main() -> int:
    print(f"fetching {_STIX_URL}")
    with urllib.request.urlopen(_STIX_URL, timeout=60) as fh:  # noqa: S310
        bundle = json.load(fh)

    techs: dict[str, dict] = {}
    for obj in bundle.get("objects", []):
        if obj.get("type") != "attack-pattern":
            continue
        if obj.get("revoked") or obj.get("x_mitre_deprecated"):
            continue
        ext = next(
            (
                r
                for r in obj.get("external_references", [])
                if r.get("source_name") == "mitre-attack"
            ),
            None,
        )
        if not ext:
            continue
        tid = ext["external_id"]
        phases = [
            p["phase_name"]
            for p in obj.get("kill_chain_phases", [])
            if p.get("kill_chain_name") == "mitre-ics-attack"
        ]
        techs[tid] = {
            "name": obj["name"],
            "tactic": phases[0] if phases else "unknown",
            "tactics": phases,
            "platforms": obj.get("x_mitre_platforms", []),
            "data_sources": obj.get("x_mitre_data_sources", []),
            "detection": (obj.get("x_mitre_detection") or "").strip(),
            "description": (obj.get("description") or "").split("\n")[0].strip(),
        }

    _OUT.write_text(
        json.dumps({k: techs[k] for k in sorted(techs)}, indent=1, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {len(techs)} ICS techniques -> {_OUT.relative_to(Path.cwd())}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
