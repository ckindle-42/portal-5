"""The reading assembly and the addressability surface (BILATERAL_CORPUS_V1 P5).

Hermetic: a miniature standard is captured into a tmp store, so the assembly's
structural selection, its budget behaviour and its refusal to suppress anything
are all checked without PDFs, models or a live index.
"""

from __future__ import annotations

import pytest

from portal.modules.compliance.core import reading_assembly as ra


class TestAddressing:
    @pytest.mark.parametrize(
        ("ref", "standard", "requirement", "part"),
        [
            ("CIP-007-6", "CIP-007-6", "", ""),
            ("CIP-007-6 R2", "CIP-007-6", "2", ""),
            ("CIP-007-6 R2 Part 2.2", "CIP-007-6", "2", "2.2"),
            ("cip-007-7.1 r5 part 5.1.1", "CIP-007-7.1", "5", "5.1.1"),
        ],
    )
    def test_a_regulatory_address_parses(
        self, ref: str, standard: str, requirement: str, part: str
    ) -> None:
        parsed = ra.parse_ref(ref)
        assert parsed is not None
        assert (parsed.standard, parsed.requirement, parsed.part) == (standard, requirement, part)

    def test_an_attachment_address_parses_and_round_trips(self) -> None:
        # A5 (COMPLIANCE_FAMILY_CENSUS_V1 §5): the register carries CIP-002-5.1a's
        # Attachment 1 structure as requirement nodes; the grammar refusing them
        # made the categorisation root unreadable by the sweep.
        for ref in (
            "CIP-002-5.1a Attachment 1 Part 2.3",
            "cip-002-5.1a attachment 1 part 2.3",
        ):
            parsed = ra.parse_ref(ref)
            assert parsed is not None
            assert str(parsed) == "CIP-002-5.1a Attachment 1 Part 2.3"
            assert parsed.attachment == "1"
            assert parsed.part == "2.3"
        section = ra.parse_ref("CIP-002-5.1a Attachment 1 Section 1")
        assert section is not None
        assert str(section) == "CIP-002-5.1a Attachment 1 Section 1"
        assert section.section == "1"

    def test_a_non_address_is_not_forced_into_one(self) -> None:
        assert ra.parse_ref("csection-abc123") is None
        assert ra.parse_ref("ACME Patching Procedure v3") is None
        assert ra.parse_ref("CIP-007-6 Requirement Twenty-Two") is None


class TestEquivalentSpellings:
    """QAT cfe67a16e run 140220Z, s5-compliance-multiframework FAIL: the seat spelled
    the canonical citation in its expanded form — pipeline log 14:43:35Z
    ``compliance_ask error='CIP-007-6 Requirement 2 Part 2.2' is not a regulatory
    address`` — and the tool rejected the address the grader itself required."""

    @pytest.mark.parametrize(
        ("ref", "canonical"),
        [
            ("CIP-007-6 R2 Part 2.2", "CIP-007-6 R2 Part 2.2"),
            # the exact reference the model sent (pipeline log, 14:43:35Z)
            ("CIP-007-6 Requirement 2 Part 2.2", "CIP-007-6 R2 Part 2.2"),
            ("CIP-007-6 requirement 2 part 2.2", "CIP-007-6 R2 Part 2.2"),
            ("CIP-007-6 Requirements 2 Part 2.2", "CIP-007-6 R2 Part 2.2"),
            ("CIP-007-6 Req 2 Part 2.2", "CIP-007-6 R2 Part 2.2"),
            ("CIP-007-6 R 2 Part 2.2", "CIP-007-6 R2 Part 2.2"),
            ("CIP-007-6 R2.2", "CIP-007-6 R2 Part 2.2"),
            ("CIP-007-6 Requirement 2.2", "CIP-007-6 R2 Part 2.2"),
            ("CIP-007 Requirement 2 Part 2.2", "CIP-007 R2 Part 2.2"),
            ("CIP-007 R2.2", "CIP-007 R2 Part 2.2"),
        ],
    )
    def test_one_address_one_canonical_form(self, ref: str, canonical: str) -> None:
        parsed = ra.parse_ref(ref)
        assert parsed is not None
        assert str(parsed) == canonical

    def test_rejection_names_the_accepted_forms(self) -> None:
        rejected = "CIP-007-6 Requirement Twenty-Two"
        message = ra.not_an_address(rejected)
        assert message.startswith(f"{rejected!r} is not a regulatory address")
        assert "CIP-007-6 R2 Part 2.2" in message
        assert "CIP-007-6 Requirement 2 Part 2.2" in message
        assert "CIP-007-6 R2.2" in message
        # assemble surfaces the same message, and parse failure never touches the repo
        out = ra.assemble(object(), rejected)
        assert out["error"] == message
        conflicts = ra.conflicts_for_requirement(object(), rejected)
        assert conflicts["error"] == message


class TestCanonicalStandard:
    """A versionless address ("CIP-007 R2 Part 2.2") resolves against the store."""

    @staticmethod
    def _repo() -> object:
        import sqlite3

        conn = sqlite3.connect(":memory:")
        conn.execute(
            "CREATE TABLE document_revisions "
            "(logical_id TEXT, effective_date TEXT, inactive_date TEXT)"
        )
        conn.executemany(
            "INSERT INTO document_revisions VALUES (?,?,?)",
            [
                ("NERC/CIP-007-5", "2020-01-01", "2024-06-30"),
                ("NERC/CIP-007-6", "2024-07-01", None),
                # companion documents are not versions of the standard
                ("NERC/CIP-007-6 implementation plan", "2024-07-01", None),
            ],
        )

        class _Repo:
            _conn = conn

        return _Repo()

    def test_versionless_resolves_to_the_version_in_force(self) -> None:
        repo = self._repo()
        assert ra.canonical_standard(repo, "CIP-007") == "CIP-007-6"
        assert ra.canonical_standard(repo, "CIP-007", "2021-01-01") == "CIP-007-5"
        parsed = ra.parse_ref("CIP-007 Requirement 2 Part 2.2")
        assert parsed is not None
        assert str(ra.canonical_ref(repo, parsed)) == "CIP-007-6 R2 Part 2.2"

    def test_versioned_unknown_and_unstored_pass_through(self) -> None:
        repo = self._repo()
        assert ra.canonical_standard(repo, "CIP-007-5") == "CIP-007-5"
        assert ra.canonical_standard(repo, "CIP-002") == "CIP-002"
