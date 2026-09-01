---
id: unit-fact-tool-registry
kind: what
title: 124 MCP tools across 29 servers
sources:
- type: code
  path: portal/modules/*/tools/*_mcp.py
  commit: a446cb0d1541
claims: []
confidence: high
tags:
- fact
- tools
- mcp
created_at: 1784049584.748966
updated_at: 1788231340.253191
---

# MCP tool registry

What each MCP server actually registers — `@mcp.tool()` defs, or `@mcp.custom_route("/tools/<name>")` for servers that only expose that route form (memory, rag, web-search). Join with `unit-fact-tool-authorizations` to spot reachability gaps.

| Server | Registered tools |
|---|---|
| `binresearch` | _(unresolved — server file not found)_ |
| `browser` | `browser_click`, `browser_close`, `browser_evaluate`, `browser_fill`, `browser_list_profiles`, `browser_navigate`, `browser_screenshot`, `browser_snapshot` |
| `cad_render` | `convert_cad`, `generate_scad`, `render_mesh`, `render_openscad` |
| `compliance` | `lookup_control`, `map_frameworks`, `nerc_cip_requirement`, `patch_evidence`, `refresh_catalogs`, `search_controls` |
| `detections` | `spl_diff_hypothesis`, `spl_explain_detection`, `spl_search_library`, `spl_techniques_covered`, `spl_validate_syntax` |
| `docker` | _(unresolved — server file not found)_ |
| `documents` | `convert_document`, `create_excel`, `create_powerpoint`, `create_word_document`, `export_pdf`, `list_generated_files`, `prepare_embed_image`, `read_excel`, `read_pdf`, `read_powerpoint`, `read_word_document` |
| `execution` | `execute_bash`, `execute_nodejs`, `execute_powershell`, `execute_python`, `list_sessions`, `reset_session`, `sandbox_status` |
| `fetch` | _(unresolved — server file not found)_ |
| `filesystem` | _(unresolved — server file not found)_ |
| `git` | _(unresolved — server file not found)_ |
| `icsot` | `asset_inventory`, `correlate_advisories`, `dissect_pcap`, `list_ics_protocols` |
| `memory` | `clear_memories`, `forget`, `list_memories`, `recall`, `remember` |
| `mflux` | _(unresolved — server file not found)_ |
| `mitre` | `mitre_data_sources_for_technique`, `mitre_detections_for_technique`, `mitre_technique_lookup`, `mitre_techniques_list` |
| `mlx_transcribe` | _(unresolved — server file not found)_ |
| `music-minimax` | _(unresolved — server file not found)_ |
| `pipeline` | `explore_repository`, `get_loaded_models`, `get_metrics_summary`, `get_pipeline_status`, `get_workspace_recommendation`, `list_directory`, `list_workspaces`, `read_text_file`, `search_files`, `trigger_backend_warmup`, `write_file` |
| `proxmox` | `proxmox_clone_vm`, `proxmox_cluster_status`, `proxmox_container_exec`, `proxmox_container_shutdown`, `proxmox_container_start`, `proxmox_container_status`, `proxmox_container_stop`, `proxmox_create_snapshot`, `proxmox_delete_snapshot`, `proxmox_delete_vm`, `proxmox_deploy_ctf_lab`, `proxmox_exec_vm`, `proxmox_find_vm`, `proxmox_list_all_vms`, `proxmox_list_containers`, `proxmox_list_networks`, `proxmox_list_nodes`, `proxmox_list_snapshots`, `proxmox_list_storage`, `proxmox_list_storage_content`, `proxmox_list_tasks`, `proxmox_list_vms`, `proxmox_node_exec`, `proxmox_node_status`, `proxmox_rollback_snapshot`, `proxmox_task_status`, `proxmox_vm_agent_info`, `proxmox_vm_config`, `proxmox_vm_reboot`, `proxmox_vm_reset`, `proxmox_vm_resume`, `proxmox_vm_shutdown`, `proxmox_vm_start`, `proxmox_vm_status`, `proxmox_vm_stop`, `proxmox_vm_suspend` |
| `rag` | `kb_ingest`, `kb_list`, `kb_optimize`, `kb_restore`, `kb_search`, `kb_search_all`, `kb_versions` |
| `reranker` | `rerank` |
| `research` | _(unresolved — server file not found)_ |
| `security` | `classify_vulnerability`, `lab_perception` |
| `serena` | _(unresolved — server file not found)_ |
| `tts` | `clone_voice`, `list_voices`, `register_voice`, `speak` |
| `video_mlx` | _(unresolved — server file not found)_ |
| `vulnintel` | `check_kev`, `get_epss`, `ics_advisories`, `lookup_cve`, `lookup_ioc`, `scan_dependencies`, `triage_cve` |
| `whisper` | `transcribe_audio`, `transcribe_with_speakers` |
| `wiki` | _(unresolved — server file not found)_ |

## Why

The registry is parsed directly from the MCP server source files: `@mcp.tool()` decorated functions, or `@mcp.custom_route("/tools/<name>")` registrations for servers that only expose that route form. Joining it with the per-workspace authorizations unit exposes which authorized tools are unreachable because no server registers them.
