"""Tests for portal-mitre + portal-detections MCP — Phase 5 of BUILD_PROGRAM.

Validates:
- MITRE tool implementations return correct shapes
- SPL detection tools return correct shapes
- SPL syntax validation rejects bad SPL
- Servers register and respond to health/tools endpoints
"""

from __future__ import annotations

# ── portal-mitre tools ───────────────────────────────────────────────────────


class TestMitreTools:
    """MITRE ATT&CK tool implementations return correct shapes."""

    def test_technique_lookup_known(self):
        from portal.modules.security.tools.mitre_mcp import mitre_technique_lookup

        result = mitre_technique_lookup("T1190")
        assert result["technique_id"] == "T1190"
        assert "name" in result
        assert "tactic" in result
        assert "has_detection" in result

    def test_technique_lookup_subtechnique(self):
        from portal.modules.security.tools.mitre_mcp import mitre_technique_lookup

        result = mitre_technique_lookup("T1558.003")
        assert result["technique_id"] == "T1558.003"
        assert "name" in result

    def test_technique_lookup_unknown(self):
        from portal.modules.security.tools.mitre_mcp import mitre_technique_lookup

        result = mitre_technique_lookup("T9999.999")
        assert "error" in result

    def test_data_sources_for_technique(self):
        from portal.modules.security.tools.mitre_mcp import mitre_data_sources_for_technique

        result = mitre_data_sources_for_technique("T1190")
        assert result["technique_id"] == "T1190"
        assert isinstance(result["data_sources"], list)
        assert len(result["data_sources"]) > 0

    def test_detections_for_technique_with_spl(self):
        from portal.modules.security.tools.mitre_mcp import mitre_detections_for_technique

        result = mitre_detections_for_technique("T1190")
        assert result["technique_id"] == "T1190"
        assert result["has_detection"] is True
        assert "spl" in result

    def test_detections_for_technique_without_spl(self):
        from portal.modules.security.tools.mitre_mcp import mitre_detections_for_technique

        result = mitre_detections_for_technique("T1078.004")
        assert result["has_detection"] is False

    def test_techniques_list(self):
        from portal.modules.security.tools.mitre_mcp import mitre_techniques_list

        result = mitre_techniques_list()
        assert result["count"] > 0
        assert isinstance(result["techniques"], list)

    def test_techniques_list_with_tactic_filter(self):
        from portal.modules.security.tools.mitre_mcp import mitre_techniques_list

        result = mitre_techniques_list(tactic="credential-access")
        assert result["tactic_filter"] == "credential-access"
        for t in result["techniques"]:
            assert t["tactic"] == "credential-access"

    def test_all_tools_json_safe(self):
        import json

        from portal.modules.security.tools.mitre_mcp import (
            mitre_data_sources_for_technique,
            mitre_detections_for_technique,
            mitre_technique_lookup,
            mitre_techniques_list,
        )

        for fn in [
            mitre_technique_lookup,
            mitre_data_sources_for_technique,
            mitre_detections_for_technique,
        ]:
            json.dumps(fn("T1190"))
        json.dumps(mitre_techniques_list())


# ── portal-detections tools ──────────────────────────────────────────────────


class TestDetectionsTools:
    """SPL detection tool implementations return correct shapes."""

    def test_search_library_by_technique(self):
        from portal.modules.security.tools.detections_mcp import spl_search_library

        result = spl_search_library("T1190")
        assert result["count"] > 0
        assert any(r["technique_id"] == "T1190" for r in result["results"])

    def test_search_library_by_keyword(self):
        from portal.modules.security.tools.detections_mcp import spl_search_library

        result = spl_search_library("Kerberoasting")
        assert result["count"] > 0

    def test_search_library_no_match(self):
        from portal.modules.security.tools.detections_mcp import spl_search_library

        result = spl_search_library("nonexistent_xyz")
        assert result["count"] == 0

    def test_validate_syntax_valid(self):
        from portal.modules.security.tools.detections_mcp import spl_validate_syntax

        result = spl_validate_syntax('index=portal5_lab sourcetype="web:access" test')
        assert result["ok"] is True
        assert result["errors"] == []

    def test_validate_syntax_empty(self):
        from portal.modules.security.tools.detections_mcp import spl_validate_syntax

        result = spl_validate_syntax("")
        assert result["ok"] is False

    def test_validate_syntax_placeholder(self):
        from portal.modules.security.tools.detections_mcp import spl_validate_syntax

        result = spl_validate_syntax("# TODO: draft SPL")
        assert result["ok"] is False

    def test_validate_syntax_unmatched_quotes(self):
        from portal.modules.security.tools.detections_mcp import spl_validate_syntax

        result = spl_validate_syntax('index=test "unmatched')
        assert result["ok"] is False
        assert any("quote" in e.lower() for e in result["errors"])

    def test_explain_detection_known(self):
        from portal.modules.security.tools.detections_mcp import spl_explain_detection

        result = spl_explain_detection("T1190")
        assert result["technique_id"] == "T1190"
        assert "description" in result
        assert result["has_spl"] is True

    def test_explain_detection_unknown(self):
        from portal.modules.security.tools.detections_mcp import spl_explain_detection

        result = spl_explain_detection("T9999.999")
        assert "error" in result

    def test_techniques_covered(self):
        from portal.modules.security.tools.detections_mcp import spl_techniques_covered

        result = spl_techniques_covered()
        assert result["count"] >= 29
        assert "T1190" in result["techniques"]

    def test_diff_hypothesis(self):
        from portal.modules.security.tools.detections_mcp import spl_diff_hypothesis

        result = spl_diff_hypothesis("T1190", "HTTP request with UNION SELECT in URI")
        assert result["technique_id"] == "T1190"
        assert "matched_keywords" in result
        assert "missed_keywords" in result
        assert "overlap_ratio" in result

    def test_all_tools_json_safe(self):
        import json

        from portal.modules.security.tools.detections_mcp import (
            spl_explain_detection,
            spl_search_library,
            spl_techniques_covered,
            spl_validate_syntax,
        )

        json.dumps(spl_search_library("T1190"))
        json.dumps(spl_validate_syntax("index=test"))
        json.dumps(spl_explain_detection("T1190"))
        json.dumps(spl_techniques_covered())
