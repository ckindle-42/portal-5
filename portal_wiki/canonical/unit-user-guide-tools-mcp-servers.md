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
  path: portal/modules/media/tools/comfyui_mcp.py
- type: code
  path: portal/modules/media/tools/music_mcp.py
- type: code
  path: portal/modules/media/tools/tts_mcp.py
- type: code
  path: portal/modules/media/tools/whisper_mcp.py
last_generated_commit: 2f35b5ad508cd284e75ad0735ab7db02961001dd
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.514928
updated_at: 1784946220.514928
---

Tool servers are registered with Open WebUI from `imports/openwebui/mcp-servers.json`,
which lists each server's name, stable id, and port. In a chat you enable a tool
server with the `+` icon, then call its tools through the model. Portal Documents
(`create_word_document`, `create_excel`, `create_powerpoint`) generates office
files; Portal Code runs `execute_bash`/`execute_python` in an isolated sandbox;
Portal TTS exposes `speak`; Portal Whisper offers `transcribe_audio` and
`transcribe_with_speakers` (speaker diarization, with an Apple Silicon primary at
port 8924 via the MLX transcribe server); Portal ComfyUI exposes `generate_image`
and `start_image_generation` backed by Qwen-Image models; Portal Music exposes
`generate_music` via MusicGen.

## Why

The guide described tools by their names in the chat UI, which left the actual
mapping to ports and code unstated. The fleet table, registration logic, and
every tool signature live in the repository, so this unit anchors each Portal
tool to the manifest entry and the MCP module that implements it, making the tool
list verifiable rather than anecdotal.
