"""TASK_COMPLIANCE_REASONING_V2 — compliance_draft_revisions (Q07)."""

from __future__ import annotations

from portal.modules.compliance.core.applicability import AssetScope


def test_missing_standard_is_a_clear_error(monkeypatch):
    from portal.modules.compliance.core.cip_register import Register
    from portal.modules.compliance.tools.compliance_mcp import compliance_draft_revisions

    monkeypatch.setattr(Register, "load", staticmethod(lambda: Register(nodes=[])))
    monkeypatch.setattr(
        "portal.modules.compliance.core.scope_derive.derive_scope",
        lambda kb_id: (AssetScope(impact_present={"high"}, declared_by="op", declared_at="x"), {}),
    )
    result = compliance_draft_revisions("CIP-999-1", "CIP-999-2")
    assert "error" in result


def test_undeclared_scope_is_honest_blocked(monkeypatch):
    from portal.modules.compliance.core.cip_register import Register
    from portal.modules.compliance.tools.compliance_mcp import compliance_draft_revisions

    monkeypatch.setattr(Register, "load", staticmethod(lambda: Register(nodes=[])))
    monkeypatch.setattr(
        "portal.modules.compliance.core.scope_derive.derive_scope",
        lambda kb_id: (AssetScope(), {"reason": "no corpus"}),
    )
    result = compliance_draft_revisions("CIP-999-1", "CIP-999-2")
    assert result["status"] == "honest-BLOCKED"


def test_specification_only_mode_by_default(monkeypatch):
    from portal.modules.compliance.core.cip_register import Register, RegisterNode
    from portal.modules.compliance.tools.compliance_mcp import compliance_draft_revisions

    def _node(standard, node_id, text):
        return RegisterNode(
            id=node_id,
            standard=standard,
            version=standard.rsplit("-", 1)[1],
            requirement="R1",
            part="1.1",
            verbatim_text=text,
            measure_text="",
            applicable_systems="",
            table_name="",
            vrf="",
            time_horizon="",
            lifecycle_state="EFFECTIVE",
            valid_from="2020-01-01",
            valid_to=None,
            supersedes=None,
            superseded_by=None,
            authority_tier=0,
            source_pdf="",
            source_pages=[],
            recorded_at=0.0,
            granularity="part",
        )

    old_node = _node("TEST-1", "TEST-1 R1 Part 1.1", "old text shall apply")
    new_node = _node("TEST-2", "TEST-2 R1 Part 1.1", "new text shall apply differently")
    monkeypatch.setattr(
        Register,
        "load",
        staticmethod(lambda: Register(nodes=[old_node, new_node])),
    )
    monkeypatch.setattr(
        "portal.modules.compliance.core.scope_derive.derive_scope",
        lambda kb_id: (AssetScope(impact_present={"high"}, declared_by="op", declared_at="x"), {}),
    )

    result = compliance_draft_revisions("TEST-1", "TEST-2")
    assert result["mode"] == "specification_only"
    assert all(s["drafted_replacement"] is None for s in result["specifications"])
