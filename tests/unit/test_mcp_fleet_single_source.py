"""Tests that MCP fleet is single-sourced in portal.yaml.

Every MCP id/port must appear exactly once. The pipeline-discovered set
must be a subset of the fleet. The IDE-advertised set must also be a subset.
"""

from __future__ import annotations

import asyncio
import importlib
import importlib.util
import json
from pathlib import Path

import pytest

from portal.platform.inference.config import get_pipeline_mcp_servers, load_portal_config
from portal.platform.inference.tool_registry import MCP_SERVERS

REPO = Path(__file__).resolve().parent.parent.parent
NATIVE_MODULES = {
    "music-minimax": "portal.modules.media.tools.music_minimax_mcp",
    "mflux": "portal.modules.media.tools.mflux_mcp",
    "video_mlx": "portal.modules.media.tools.video_mlx_mcp",
    "documents": "portal.modules.documents.tools.document_mcp",
    "execution": "portal.modules.coding.tools.code_sandbox_mcp",
    "whisper": "portal.modules.media.tools.whisper_mcp",
    "tts": "portal.modules.media.tools.tts_mcp",
    "security": "portal.modules.security.tools.security_mcp",
    "memory": "portal.platform.memory.memory_mcp",
    "rag": "portal.modules.research.tools.rag_mcp",
    "research": "portal.modules.research.tools.web_search_mcp",
    "mlx_transcribe": None,
    "cad_render": "portal.modules.cad.tools.cad_render_mcp",
    "pipeline": "portal.platform.mcp_host.pipeline_mcp",
    "mitre": "portal.modules.security.tools.mitre_mcp",
    "detections": "portal.modules.security.tools.detections_mcp",
    "wiki": "portal_wiki.wiki_mcp",
    "vulnintel": "portal.modules.vulnintel.tools.vulnintel_mcp",
    "icsot": "portal.modules.icsot.tools.icsot_mcp",
    "compliance": "portal.modules.compliance.tools.compliance_mcp",
    "detection": "portal.modules.detection.tools.detection_mcp",
    "data": "portal.modules.data.tools.data_mcp",
    "netforensics": "portal.modules.netforensics.tools.netforensics_mcp",
    "review": "portal.modules.security.tools.review_mcp",
}


@pytest.fixture(autouse=True)
def _restore_config_cache():
    """Reload config from real portal.yaml before each fleet test.

    Other test files call load_portal_config(_force_reload=True) with minimal
    YAML fixtures, which leaves the module-level cache pointing at an empty
    fleet. This fixture resets it to the real config before each test here.
    """
    load_portal_config(_force_reload=True)
    yield
    # Restore to real config after the test too
    load_portal_config(_force_reload=True)


def test_no_duplicate_ports_in_fleet() -> None:
    """No two MCP servers in portal.yaml fleet may share a port."""
    config = load_portal_config()
    ports = [s.port for s in config.mcp_fleet if s.port is not None]
    seen: set[int] = set()
    dupes = []
    for p in ports:
        if p in seen:
            dupes.append(p)
        seen.add(p)
    assert not dupes, f"Duplicate ports in mcp_fleet: {dupes}"


def test_no_duplicate_ids_in_fleet() -> None:
    """No two MCP servers in portal.yaml fleet may share an id."""
    config = load_portal_config()
    ids = [s.id for s in config.mcp_fleet]
    seen: set[str] = set()
    dupes = []
    for i in ids:
        if i in seen:
            dupes.append(i)
        seen.add(i)
    assert not dupes, f"Duplicate ids in mcp_fleet: {dupes}"


def test_pipeline_mcp_servers_subset_of_fleet() -> None:
    """Every key in tool_registry.MCP_SERVERS must be in the portal.yaml fleet."""
    config = load_portal_config()
    fleet_ids = {s.id for s in config.mcp_fleet}
    pipeline_ids = set(MCP_SERVERS.keys())
    extra = pipeline_ids - fleet_ids
    assert not extra, f"MCP_SERVERS keys not in fleet: {sorted(extra)}"


def test_pipeline_mcp_servers_all_pipeline_exposed() -> None:
    """Every key in MCP_SERVERS must have expose_to_pipeline=True in the fleet."""
    config = load_portal_config()
    pipeline_exposed = {s.id for s in config.mcp_fleet if s.expose_to_pipeline}
    non_exposed = set(MCP_SERVERS.keys()) - pipeline_exposed
    assert not non_exposed, (
        f"MCP_SERVERS has servers not expose_to_pipeline in fleet: {non_exposed}"
    )


