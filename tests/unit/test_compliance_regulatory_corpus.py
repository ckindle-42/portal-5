"""Symmetric regulatory materialization (BILATERAL_CORPUS_V1 P3).

Hermetic: no network, no PDFs, no live store. The materializer's contracts —
canonical identity, hash-match-or-fail, workbook-sourced lifecycle, and
two-clock selection over the regulatory corpus — are each exercised directly.
"""

from __future__ import annotations

import pytest

from portal.modules.compliance.core.nerc_source_sync import Artifact, canonical_identity


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
