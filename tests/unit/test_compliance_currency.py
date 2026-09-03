"""T3 Phase 8 — the currency probe. Currency is never inferred; honest-BLOCKED
when nerc.com is unreachable.
"""

from __future__ import annotations

import urllib.error
import urllib.request

import pytest

from portal.modules.compliance.core.currency import _next_versions, nerc_currency


def _online() -> bool:
    try:
        urllib.request.urlopen("https://www.nerc.com/", timeout=5)  # noqa: S310
        return True
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def test_next_versions_enumerates_candidate_stems():
    assert _next_versions("CIP-007-6") == ["cip-007-7", "cip-007-8"]
    assert _next_versions("CIP-002-5.1a") == ["cip-002-6", "cip-002-7"]
    assert _next_versions("not-a-standard") == []


def test_currency_never_infers_an_enforcement_date():
    if not _online():
        pytest.skip("offline — currency probe is honest-BLOCKED, nothing to assert")
    r = nerc_currency()
    assert r["status"] in ("ok", "honest-BLOCKED")
    if r["status"] == "honest-BLOCKED":
        assert "never inferred" in r["reason"] or "unreachable" in r["reason"]
        return
    for p in r["per_standard"]:
        # no probe result is ever presented AS an enforcement date
        assert "verify" in p["enforcement_date"].lower()
        assert "do not infer" in p["enforcement_date"].lower()


def test_currency_blocked_when_unreachable(monkeypatch):
    from portal.modules.compliance.core import currency as cur

    monkeypatch.setattr(cur, "_pdf_exists", lambda name: None)
    r = nerc_currency()
    assert r["status"] == "honest-BLOCKED"
    assert "never inferred" in r["reason"]
