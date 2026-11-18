"""The requirement → section join (ONE_REGULATORY_EXTRACTION_V1 P1/P2).

The defect these tests pin is an ABSENCE: `RegisterNode` carried no
`section_id`, `source_sections` carried no requirement reference, and the only
overlap was `source_pdf` + `source_pages` — page granularity, where a page holds
many sections and a Part spans pages. So "the sections constituting R2 Part 2.2"
was not a question the store could answer.

Two things must hold for the fix to be worth having. The anchor must be **exact**
— a fuzzy join produces citations that look correct, cannot be checked
afterwards, and get built on — and it must leave the capture **untouched**,
because `assert_faithful` raises on overlapping spans and a `table_row` already
carries the requirement text, the applicable-systems column and the Measures
column as one unit.
"""

from __future__ import annotations

import pytest

from portal.modules.compliance.core import requirement_anchor as ra


class TestNormalisationIsLicensedOnly:
    @pytest.mark.parametrize(
        "rendered",
        [
            "A dated mitigation plan – the entity’s planned actions — and a timeframe",
            "A dated mitigation plan - the entity's planned actions - and a timeframe",
            "A dated mitigation plan - the entity's planned actions - and a timeframe",
            "A dated miti­gation plan - the entity's planned actions - and a timeframe",
        ],
    )
    def test_a_rendering_difference_still_anchors(self, rendered: str) -> None:
        canonical = "A dated mitigation plan - the entity's planned actions - and a timeframe"
        assert ra.normalise(rendered) == ra.normalise(canonical)

    def test_the_pua_bullet_reconciles_with_the_hyphen_pymupdf_renders(self) -> None:
        captured = "take one of the following actions:  Apply the applicable patches"
        register = "take one of the following actions: - Apply the applicable patches"
        assert ra.normalise(captured) == ra.normalise(register)

    def test_the_two_readers_quote_marks_fold_to_one_form(self) -> None:
        # the same glyph in the PDF: pymupdf gives U+201C/U+201D, docling ASCII "'"
        register = "systems identified in the \u201cApplicable Systems\u201d column"
        captured = "systems identified in the 'Applicable Systems' column"
        assert ra.normalise(register) == ra.normalise(captured)

    def test_a_list_bullet_the_capture_folded_into_structure_is_dropped(self) -> None:
        # docling makes the unit a list_item and drops the marker glyph
        register = "shall be performed: \u2022 At least once every 30 calendar months"
        captured = "shall be performed: At least once every 30 calendar months"
        assert ra.normalise(register) == ra.normalise(captured)

    def test_the_ligature_is_licensed(self) -> None:
        assert ra.normalise("conﬁrm the conﬂict") == ra.normalise("confirm the conflict")
