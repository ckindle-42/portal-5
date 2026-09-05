"""TASK_COMPLIANCE_REASONING_V2 — compliance_prospective (Q11: "what requires
review when a new/revised standard takes effect").
"""

from __future__ import annotations

from portal.modules.compliance.core.applicability import AssetScope
from portal.modules.compliance.core.cip_register import RegisterNode


def _node(**kw) -> RegisterNode:
    base = {
        "id": "TEST-1 R1 Part 1.1",
        "standard": "TEST-1",
        "version": "1",
        "requirement": "R1",
        "part": "1.1",
        "verbatim_text": "Do the future thing.",
        "measure_text": "",
        "applicable_systems": "",
        "table_name": "",
        "vrf": "",
        "time_horizon": "",
        "lifecycle_state": "FUTURE_EFFECTIVE",
        "valid_from": "2027-01-01",
        "valid_to": None,
        "supersedes": None,
        "superseded_by": None,
        "authority_tier": 0,
        "source_pdf": "",
        "source_pages": [],
        "recorded_at": 0.0,
        "granularity": "part",
    }
    base.update(kw)
    return RegisterNode(**base)


def test_prospective_report_segregates_future_content(monkeypatch):
    from portal.modules.compliance.core.cip_register import Register
    from portal.modules.compliance.tools.compliance_mcp import compliance_prospective

    future_node = _node()
    monkeypatch.setattr(Register, "load", staticmethod(lambda: Register(nodes=[future_node])))
    monkeypatch.setattr(
        "portal.modules.compliance.core.scope_derive.derive_scope",
        lambda kb_id: (
            AssetScope(impact_present={"high"}, declared_by="op", declared_at="2026-01-01"),
            {},
        ),
    )

    result = compliance_prospective(effective_on="2026-09-05")
    assert result["as_of"] == "2026-09-05"
    assert result["n_future_effective"] == 1
    row = result["rows"][0]
    assert row["requirement_id"] == "TEST-1 R1 Part 1.1"
    assert row["prospective"] is True
    assert "MUST NOT" in result["segregation"]


def test_prospective_report_defaults_effective_on_to_today(monkeypatch):
    import datetime

    from portal.modules.compliance.core.cip_register import Register
    from portal.modules.compliance.tools.compliance_mcp import compliance_prospective

    monkeypatch.setattr(Register, "load", staticmethod(lambda: Register(nodes=[])))
    monkeypatch.setattr(
        "portal.modules.compliance.core.scope_derive.derive_scope",
        lambda kb_id: (AssetScope(), {}),
    )

    result = compliance_prospective()
    assert result["as_of"] == datetime.date.today().isoformat()
    assert result["n_future_effective"] == 0
