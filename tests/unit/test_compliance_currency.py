"""T3 Phase 8 — the currency probe. Currency is never inferred; honest-BLOCKED
when nerc.com is unreachable.
"""

from __future__ import annotations

import urllib.error
import urllib.request

import pytest

from portal.modules.compliance.core.currency import (
    _next_versions,
    discover_new_families,
    nerc_currency,
)


def _online() -> bool:
    try:
        urllib.request.urlopen("https://www.nerc.com/", timeout=5)  # noqa: S310
        return True
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def test_next_versions_enumerates_candidate_stems_including_decimal_errata():
    """F02: the prior version of this function checked only the next two
    INTEGER versions and could never discover a decimal/errata revision of
    the SAME major version (the design doc's real example: CIP-006-7.1)."""
    assert _next_versions("CIP-007-6") == ["cip-007-6.1", "cip-007-7", "cip-007-7.1", "cip-007-8"]
    assert _next_versions("CIP-002-5.1a") == [
        "cip-002-5.1",
        "cip-002-6",
        "cip-002-6.1",
        "cip-002-7",
    ]
    assert _next_versions("not-a-standard") == []


def test_discover_new_families_probes_beyond_highest_held(monkeypatch):
    """F02: "the held register's zero future nodes does not demonstrate that
    no future obligations exist" applies equally to whole new families
    (design doc's real CIP-015 example) — this must probe beyond the highest
    held family number, not just next-version bumps of held standards."""
    from portal.modules.compliance.core import currency as cur

    def fake_exists(name: str) -> bool | None:
        return name == "cip-015-1"  # a new family, one past the highest held

    monkeypatch.setattr(cur, "_pdf_exists", fake_exists)
    found = discover_new_families(["CIP-002-5.1a", "CIP-014-3"], probe_ahead=3)
    assert found == ["CIP-015"]


def test_discover_new_families_reports_nothing_when_none_reachable(monkeypatch):
    from portal.modules.compliance.core import currency as cur

    monkeypatch.setattr(cur, "_pdf_exists", lambda name: False)
    assert discover_new_families(["CIP-002-5.1a"], probe_ahead=2) == []


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


def test_currency_ok_report_includes_new_family_discovery(monkeypatch):
    from portal.modules.compliance.core import currency as cur
    from portal.modules.compliance.core.cip_register import Register, RegisterNode

    monkeypatch.setattr(cur, "_pdf_exists", lambda name: False)
    node = RegisterNode(
        id="CIP-014-3 R1",
        standard="CIP-014-3",
        version="3",
        requirement="R1",
        part="",
        verbatim_text="x",
        measure_text="",
        applicable_systems="",
        table_name="",
        vrf="",
        time_horizon="",
        lifecycle_state="EFFECTIVE",
        valid_from="2022-01-01",
        valid_to=None,
        supersedes=None,
        superseded_by=None,
        authority_tier=0,
        source_pdf="",
        source_pages=[],
        recorded_at=0.0,
        granularity="requirement",
    )
    r = cur.nerc_currency(Register(nodes=[node]))
    assert r["status"] == "ok"
    assert r["new_families_discovered"] == []
    assert "new_family_discovery_note" in r


def test_currency_blocked_when_unreachable(monkeypatch):
    from portal.modules.compliance.core import currency as cur

    monkeypatch.setattr(cur, "_pdf_exists", lambda name: None)
    r = nerc_currency()
    assert r["status"] == "honest-BLOCKED"
    assert "never inferred" in r["reason"]
