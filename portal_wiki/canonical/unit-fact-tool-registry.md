---
id: unit-fact-tool-registry
kind: what
title: 114 MCP tools across 24 servers
sources:
- type: code
  path: portal/modules/*/tools/*_mcp.py
  commit: c6d81e41a44b
last_generated_commit: c6d81e41a44b
confidence: high
tags:
- fact
- tools
- mcp
created_at: 1784049584.748966
updated_at: 1784049873.7773068
---

# MCP tool registry (114 tools across 24 servers)

What each MCP server actually registers — `@mcp.tool()` defs, or `@mcp.custom_route("/tools/<name>")` for servers that only expose that route form (memory, rag, web-search). Join with `unit-fact-tool-authorizations` to spot reachability gaps.

| Server | Registered tools |
|---|---|
| `browser` | `browser_click`, `browser_close`, `browser_evaluate`, `browser_fill`, `browser_list_profiles`, `browser_navigate`, `browser_screenshot`, `browser_snapshot` |
| `cad_render` | `convert_cad`, `render_mesh`, `render_openscad` |
| `comfyui` | `generate_image`, `get_generation_status`, `get_image_status`, `get_latest_images`, `list_workflows`, `start_image_generation` |
| `detections` | `spl_diff_hypothesis`, `spl_explain_detection`, `spl_search_library`, `spl_techniques_covered`, `spl_validate_syntax` |
| `docker` | _(unresolved — server file not found)_ |
| `documents` | `convert_document`, `create_excel`, `create_powerpoint`, `create_word_document`, `list_generated_files`, `read_excel`, `read_pdf`, `read_powerpoint`, `read_word_document` |
| `execution` | `execute_bash`, `execute_nodejs`, `execute_powershell`, `execute_python`, `sandbox_status` |
| `fetch` | _(unresolved — server file not found)_ |
| `filesystem` | _(unresolved — server file not found)_ |
| `git` | _(unresolved — server file not found)_ |
| `memory` | `clear_memories`, `forget`, `list_memories`, `recall`, `remember` |
| `mitre` | `mitre_data_sources_for_technique`, `mitre_detections_for_technique`, `mitre_technique_lookup`, `mitre_techniques_list` |
| `mlx_transcribe` | _(unresolved — server file not found)_ |
| `music` | `generate_continuation`, `generate_music`, `list_music_models` |
| `pipeline` | `explore_repository`, `get_loaded_models`, `get_metrics_summary`, `get_pipeline_status`, `get_workspace_recommendation`, `list_directory`, `list_workspaces`, `read_text_file`, `search_files`, `trigger_backend_warmup`, `write_file` |
| `proxmox` | `proxmox_clone_vm`, `proxmox_cluster_status`, `proxmox_container_exec`, `proxmox_container_shutdown`, `proxmox_container_start`, `proxmox_container_status`, `proxmox_container_stop`, `proxmox_create_snapshot`, `proxmox_delete_snapshot`, `proxmox_delete_vm`, `proxmox_deploy_ctf_lab`, `proxmox_exec_vm`, `proxmox_find_vm`, `proxmox_list_all_vms`, `proxmox_list_containers`, `proxmox_list_networks`, `proxmox_list_nodes`, `proxmox_list_snapshots`, `proxmox_list_storage`, `proxmox_list_storage_content`, `proxmox_list_tasks`, `proxmox_list_vms`, `proxmox_node_exec`, `proxmox_node_status`, `proxmox_rollback_snapshot`, `proxmox_task_status`, `proxmox_vm_agent_info`, `proxmox_vm_config`, `proxmox_vm_reboot`, `proxmox_vm_reset`, `proxmox_vm_resume`, `proxmox_vm_shutdown`, `proxmox_vm_start`, `proxmox_vm_status`, `proxmox_vm_stop`, `proxmox_vm_suspend` |
| `rag` | `kb_ingest`, `kb_list`, `kb_optimize`, `kb_restore`, `kb_search`, `kb_search_all`, `kb_versions` |
| `reranker` | `rerank` |
| `research` | _(unresolved — server file not found)_ |
| `security` | `classify_vulnerability` |
| `tts` | `clone_voice`, `list_voices`, `speak` |
| `video` | `generate_video`, `get_latest_videos`, `get_video_status`, `list_video_models`, `start_video_generation` |
| `whisper` | `transcribe_audio`, `transcribe_with_speakers` |
| `wiki` | _(unresolved — server file not found)_ |
