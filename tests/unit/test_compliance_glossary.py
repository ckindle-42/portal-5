"""The NERC Glossary as a resolvable corpus (BILATERAL_CORPUS_V1 P2).

Hermetic: a miniature ``window._model`` page stands in for the live Glossary, so
parsing, capture, registration and two-clock resolution are all exercised with no
network and no store on disk beyond ``tmp_path``.
"""

from __future__ import annotations

import json

import pytest

from portal.modules.compliance.core import glossary as gl


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
