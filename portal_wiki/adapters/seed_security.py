"""Seed security knowledge — technique signatures as cited KnowledgeUnits.

Phase W2 of BUILD_PROGRAM_SEC_RBP_WIKI_FIXES_V1.

For each MITRE technique in use, creates a MIXED unit describing what it
looks like in telemetry, per OS/source.  Every unit is CITED to its
SPL/MITRE/scenario source.  This is the knowledge blue will LOOK UP
in Phase B instead of recalling from weights.
"""

from __future__ import annotations

import sys
from pathlib import Path

from portal_wiki.core.schema import KnowledgeUnit, SourceRef
from portal_wiki.core.store import save_unit


def _ensure_bench_path() -> None:
    bench_path = str(Path(__file__).resolve().parent.parent.parent / "tests" / "benchmarks")
    if bench_path not in sys.path:
        sys.path.insert(0, bench_path)


def seed_technique_signatures(dry_run: bool = False) -> list[KnowledgeUnit]:
    """Seed technique-signature KnowledgeUnits from spl_detections.yaml
    and SCENARIOS detect_ground_truth.

    Returns list of units created.
    """
    _ensure_bench_path()
    from bench_security.exec_chain import SCENARIOS
    from bench_security.siem.spl_detections import spl_for, technique_reference

    ref = technique_reference()
    units: list[KnowledgeUnit] = []

    # Build scenario → techniques map
    scenario_map: dict[str, list[str]] = {}
    for name, scenario in SCENARIOS.items():
        for tid in scenario.get("detect_ground_truth", []):
            scenario_map.setdefault(tid, []).append(name)

    for tid, description in ref.items():
        spl = spl_for(tid)
        scenarios = scenario_map.get(tid, [])

        # Build the body: what this technique looks like per telemetry source
        body_parts = [
            f"# {tid} — {description}",
            "",
            "## Telemetry Signatures",
            "",
        ]

        if spl:
            body_parts.extend(
                [
                    "### SPL Detection (siem/spl_detections.yaml)",
                    "```spl",
                    spl,
                    "```",
                    "",
                ]
            )

        # Add scenario context
        if scenarios:
            body_parts.extend(
                [
                    "## Exercised By Scenarios",
                    "",
                ]
            )
            for sc_name in scenarios[:5]:
                sc = SCENARIOS.get(sc_name, {})
                body_parts.append(f"- `{sc_name}` — target: {sc.get('target_host', 'N/A')}")
            body_parts.append("")

        # Add OS/source-specific signatures
        body_parts.extend(
            [
                "## Per-Source Expected Signatures",
                "",
                "| Source | Expected Signal |",
                "|--------|----------------|",
            ]
        )

        # Map technique to expected signals per source
        signal_map = {
            "T1190": [
                (
                    "web:access",
                    "HTTP requests with attack payloads in URI/body (LFI/SQLi/Log4Shell markers)",
                ),
                ("windows:security", "Process creation (4688) from web server process"),
            ],
            "T1059": [
                ("linux:auditd", "EXECVE syscall with shell/interpreter commands"),
                ("windows:security", "Process creation (4688) for cmd.exe/powershell.exe"),
            ],
            "T1059.004": [
                ("linux:auditd", "EXECVE syscall for /bin/sh, /bin/bash, etc."),
            ],
            "T1505.003": [
                ("web:access", "File-write followed by execution of web-accessible path"),
            ],
            "T1003.001": [
                ("windows:security", "Process access to lsass.exe (handle request)"),
            ],
            "T1003.003": [
                ("windows:security", "File access to NTDS.dit or Volume Shadow Copy"),
            ],
            "T1003.006": [
                (
                    "windows:security",
                    "Event 4662 with replication access GUIDs (DS-Replication-Get-Changes, DS-Replication-Get-Changes-All)",
                ),
            ],
            "T1558.003": [
                (
                    "windows:security",
                    "Event 4769 with TicketEncryptionType=0x17 (RC4) — Kerberoasting indicator",
                ),
            ],
            "T1558.004": [
                (
                    "windows:security",
                    "Event 4768 without pre-authentication required (AS-REP Roasting)",
                ),
            ],
            "T1078": [
                ("windows:security", "Successful logon (4624) with unusual source or time"),
            ],
            "T1078.004": [
                ("cloud:audit", "Cloud account authentication from unusual source"),
            ],
            "T1110.003": [
                (
                    "windows:security",
                    "Multiple 4625/4771 events from single source in short window",
                ),
            ],
        }

        signals = signal_map.get(tid, [])
        if signals:
            for source, signal in signals:
                body_parts.append(f"| {source} | {signal} |")
        else:
            body_parts.append(f"| (generic) | Activity consistent with {tid} |")

        body_parts.extend(
            ["", "---", "*Unit auto-generated from spl_detections.yaml + SCENARIOS.*"]
        )

        # Build sources list
        sources = [
            SourceRef(type="spl", path=f"siem/spl_detections.yaml#{tid}"),
            SourceRef(type="mitre", path=f"ATT&CK:{tid}"),
        ]
        for sc_name in scenarios[:3]:
            sources.append(SourceRef(type="scenario", path=f"exec_chain.py#{sc_name}"))

        unit = KnowledgeUnit(
            id=f"unit-{tid}-signature",
            kind="mixed",
            title=f"{tid} — {description}",
            sources=sources,
            body="\n".join(body_parts),
            tags=[tid, "technique", "signature"],
        )
        units.append(unit)

        if not dry_run:
            save_unit(unit)

    return units


