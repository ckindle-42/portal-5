---
id: unit-fact-mcp-fleet
kind: what
title: 32 MCP fleet servers
sources:
- type: code
  path: config/portal.yaml
  commit: 72eb9714da3a
  section: mcp_fleet
claims:
- probe: mcp.fleet.entries
  pattern: MCP fleet ({value} servers)
confidence: high
tags:
- fact
- mcp
created_at: 1784000421.477582
updated_at: 1788232840.02067
---

# MCP fleet (32 servers)

| ID | Name | Port |
|---|---|---|
| `filesystem` | filesystem |  |
| `fetch` | fetch |  |
| `git` | git |  |
| `serena` | serena |  |
| `docker` | docker |  |
| `context7` | portal-context7 |  |
| `music-minimax` | portal-music-minimax | 8912 |
| `documents` | portal-documents | 8913 |
| `execution` | portal-sandbox | 8914 |
| `whisper` | portal-whisper | 8915 |
| `tts` | portal-tts | 8916 |
| `security` | portal-security | 8919 |
| `memory` | portal-memory | 8920 |
| `rag` | portal-rag | 8921 |
| `research` | portal-research | 8922 |
| `browser` | portal-browser | 8923 |
| `mlx_transcribe` | portal-mlx-transcribe | 8924 |
| `reranker` | portal-reranker | 8925 |
| `cad_render` | portal-cad-render | 8926 |
| `proxmox` | portal-proxmox | 8927 |
| `pipeline` | portal-pipeline | 8928 |
| `mitre` | portal-mitre | 8929 |
| `binresearch` | portal-binresearch | 8930 |
| `wiki` | portal-wiki | 8931 |
| `detections` | portal-detections | 8932 |
| `mflux` | portal-mflux | 8933 |
| `vulnintel` | portal-vulnintel | 8934 |
| `video_mlx` | portal-video-mlx | 8935 |
| `icsot` | portal-icsot | 8936 |
| `compliance` | portal-compliance | 8937 |
| `detection` | portal-detection | 8938 |
| `data` | portal-data | 8939 |

## Why

The fleet table is the `mcp_fleet` list in `config/portal.yaml`, the single source for every MCP tool server the pipeline can dispatch to. Each entry carries the server id, display name, and reserved port, so the wiki fleet roster is the same list the tool registry and the Open WebUI tool-server wiring are built from.
