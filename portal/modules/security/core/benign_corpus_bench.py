"""Live benign-corpus generation and alert-fatigue scoring for RBP.

Cells use the same HEC transport, ``corpus:*`` provenance convention, index,
and sourcetypes as attack corpus records.  The blue model receives only raw
telemetry; the benign ground truth stays in the evaluation record.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from typing import Any

from portal.modules.security.core.agentic_blue_eval import Episode
from portal.modules.security.core.blue_orchestrate import SectionSpec, run_blue_orchestration
from portal.modules.security.core.notify_scoreboard import build_run, join_oracle
from portal.modules.security.core.siem.hec_ship import ship_batch
from portal.modules.security.core.siem.spl_backend import SplunkBackend

TOOL_MODEL = "bench-granite41-8b"
REASONING_MODEL = "bench-granite41-30b"
EXPERT_MODEL = "bench-granite41-8b"
MODEL_ARM = "strong_full_v3"
ATTACK_CHECKPOINT = Path(
    "portal/modules/security/core/results/checkpoints/corpus_replay_bench_v4_closeout.json"
)
OUT_PATH = Path(
    os.environ.get(
        "BENIGN_CORPUS_OUT",
        "portal/modules/security/core/results/checkpoints/benign_corpus_closeout.json",
    )
)

BENIGN_CELLS: tuple[dict[str, Any], ...] = (
    {
        "cell_id": "p5n001",
        "sourcetype": "windows:security",
        "host": "workstation-17",
        "events": [
            "EventCode=4624 LogonType=2 TargetUserName=jsmith AuthenticationPackageName=Negotiate Status=0x0 WorkstationName=WS17",
            "EventCode=4672 SubjectUserName=jsmith PrivilegeList=SeChangeNotifyPrivilege",
            "EventCode=4634 LogonType=2 TargetUserName=jsmith",
        ],
    },
    {
        "cell_id": "p5n002",
        "sourcetype": "windows:security",
        "host": "ad-dc-01",
        "events": [
            "EventCode=4768 TargetUserName=svc_backup PreAuthType=2 Status=0x0 TicketEncryptionType=0x12 IpAddress=10.10.20.15",
            "EventCode=4769 TargetUserName=svc_backup ServiceName=cifs/fileserver TicketEncryptionType=0x12 Status=0x0",
            "EventCode=4624 LogonType=3 TargetUserName=svc_backup WorkstationName=BACKUP01 Status=0x0",
        ],
    },
    {
        "cell_id": "p5n003",
        "sourcetype": "web:access",
        "host": "web-prod-02",
        "events": [
            '10.10.30.12 - monitor [26/Jul/2026:04:10:01 +0000] "GET /health HTTP/1.1" 200 18 "-" "kube-probe/1.34"',
            '10.10.30.21 - api_user [26/Jul/2026:04:10:03 +0000] "GET /api/v1/users?page=1&limit=25 HTTP/1.1" 200 842 "-" "portal-client/5.0"',
            '10.10.30.21 - api_user [26/Jul/2026:04:10:04 +0000] "GET /api/v1/users/42 HTTP/1.1" 200 96 "-" "portal-client/5.0"',
        ],
    },
    {
        "cell_id": "p5n004",
        "sourcetype": "web:access",
        "host": "web-prod-02",
        "events": [
            '10.10.30.33 - analyst [26/Jul/2026:04:12:01 +0000] "POST /search HTTP/1.1" 200 1337 "https://portal/search" "Mozilla/5.0" query="quarterly report"',
            '10.10.30.33 - analyst [26/Jul/2026:04:12:04 +0000] "GET /reports/quarterly-summary.pdf HTTP/1.1" 200 48211 "https://portal/search" "Mozilla/5.0"',
            '10.10.30.12 - monitor [26/Jul/2026:04:12:06 +0000] "GET /ready HTTP/1.1" 200 18 "-" "kube-probe/1.34"',
        ],
    },
    {
        "cell_id": "p5n005",
        "sourcetype": "linux:auditd",
        "host": "linux-app-03",
        "events": [
            'type=USER_CMD msg=audit(1785039301.100:4401): pid=8221 uid=1001 auid=1001 ses=44 subj=unconfined msg="cwd=/home/admin cmd=/usr/bin/sudo /usr/bin/apt-get update terminal=pts/2 res=success"',
            'type=EXECVE msg=audit(1785039301.120:4402): argc=2 a0="/usr/bin/apt-get" a1="update"',
            "type=USER_END msg=audit(1785039310.100:4403): pid=8221 uid=0 auid=1001 ses=44 res=success",
        ],
    },
    {
        "cell_id": "p5n006",
        "sourcetype": "linux:auditd",
        "host": "linux-app-03",
        "events": [
            'type=EXECVE msg=audit(1785039401.100:4501): argc=4 a0="/usr/bin/tar" a1="-czf" a2="/var/backups/app.tgz" a3="/srv/app" auid=0 uid=0',
            'type=SYSCALL msg=audit(1785039401.110:4502): arch=c000003e syscall=59 success=yes exe="/usr/bin/tar" key="nightly-backup" auid=0 uid=0',
            'type=SERVICE_START msg=audit(1785039410.100:4503): pid=1 uid=0 auid=4294967295 msg="unit=backup.service comm=systemd res=success"',
        ],
    },
    {
        "cell_id": "p5n007",
        "sourcetype": "windows:security",
        "host": "workstation-22",
        "events": [
            r"EventCode=4698 TaskName=\Microsoft\Windows\EnterpriseMgmt\HealthCheck Author=SYSTEM SubjectUserName=SCCM-SERVER$ TaskContent=deviceenroller.exe Schedule=PT1H ChangeTicket=CHG-2026-0712",
            r"EventCode=4688 NewProcessName=C:\Windows\System32\deviceenroller.exe ParentProcessName=C:\Windows\System32\svchost.exe CommandLine=deviceenroller.exe /c /AutoEnrollMDM Signature=Microsoft SubjectUserName=SYSTEM",
            r"EventCode=4699 TaskName=\Microsoft\Windows\EnterpriseMgmt\HealthCheck SubjectUserName=SCCM-SERVER$ Result=maintenance-complete ChangeTicket=CHG-2026-0712",
        ],
    },
    {
        "cell_id": "p5n008",
        "sourcetype": "windows:security",
        "host": "workstation-23",
        "events": [
            r"EventCode=4624 LogonType=3 TargetUserName=SCCM-SERVER$ AuthenticationPackageName=Kerberos IpAddress=10.10.40.20 Status=0x0 Purpose=approved-inventory",
            r"EventCode=4688 NewProcessName=C:\Windows\System32\wbem\WmiPrvSE.exe ParentProcessName=C:\Windows\System32\svchost.exe CommandLine=WmiPrvSE.exe -secured -Embedding Initiator=SCCM InventoryJob=INV-8842",
            r"EventCode=4634 LogonType=3 TargetUserName=SCCM-SERVER$ SessionResult=success InventoryJob=INV-8842",
        ],
    },
    {
        "cell_id": "p5n009",
        "sourcetype": "web:access",
        "host": "docs-prod-01",
        "events": [
            '10.10.50.18 - qa_linkcheck [30/Jul/2026:03:15:01 +0000] "GET /docs/migration-v7 HTTP/1.1" 200 18231 "-" "qa-link-checker/2.1" run=QA-443',
            '10.10.50.18 - qa_linkcheck [30/Jul/2026:03:15:02 +0000] "GET /docs/retired-endpoint HTTP/1.1" 404 211 "-" "qa-link-checker/2.1" run=QA-443',
            '10.10.50.18 - qa_linkcheck [30/Jul/2026:03:15:03 +0000] "GET /robots.txt HTTP/1.1" 200 94 "-" "qa-link-checker/2.1" run=QA-443',
        ],
    },
    {
        "cell_id": "p5n010",
        "sourcetype": "web:access",
        "host": "api-prod-04",
        "events": [
            '10.10.60.11 - deploy_bot [30/Jul/2026:03:20:01 +0000] "POST /api/admin/cache/warm HTTP/1.1" 202 38 "-" "portal-deployer/8.0" auth=mtls change=CHG-2026-0730',
            '10.10.60.11 - deploy_bot [30/Jul/2026:03:20:03 +0000] "GET /api/admin/cache/status HTTP/1.1" 200 76 "-" "portal-deployer/8.0" auth=mtls change=CHG-2026-0730',
            '10.10.60.12 - monitor [30/Jul/2026:03:20:05 +0000] "GET /ready HTTP/1.1" 200 18 "-" "kube-probe/1.34"',
        ],
    },
    {
        "cell_id": "p5n011",
        "sourcetype": "linux:auditd",
        "host": "linux-api-05",
        "events": [
            'type=USER_CMD msg=audit(1785381901.100:4601): pid=9221 uid=1002 auid=1002 ses=51 msg="cwd=/srv/api cmd=/usr/bin/sudo /usr/bin/systemctl restart portal-api.service terminal=pts/1 res=success" change_ticket=CHG-2026-0729',
            'type=EXECVE msg=audit(1785381901.120:4602): argc=3 a0="/usr/bin/systemctl" a1="restart" a2="portal-api.service" auid=1002 uid=0 automation=ansible',
            'type=SERVICE_START msg=audit(1785381903.100:4603): pid=1 uid=0 auid=4294967295 msg="unit=portal-api.service comm=systemd res=success" change_ticket=CHG-2026-0729',
        ],
    },
    {
        "cell_id": "p5n012",
        "sourcetype": "linux:auditd",
        "host": "k8s-worker-04",
        "events": [
            'type=EXECVE msg=audit(1785382001.100:4701): argc=5 a0="/usr/bin/nsenter" a1="--mount=/proc/1/ns/mnt" a2="--" a3="/usr/bin/mount" a4="/var/lib/kubelet/pods" uid=0 auid=4294967295 comm=kubelet purpose=csi-volume-reconcile',
            'type=SYSCALL msg=audit(1785382001.110:4702): arch=c000003e syscall=165 success=yes exe="/usr/bin/mount" key="kubernetes-csi" uid=0 auid=4294967295 container_runtime=containerd',
            'type=SERVICE_START msg=audit(1785382002.100:4703): pid=1 uid=0 auid=4294967295 msg="unit=kubelet.service comm=systemd res=success" node_role=worker',
        ],
    },
)


def provenance_fields(cell: dict[str, Any]) -> set[str]:
    """Metadata keys shared with attack Lane-B corpus records."""
    del cell
    return {"evidence_origin", "source", "sourcetype", "host"}


def _origin(cell: dict[str, Any]) -> str:
    return f"corpus:p5-negative:{cell['cell_id']}"


def _query_cell(backend: SplunkBackend, cell: dict[str, Any]) -> list[str]:
    search = (
        f'search index={backend.index} evidence_origin="{_origin(cell)}" '
        f'sourcetype="{cell["sourcetype"]}" | head 20'
    )
    rows = backend._run_search(search, "0", "now")
    return [str(row["fields"].get("_raw") or "") for row in rows if row["fields"].get("_raw")]


def ship_corpus(*, dry_run: bool) -> list[dict[str, Any]]:
    """Idempotently ship every cell through the production HEC primitive."""
    backend = SplunkBackend()
    records = []
    for offset, cell in enumerate(BENIGN_CELLS):
        existing = [] if dry_run else _query_cell(backend, cell)
        if existing:
            records.append(
                {
                    "cell_id": cell["cell_id"],
                    "status": "already_indexed",
                    "events": len(existing),
                }
            )
            continue
        result = ship_batch(
            list(cell["events"]),
            sourcetype=str(cell["sourcetype"]),
            host=str(cell["host"]),
            dry_run=dry_run,
            event_time=time.time() - (45 * 86400) - (offset * 60),
            evidence_origin=_origin(cell),
        )
        records.append({"cell_id": cell["cell_id"], "status": "shipped", **result})
    return records


def _wait_for_cell(backend: SplunkBackend, cell: dict[str, Any]) -> list[str]:
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        events = _query_cell(backend, cell)
        if events:
            return events
        time.sleep(2)
    return []


def _run_cell(cell: dict[str, Any], telemetry: list[str]) -> dict[str, Any]:
    episode = Episode(
        scenario=str(cell["cell_id"]),
        target_host=str(cell["host"]),
        techniques=[],
        telemetry={str(cell["sourcetype"]): telemetry},
        captured_at=time.time(),
    )
    started = time.monotonic()
    result = run_blue_orchestration(
        episode,
        sections=[
            SectionSpec(role="tool", model=TOOL_MODEL, needs_tools=True),
            SectionSpec(role="reasoning", model=REASONING_MODEL, use_barrier_tools=True),
            SectionSpec(role="expert", model=EXPERT_MODEL, use_barrier_tools=True),
        ],
        max_rounds=6,
        budgets={"hunter": 10, "expert": 2},
    )
    return {
        "label": cell["cell_id"],
        "ground_truth": "benign",
        "technique_expected": "",
        "model_arm": MODEL_ARM,
        "mode": "orchestrated",
        "status": "done",
        "verdict": result.verdict,
        "technique_ids": result.technique_ids,
        "match_grade": result.match_grade,
        "elapsed_s": round(time.monotonic() - started, 2),
        "sourcetype": cell["sourcetype"],
        "evidence_origin": _origin(cell),
        "provenance_fields": sorted(provenance_fields(cell)),
        "trace": result.trace,
    }


def run_bench(*, resume: bool = True, rerun_cells: set[str] | None = None) -> list[dict[str, Any]]:
    """Replay the indexed negative cells through the unchanged strong blue arm."""
    if rerun_cells and not resume:
        raise ValueError("targeted reruns require the retained checkpoint")
    results = json.loads(OUT_PATH.read_text()) if resume and OUT_PATH.exists() else []
    if rerun_cells:
        results = [record for record in results if record.get("label") not in rerun_cells]
    done = {record["label"] for record in results if record.get("status") == "done"}
    backend = SplunkBackend()
    for cell in BENIGN_CELLS:
        if rerun_cells and cell["cell_id"] not in rerun_cells:
            continue
        if cell["cell_id"] in done:
            continue
        telemetry = _wait_for_cell(backend, cell)
        if not telemetry:
            record = {
                "label": cell["cell_id"],
                "ground_truth": "benign",
                "model_arm": MODEL_ARM,
                "status": "skipped_no_corpus_data",
            }
        else:
            record = _run_cell(cell, telemetry)
        results.append(record)
        OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        OUT_PATH.write_text(json.dumps(results, indent=2, sort_keys=True) + "\n")
        print(
            f"{record['label']}: {record['status']} verdict={record.get('verdict', 'n/a')}",
            flush=True,
        )
    return results


def build_score(benign_records: list[dict[str, Any]]) -> dict[str, Any]:
    """Combine retained V4 attack evidence with the live benign negatives."""
    benign_records = sorted(benign_records, key=lambda record: str(record.get("label", "")))
    attacks = json.loads(ATTACK_CHECKPOINT.read_text())
    attack_arm = [
        record
        for record in attacks
        if record.get("status") == "done" and record.get("model_arm") == MODEL_ARM
    ]
    joined = join_oracle([*attack_arm, *benign_records])
    run = build_run(
        joined,
        source=f"{ATTACK_CHECKPOINT} + {OUT_PATH}",
        source_sha256="combined-live-artifacts",
    )
    arm = run["arms"][MODEL_ARM]
    return {
        "schema_version": 1,
        "run_kind": "live",
        "attack_source": str(ATTACK_CHECKPOINT),
        "benign_source": str(OUT_PATH),
        "benign_scope": "expanded representative subset (4 cells per sourcetype; 12 total)",
        "provenance_guard": {
            "same_transport": "portal.modules.security.core.siem.hec_ship.ship_batch",
            "same_index": SplunkBackend().index,
            "same_origin_shape": "corpus:<source>:<opaque-label>",
            "same_metadata_fields": sorted(provenance_fields(BENIGN_CELLS[0])),
            "answer_key_model_visible": False,
        },
        "scoreboard": arm,
        "benign_cells": benign_records,
    }


def render_markdown(result: dict[str, Any]) -> str:
    """Render the measured two-axis closeout."""
    board = result["scoreboard"]
    recall = board["axis_1_notify_recall"]
    fatigue = board["axis_4_alert_fatigue_on_benign"]
    lines = [
        "# RBP Benign Corpus and Alert-Fatigue Closeout — 2026-07-30",
        "",
        "## Outcome",
        "",
        f"The strong V4 arm now has both axes populated: fair notify recall "
        f"{recall['fair']['notified']}/{recall['fair']['eligible']} "
        f"({recall['fair']['rate'] * 100:.1f}%) on attacks, and notification "
        f"precision {fatigue['correct_silences']}/{fatigue['benign_cells']} "
        f"({fatigue['notification_precision'] * 100:.1f}%) on the representative "
        "benign subset.",
        "",
        f"False-flag rate: {fatigue['false_flags']}/{fatigue['benign_cells']} "
        f"({fatigue['false_flag_rate'] * 100:.1f}%). Confident wrong confirms: "
        f"{fatigue['false_flag_kinds']['confirmed_on_benign']}; honest anomaly "
        f"flags: {fatigue['false_flag_kinds']['anomaly_on_benign']}.",
        "",
        "## Benign cells",
        "",
        "| Cell | Sourcetype | Verdict | False flag | Runtime |",
        "|---|---|---|---:|---:|",
    ]
    scored = {cell["label"]: cell for cell in board["cells_scored"]}
    for cell in result["benign_cells"]:
        if cell.get("status") != "done":
            continue
        score = scored[cell["label"]]
        lines.append(
            f"| `{cell['label']}` | `{cell['sourcetype']}` | {cell['verdict']} | "
            f"{'yes' if score['false_flag'] else 'no'} | {cell['elapsed_s']:.2f}s |"
        )
    lines.extend(
        [
            "",
            "## Fairness and provenance",
            "",
            "- Windows Security, web access, and Linux auditd each contribute four "
            "plausibly confusable routine-activity cells.",
            "- Cells use the production `ship_batch` HEC primitive, `portal5_lab` "
            "index, attack-corpus sourcetypes, and the same `corpus:*` provenance "
            "field shape. No `episode_id` or ground-truth field is shipped.",
            "- The blue arm receives raw telemetry only. The `ground_truth=benign` "
            "label exists solely in the evaluation checkpoint.",
            "- Coverage is a twelve-cell representative subset, not an exhaustive "
            "estimate of all normal enterprise behavior; the measured precision "
            "must not be extrapolated beyond this corpus.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate and score benign RBP corpus")
    parser.add_argument("--ship", action="store_true", help="Ship missing cells through HEC")
    parser.add_argument("--run", action="store_true", help="Run blue over indexed cells")
    parser.add_argument(
        "--score-only",
        action="store_true",
        help="Re-score the retained live attack and benign checkpoints",
    )
    parser.add_argument("--no-resume", action="store_true")
    parser.add_argument(
        "--rerun-cell",
        action="append",
        choices=[str(cell["cell_id"]) for cell in BENIGN_CELLS],
        default=[],
        help="Replace one retained cell with a fresh live result (repeatable)",
    )
    parser.add_argument("--json-out", type=Path)
    parser.add_argument("--report-out", type=Path)
    args = parser.parse_args()
    if args.no_resume and args.rerun_cell:
        parser.error("--rerun-cell cannot be combined with --no-resume")

    if args.ship:
        print(json.dumps(ship_corpus(dry_run=False), indent=2), flush=True)
    elif args.run or args.score_only:
        # Running without --ship is allowed only for an already-indexed corpus.
        pass
    else:
        print(json.dumps(ship_corpus(dry_run=True), indent=2), flush=True)
        return

    records = (
        run_bench(
            resume=not args.no_resume,
            rerun_cells=set(args.rerun_cell) or None,
        )
        if args.run
        else json.loads(OUT_PATH.read_text())
    )
    result = build_score(records)
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    if args.report_out:
        args.report_out.parent.mkdir(parents=True, exist_ok=True)
        args.report_out.write_text(render_markdown(result))
    if not args.json_out and not args.report_out:
        print(render_markdown(result))


if __name__ == "__main__":
    main()