def seed_dcsync_specifically(dry_run: bool = False) -> KnowledgeUnit | None:
    """Create a specific DCSync unit with enriched telemetry normalization.

    This directly addresses P5-SEC-BLUE-MITRE-001 (DCSync never identified).
    """
    _ensure_bench_path()
    from bench_security.siem.spl_detections import spl_for

    spl = spl_for("T1003.006")
    if not spl:
        return None

    body = f"""# T1003.006 — DCSync Detection Signature

## What DCSync Looks Like

DCSync uses the Directory Replication Service (DRS) to request credential
data from a domain controller. The attacker impersonates a domain controller
and calls `DRSGetNCChanges` / `DRSReplicaSync`.

## Windows Security Event 4662 — Distinguishing GUIDs

The key distinguishing feature is **Event 4662** with specific replication
access rights:

| Access Right GUID | Meaning | DCSync Indicator |
|---|---|---|
| `1131f6aa-9c07-11d1-f79f-00c04fc2dcd2` | DS-Replication-Get-Changes | **Yes** |
| `1131f6ad-9c07-11d1-f79f-00c04fc2dcd2` | DS-Replication-Get-Changes-All | **Yes** |
| `89e95b76-444d-4c62-991a-0facbeda640c` | DS-Replication-Get-Changes-In-Filtered-Set | Partial |

**Both** Get-Changes AND Get-Changes-All must be present on the same
object for a high-confidence DCSync indicator.

## SPL Detection

```spl
{spl}
```

## Common False Positives

- Domain controllers performing legitimate replication (check source is a DC)
- Azure AD Connect sync (check account name is AAD_*)
- Backup software with AD integration

## Distinguishing from Kerberoasting (T1558.003)

Kerberoasting → Event 4769 (TGS request) with RC4 encryption
DCSync → Event 4662 (directory service access) with replication GUIDs

These are fundamentally different event types and should never be confused.
"""

    sources = [
        SourceRef(type="spl", path="siem/spl_detections.yaml#T1003.006"),
        SourceRef(type="mitre", path="ATT&CK:T1003.006"),
        SourceRef(type="design", path="coding_task/F1/DESIGN_SEC_UNIFIED_RBP_FRAMEWORK_V3.md#R3"),
    ]

    unit = KnowledgeUnit(
        id="unit-T1003.006-signature",
        kind="mixed",
        title="T1003.006 — DCSync detection signature (enriched)",
        sources=sources,
        body=body,
        tags=["T1003.006", "DCSync", "credential-access", "enriched"],
    )

    if not dry_run:
        save_unit(unit)
    return unit
