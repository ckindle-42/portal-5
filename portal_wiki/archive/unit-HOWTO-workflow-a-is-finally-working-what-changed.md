---
id: unit-HOWTO-workflow-a-is-finally-working-what-changed
kind: why
title: "HOWTO \u2014 Workflow A is finally working \u2014 what changed"
sources:
- type: design
  path: docs/HOWTO.md
  section: "Workflow A is finally working \u2014 what changed"
last_generated_commit: ''
confidence: high
tags:
- docs
- HOWTO
created_at: 1783195000.850334
updated_at: 1783195000.850334
---


After TASK-OWUI-AUDIO-DROP-001 lands, three configuration items handle the gaps that previously broke chat-drop:

1. **`AIOHTTP_CLIENT_TIMEOUT_TOOL_SERVER_DATA=1800`** lifts OWUI's default ~60s tool-call timeout to 30 minutes.
2. **`WEBUI_SECRET_KEY`** is auto-generated and persistent so MCP tool registrations survive container rebuilds.
3. **`scripts/openwebui_init.py`** auto-registers the `portal_mlx_transcribe` MCP server on launch — no manual UI clicks.

**Sanity check after a fresh deploy:**
```bash
./tests/integration/test_owui_audio_drop.sh
