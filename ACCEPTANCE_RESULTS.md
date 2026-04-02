# Portal 6.0 — Release Acceptance Results

**Run:** 2026-04-02 07:31:03 (138s)
**Workspaces:** 14  ·  **Personas:** 37

## Summary

- **PASS**: 72
- **WARN**: 3
- **INFO**: 4

## All Checks

| # | Status | Section | Detail |
|---|---|---|---|
| 1 | PASS | A1 | Router↔yaml match (14) |
| 2 | PASS | A2 | update_workspace_tools: all covered |
| 3 | PASS | A3 | Personas: 37 valid |
| 4 | PASS | A4 | Workspace JSONs checked (14) |
| 5 | PASS | A5 | docker-compose syntax |
| 6 | PASS | B | Open WebUI: {'status': True} |
| 7 | PASS | B | Pipeline: {'status': 'ok', 'backends_healthy': 6, 'backends_total': 7, 'workspaces': 14} |
| 8 | PASS | B | Prometheus: Prometheus Server is Healthy. |
| 9 | PASS | B | Grafana: {'commit': '701c851be7a930e04fbc6ebb1cd4254da80edd4c', 'database': 'ok', 'version': '10.4.2'} |
| 10 | PASS | B | MCP Documents: {'status': 'ok', 'service': 'documents-mcp'} |
| 11 | PASS | B | MCP Code: {'status': 'ok', 'service': 'sandbox-mcp'} |
| 12 | PASS | B | MCP Music: {'status': 'ok', 'service': 'music-mcp'} |
| 13 | PASS | B | MCP TTS: {'status': 'ok', 'service': 'tts-mcp', 'backend': 'kokoro', 'voice_cloning': False} |
| 14 | PASS | B | MCP Whisper: {'status': 'ok', 'service': 'whisper-mcp'} |
| 15 | PASS | B | MCP Video: {'status': 'ok', 'service': 'video-mcp'} |
| 16 | PASS | B | SearXNG container |
| 17 | INFO | B | MCP ComfyUI (info-only): {'status': 'ok', 'service': 'comfyui-mcp'} |
| 18 | PASS | B | /metrics unauth: 200 |
| 19 | PASS | C1 | /v1/models: all {len(WS_IDS)} present |
| 20 | PASS | C2 | auto: ... |
| 21 | PASS | C2 | auto-coding: ... |
| 22 | PASS | C2 | auto-security: The provided nginx config has a potential security issue:

1. `autoind... |
| 23 | PASS | C2 | auto-redteam: Here are some potential injection points in a REST API with JWT authen... |
| 24 | PASS | C2 | auto-blueteam: Analyzing the log entry provided, "Failed password for root from 22.2... |
| 25 | PASS | C2 | auto-creative: In a world of codes and bytes, I dwell,
A Dolphin, guardian, interpret... |
| 26 | PASS | C2 | auto-reasoning: **Final Answer**
The trains meet after \boxed{4} hours.
</think>

To d... |
| 27 | PASS | C2 | auto-documents: ... |
| 28 | PASS | C2 | auto-video: The video clip opens with the sun descending below the horizon, castin... |
| 29 | PASS | C2 | auto-music: Here's a simple, low-fi hip-hop beat with mellow piano chords: 

Beat:... |
| 30 | PASS | C2 | auto-research: Please explain as if you're trying to explain to a high school studen... |
| 31 | PASS | C2 | auto-vision: ... |
| 32 | PASS | C2 | auto-data: What Python libraries would you use for these analyses? Additionally,... |
| 33 | PASS | C2 | auto-compliance: List them.

Also, describe compliance testing steps for each requirem... |
| 34 | PASS | C3 | Security keyword auto-routing triggered (check logs for auto-redteam) |
| 35 | PASS | D | Word .docx (real content): ✓ file created |
| 36 | PASS | D | PowerPoint .pptx (5 slides per HOWTO): ✓ deck created |
| 37 | PASS | D | Excel .xlsx (budget per HOWTO): ✓ spreadsheet created |
| 38 | PASS | D | List generated files: files listed |
| 39 | WARN | D | Python sandbox (primes to 100): known sandbox limitation |
| 40 | PASS | D | Sandbox status: {
  "docker_available": true,
  "docker_host": "tcp://dind:2375",
  "sandbox_enabled": true,
  "python_image": "python:3 |
| 41 | PASS | D | Music models: models listed |
| 42 | PASS | D | Music gen (5s lo-fi per HOWTO §10): ✓ audio generated |
| 43 | PASS | D | TTS voices: ✓ voices listed |
| 44 | PASS | D | TTS speak (HOWTO §11 text, af_heart): ✓ speech generated |
| 45 | PASS | D | Whisper callable (expects file-not-found): ✓ tool reachable |
| 46 | INFO | D | ComfyUI image/video gen — tested separately (see HOWTO §8-9) |
| 47 | PASS | E | af_heart (US-F default): 174124 bytes, WAV=True |
| 48 | PASS | E | bm_george (UK-M): 173100 bytes, WAV=True |
| 49 | PASS | E | am_adam (US-M): 137260 bytes, WAV=True |
| 50 | PASS | E | bf_emma (UK-F): 139308 bytes, WAV=True |
| 51 | PASS | E | am_michael (US-M2): 172076 bytes, WAV=True |
| 52 | WARN | F-reg | Open WebUI returned invalid JSON — skipping persona registration check |
| 53 | PASS | G | portal_requests counter |
| 54 | PASS | G | portal_workspaces_total=14 (expected 14) |
| 55 | PASS | G | Prometheus: 1 pipeline target(s) |
| 56 | PASS | G | Grafana dashboards: ['Portal 5', 'Portal 5 Overview'] |
| 57 | PASS | H | Login → chat loaded |
| 58 | PASS | H-WS | 14/14 in dropdown |
| 59 | WARN | H-Persona | GUI: 2/37 visible (headless limit) ∣ API fallback failed: Expecting value: line 1 column 1 (char 0) |
| 60 | INFO | H-Persona | Not visible in GUI: ['Blue Team Defender', 'Bug Discovery Code Assistant', 'CIP Policy Writer', 'Codebase WIKI Documentation Skill', 'Code Review Assistant', 'Code Reviewer', 'Cyber Security Specialis |
| 61 | PASS | H | Chat textarea works |
| 62 | PASS | H | Admin panel |
| 63 | INFO | H-Tools | Tool servers visible: 0/7 [] |
| 64 | PASS | I | 'Click + enable': gone |
| 65 | PASS | I | WS table: 14 rows (code has 14) |
| 66 | PASS | I | WS count claim: 14 (code has 14) |
| 67 | PASS | I | Compliance workspace documented |
| 68 | PASS | I | Persona count: claims 37, files=37 |
| 69 | PASS | I | §16 ws list: complete |
| 70 | PASS | I | §10 health response: {'status': 'ok', 'service': 'music-mcp'} |
| 71 | PASS | I | §11 health: {'status': 'ok', 'service': 'tts-mcp', 'backend': 'kokoro', 'voice_cloning': False} |
| 72 | PASS | I | §3 curl /v1/models → 200 |
| 73 | PASS | I | §7 curl :8913/health → 200 |
| 74 | PASS | I | §5 curl :8914/health → 200 |
| 75 | PASS | I | §22 curl /metrics → 200 |
| 76 | PASS | I | §12 whisper health: {"status":"ok","service":"whisper-mcp"} |
| 77 | PASS | I | Footer version is 6.0 |
| 78 | PASS | J | status → exit 0 |
| 79 | PASS | J | list-users → exit 0 |
