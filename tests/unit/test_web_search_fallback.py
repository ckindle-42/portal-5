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


class TestSearchFallbackOrder:
    async def _run(self, monkeypatch, primary, searxng, brave, key="k"):
        monkeypatch.setattr(m, "WEB_SEARCH_PRIMARY", primary)
        monkeypatch.setattr(m, "BRAVE_API_KEY", key)

        async def _sx(*a, **k):
            return list(searxng)

        async def _bv(*a, **k):
            return list(brave)

        monkeypatch.setattr(m, "_searxng_search", _sx)
        monkeypatch.setattr(m, "_brave_search", _bv)
        return await m._search_with_fallback("q", 4)

    async def test_brave_primary_uses_brave(self, monkeypatch):
        good = [_r("https://x.com/deep", "a real answer snippet that is quite long indeed")]
        out = await self._run(monkeypatch, "brave", searxng=[_r("https://y.com/")], brave=good)
        assert out == good

    async def test_falls_back_when_primary_weak(self, monkeypatch):
        good = [_r("https://x.com/deep", "a real answer snippet that is quite long indeed")]
        out = await self._run(monkeypatch, "searxng", searxng=[_r("https://iso.org/")], brave=good)
        assert out == good

    async def test_no_brave_key_stays_on_searxng(self, monkeypatch):
        sx = [_r("https://iso.org/")]  # weak, but no key -> best-effort return
        out = await self._run(monkeypatch, "searxng", searxng=sx, brave=[], key="")
        assert out == sx

    async def test_primary_good_result_wins_without_fallback(self, monkeypatch):
        good = [_r("https://x.com/deep", "long substantive snippet answering the question")]
        called = {"brave": False}

        async def _bv(*a, **k):
            called["brave"] = True
            return []

        monkeypatch.setattr(m, "WEB_SEARCH_PRIMARY", "searxng")
        monkeypatch.setattr(m, "BRAVE_API_KEY", "k")
        monkeypatch.setattr(m, "_brave_search", _bv)

        async def _sx(*a, **k):
            return list(good)

        monkeypatch.setattr(m, "_searxng_search", _sx)
        out = await m._search_with_fallback("q", 4)
        assert out == good
        assert called["brave"] is False


class TestSearchCache:
    def _reset(self, m):
        m._search_cache.clear()

    async def test_repeat_query_served_from_cache(self, monkeypatch):
        m.WEB_SEARCH_PRIMARY  # noqa
        monkeypatch.setattr(m, "WEB_SEARCH_PRIMARY", "searxng")
        monkeypatch.setattr(m, "BRAVE_API_KEY", "")
        self._reset(m)
        calls = {"n": 0}
        good = [_r("https://x.com/deep", "a substantive snippet long enough to count as real")]

        async def _sx(*a, **k):
            calls["n"] += 1
            return list(good)

        monkeypatch.setattr(m, "_searxng_search", _sx)
        a = await m._search_with_fallback("ISO 27001 controls", 4)
        b = await m._search_with_fallback("  iso 27001 CONTROLS ", 4)  # normalized key
        assert a == b == good
        assert calls["n"] == 1  # second call hit the cache

    async def test_empty_result_not_cached(self, monkeypatch):
        monkeypatch.setattr(m, "WEB_SEARCH_PRIMARY", "searxng")
        monkeypatch.setattr(m, "BRAVE_API_KEY", "")
        self._reset(m)
        calls = {"n": 0}

        async def _sx(*a, **k):
            calls["n"] += 1
            return []

        monkeypatch.setattr(m, "_searxng_search", _sx)
        await m._search_with_fallback("nothing", 4)
        await m._search_with_fallback("nothing", 4)
        assert calls["n"] == 2  # empty never cached

    def test_cache_ttl_expiry(self, monkeypatch):
        self._reset(m)
        monkeypatch.setattr(m, "_SEARCH_CACHE_TTL_S", 0)
        m._cache_put(("q", 4, "any", "general"), [_r("https://x.com/a", "s" * 50)])
        assert m._cache_get(("q", 4, "any", "general")) is None

    def test_cache_bound_evicts_oldest(self, monkeypatch):
        self._reset(m)
        monkeypatch.setattr(m, "_SEARCH_CACHE_MAX", 2)
        for i in range(3):
            m._cache_put((f"q{i}", 4, "any", "general"), [_r(f"https://x/{i}", "s" * 50)])
        assert len(m._search_cache) == 2
        assert ("q0", 4, "any", "general") not in m._search_cache
