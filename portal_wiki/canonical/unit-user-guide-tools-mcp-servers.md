---
id: unit-user-guide-tools-mcp-servers
kind: what
title: "USER_GUIDE \u2014 Tools (MCP Servers)"
sources:
- type: code
  path: imports/openwebui/mcp-servers.json
- type: code
  path: portal/modules/documents/tools/document_mcp.py
- type: code
  path: portal/modules/coding/tools/code_sandbox_mcp.py
- type: code
  path: portal/modules/media/tools/mflux_mcp.py
- type: code
  path: portal/modules/media/tools/music_minimax_mcp.py
- type: code
  path: portal/modules/media/tools/tts_mcp.py
- type: code
  path: portal/modules/media/tools/whisper_mcp.py
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.514928
updated_at: 1788032812
---

Tool servers are registered with Open WebUI from `imports/openwebui/mcp-servers.json`,
which lists each server's name, stable id, and port. In a chat you enable a tool
server with the `+` icon, then call its tools through the model. Portal Documents
(`create_word_document`, `create_excel`, `create_powerpoint`) generates office
files; Portal Code runs `execute_bash`/`execute_python` in an isolated sandbox;
Portal TTS exposes `speak`; Portal Whisper offers `transcribe_audio` and
`transcribe_with_speakers` (speaker diarization, with an Apple Silicon primary at
port 8924 via the MLX transcribe server); Portal MFLUX exposes `generate_image` / `edit_image`
(synchronous, MLX FLUX — including the `qwen-image` model); Portal Music exposes
the MiniMax job-based music toolset.

## Why

The guide described tools by their names in the chat UI, which left the actual
mapping to ports and code unstated. The fleet table, registration logic, and
every tool signature live in the repository, so this unit anchors each Portal
tool to the manifest entry and the MCP module that implements it, making the tool
list verifiable rather than anecdotal.
