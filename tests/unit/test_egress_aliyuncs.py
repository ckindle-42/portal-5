"""Unit test: aliyuncs.com suffix block in web_fetch and browser URL gates."""

import os

os.environ.setdefault("PROFILES_DIR", "/tmp/test_profiles_egress")
os.environ.setdefault("AUDIT_LOG_PATH", "/tmp/test_profiles_egress/audit.log")

from portal.modules.research.tools import browser_mcp as browser
from portal.modules.research.tools import web_search_mcp as web_search


class TestAliyuncsBlockWebFetch:
    async def test_aliyuncs_subdomain_blocked(self):
        # x.oss-cn-hangzhou.aliyuncs.com must be blocked
        result = await web_search._fetch_payload("https://x.oss-cn-hangzhou.aliyuncs.com/file", 100)
        assert "aliyuncs.com" in result.get("error", "")

    async def test_aliyuncs_domain_blocked(self):
        result = await web_search._fetch_payload("https://aliyuncs.com/", 100)
        assert "aliyuncs.com" in result.get("error", "")

    async def test_not_aliyuncs_allowed(self, monkeypatch):
        # notaliyuncs.com must NOT trigger the suffix block.
        # Stub httpx so we don't make a live request.
        class FakeResponse:
            status_code = 200
            url = "https://notaliyuncs.com/"
            headers = {"content-type": "text/html"}
            content = b"<html></html>"

        async def _fake_get(self, url, **kwargs):
            return FakeResponse()

        monkeypatch.setattr(
            "portal.modules.research.tools.web_search_mcp.httpx.AsyncClient.get", _fake_get
        )
        result = await web_search._fetch_payload("https://notaliyuncs.com/", 100)
        assert "aliyuncs.com" not in result.get("error", "")

    async def test_example_com_allowed(self, monkeypatch):
        # Must not mention aliyuncs; prevent live network call by stubbing httpx.
        class FakeResponse:
            status_code = 200
            url = "https://example.com/"
            headers = {"content-type": "text/html"}
            content = b"<html><body>hello</body></html>"

        async def _fake_get(self, url, **kwargs):
            return FakeResponse()

        monkeypatch.setattr(
            "portal.modules.research.tools.web_search_mcp.httpx.AsyncClient.get", _fake_get
        )
        result = await web_search._fetch_payload("https://example.com/", 100)
        assert "aliyuncs.com" not in result.get("error", "")
        assert result.get("status_code") == 200


class TestAliyuncsBlockBrowser:
    def test_browser_subdomain_blocked(self):
        ok, why = browser._validate_url("https://x.oss-cn-hangzhou.aliyuncs.com/file")
        assert not ok
        assert "aliyuncs" in why

    def test_browser_domain_blocked(self):
        ok, why = browser._validate_url("https://aliyuncs.com/")
        assert not ok
        assert "aliyuncs" in why

    def test_browser_not_aliyuncs_allowed(self):
        ok, why = browser._validate_url("https://notaliyuncs.com/")
        # Should not be blocked by the suffix rule; allowed unless other rules apply
        assert ok or "aliyuncs" not in why

    def test_browser_example_com_allowed(self):
        ok, why = browser._validate_url("https://example.com/")
        assert ok
