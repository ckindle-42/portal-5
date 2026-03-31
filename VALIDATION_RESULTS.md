# Portal 5.2 Validation Results

**Run:** 2026-03-30 20:20:19

## Summary

- **PASS**: 38
- **WARN**: 9
- **INFO**: 9
- **SKIP**: 1

## Detailed Results

| Status | Section | Detail |
|---|---|---|
| PASS | Workspaces | All 13 workspace IDs present in pipeline |
| PASS | WS-Chat | auto → response: 'Four....' |
| PASS | WS-Chat | auto-coding → response: 'Thinking Process:

1.  **Analyze the Request:** The user wan...' (via reasoning) |
| PASS | WS-Chat | auto-security → response: 'A firewall is a network security system that monitors and co...' |
| PASS | WS-Chat | auto-redteam → response: 'SQL injection is a type of web application vulnerability whe...' |
| PASS | WS-Chat | auto-blueteam → response: ' An IDS, short for Intrusion Detection System, is a security...' |
| PASS | WS-Chat | auto-creative → response: 'Sunset's golden hue, ocean's rhythmic song, calm night's gen...' |
| PASS | WS-Chat | auto-reasoning → response: ' Please respond in English.
Okay, so I need to figure out wh...' |
| PASS | WS-Chat | auto-documents → response: 'Thinking Process:

1.  **Analyze the Request:**
    *   Task...' (via reasoning) |
| PASS | WS-Chat | auto-video → response: 'As the sun descends below the horizon, it paints the sky wit...' |
| PASS | WS-Chat | auto-music → response: 'Jazz is a genre of music characterized by improvisation, syn...' |
| PASS | WS-Chat | auto-research → response: ' What is quantum computing?
</think>

Quantum computing leve...' |
| PASS | WS-Chat | auto-vision → response: 'Okay, the user is asking what I can analyze in images, and t...' (via reasoning) |
| PASS | WS-Chat | auto-data → response: ' 0
Okay, so I need to figure out what a mean is. I've heard ...' |
| PASS | MCP-Health | ComfyUI :8910 → healthy |
| INFO | MCP-Tools | ComfyUI: ['generate_image', 'list_workflows', 'get_generation_status'] |
| PASS | MCP-Health | Video :8911 → healthy |
| INFO | MCP-Tools | Video: ['generate_video', 'list_video_models'] |
| PASS | MCP-Health | Music :8912 → healthy |
| INFO | MCP-Tools | Music: ['generate_music', 'generate_continuation', 'list_music_models'] |
| PASS | MCP-Health | Documents :8913 → healthy |
| INFO | MCP-Tools | Documents: ['create_word_document', 'create_powerpoint', 'create_excel', 'convert_document', 'list_generated_files'] |
| PASS | MCP-Health | Code :8914 → healthy |
| INFO | MCP-Tools | Code: ['execute_python', 'execute_nodejs', 'execute_bash', 'sandbox_status'] |
| PASS | MCP-Health | Whisper :8915 → healthy |
| INFO | MCP-Tools | Whisper: ['transcribe_audio'] |
| PASS | MCP-Health | TTS :8916 → healthy |
| INFO | MCP-Tools | TTS: ['speak', 'clone_voice', 'list_voices'] |
| WARN | DocCreate | Word: FastMCP SSE transport incompatible with httpx JSON-RPC POST — server healthy (see /tools above) |
| WARN | DocCreate | PPTX: FastMCP SSE transport incompatible with httpx JSON-RPC POST |
| WARN | DocCreate | Excel: FastMCP SSE transport incompatible with httpx JSON-RPC POST |
| WARN | Sandbox | execute_python: FastMCP SSE transport incompatible with httpx JSON-RPC POST |
| PASS | TTS | af_heart (American female): 90156 bytes, WAV=True |
| PASS | TTS | bm_george (British male): 94252 bytes, WAV=True |
| WARN | Music | generate_music: FastMCP SSE transport incompatible with httpx JSON-RPC POST |
| PASS | Image | ComfyUI running (v0.16.3) |
| WARN | Image | generate_image: FastMCP SSE transport incompatible with httpx JSON-RPC POST |
| WARN | Video | generate_video: FastMCP SSE transport incompatible with httpx JSON-RPC POST |
| PASS | AutoRoute | Security keywords through 'auto' → HTTP 200 |
| INFO | AutoRoute | Verify in logs: docker compose -f deploy/portal-5/docker-compose.yml logs portal-pipeline --tail=10 ∣ grep 'Auto-routing' |
| PASS | Metrics | Pipeline /metrics: has portal_* counters |
| PASS | Metrics | Prometheus → HTTP 200 |
| PASS | Metrics | Grafana → HTTP 200 |
| PASS | ToolWiring | All 13 workspace toolIds match expected MCP server assignments |
| WARN | ToolWiring | portal_import_bundle.json has 3 workspaces WITHOUT toolIds: ['auto', 'auto-reasoning', 'auto-research']. This bundle is NOT used by openwebui_init.py (it reads individual workspace files), but it IS a |
| INFO | ToolWiring | MCP servers registered: ['Portal ComfyUI', 'Portal Video', 'Portal Music', 'Portal Documents', 'Portal Code', 'Portal Whisper', 'Portal TTS'] |
| PASS | ToolWiring | Tool 'portal_code' → server 'Portal Code' registered |
| PASS | ToolWiring | Tool 'portal_comfyui' → server 'Portal ComfyUI' registered |
| PASS | ToolWiring | Tool 'portal_documents' → server 'Portal Documents' registered |
| PASS | ToolWiring | Tool 'portal_music' → server 'Portal Music' registered |
| PASS | ToolWiring | Tool 'portal_tts' → server 'Portal TTS' registered |
| PASS | ToolWiring | Tool 'portal_video' → server 'Portal Video' registered |
| SKIP | GUI | playwright not installed: pip install playwright && python3 -m playwright install chromium |
| PASS | HOWTO | No incorrect 'Click + → enable' pattern found |
| PASS | HOWTO | Workspace count claim (13) documented |
| PASS | HOWTO | HOWTO mentions automatic tool activation |
| WARN | HOWTO | portal_import_bundle.json workspaces lack toolIds — only individual workspace files have them. If a user manually imports the bundle instead of using automated seeding, tools won't be attached to work |

## Documentation Issues Found

### ToolWiring

portal_import_bundle.json has 3 workspaces WITHOUT toolIds: ['auto', 'auto-reasoning', 'auto-research']. This bundle is NOT used by openwebui_init.py (it reads individual workspace files), but it IS a reference file that could mislead manual imports. Consider updating it.

### HOWTO

portal_import_bundle.json workspaces lack toolIds — only individual workspace files have them. If a user manually imports the bundle instead of using automated seeding, tools won't be attached to workspaces. Fix: add toolIds to bundle workspaces, or document that the bundle is not the primary import path.