def test_fleet_pipeline_exposed_matches_mcp_servers() -> None:
    """get_pipeline_mcp_servers() must equal MCP_SERVERS (same derivation)."""
    config = load_portal_config()
    derived = get_pipeline_mcp_servers(config)
    # Allow env-override variation but keys must match
    assert set(derived.keys()) == set(MCP_SERVERS.keys()), (
        f"Fleet pipeline keys mismatch:\n"
        f"  derived: {sorted(derived.keys())}\n"
        f"  MCP_SERVERS: {sorted(MCP_SERVERS.keys())}"
    )


def test_env_override_normalizes_hyphenated_id(monkeypatch: pytest.MonkeyPatch) -> None:
    """A hyphenated fleet id is overridable via an underscored env key.

    ``music-minimax`` runs host-native (no compose service), so the pipeline
    container must be able to repoint it at host.docker.internal. Env var names
    can't carry hyphens, so the key is ``MCP_MUSIC_MINIMAX_URL``.
    """
    config = load_portal_config()
    assert any(s.id == "music-minimax" for s in config.mcp_fleet)
    monkeypatch.setenv("MCP_MUSIC_MINIMAX_URL", "http://host.docker.internal:8912")
    derived = get_pipeline_mcp_servers(config)
    assert derived["music-minimax"] == "http://host.docker.internal:8912"


def test_ide_servers_in_fleet() -> None:
    """.mcp.json server names must all be from the fleet (expose_to_ide=True entries)."""
    mcp_json = json.loads((REPO / ".mcp.json").read_text())
    mcp_names = set(mcp_json.get("mcpServers", {}).keys())

    config = load_portal_config()
    ide_names = {s.name for s in config.mcp_fleet if s.expose_to_ide}

    extra = mcp_names - ide_names
    assert not extra, f".mcp.json has servers not in fleet (expose_to_ide=True): {sorted(extra)}"


def test_execution_alias_recorded() -> None:
    """The 'execution' server must have 'sandbox' as an alias (drift reconciliation)."""
    config = load_portal_config()
    execution = next((s for s in config.mcp_fleet if s.id == "execution"), None)
    assert execution is not None, "MCP server 'execution' (port 8914) not found in fleet"
    assert "sandbox" in execution.aliases, (
        "'sandbox' alias not recorded on execution server (needed for backward compatibility)"
    )


def test_browser_is_ide_only() -> None:
    """The 'browser' MCP (port 8923) must not be pipeline-exposed."""
    config = load_portal_config()
    browser = next((s for s in config.mcp_fleet if s.id == "browser"), None)
    if browser is not None:
        assert not browser.expose_to_pipeline, (
            "browser MCP should not be pipeline-exposed (raw browser tools are not model-callable)"
        )


