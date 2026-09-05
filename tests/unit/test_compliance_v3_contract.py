from __future__ import annotations

import sqlite3

import pytest

from portal.modules.compliance.core.boundary import BoundarySearch
from portal.modules.compliance.core.determination import AtomResult, DeterminationContractError
from portal.modules.compliance.core.repository import Repository


def test_v01_dataclass_contract_rejects_invalid_results():
    with pytest.raises(DeterminationContractError):
        AtomResult("TEST-ATOM", "UNRESOLVED")
    with pytest.raises(DeterminationContractError):
        AtomResult("TEST-ATOM", "ABSENT")
    with pytest.raises(DeterminationContractError):
        AtomResult("TEST-ATOM", "SUPPORTED", governing_anchor_ids=["g"])


def test_v02_store_constraints_physically_reject_invalid_results(tmp_path):
    repo = Repository(tmp_path / "contract.db")
    run_id = repo.record_analysis_run({"test": True})
    base = ("claim", run_id, "[]", "test", "proposed", "x", "x", "[]", "[]", "[]", "now", "default")
    sql = """INSERT INTO claims(claim_id,run_id,obligation_atom_ids_json,claim_kind,
        review_status,assertion,rationale,governing_anchor_ids_json,internal_anchor_ids_json,
        counterevidence_anchor_ids_json,created_at,org_id,determination,unresolved_code,
        missing_fact_json,field_results_json,boundary_proof_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"""
    with pytest.raises(sqlite3.IntegrityError):
        repo._conn.execute(sql, (*base, "UNRESOLVED", "", "{}", "[]", ""))
    with pytest.raises(sqlite3.IntegrityError):
        repo._conn.execute(sql, (*base, "ABSENT", "", "{}", "[]", ""))
    with pytest.raises(DeterminationContractError):
        repo.record_claim(
            {
                "atom_id": "TEST-SUPPORTED",
                "determination": "SUPPORTED",
                "governing_anchor_ids": ["gov"],
            },
            run_id=run_id,
        )


def test_migration_is_idempotent_and_foreign_keys_are_clean(tmp_path):
    repo = Repository(tmp_path / "migration.db")
    assert repo.schema_version >= 6
    assert repo.migrate()["applied"] == []
    assert repo._conn.execute("PRAGMA foreign_key_check").fetchall() == []


def exhaustive(subject: str) -> BoundarySearch:
    return BoundarySearch(subject, [subject, "plain language query"], "test-index", "manifest", 1)
