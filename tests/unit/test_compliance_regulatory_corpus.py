"""Symmetric regulatory materialization (BILATERAL_CORPUS_V1 P3).

Hermetic: no network, no PDFs, no live store. The materializer's contracts —
canonical identity, hash-match-or-fail, workbook-sourced lifecycle, and
two-clock selection over the regulatory corpus — are each exercised directly.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from portal.modules.compliance.core.models import SourceDocument
from portal.modules.compliance.core.nerc_source_sync import Artifact, canonical_identity
from portal.modules.compliance.core.repository import Repository
from portal.modules.compliance.core.temporal_selection import select_document_effectivity


class TestCanonicalIdentity:
    @pytest.mark.parametrize(
        ("name", "role", "logical_id", "kind"),
        [
            ("cip-007-6.pdf", "standard", "NERC/CIP-007-6", "regulatory_standard"),
            ("cip-007-7.1.pdf", "standard", "NERC/CIP-007-7.1", "regulatory_standard"),
            # the version's own case is published, not normalised: the register
            # spells it CIP-002-5.1a and 5.1A is a different string
            ("cip-002-5.1a.pdf", "standard", "NERC/CIP-002-5.1a", "regulatory_standard"),
            (
                "cip-007-6-implementation-plan.pdf",
                "implementation_plan",
                "NERC/CIP-007-6 implementation plan",
                "implementation_plan",
            ),
            (
                "cip-007-7.1-technical-rationale.pdf",
                "technical_rationale",
                "NERC/CIP-007-7.1 technical rationale",
                "technical_rationale",
            ),
            ("cip-007-6-rsaw.pdf", "rsaw", "NERC/CIP-007-6 RSAW", "rsaw"),
            ("one-stop-shop.xlsx", "registry", "NERC/one-stop-shop", "lifecycle_registry"),
        ],
    )
    def test_identity_comes_from_the_standard_not_the_filename(
        self, name: str, role: str, logical_id: str, kind: str
    ) -> None:
        got_id, got_kind, _title = canonical_identity(Artifact(name=name, url="", role=role))
        assert got_id == logical_id
        assert got_kind == kind

    def test_a_renamed_file_is_the_same_document(self) -> None:
        a = canonical_identity(Artifact(name="cip-007-6.pdf", url="", role="standard"))
        b = canonical_identity(Artifact(name="cip-007-6.PDF", url="", role="standard"))
        assert a[0] == b[0]

    def test_a_name_with_no_standard_id_keeps_its_own_identity(self) -> None:
        got_id, _kind, _title = canonical_identity(
            Artifact(name="some-guidance.pdf", url="", role="standard")
        )
        assert got_id == "NERC/some-guidance.pdf"


class TestHashMatchOrFail:
    def _manifest(self, tmp_path: Path, *, corrupt: bool) -> Path:
        payload = b"%PDF-1.6 official bytes\n"
        artifact = tmp_path / "cip-007-6.pdf"
        artifact.write_bytes(payload if not corrupt else payload + b"tampered")
        manifest = {
            "ran_at": "2026-09-15T00:00:00Z",
            "family": "CIP-007",
            "artifacts": [
                {
                    "name": "cip-007-6.pdf",
                    "url": "https://example.invalid/cip-007-6.pdf",
                    "role": "standard",
                    "status": "ACQUIRED",
                    "sha256": hashlib.sha256(payload).hexdigest(),
                    "path": str(artifact),
                }
            ],
            "lifecycle": {},
            "warnings": [],
            "store_revisions": {},
        }
        (tmp_path / "acquisition_manifest.json").write_text(json.dumps(manifest))
        return tmp_path

    def test_matching_bytes_pass(self, tmp_path: Path) -> None:
        from portal.modules.compliance.core.nerc_source_sync import load_manifest
        from scripts.materialize_regulatory_corpus import _verify_hashes

        directory = self._manifest(tmp_path, corrupt=False)
        assert len(_verify_hashes(load_manifest(directory))) == 1

    def test_moved_bytes_are_a_hard_failure_not_a_warning(self, tmp_path: Path) -> None:
        from portal.modules.compliance.core.nerc_source_sync import load_manifest
        from scripts.materialize_regulatory_corpus import HashMismatchError, _verify_hashes

        directory = self._manifest(tmp_path, corrupt=True)
        with pytest.raises(HashMismatchError, match="does not match the bytes on disk"):
            _verify_hashes(load_manifest(directory))

    def test_a_missing_file_is_a_hard_failure(self, tmp_path: Path) -> None:
        from portal.modules.compliance.core.nerc_source_sync import load_manifest
        from scripts.materialize_regulatory_corpus import HashMismatchError, _verify_hashes

        directory = self._manifest(tmp_path, corrupt=False)
        (directory / "cip-007-6.pdf").unlink()
        with pytest.raises(HashMismatchError, match="does not exist"):
            _verify_hashes(load_manifest(directory))


def _standard(repo: Repository, version: str, effective: str, inactive: str, status: str) -> None:
    logical_id = f"NERC/CIP-007-{version}"
    repo.upsert_source_document(
        SourceDocument(
            logical_id=logical_id,
            title=f"CIP-007-{version}",
            issuer="NERC",
            source_kind="regulatory_standard",
            jurisdiction="US",
        )
    )
    revision = repo.add_document_revision(
        logical_id, f"/tmp/cip-007-{version}.pdf", f"bytes-{version}".encode()
    )
    repo.set_regulatory_lifecycle(
        revision.revision_id,
        effective_date=effective,
        inactive_date=inactive,
        lifecycle_status=status,
    )


@pytest.fixture
def corpus(tmp_path: Path) -> Repository:
    repo = Repository(tmp_path / "store.db")
    _standard(repo, "6", "2016-07-01", "2028-06-30", "Mandatory Subject to Enforcement")
    _standard(repo, "7.1", "2028-07-01", "", "Subject to Future Enforcement")
    yield repo
    repo.close()


class TestTwoClocksOverTheRegulatoryCorpus:
    def test_today_selects_the_enforceable_revision(self, corpus: Repository) -> None:
        out = select_document_effectivity(corpus._conn, family="CIP-007", valid_at="2026-09-15")
        assert [r["version"] for r in out["selected"]] == ["6"]
        assert [r["version"] for r in out["future"]] == ["7.1"]
        assert out["historical"] == []
        assert out["basis"].startswith("regulatory corpus")

    def test_a_later_valid_at_retires_it_and_selects_the_successor(
        self, corpus: Repository
    ) -> None:
        out = select_document_effectivity(corpus._conn, family="CIP-007", valid_at="2029-01-01")
        assert [r["version"] for r in out["selected"]] == ["7.1"]
        assert [r["version"] for r in out["historical"]] == ["6"]

    def test_before_either_was_effective_both_are_future(self, corpus: Repository) -> None:
        out = select_document_effectivity(corpus._conn, family="CIP-007", valid_at="2010-01-01")
        assert out["selected"] == []
        assert {r["version"] for r in out["future"]} == {"6", "7.1"}

    def test_a_late_recorded_revision_answers_unknown_knowledge(self, corpus: Repository) -> None:
        out = select_document_effectivity(
            corpus._conn, family="CIP-007", valid_at="2026-09-15", known_at="2015-01-01"
        )
        assert out["selected"] == []
        assert {r["version"] for r in out["unknown_knowledge"]} == {"6", "7.1"}

    def test_an_undated_revision_is_never_read_as_always_in_force(self, corpus: Repository) -> None:
        _standard(corpus, "9", "", "", "")
        out = select_document_effectivity(corpus._conn, family="CIP-007", valid_at="2026-09-15")
        assert [r["version"] for r in out["selected"]] == ["6"]
        assert [r["version"] for r in out["undated"]] == ["9"]

    def test_an_internal_document_is_never_selected_as_a_standard(self, corpus: Repository) -> None:
        corpus.upsert_source_document(
            SourceDocument(
                logical_id="NERC/CIP-007-6 internal lookalike",
                title="lookalike",
                issuer="LSPG",
                source_kind="procedure",
                jurisdiction="internal",
            )
        )
        corpus.add_document_revision(
            "NERC/CIP-007-6 internal lookalike", "/tmp/x.pdf", b"lookalike"
        )
        out = select_document_effectivity(corpus._conn, family="CIP-007", valid_at="2026-09-15")
        assert [r["version"] for r in out["selected"]] == ["6"]


class TestLifecycleIsOverwritable:
    def test_a_corrected_retirement_date_lands(self, corpus: Repository) -> None:
        row = corpus._conn.execute(
            "SELECT revision_id FROM document_revisions WHERE logical_id = 'NERC/CIP-007-6'"
        ).fetchone()
        assert corpus.set_regulatory_lifecycle(row[0], inactive_date="2030-01-01") is True
        out = select_document_effectivity(corpus._conn, family="CIP-007", valid_at="2029-01-01")
        assert [r["version"] for r in out["selected"]] == ["6", "7.1"]

    def test_an_empty_argument_never_erases_a_recorded_date(self, corpus: Repository) -> None:
        row = corpus._conn.execute(
            "SELECT revision_id, inactive_date FROM document_revisions "
            "WHERE logical_id = 'NERC/CIP-007-6'"
        ).fetchone()
        corpus.set_regulatory_lifecycle(row[0], lifecycle_status="Inactive")
        after = corpus._conn.execute(
            "SELECT inactive_date FROM document_revisions WHERE revision_id = ?", (row[0],)
        ).fetchone()
        assert after[0] == row[1]
