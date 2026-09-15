"""Complete regulatory bundle extraction and readiness (foundation P3).

Positive paths run against the pinned official CIP-007-6 / CIP-007-7.1
revisions (hash-prefixed against the register, skipped when the corpus is not
fetched locally). Every required component also gets a negative case proving
readiness can fail — the defect budget of the extractor is a named
``U14_INCOMPLETE_SOURCE_BUNDLE`` component list, never a silent empty string.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from portal.modules.compliance.core.regulatory_bundle import (
    U14_INCOMPLETE_SOURCE_BUNDLE,
    extract_revision_bundle,
    part_bundle,
    readiness_failures,
    required_components,
    verify_bundle_spans,
)

_PDF_DIR = Path(__file__).resolve().parents[2] / "portal/modules/compliance/data"
CIP007_6 = _PDF_DIR / "cip_pdfs" / "cip-007-6.pdf"
CIP007_71 = _PDF_DIR / "private" / "nerc_official" / "cip-007-7.1.pdf"

needs = pytest.mark.skipif(not CIP007_6.is_file(), reason="NERC CIP PDF corpus not fetched locally")
needs_71 = pytest.mark.skipif(
    not CIP007_71.is_file(), reason="official CIP-007-7.1 PDF not synced locally"
)


@pytest.fixture(scope="module")
def bundle6():
    return extract_revision_bundle(CIP007_6)


@needs
class TestCIP0076Extraction:
    def test_revision_identity_is_the_bytes_hash(self, bundle6):
        assert bundle6.standard == "CIP-007" and bundle6.version == "6"
        assert bundle6.source_sha256 == hashlib.sha256(CIP007_6.read_bytes()).hexdigest()

    def test_mixed_fingerprint_is_refused(self):
        with pytest.raises(ValueError, match="source revision mismatch"):
            extract_revision_bundle(CIP007_6, expected_sha256="0" * 64)

    def test_r2_table_components_extracted(self, bundle6):
        pb = part_bundle(bundle6, "R2", "2.2")
        assert pb["shape"] == "table"
        assert pb["lead_in"].startswith("Each Responsible Entity shall implement")
        assert pb["part_text"].startswith("At least once every 35 calendar days")
        assert "High Impact BES Cyber Systems" in pb["applicable_systems"]
        assert len(pb["measures"]) == 2  # Measures column + M2 lead-in
        assert all(m["role"] == "MEASURE" for m in pb["measures"])

    def test_technical_basis_spans_are_nonbinding_context(self, bundle6):
        pb = part_bundle(bundle6, "R2", "2.3")
        assert pb["technical_basis_section"] == "present"
        texts = [t["text"] for t in pb["technical_basis"]]
        assert any("intent of Requirement R2" in t for t in texts)
        assert all(t["role"] == "TECHNICAL_BASIS" for t in pb["technical_basis"])
        # Technical Basis is context — never concatenated into the duty text
        assert all(pb["part_text"] != t for t in texts)

    def test_definitions_are_explicit_not_placeholder(self, bundle6):
        pb = part_bundle(bundle6, "R2", "2.1")
        # CIP-007 defers defined terms to the NERC Glossary — recorded, never
        # a fabricated body
        assert pb["definitions_disposition"] == "external_glossary"
        assert all(
            "Canonical NERC defined term" not in d.get("body", "") for d in pb["definitions"]
        )

    def test_every_span_hash_verifies_against_the_revision(self, bundle6):
        assert verify_bundle_spans(bundle6) == []

    def test_r2_1_through_r2_4_bundles_are_ready(self, bundle6):
        for part in ("2.1", "2.2", "2.3", "2.4"):
            pb = part_bundle(bundle6, "R2", part)
            assert readiness_failures(pb) == [], part


@needs_71
class TestCIP00771Extraction:
    def test_future_revision_extracts_completely(self):
        bundle = extract_revision_bundle(CIP007_71)
        assert bundle.standard == "CIP-007" and bundle.version == "7.1"
        assert bundle.source_sha256 == hashlib.sha256(CIP007_71.read_bytes()).hexdigest()
        for part in ("2.1", "2.2", "2.3", "2.4"):
            pb = part_bundle(bundle, "R2", part)
            assert readiness_failures(pb) == [], part

    def test_absent_technical_basis_section_is_a_recorded_shape_fact(self):
        bundle = extract_revision_bundle(CIP007_71)
        # the 2024 edition carries no Guidelines and Technical Basis section;
        # absence is recorded, and readiness does not demand the unshapeable
        assert bundle.technical_basis_section == "absent"

    def test_span_verification_refuses_foreign_bytes(self):
        bundle = extract_revision_bundle(CIP007_71)
        foreign = CIP007_71.read_bytes() + b"\x00"
        with pytest.raises(ValueError, match="not the pinned revision"):
            verify_bundle_spans(bundle, source=foreign)


class TestReadinessNegatives:
    """Each required component can fail readiness with a named U14 entry."""

    @pytest.fixture(autouse=True)
    def _bundle(self, bundle6):
        self.bundle6 = bundle6

    def _table_pb(self, part="2.2"):
        return part_bundle(self.bundle6, "R2", part)

    @needs
    def test_missing_lead_in_fails(self):
        pb = self._table_pb()
        pb["lead_in"] = ""
        assert any(f["component"] == "lead_in" for f in readiness_failures(pb))

    @needs
    def test_missing_part_text_fails(self):
        pb = self._table_pb()
        pb["part_text"] = ""
        assert any(f["component"] == "part_text" for f in readiness_failures(pb))

    @needs
    def test_truncated_measures_fail(self):
        pb = self._table_pb()
        pb["measures"] = [{"text": "An example", "role": "MEASURE"}]
        failures = readiness_failures(pb)
        assert any(f["component"] == "measures" and "truncated" in f["detail"] for f in failures)

    @needs
    def test_missing_measures_fail(self):
        pb = self._table_pb()
        pb["measures"] = []
        assert any(f["component"] == "measures" for f in readiness_failures(pb))

    @needs
    def test_missing_applicable_systems_fails(self):
        pb = self._table_pb()
        pb["applicable_systems"] = ""
        assert any(f["component"] == "applicable_systems" for f in readiness_failures(pb))

    @needs
    def test_truncated_technical_basis_fails_when_section_present(self):
        pb = self._table_pb()
        assert pb["technical_basis_section"] == "present"
        pb["technical_basis"] = []
        pb["technical_basis_parts"] = []
        pb["technical_basis_rationale"] = []
        failures = readiness_failures(pb)
        assert any(f["component"] == "technical_basis" for f in failures)

    @needs
    def test_unrecorded_technical_basis_fact_fails(self):
        pb = self._table_pb()
        pb["technical_basis_section"] = ""
        assert any(f["component"] == "technical_basis" for f in readiness_failures(pb))

    @needs
    def test_unresolved_definitions_disposition_fails(self):
        pb = self._table_pb()
        pb["definitions_disposition"] = ""
        failures = readiness_failures(pb)
        assert any(
            f["component"] == "definitions_disposition"
            and f["code"] == U14_INCOMPLETE_SOURCE_BUNDLE
            for f in failures
        )

    @needs
    def test_inverted_span_offsets_fail(self):
        pb = self._table_pb()
        span = dict(pb["technical_basis"][0])
        span["doc_char_start"], span["doc_char_end"] = 10, 10
        pb["technical_basis"] = [span]
        assert any(f["component"] == "span_offsets" for f in readiness_failures(pb))

    @needs
    def test_unpinned_revision_fails(self):
        pb = self._table_pb()
        pb["revision_id"] = ""
        assert any(f["component"] == "revision_id" for f in readiness_failures(pb))

    @needs
    def test_every_failure_carries_the_u14_code(self):
        pb = self._table_pb()
        pb.update(
            lead_in="",
            part_text="",
            applicable_systems="",
            measures=[],
            technical_basis=[],
            technical_basis_parts=[],
            technical_basis_section="",
            definitions_disposition="",
            revision_id="",
        )
        failures = readiness_failures(pb)
        assert len(failures) >= 7
        assert all(f["code"] == U14_INCOMPLETE_SOURCE_BUNDLE for f in failures)

    @needs
    def test_decomposition_defects_surface_in_readiness(self):
        from portal.modules.compliance.core.obligations import decompose

        pb = self._table_pb()
        atoms = decompose(pb["ref"], pb["part_text"])
        forged = {"kind": "ANY_OF", "children": []}
        failures = readiness_failures(pb, atoms=atoms, expression=forged, text=pb["part_text"])
        assert any(f["component"] == "decomposition" for f in failures)


def test_attachment_shape_requires_only_its_own_components():
    required = required_components("attachment")
    assert "part_text" in required
    assert "measures" not in required and "technical_basis" not in required
    failures = readiness_failures(
        {
            "shape": "attachment",
            "ref": "CIP-002-5.1a Attachment 1 Part 1.1",
            "part_text": "Criterion text",
            "definitions_disposition": "external_glossary",
            "revision_id": "abc123",
        }
    )
    assert failures == []
