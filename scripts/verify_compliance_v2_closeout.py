#!/usr/bin/env python3
"""Strict V3 closeout arbiter. NOT_RUN is always a failure."""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import subprocess
import tempfile
import urllib.request
from pathlib import Path

from portal.modules.compliance.core.assessment import assess_atom
from portal.modules.compliance.core.determination import (
    SME_DECISION_KINDS,
    AtomResult,
    DeterminationContractError,
)
from portal.modules.compliance.core.repository import Repository

ROOT = Path(__file__).resolve().parents[1]
DB = Path(
    os.environ.get(
        "COMPLIANCE_DB_PATH", ROOT / "portal/modules/compliance/data/compliance_store.db"
    )
)
REQUIRED_TABLES = (
    "obligation_atoms",
    "obligation_expressions",
    "definitions",
    "authority_assertions",
    "internal_controls",
    "activities",
    "roles",
    "systems",
    "evidence_specs",
    "analysis_runs",
    "claims",
    "claim_evidence",
    "findings",
)
COMPONENTS = (
    "comparison",
    "constraints",
    "assessment",
    "traceability",
    "impact",
    "change_plan",
    "boundary",
)


def _args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--live", action="store_true")
    return parser.parse_args()


def _http(path: str) -> dict:
    with urllib.request.urlopen(f"http://localhost:8937{path}", timeout=30) as response:  # noqa: S310
        return json.load(response)


