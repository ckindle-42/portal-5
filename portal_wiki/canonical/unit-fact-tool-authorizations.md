---
id: unit-fact-tool-authorizations
kind: what
title: tool authorizations for 21 production workspaces
sources:
- type: code
  path: config/portal.yaml
  commit: c4895be18722
  section: workspaces[].tools
last_generated_commit: c4895be18722
confidence: high
tags:
- fact
- tools
- workspaces
created_at: 1784049584.703768
updated_at: 1784055273.6847548
---

# Tool authorizations (per-workspace `tools:` whitelist)

The pipeline strips any tool a workspace does not authorize (metric `portal5_tool_workspace_strip_total`). A trailing `!` marks an authorized tool with no matching `@mcp.tool()` in the registry (see `unit-fact-tool-registry`).

| Workspace | Module | Authorized tools |
|---|---|---|
| `auto` | general | _(none)_ |
| `auto-audio` | media | `transcribe_audio`, `transcribe_with_speakers` |
| `auto-bigfix` | general | `execute_python`, `execute_bash`, `web_search` |
| `auto-cad` | cad | `execute_python`, `execute_bash`, `sandbox_status`, `read_pdf`, `read_word_document`, `web_search`, `web_fetch`, `remember`, `recall`, `kb_search`, `render_mesh`, `render_openscad`, `convert_cad` |
| `auto-coding` | coding | `execute_python`, `execute_nodejs`, `execute_bash`, `sandbox_status`, `read_word_document`, `read_pdf`, `remember`, `recall` |
| `auto-compliance` | compliance | `create_word_document`, `read_pdf`, `kb_search`, `kb_list`, `web_search` |
| `auto-creative` | media | _(none)_ |
| `auto-daily` | general | `web_search`, `web_fetch`, `kb_search`, `kb_list`, `read_pdf`, `read_word_document`, `read_excel`, `create_word_document`, `create_excel`, `create_powerpoint`, `execute_python`, `remember`, `recall`, `generate_music`, `transcribe_audio` |
| `auto-data` | research | `execute_python`, `create_excel`, `kb_search` |
| `auto-documents` | documents | `create_word_document`, `create_excel`, `create_powerpoint`, `read_word_document`, `read_excel`, `read_powerpoint`, `read_pdf`, `transcribe_with_speakers` |
| `auto-extract-uncensored` | documents | _(none)_ |
| `auto-general-uncensored` | general | `execute_bash`, `execute_python`, `read_word_document`, `read_pdf`, `remember`, `recall` |
| `auto-math` | general | _(none)_ |
| `auto-music` | media | `generate_music`, `generate_continuation`, `list_music_models`, `speak`, `transcribe_audio`, `clone_voice`, `list_voices` |
| `auto-reasoning` | general | _(none)_ |
| `auto-research` | research | `web_search`, `web_fetch`, `news_search`, `kb_search`, `kb_search_all`, `kb_list`, `remember`, `recall` |
| `auto-security` | security | `web_search`, `web_fetch`, `classify_vulnerability`, `execute_python`, `execute_bash`, `kb_search`, `kb_list` |
| `auto-spl` | general | `classify_vulnerability`, `kb_search`, `kb_list` |
| `auto-video` | media | `generate_video`, `generate_image`, `list_video_models` |
| `auto-vision` | general | `transcribe_audio`, `generate_image`, `list_workflows`, `get_generation_status` |
| `tools-specialist` | general | `execute_python`, `remember`, `recall` |
