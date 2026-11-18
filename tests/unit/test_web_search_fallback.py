"""web_search_mcp backend-selection logic — weak-result detection + fallback
ordering. No network: _searxng_search / _brave_search are monkeypatched."""

from __future__ import annotations

import pytest

from portal.modules.research.tools import web_search_mcp as m


@pytest.fixture(autouse=True)
def _clear_search_cache():
    m._search_cache.clear()
    yield
    m._search_cache.clear()


def _r(url, snippet=""):
    return {"title": "t", "url": url, "snippet": snippet, "engine": "x", "published": ""}


class TestResultsAreWeak:
    def test_empty_is_weak(self):
        assert m._results_are_weak([]) is True

    def test_all_root_urls_is_weak(self):
        assert m._results_are_weak(
            [_r("https://iso.org/", "x" * 60), _r("https://nerc.com/", "y" * 60)]
        )

    def test_no_snippets_is_weak(self):
        assert m._results_are_weak([_r("https://a.com/page1"), _r("https://b.com/page2")])

    def test_wikipedia_and_root_dominated_is_weak(self):
        assert m._results_are_weak(
            [
                _r("https://en.wikipedia.org/wiki/ISO", "s" * 60),
                _r("https://iso.org/", "s" * 60),
                _r("https://nerc.com/", "s" * 60),
            ]
        )

    def test_substantive_results_not_weak(self):
        assert not m._results_are_weak(
            [
                _r(
                    "https://hightable.io/iso-27001-annex-a",
                    "Explore the 93 controls in ISO 27001:2022",
                ),
                _r(
                    "https://isms.online/annex-a",
                    "The Annex A controls are organised under four themes",
                ),
            ]
        )
