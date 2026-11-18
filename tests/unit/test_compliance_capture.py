"""Fidelity gates for whole-document capture (BILATERAL_CORPUS_V1 P1).

These are hermetic: a stub layout document stands in for docling, so the gates
run with no network, no models and no PDFs. The same gates run against the real
regulatory PDFs in ``scripts/verify_compliance_bilateral.py --live``.
"""

from __future__ import annotations

from portal.modules.compliance.core import capture as cap


class TestPositionalOnly:
    def test_role_is_a_positional_fact(self) -> None:
        assert (
            cap.positional_role("B. Requirements and Measures > R2")
            == "B_REQUIREMENTS_AND_MEASURES"
        )
        assert cap.positional_role("") == "FRONT_MATTER"


class TestInternalCorpusTilesCompletely:
    def test_sectionize_leaves_no_gap(self) -> None:
        from portal.modules.compliance.core.internal_corpus import sectionize

        pages = [
            "ACME Procedure\nDocument Type: Procedure\n",
            "Table of Contents\n1.0 Purpose ...... 3\n2.0 Scope ...... 4\n",
            "trailing text nobody gave a heading\n1.0 Purpose\nThe purpose is to do the thing.\n",
            "2.0 Scope\nApplies to everything.\ntail matter after the last heading\n",
        ]
        full = "\n".join(pages)
        sections = sectionize(pages, operative_role="OPERATIVE_PROCEDURE")
        cursor = 0
        for section in sorted(sections, key=lambda s: s.char_start):
            assert section.char_start == cursor, f"gap or overlap at {section.path}"
            assert section.text == full[section.char_start : section.char_end]
            cursor = section.char_end
        assert cursor == len(full)

    def test_the_table_of_contents_no_longer_hides_the_cover_block(self) -> None:
        from portal.modules.compliance.core.internal_corpus import sectionize

        pages = ["cover\n", "Table of Contents\n1.0 x ... 3\n", "1.0 Purpose\nbody\n"]
        sections = sectionize(pages, operative_role="OPERATIVE_PROCEDURE")
        roles = [s.role for s in sorted(sections, key=lambda s: s.char_start)]
        assert roles[0] == "DOCUMENT_CONTROL"
        assert "TABLE_OF_CONTENTS" in roles
