---
id: unit-fact-tool-authorizations
kind: what
title: tool authorizations for 25 production workspaces
sources:
- type: code
  path: config/portal.yaml
  commit: b9d2c71bf613
  section: workspaces[].tools
claims: []
confidence: high
tags:
- fact
- tools
- workspaces
created_at: 1784049584.703768
updated_at: 1788234974.0847092
---

# Tool authorizations (per-workspace `tools:` whitelist)

The pipeline strips any tool a workspace does not authorize (metric `portal5_tool_workspace_strip_total`). A trailing `!` marks an authorized tool with no matching `@mcp.tool()` in the registry (see `unit-fact-tool-registry`).

| Workspace | Module | Authorized tools |
|---|---|---|
| `auto` | general | _(none)_ |
| `auto-audio` | media | `transcribe_audio`, `transcribe_with_speakers` |
| `auto-bigfix` | general | `execute_python`, `execute_bash`, `web_search` |
| `auto-cad` | cad | `execute_python`, `execute_bash`, `sandbox_status`, `read_pdf`, `read_word_document`, `web_search`, `web_fetch`, `remember`!, `recall`!, `kb_search`!, `render_mesh`, `render_openscad`, `convert_cad`, `generate_scad` |
| `auto-coding` | coding | `execute_python`, `execute_nodejs`, `execute_bash`, `sandbox_status`, `read_word_document`, `read_pdf`, `remember`!, `recall`! |
| `auto-compliance` | compliance | `create_word_document`, `read_pdf`, `kb_search`!, `kb_list`, `web_search`, `lookup_cve`, `get_epss`, `check_kev`, `triage_cve`, `ics_advisories`, `scan_dependencies`, `lookup_control`, `search_controls`, `nerc_cip_requirement`, `map_frameworks`, `patch_evidence`, `refresh_catalogs` |
| `auto-council` | general | _(none)_ |
| `auto-creative` | media | _(none)_ |
| `auto-daily` | general | `web_search`, `web_fetch`, `kb_search`!, `kb_list`, `read_pdf`, `read_word_document`, `read_excel`, `create_word_document`, `create_excel`, `create_powerpoint`, `execute_python`, `remember`!, `recall`!, `minimax_generate`, `minimax_status`, `transcribe_audio` |
| `auto-data` | research | `execute_python`, `create_excel`, `kb_search`!, `attach_source`, `run_sql`, `profile_table`, `list_session` |
| `auto-documents` | documents | `create_word_document`, `create_excel`, `create_powerpoint`, `read_word_document`, `read_excel`, `read_powerpoint`, `read_pdf`, `transcribe_with_speakers` |
| `auto-extract-uncensored` | documents | _(none)_ |
| `auto-general-uncensored` | general | `execute_bash`, `execute_python`, `read_word_document`, `read_pdf`, `remember`!, `recall`! |
| `auto-image` | image | `generate_image`, `edit_image` |
| `auto-math` | general | _(none)_ |
| `auto-music` | media | `minimax_generate`, `minimax_status`, `minimax_models`, `speak`, `transcribe_audio`, `clone_voice`, `register_voice`, `list_voices` |
| `auto-nemotron` | general | `web_search`, `web_fetch`, `kb_search`!, `kb_list`, `read_pdf`, `read_word_document`, `remember`!, `recall`! |
| `auto-reasoning` | general | _(none)_ |
| `auto-research` | research | `web_search`, `web_fetch`, `news_search`, `kb_search`!, `kb_search_all`!, `kb_list`, `remember`!, `recall`!, `graph_recall`!, `neighbors`!, `entity_timeline`! |
| `auto-security` | security | `web_search`, `web_fetch`, `classify_vulnerability`, `execute_python`, `execute_bash`, `kb_search`!, `kb_list`, `lookup_cve`, `get_epss`, `check_kev`, `triage_cve`, `ics_advisories`, `scan_dependencies`, `lookup_ioc`, `list_ics_protocols`, `dissect_pcap`, `asset_inventory`, `correlate_advisories` |
| `auto-spl` | general | `classify_vulnerability`, `kb_search`!, `kb_list`, `lookup_cve`, `get_epss`, `check_kev`, `triage_cve`, `ics_advisories`, `scan_dependencies`, `lookup_ioc`, `list_ics_protocols`, `dissect_pcap`, `asset_inventory`, `correlate_advisories`, `convert_sigma`, `validate_sigma`, `compile_yara`, `scan_yara`, `query_splunk`, `query_windows_events`, `protocol_hierarchy`, `extract_fields`, `conversations` |
| `auto-uncensored-throwaway` | general | `web_search`, `web_fetch`, `news_search`, `execute_bash`, `execute_python`, `remember`!, `recall`! |
| `auto-video` | video | `generate_video`, `animate_image` |
| `auto-vision` | general | `transcribe_audio`, `generate_image`, `edit_image` |
| `tools-specialist` | general | `execute_python`, `remember`!, `recall`! |

## Why

The authorizations table is the per-workspace `tools:` whitelist in `config/portal.yaml`, which is exactly what the pipeline enforces at dispatch time. A trailing `!` marks an authorized tool with no matching registration in `unit-fact-tool-registry`, so the table doubles as a reachability check between what a workspace is allowed to call and what any MCP server actually exposes.
