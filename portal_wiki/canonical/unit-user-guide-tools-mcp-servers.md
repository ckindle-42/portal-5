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
  path: portal/modules/media/tools/music_mcp.py
- type: code
  path: portal/modules/media/tools/tts_mcp.py
- type: code
  path: portal/modules/media/tools/whisper_mcp.py
claims:
- probe: repo.symbol.exists
  path: portal/modules/documents/tools/document_mcp.py
  symbol: create_word_document
  equals: true
confidence: high
tags:
- docs
- verified-v1
---

Tool servers are registered with Open WebUI from `imports/openwebui/mcp-servers.json`,
which lists each server's name, stable id, and port. In a chat you enable a tool
server with the `+` icon, then call its tools through the model. Portal Documents
(`create_word_document`, `create_excel`, `create_powerpoint`) generates office
files; Portal Code runs `execute_bash`/`execute_python` in an isolated sandbox;
Portal TTS exposes `speak`; Portal Whisper offers `transcribe_audio` and
`transcribe_with_speakers` (speaker diarization, Apple Silicon primary at
port 8924 via the MLX transcribe server; both always write JSON + Markdown + Word
`.docx` sidecars and return their download URLs); Portal MFLUX exposes `generate_image` / `edit_image` /
`image_start` / `image_status` (MLX MFLUX — flux2-klein 4-step default, flux3-klein,
qwen-2.1, z-image; start/status is the async surface); Portal Music exposes
`music_start` / `music_status` / `music_models` (ACE-Step 1.5 XL-Turbo primary,
MiniMax-Music3 8-bit fallback; gated by `music` — see `unit-fact-module-states`).

## Why

The guide described tools by their names in the chat UI, which left the actual
mapping to ports and code unstated. The fleet table, registration logic, and
every tool signature live in the repository, so this unit anchors each Portal
tool to the manifest entry and the MCP module that implements it, making the tool
list verifiable rather than anecdotal.