NATIVE_TOOL_NAMES = {
    "music-minimax": ["minimax_generate", "minimax_models", "minimax_status"],
    "mflux": ["edit_image", "generate_image"],
    "video_mlx": ["animate_image", "generate_video"],
    "documents": [
        "convert_document",
        "create_excel",
        "create_powerpoint",
        "create_word_document",
        "export_pdf",
        "list_generated_files",
        "prepare_embed_image",
        "read_excel",
        "read_pdf",
        "read_powerpoint",
        "read_word_document",
    ],
    "execution": [
        "execute_bash",
        "execute_nodejs",
        "execute_powershell",
        "execute_python",
        "list_sessions",
        "reset_session",
        "sandbox_status",
    ],
    "whisper": ["transcribe_audio", "transcribe_with_speakers"],
    "tts": ["clone_voice", "list_voices", "register_voice", "speak"],
    "security": ["classify_vulnerability", "lab_perception"],
    "memory": [
        "clear_memories",
        "entity_timeline",
        "forget",
        "graph_recall",
        "link",
        "list_memories",
        "neighbors",
        "recall",
        "remember",
    ],
    "rag": [
        "kb_ingest",
        "kb_list",
        "kb_optimize",
        "kb_restore",
        "kb_search",
        "kb_search_all",
        "kb_versions",
    ],
    "research": ["news_search", "web_fetch", "web_search"],
    "mlx_transcribe": ["transcribe_audio", "transcribe_with_speakers"],
    "cad_render": [
        "cad_build",
        "cad_execute",
        "cad_finalize",
        "cad_find_holes",
        "cad_measure",
        "cad_render",
        "convert_cad",
        "generate_part",
        "generate_scad",
        "render_mesh",
        "render_openscad",
    ],
    "pipeline": [
        "arm_queue_task",
        "explore_repository",
        "get_loaded_models",
        "get_metrics_summary",
        "get_pipeline_status",
        "get_workspace_recommendation",
        "list_directory",
        "list_workspaces",
        "read_text_file",
        "search_files",
        "trigger_backend_warmup",
        "write_file",
    ],
    "mitre": [
        "mitre_data_sources_for_technique",
        "mitre_detections_for_technique",
        "mitre_technique_lookup",
        "mitre_techniques_list",
    ],
    "detections": [
        "spl_diff_hypothesis",
        "spl_explain_detection",
        "spl_search_library",
        "spl_techniques_covered",
        "spl_validate_syntax",
    ],
    "wiki": ["wiki_explain", "wiki_get_unit", "wiki_search"],
    "vulnintel": [
        "check_kev",
        "get_epss",
        "ics_advisories",
        "lookup_cve",
        "lookup_ioc",
        "scan_dependencies",
        "triage_cve",
    ],
    "icsot": [
        "asset_inventory",
        "correlate_advisories",
        "dissect_pcap",
        "list_ics_protocols",
    ],
    "compliance": [
        "compliance_analyze",
        "compliance_answers",
        "compliance_ask",
        "compliance_bundle",
        "compliance_change_impact",
        "compliance_compare",
        "compliance_conflicts",
        "compliance_context",
        "compliance_correct",
        "compliance_coverage",
        "compliance_draft_revisions",
        "compliance_flexibility",
        "compliance_gaps",
        "compliance_impact",
        "compliance_ingest",
        "compliance_intentionality",
        "compliance_kb_search",
        "compliance_links",
        "compliance_mappings",
        "compliance_note",
        "compliance_notes",
        "compliance_orphans",
        "compliance_prospective",
        "compliance_read",
        "compliance_requirement",
        "compliance_review_decide",
        "compliance_review_decide_batch",
        "compliance_review_list",
        "compliance_route",
        "compliance_scenario",
        "compliance_scope",
        "compliance_search",
        "compliance_sources",
        "compliance_standing_questions",
        "compliance_timeline",
        "compliance_trace",
        "lookup_control",
        "map_frameworks",
        "nerc_cip_currency",
        "nerc_cip_requirement",
        "patch_evidence",
        "refresh_catalogs",
        "search_controls",
    ],
    "detection": [
        "compile_yara",
        "convert_sigma",
        "query_splunk",
        "query_windows_events",
        "scan_yara",
        "validate_sigma",
    ],
    "data": ["attach_source", "list_session", "profile_table", "run_sql"],
    "netforensics": ["conversations", "extract_fields", "protocol_hierarchy", "recon_scan"],
    "review": [
        "review_cancel",
        "review_doctor",
        "review_explain",
        "review_queue",
        "review_result",
        "review_start",
        "review_status",
        "review_verdict",
    ],
}


def test_pipeline_exposed_native_tools_are_complete() -> None:
    pytest.importorskip("mcp")
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setenv("SECURITY_MCP_PREWARM", "0")
    try:
        config = load_portal_config()
        exposed = {server.id for server in config.mcp_fleet if server.expose_to_pipeline}
        assert exposed == set(NATIVE_MODULES) == set(NATIVE_TOOL_NAMES)

        for server_id, module_path in NATIVE_MODULES.items():
            module = _load(module_path)
            tools = asyncio.run(module.mcp.list_tools())
            names = sorted(tool.name for tool in tools)
            assert names == NATIVE_TOOL_NAMES[server_id], server_id
            for tool in tools:
                assert tool.description, (server_id, tool.name)
                assert tool.input_schema.get("type") == "object", (server_id, tool.name)
                assert tool.output_schema is not None, (server_id, tool.name)
    finally:
        monkeypatch.undo()


def _load(module_path: str | None):
    if module_path is None:
        spec = importlib.util.spec_from_file_location(
            "portal_mlx_transcribe_contract", REPO / "scripts" / "mlx-transcribe.py"
        )
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    return importlib.reload(importlib.import_module(module_path))