def _post(tool: str, payload: dict) -> dict:
    request = urllib.request.Request(
        f"http://localhost:8937/tools/{tool}",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310
        return json.load(response)


def _latest_rows(conn):
    run = conn.execute(
        "SELECT run_id FROM analysis_runs ORDER BY created_at DESC,rowid DESC LIMIT 1"
    ).fetchone()
    return (
        [] if not run else conn.execute("SELECT * FROM claims WHERE run_id=?", (run[0],)).fetchall()
    )


def main() -> int:  # noqa: C901, PLR0912, PLR0915
    args = _args()
    results: dict[str, tuple[bool, str]] = {}

    def check(cid: str, fn):
        try:
            ok, evidence = fn()
        except Exception as exc:  # noqa: BLE001
            ok, evidence = False, f"{type(exc).__name__}: {exc}"
        results[cid] = (bool(ok), str(evidence))

    ledger = json.loads((args.run_dir / "acceptance-ledger.json").read_text())
    traces = [
        json.loads(line)
        for line in (args.run_dir / "question-traces.jsonl").read_text().splitlines()
        if line
    ]
    sweeps = [
        json.loads(line)
        for line in (args.run_dir / "standard-sweep.jsonl").read_text().splitlines()
        if line
    ]
    sme = json.loads((args.run_dir / "sme-review.json").read_text())
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    rows = _latest_rows(conn)

    def v01():
        rejected = 0
        for kwargs in (
            {"atom_id": "x", "determination": "UNRESOLVED"},
            {"atom_id": "x", "determination": "ABSENT"},
            {"atom_id": "x", "determination": "SUPPORTED", "governing_anchor_ids": ["g"]},
        ):
            try:
                AtomResult(**kwargs)
            except DeterminationContractError:
                rejected += 1
        return rejected == 3, f"{rejected}/3 invalid dataclasses rejected"

    check("V01", v01)

    def v02():
        sql = conn.execute("SELECT sql FROM sqlite_master WHERE name='claims'").fetchone()[0]
        return all(
            token in sql
            for token in (
                "SUPPORTED','PARTIAL','CONTRADICTED','ABSENT','UNRESOLVED",
                "unresolved_code <> ''",
                "boundary_proof_id <> ''",
            )
        ), "claims CHECK constraints present"

    check("V02", v02)
    check(
        "V03",
        lambda: (
            assess_atom(
                {"atom_id": "x", "action": "do work", "source_anchor_ids": ["g"]},
                [{"action": "do work", "anchor_id": "i"}],
                {},
            ).determination
            == "SUPPORTED",
            "complete-evidence fixture is SUPPORTED",
        ),
    )
    check(
        "V04",
        lambda: (
            all(
                conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0] > 0
                for table in REQUIRED_TABLES
            ),
            ", ".join(
                f"{table}:{conn.execute(f'SELECT count(*) FROM {table}').fetchone()[0]}"
                for table in REQUIRED_TABLES
            ),
        ),
    )

    def v05():
        counts = ledger["runtime_call_counts"]
        missing = [name for name in COMPONENTS if counts.get(name, 0) <= 0]
        return not missing, f"runtime counts={counts}; missing={missing}"

    check("V05", v05)
    check(
        "V06",
        lambda: (
            ledger["anchor_resolution_rate"] == 1.0,
            f"{ledger['anchors_resolved']} anchors, rate={ledger['anchor_resolution_rate']}",
        ),
    )

    def v07():
        absent = [row for row in rows if row["determination"] == "ABSENT"]
        bad = []
        for row in absent:
            proof = conn.execute(
                "SELECT * FROM corpus_boundary_proofs WHERE boundary_proof_id=?",
                (row["boundary_proof_id"],),
            ).fetchone()
            if (
                not proof
                or not json.loads(proof["query_set_json"])
                or not proof["index_generation"]
            ):
                bad.append(row["claim_id"])
        return not bad, f"ABSENT={len(absent)}, invalid proofs={len(bad)}"

    check("V07", v07)
    check(
        "V08",
        lambda: (
            assess_atom(
                {"atom_id": "x", "action": "work", "source_anchor_ids": ["g"]},
                [{"action": "work", "anchor_id": "i"}],
                {},
            ).determination
            == "SUPPORTED",
            "assessment has no mapping/approval input",
        ),
    )
    boundary_text = (ROOT / "portal/modules/compliance/core/propose.py").read_text()
    check(
        "V09",
        lambda: (
            "standard_hint != target_std" not in boundary_text
            and "folder mismatch"
            not in json.dumps(
                [dict(r) for r in conn.execute("SELECT * FROM corpus_boundary_proofs")]
            ),
            "folder mismatch is not an eligibility exclusion",
        ),
    )
    check(
        "V10",
        lambda: (
            lambda r: (
                r.get("found") and r["parts"][0]["temporal_label"] == "historical",
                r["parts"][0]["id"],
            )
        )(
            _post(
                "compliance_requirement", {"requirement": "CIP-003-8 R1", "valid_at": "2023-01-01"}
            )
        ),
    )
    check(
        "V11", lambda: (ledger["a_matrix"] == {"passed": 30, "total": 30}, str(ledger["a_matrix"]))
    )
    check(
        "V12", lambda: (ledger["q_matrix"] == {"passed": 36, "total": 36}, str(ledger["q_matrix"]))
    )
    acceptance_text = (
        ROOT / "tests/acceptance/test_compliance_reasoning_v2_questions.py"
    ).read_text()
    check(
        "V13",
        lambda: (
            not re.search(r'assert\s+["\'][^"\']+["\']\s+in\s+result\s*$', acceptance_text, re.M),
            "no key-presence-only assertions",
        ),
    )

    def v14():
        if not args.live:
            return False, "--live not supplied"
        proc = subprocess.run(
            [
                "uv",
                "run",
                "pytest",
                "tests/acceptance/test_compliance_reasoning_v2_questions.py",
                "-q",
            ],
            cwd=ROOT,
            env={**os.environ, "COMPLIANCE_LIVE": "1"},
            capture_output=True,
            text=True,
            timeout=360,
        )
        return (
            proc.returncode == 0 and "skipped" not in proc.stdout.lower(),
            f"exit={proc.returncode}; skipped={'skipped' in proc.stdout.lower()}",
        )

    check("V14", v14)
    draft = _post(
        "compliance_draft_revisions", {"old_standard": "CIP-003-8", "new_standard": "CIP-003-9"}
    )
    check(
        "V15",
        lambda: (
            draft.get("mode") == "draft_as_proposal"
            and all(item.get("reassessment") for item in draft.get("specifications", [])),
            f"mode={draft.get('mode')}, proposals={len(draft.get('specifications', []))}",
        ),
    )
    scenario_test = subprocess.run(
        ["uv", "run", "pytest", "tests/unit/test_compliance_scenarios.py", "-k", "weakening", "-q"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    check(
        "V16",
        lambda: (
            scenario_test.returncode == 0,
            f"weakening regression exit={scenario_test.returncode}",
        ),
    )
    chain = {
        "question",
        "route",
        "tool",
        "file_symbol",
        "governing_selection",
        "obligation_context",
        "internal_implementation",
        "comparison_delta_path",
        "determination",
        "exact_citations",
        "displayed_finding",
        "sme_decision_kind",
    }
    check(
        "V17",
        lambda: (
            len(traces) == 12
            and all(chain <= trace.keys() and trace["exact_citations"] for trace in traces),
            f"complete traces={len(traces)}/12",
        ),
    )
    check(
        "V18",
        lambda: (
            len(sweeps) == ledger["standards"] and all(not row["incomplete"] for row in sweeps),
            f"standards={len(sweeps)}, incomplete={sum(row['incomplete'] for row in sweeps)}",
        ),
    )
    check(
        "V19",
        lambda: (
            ledger["determination_rate"] >= 0.9,
            f"{ledger['answers']}/{ledger['applicable']}={ledger['determination_rate']:.3%}",
        ),
    )
    unresolved = [row for row in rows if row["determination"] == "UNRESOLVED"]
    valid_unresolved = sum(
        bool(row["unresolved_code"] and json.loads(row["missing_fact_json"])) for row in unresolved
    )
    check(
        "V20",
        lambda: (
            valid_unresolved == len(unresolved),
            f"valid unresolved={valid_unresolved}/{len(unresolved)}",
        ),
    )
    check(
        "V21",
        lambda: (
            all(item.get("kind") in SME_DECISION_KINDS for item in sme),
            f"queue={len(sme)}, invalid={sum(item.get('kind') not in SME_DECISION_KINDS for item in sme)}",
        ),
    )

    def v22():
        with tempfile.TemporaryDirectory() as tmp:
            backup = Path(tmp) / "backup.db"
            restored = Path(tmp) / "restored.db"
            repo = Repository(DB)
            repo.backup_to(backup)
            rr = Repository.restore_from(backup, restored)
            clean = rr._conn.execute("PRAGMA foreign_key_check").fetchall() == []
            return clean and rr.migrate()[
                "applied"
            ] == [], f"schema={rr.schema_version}, FK clean={clean}"

    check("V22", v22)
    check(
        "V23",
        lambda: (
            conn.execute("SELECT count(*) FROM review_events").fetchone()[0] > 0,
            f"review_events={conn.execute('SELECT count(*) FROM review_events').fetchone()[0]}",
        ),
    )
    before_after = json.loads((args.run_dir / "before-after.json").read_text())
    check(
        "V24",
        lambda: (
            bool(before_after.get("Q05")) and bool(before_after.get("Q12")),
            "before/after artifacts recorded",
        ),
    )
    check(
        "V25",
        lambda: (
            _http("/health").get("status") == "ok" and Repository().schema_version >= 6,
            "live MCP healthy; schema current",
        ),
    )
    check(
        "V26",
        lambda: (
            (ROOT / "KNOWN_LIMITATIONS.md").stat().st_mtime
            > (ROOT / "coding_task/v9_compliance/TASK_COMPLIANCE_REASONING_V3.md").stat().st_mtime
            and "native Python"
            in (ROOT / "reports/compliance/REASONING_V2_REUSE_DECISIONS.md").read_text(),
            "KNOWN_LIMITATIONS and reuse decision updated",
        ),
    )
    acceptance = ROOT / "reports/compliance/REASONING_V3_ACCEPTANCE.md"
    check(
        "V27",
        lambda: (
            acceptance.is_file() and ledger["run_id"] in acceptance.read_text(),
            f"acceptance report names final run {ledger['run_id']}",
        ),
    )
    ladder = args.run_dir / "command-ladder.json"
    check(
        "V28",
        lambda: (
            ladder.is_file()
            and all(item.get("exit_code") == 0 for item in json.loads(ladder.read_text())),
            "all recorded command exits are zero",
        ),
    )

    failed = []
    for number in range(1, 29):
        cid = f"V{number:02d}"
        ok, evidence = results.get(cid, (False, "NOT_RUN"))
        status = "PASS" if ok else ("NOT_RUN" if evidence == "NOT_RUN" else "FAIL")
        print(f"{cid} {status} {evidence}")
        if not ok:
            failed.append(cid)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
