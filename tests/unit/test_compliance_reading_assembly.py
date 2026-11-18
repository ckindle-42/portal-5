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
