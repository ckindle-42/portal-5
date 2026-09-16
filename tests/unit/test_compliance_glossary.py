"""The NERC Glossary as a resolvable corpus (BILATERAL_CORPUS_V1 P2).

Hermetic: a miniature ``window._model`` page stands in for the live Glossary, so
parsing, capture, registration and two-clock resolution are all exercised with no
network and no store on disk beyond ``tmp_path``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from portal.modules.compliance.core import glossary as gl
from portal.modules.compliance.core.repository import Repository


def _page(records: list[dict]) -> bytes:
    model = {"pageModel": {"searchResults": {"items": records}}}
    return (
        "<!DOCTYPE html><html><head><script>\n"
        "        window._model = " + json.dumps(model) + ";\n"
        "</script></head><body></body></html>"
    ).encode()


def _record(term: str, definition: str, **kw: object) -> dict:
    base = {
        "term": term,
        "definitionHtml": definition,
        "acronym": None,
        "acronymHtml": None,
        "footnoteHtml": None,
        "status": "Subject to Enforcement",
        "region": "Continent-wide Term",
        "docketNumber": "RM13-5-000",
        "botAdoptionDate": "2013-02-07T05:00:00+00:00",
        "effectiveDate": "2016-07-01T04:00:00+00:00",
        "inactiveDate": None,
    }
    base.update(kw)
    return base


RECORDS = [
    _record(
        "BES Cyber System",
        "One or more <b>BES Cyber Assets</b> logically grouped&nbsp;by a responsible entity.",
    ),
    _record(
        "Electronic Access Control or Monitoring Systems",
        "Cyber Assets that perform electronic access control.",
        acronym="EACMS",
    ),
    _record(
        "Protected Cyber Assets",
        "One or more Cyber Assets connected using a routable protocol.",
        acronym="PCA",
        inactiveDate="2028-06-30T04:00:00+00:00",
    ),
    _record(
        "Protected Cyber Asset",
        "One or more Cyber Assets or Virtual Cyber Assets that are protected.",
        acronym="PCA",
        status="Subject to Future Enforcement",
        effectiveDate="2028-07-01T04:00:00+00:00",
    ),
    _record("CIP Senior Manager", "A single senior management official."),
]


@pytest.fixture
def page() -> bytes:
    return _page(RECORDS)


@pytest.fixture
def repo(tmp_path: Path, page: bytes) -> Repository:
    store = Repository(tmp_path / "store.db")
    artifact = tmp_path / gl.GLOSSARY_ARTIFACT
    artifact.write_bytes(page)
    gl.write_term_dates(tmp_path, gl.parse_glossary(page))
    gl.register_glossary(store, page, str(artifact))
    yield store
    store.close()


class TestParsing:
    def test_every_term_is_parsed(self, page: bytes) -> None:
        assert len(gl.parse_glossary(page)) == len(RECORDS)

    def test_the_definition_is_verbatim_text_not_markup(self, page: bytes) -> None:
        term = next(t for t in gl.parse_glossary(page) if t.term == "BES Cyber System")
        assert term.definition == (
            "One or more BES Cyber Assets logically grouped by a responsible entity."
        )

    def test_dates_are_iso_days(self, page: bytes) -> None:
        term = next(t for t in gl.parse_glossary(page) if t.term == "Protected Cyber Assets")
        assert term.effective_date == "2016-07-01"
        assert term.inactive_date == "2028-06-30"

    def test_a_page_without_term_records_fails_loudly(self) -> None:
        with pytest.raises(ValueError, match="no term records"):
            gl.parse_glossary(_page([]))

    def test_a_page_without_a_model_fails_loudly(self) -> None:
        with pytest.raises(ValueError, match="no window._model"):
            gl.parse_glossary(b"<html>nothing here</html>")

    def test_records_are_found_by_shape_not_by_path(self) -> None:
        moved = json.dumps({"someOtherPlace": {"deeper": {"rows": RECORDS}}})
        payload = ("<script>window._model = " + moved + ";</script>").encode()
        assert len(gl.parse_glossary(payload)) == len(RECORDS)


class TestRegistration:
    def test_the_glossary_is_a_document_with_a_section_per_term(self, repo: Repository) -> None:
        row = repo._conn.execute(
            "SELECT source_kind, jurisdiction FROM source_documents WHERE logical_id = ?",
            (gl.GLOSSARY_LOGICAL_ID,),
        ).fetchone()
        assert tuple(row) == ("glossary", "US")
        count = repo._conn.execute(
            "SELECT count(*) FROM source_sections WHERE extractor = ?", (gl.EXTRACTOR,)
        ).fetchone()[0]
        assert count == len(RECORDS)

    def test_registration_is_idempotent_on_identical_bytes(
        self, repo: Repository, tmp_path: Path, page: bytes
    ) -> None:
        before = repo._conn.execute("SELECT count(*) FROM document_revisions").fetchone()[0]
        gl.register_glossary(repo, page, str(tmp_path / gl.GLOSSARY_ARTIFACT))
        after = repo._conn.execute("SELECT count(*) FROM document_revisions").fetchone()[0]
        assert before == after


class TestResolution:
    @pytest.mark.parametrize(
        ("query", "headword"),
        [
            ("BES Cyber System", "BES Cyber System"),
            ("EACMS", "Electronic Access Control or Monitoring Systems"),
            ("CIP Senior Manager", "CIP Senior Manager"),
            # the headword is plural; a requirement written in the singular
            # must still reach its own definition
            ("Protected Cyber Asset", "Protected Cyber Assets"),
        ],
    )
    def test_a_term_resolves_with_verbatim_text_and_a_date(
        self, repo: Repository, query: str, headword: str
    ) -> None:
        (result,) = gl.resolve_terms(repo, [query], valid_at="2026-09-15")
        assert result["resolved"] is True
        assert result["matched_as"] == headword
        assert result["definition"]
        assert result["effective_date"] == "2016-07-01"
        assert result["section_id"]

    def test_an_invented_term_does_not_resolve(self, repo: Repository) -> None:
        (result,) = gl.resolve_terms(repo, ["Frobnicating Widget Authority"])
        assert result["resolved"] is False
        assert result["definition"] == ""
        assert result["detail"] == "not a NERC Glossary term"
        assert result["term"] == "Frobnicating Widget Authority"

    def test_an_unregistered_glossary_says_so_rather_than_being_empty(self, tmp_path: Path) -> None:
        bare = Repository(tmp_path / "bare.db")
        try:
            (result,) = gl.resolve_terms(bare, ["BES Cyber System"])
            assert result["resolved"] is False
            assert "not registered" in result["detail"]
        finally:
            bare.close()


class TestBothClocks:
    def test_today_selects_the_enforceable_revision_not_its_successor(
        self, repo: Repository
    ) -> None:
        (result,) = gl.resolve_terms(repo, ["PCA"], valid_at="2026-09-15")
        assert result["matched_as"] == "Protected Cyber Assets"
        assert result["inactive_date"] == "2028-06-30"

    def test_a_later_valid_at_selects_the_successor(self, repo: Repository) -> None:
        (result,) = gl.resolve_terms(repo, ["PCA"], valid_at="2029-01-01")
        assert result["resolved"] is True
        assert result["matched_as"] == "Protected Cyber Asset"
        assert result["effective_date"] == "2028-07-01"

    def test_the_other_revision_is_named_not_hidden(self, repo: Repository) -> None:
        (result,) = gl.resolve_terms(repo, ["PCA"], valid_at="2026-09-15")
        assert [r["term"] for r in result["other_revisions"]] == ["Protected Cyber Asset"]

    def test_a_term_not_yet_effective_is_labelled_not_served(self, repo: Repository) -> None:
        (result,) = gl.resolve_terms(repo, ["BES Cyber System"], valid_at="2010-01-01")
        assert result["resolved"] is False
        assert "not effective at 2010-01-01" in result["detail"]
        # still returned, with the text, so the reader can see what it is
        assert result["definition"]


class TestAmbiguityIsNeverGuessed:
    def test_an_acronym_shared_by_two_terms_is_not_indexed(self, tmp_path: Path) -> None:
        records = [
            _record("Alpha Beta Gamma", "first", acronym="ABG"),
            _record("Another Big Grouping", "second", acronym="ABG"),
        ]
        payload = _page(records)
        store = Repository(tmp_path / "amb.db")
        try:
            artifact = tmp_path / gl.GLOSSARY_ARTIFACT
            artifact.write_bytes(payload)
            gl.write_term_dates(tmp_path, gl.parse_glossary(payload))
            gl.register_glossary(store, payload, str(artifact))
            (result,) = gl.resolve_terms(store, ["ABG"])
            assert result["resolved"] is False
        finally:
            store.close()


class TestDeferralIsResolved:
    def test_a_bundle_deferring_to_the_glossary_carries_its_terms(self, repo: Repository) -> None:
        duty = (
            "Each Responsible Entity shall implement a process that applies to each "
            "BES Cyber System and its associated EACMS and Protected Cyber Asset."
        )
        out = gl.resolve_bundle_definitions(repo, duty, valid_at="2026-09-15")
        assert out["disposition"] == "external_glossary"
        assert out["glossary_registered"] is True
        names = {t["matched_as"] for t in out["terms"]}
        assert "BES Cyber System" in names
        assert "Electronic Access Control or Monitoring Systems" in names
        assert "Protected Cyber Assets" in names
        assert out["unresolved"] == []

    def test_term_membership_is_decided_by_the_glossary_not_by_capitalisation(
        self, repo: Repository
    ) -> None:
        index = gl.glossary_index(repo)
        found = gl.terms_in("The Responsible Entity shall patch each BES Cyber System.", index)
        assert found == ["BES Cyber System"]
