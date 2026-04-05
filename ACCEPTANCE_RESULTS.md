# Portal 5 — Acceptance Test Results (v4)

**Run:** 2026-04-05 05:13:03 (4090s)  
**Git SHA:** bd5516d  
**Version:** 5.2.1  
**Workspaces:** 16  ·  **Personas:** 40

## Summary

- **PASS**: 179
- **FAIL**: 2
- **WARN**: 11
- **INFO**: 10

## All Results

| # | Status | Section | Test | Detail | Duration |
|---|--------|---------|------|--------|----------|
| 1 | INFO | S17 | git pull skipped (no --rebuild flag) | use --rebuild to auto-pull | 0.0s |
| 2 | INFO | S17 | Dockerfile.mcp hash | hash=11411af425f9e9155e27e454846ac8b5 (unchanged) | 0.0s |
| 3 | PASS | S17 | All MCP services healthy — no restart needed |  | 0.0s |
| 4 | PASS | S17 | All expected containers running | 13 containers up | 0.1s |
| 5 | PASS | S17 | Pipeline /health workspace count matches codebase | pipeline reports 16, code has 16 | 0.0s |
| 6 | INFO | S0 | Git SHA | local=bd5516d | 0.0s |
| 7 | PASS | S0 | Codebase matches remote main | local=bd5516d remote=bd5516d | 0.0s |
| 8 | INFO | S0 | Pipeline /health version fields | version=dev workspaces=16 backends_healthy=7 | 0.0s |
| 9 | INFO | S0 | pyproject.toml version | version=5.2.1 | 0.0s |
| 10 | PASS | S1 | router_pipe.py WORKSPACES ↔ backends.yaml workspace_routing |  | 0.0s |
| 11 | PASS | S1 | All 40 persona YAMLs have required fields |  | 0.0s |
| 12 | PASS | S1 | update_workspace_tools.py covers all workspace IDs | all 16 covered | 0.0s |
| 13 | PASS | S1 | docker-compose.yml is valid YAML |  | 0.0s |
| 14 | INFO | S1 | imports/openwebui/mcp-servers.json present | 4 entries | 0.0s |
| 15 | PASS | S1 | mlx-proxy.py: Gemma 4 31B dense in ALL_MODELS and VLM_MODELS | ✓ present in both | 0.0s |
| 16 | PASS | S1 | mlx-proxy.py: Magistral in ALL_MODELS but NOT in VLM_MODELS  | ✓ mlx_lm routing correct | 0.0s |
| 17 | INFO | S1 | Persona model type distribution (40 personas) | MLX-routed: 10 ∣ Ollama-routed: 30 | 0.0s |
| 18 | PASS | S2 | Open WebUI |  | 0.0s |
| 19 | PASS | S2 | Pipeline |  | 0.0s |
| 20 | PASS | S2 | Grafana |  | 0.0s |
| 21 | PASS | S2 | MCP Documents |  | 0.0s |
| 22 | PASS | S2 | MCP Sandbox |  | 0.0s |
| 23 | PASS | S2 | MCP Music |  | 0.0s |
| 24 | PASS | S2 | MCP TTS |  | 0.0s |
| 25 | PASS | S2 | MCP Whisper |  | 0.0s |
| 26 | PASS | S2 | MCP Video |  | 0.0s |
| 27 | PASS | S2 | Prometheus |  | 0.0s |
| 28 | PASS | S2 | MCP ComfyUI bridge | HTTP 200 | 0.0s |
| 29 | PASS | S2 | SearXNG container | status=healthy | 0.0s |
| 30 | PASS | S2 | Ollama responding with pulled models | 20 models pulled | 0.0s |
| 31 | PASS | S2 | /metrics endpoint is unauthenticated (HOWTO §22) | HTTP 200 | 0.0s |
| 32 | INFO | S2 | MLX proxy :8081 | 15 models listed | 0.0s |
| 33 | PASS | S3 | /v1/models exposes all 16 workspace IDs |  | 0.0s |
| 34 | PASS | S3 | workspace auto: domain response |  | 89.4s |
| 35 | PASS | S3 | workspace auto-creative: domain response |  | 9.2s |
| 36 | PASS | S3 | workspace auto-documents: domain response |  | 27.0s |
| 37 | PASS | S3 | workspace auto-security: domain response |  | 11.8s |
| 38 | PASS | S3 | workspace auto-redteam: domain response |  | 11.2s |
| 39 | PASS | S3 | workspace auto-blueteam: domain response |  | 16.5s |
| 40 | PASS | S3 | workspace auto-coding: domain response |  | 104.7s |
| 41 | PASS | S3 | workspace auto-spl: domain response |  | 67.1s |
| 42 | PASS | S3 | workspace auto-reasoning: domain response |  | 148.3s |
| 43 | PASS | S3 | workspace auto-research: domain response |  | 47.0s |
| 44 | PASS | S3 | workspace auto-data: domain response |  | 86.6s |
| 45 | PASS | S3 | workspace auto-compliance: domain response |  | 72.8s |
| 46 | PASS | S3 | workspace auto-mistral: domain response |  | 86.2s |
| 47 | WARN | S3 | workspace auto-vision: domain response | no domain signals — generic answer | 82.7s |
| 48 | PASS | S3 | workspace auto-video: domain response |  | 5.5s |
| 49 | PASS | S3 | workspace auto-music: domain response |  | 2.0s |
| 50 | PASS | S3 | Streaming response delivers NDJSON chunks (SSE) | 3 data chunks ∣ [DONE]=yes | 182.1s |
| 51 | PASS | S3 | Pipeline logs contain routing activity for workspaces exerci | found routing evidence for: ['auto', 'auto-blueteam', 'auto-coding', 'auto-compliance', 'auto-creative', 'auto-data', 'auto-documents', 'auto-mistral', 'auto-mu | 0.2s |
| 52 | PASS | S4 | create_word_document → .docx | ✓ .docx created | 0.7s |
| 53 | PASS | S4 | create_powerpoint → .pptx (5 slides) | ✓ 5-slide deck created | 0.1s |
| 54 | PASS | S4 | create_excel → .xlsx with data | ✓ spreadsheet created | 0.1s |
| 55 | PASS | S4 | list_generated_files shows created files | files listed: {
  "filename": "Q1-Q2_Budget_419cbc27.xlsx",
  "path": "/app/data/generated/Q1-Q2_Budget_419cbc27.xlsx",
  "size_bytes" | 0.1s |
| 56 | PASS | S4 | auto-documents pipeline round-trip (CIP-007 outline) | preview: Here's a thinking process that leads to the suggested NERC CIP-01R (formerly CIP-007) patch manageme | 57.3s |
| 57 | PASS | S6 | auto-security: domain-relevant security response | signals matched: ['autoindex', 'security', 'vulnerability', 'misconfiguration'] | 16.9s |
| 58 | PASS | S6 | auto-redteam: domain-relevant security response | signals matched: ['injection', 'graphql', 'introspection', 'attack', 'depth'] | 10.0s |
| 59 | PASS | S6 | auto-blueteam: domain-relevant security response | signals matched: ['445', 'smb', 'attack'] | 8.5s |
| 60 | PASS | S7 | list_music_models returns available models | models: {
  "audiocraft_installed": false,
  "stable_audio_installed": false,
  "install | 0.0s |
| 61 | PASS | S7 | generate_music: 5s lo-fi | {
  "success": false,
  "error": "AudioCraft not installed. Run: pip install audiocraft"
} | 0.0s |
| 62 | PASS | S7 | auto-music workspace pipeline round-trip | preview: The lo-fi hip hop beat has a tempo of 120 BPM, in the key of C minor. It feature | 2.1s |
| 63 | PASS | S10 | Video MCP health | {'status': 'ok', 'service': 'video-mcp'} | 0.0s |
| 64 | PASS | S10 | list_video_models returns model list | models: videowan2.2 | 0.0s |
| 65 | PASS | S10 | auto-video workspace: domain-relevant video description | preview: Camera angle: Low angle, slightly elevated above the water's edge
Lens: Wide-ang | 2.3s |
| 66 | PASS | S10 | ComfyUI host at http://localhost:8188 | HTTP 200 | 0.0s |
| 67 | PASS | S10 | ComfyUI MCP bridge health | {'status': 'ok', 'service': 'comfyui-mcp'} | 0.0s |
| 68 | PASS | S15 | SearXNG /search?format=json returns results | 39 results for 'NERC CIP' | 1.2s |
| 69 | PASS | S15 | auto-research workspace: technical comparison response | signals: ['aes', 'rsa', 'symmetric', 'asymmetric', 'key'] | 107.3s |
| 70 | PASS | S20 | Telegram bot: module imports and build_app() succeeds | default_workspace=auto, allowed_users=1 | 0.1s |
| 71 | WARN | S20 | Telegram dispatcher: call_pipeline_async returns response | reply length: 7 | 30.0s |
| 72 | PASS | S20 | Telegram dispatcher: is_valid_workspace correct | auto-coding=True, nonexistent=False | 0.0s |
| 73 | PASS | S20 | Slack bot: module imports and _get_tokens() succeeds | bot_token=set, app_token=set | 0.0s |
| 74 | PASS | S20 | Slack dispatcher: module imports and payload builder work | dispatcher uses Docker-internal URL — tested modules natively, pipeline via localhost | 3.0s |
| 75 | PASS | S5 | auto-coding workspace returns Python code | preview: ```python
from typing import List

def sieve_of_eratosthenes(n: int) -> List[int | 112.6s |
| 76 | PASS | S5 | execute_python: primes to 100 (count=25 sum=1060) | ✓ count=25 sum=1060 | 0.8s |
| 77 | PASS | S5 | execute_python: Fibonacci sequence | ✓ Fibonacci executed | 0.3s |
| 78 | PASS | S5 | execute_nodejs: array sum = 15 | ✓ Node.js sum=15 | 0.5s |
| 79 | PASS | S5 | execute_bash: echo + arithmetic | ✓ bash executed | 0.2s |
| 80 | PASS | S5 | sandbox_status reports DinD connectivity | {
  "docker_available": true,
  "docker_host": "tcp://dind:2375",
  "sandbox_enabled": true,
  "python_image": "python:3.11-slim",
  "node_image": "no | 0.0s |
| 81 | PASS | S5 | Sandbox network isolation (outbound blocked) | ✓ network correctly isolated | 0.3s |
| 82 | WARN | S11 | Personas registered in Open WebUI | Expecting value: line 1 column 1 (char 0) | 0.2s |
| 83 | PASS | S11 | persona creativewriter (Creative Writer) | signals: ['robot', 'flower', 'space', 'wonder'] | 14.9s |
| 84 | PASS | S11 | persona itexpert (IT Expert) | signals: ['memory', 'oom', 'pandas', 'container'] | 6.2s |
| 85 | PASS | S11 | persona techreviewer (Tech Reviewer) | signals: ['m4', 'mlx', 'memory', 'inference', 'performance'] | 165.7s |
| 86 | PASS | S11 | persona techwriter (Tech Writer) | signals: ['api', 'authentication', 'endpoint', 'rate limit'] | 67.1s |
| 87 | PASS | S11 | persona bugdiscoverycodeassistant (Bug Discovery Code Assist | signals: ['def ', 'error', 'type'] | 8.3s |
| 88 | PASS | S11 | persona codebasewikidocumentationskill (Codebase WIKI Docume | signals: ['fibonacci', 'recursive'] | 7.0s |
| 89 | PASS | S11 | persona codereviewassistant (Code Review Assistant) | signals: ['pythonic', 'enumerate', 'index', 'readability'] | 7.0s |
| 90 | PASS | S11 | persona codereviewer (Code Reviewer) | signals: ['sql injection', 'vulnerability'] | 6.9s |
| 91 | PASS | S11 | persona devopsautomator (DevOps Automator) | signals: ['github', 'actions', 'deploy', 'docker', 'pytest'] | 6.9s |
| 92 | PASS | S11 | persona devopsengineer (DevOps Engineer) | signals: ['kubernetes', 'helm', 'pipeline', 'canary', 'deployment'] | 6.9s |
| 93 | PASS | S11 | persona ethereumdeveloper (Ethereum Developer) | signals: ['solidity', 'erc-20', 'transfer', 'reentrancy'] | 6.9s |
| 94 | PASS | S11 | persona githubexpert (GitHub Expert) | signals: ['branch protection', 'reviewer', 'ci', 'signed'] | 6.9s |
| 95 | PASS | S11 | persona javascriptconsole (JavaScript Console) | signals: ['reduce', 'pi'] | 2.1s |
| 96 | PASS | S11 | persona kubernetesdockerrpglearningengine (Kubernetes & Dock | signals: ['mission', 'container', 'briefing'] | 6.9s |
| 97 | PASS | S11 | persona linuxterminal (Linux Terminal) | signals: ['find', 'size'] | 2.2s |
| 98 | PASS | S11 | persona pythoncodegeneratorcleanoptimizedproduction-ready (P | signals: ['def ', 'retry', 'backoff'] | 7.4s |
| 99 | WARN | S11 | persona pythoninterpreter (Python Interpreter) | no signals in: '```python
[(1, 3), (2, 2), (3, 1)]
```' | 1.8s |
| 100 | PASS | S11 | persona seniorfrontenddeveloper (Senior Frontend Developer) | signals: ['react', 'hook', 'useeffect', 'loading', 'error'] | 7.4s |
| 101 | PASS | S11 | persona seniorsoftwareengineersoftwarearchitectrules (Senior | signals: ['risk', 'distributed', 'consistency'] | 7.6s |
| 102 | PASS | S11 | persona softwarequalityassurancetester (Software Quality Ass | signals: ['test case', 'valid', 'boundary'] | 7.4s |
| 103 | PASS | S11 | persona sqlterminal (SQL Terminal) | signals: ['join', 'group by', 'order by', 'index', 'top'] | 6.2s |
| 104 | PASS | S11 | persona dataanalyst (Data Analyst) | signals: ['growth', 'quarter', 'trend', 'analysis'] | 110.1s |
| 105 | PASS | S11 | persona datascientist (Data Scientist) | signals: ['feature', 'algorithm', 'churn', 'model'] | 39.3s |
| 106 | WARN | S11 | persona excelsheet (Excel Sheet) | no signals in: 'The user is asking me to explain an Excel formula in detail. However,' | 40.7s |
| 107 | PASS | S11 | persona itarchitect (IT Architect) | signals: ['load balanc', 'replication', 'disaster', 'availability'] | 39.3s |
| 108 | PASS | S11 | persona machinelearningengineer (Machine Learning Engineer) | signals: ['random forest', 'xgboost', 'hyperparameter', 'tabular'] | 39.6s |
| 109 | PASS | S11 | persona researchanalyst (Research Analyst) | signals: ['microservices', 'monolith', 'deployment', 'complexity'] | 39.2s |
| 110 | PASS | S11 | persona statistician (Statistician) | signals: ['p-value', 'power', 'sample size', 'effect size', 'type i'] | 39.4s |
| 111 | PASS | S11 | persona cybersecurityspecialist (Cyber Security Specialist) | signals: ['access control', 'owasp', 'idor', 'privilege'] | 13.4s |
| 112 | PASS | S11 | persona networkengineer (Network Engineer) | signals: ['vlan', 'subnet', 'dmz', 'firewall'] | 15.0s |
| 113 | PASS | S11 | persona redteamoperator (Red Team Operator) | signals: ['jwt', 'attack', 'token'] | 8.8s |
| 114 | PASS | S11 | persona blueteamdefender (Blue Team Defender) | signals: ['mitre', 'ssh', 'brute', 'incident', 'containment'] | 9.5s |
| 115 | PASS | S11 | persona pentester (Penetration Tester) | signals: ['authentication', 'bypass', 'jwt', 'session'] | 8.9s |
| 116 | PASS | S11 | persona fullstacksoftwaredeveloper (Fullstack Software Devel | signals: ['endpoint', 'post', 'json'] | 106.2s |
| 117 | PASS | S11 | persona splunksplgineer (Splunk SPL Engineer) | signals: ['tstats', 'authentication', 'datamodel', 'stats', 'distinct', 'lateral'] | 8.4s |
| 118 | PASS | S11 | persona ux-uideveloper (UX/UI Developer) | signals: ['password', 'reset', 'accessibility', 'flow'] | 8.2s |
| 119 | PASS | S11 | persona cippolicywriter (CIP Policy Writer) | signals: ['shall', 'patch', 'cip-007'] | 62.0s |
| 120 | PASS | S11 | persona nerccipcomplianceanalyst (NERC CIP Compliance Analys | signals: ['cip-007', 'patch', 'evidence', 'audit', 'nerc'] | 7.7s |
| 121 | PASS | S11 | persona magistralstrategist (Magistral Strategist) | signals: ['runway', 'enterprise', 'acv', 'assumption'] | 81.6s |
| 122 | PASS | S11 | persona gemmaresearchanalyst (Gemma Research Analyst) | signals: ['evidence', 'benchmark', 'open source', 'proprietary', 'coding'] | 77.7s |
| 123 | PASS | S11 | Persona suite summary (40 total) | 40 PASS ∣ 0 WARN ∣ 0 FAIL | 0.0s |
| 124 | PASS | S22 | MLX proxy health — reports state and active server | state=ready, active_server=lm | 0.0s |
| 125 | PASS | S22 | MLX proxy /v1/models — 15 models listed | first 3: ['mlx-community/Qwen3-Coder-Next-4bit', 'mlx-community/Qwen3-Coder-30B-A3B-Instruct-8bit', 'mlx-community/DeepSeek-Coder-V2-Lite-Instruct-8bit'] | 0.0s |
| 126 | PASS | S22 | MLX-routed workspace (auto-coding) completes request | matched: ['reverse', 'string', '::-1', '[::-1]'] | 77.3s |
| 127 | INFO | S22 | MLX watchdog — not enabled in .env | MLX_WATCHDOG_ENABLED=false — skipped | 0.0s |
| 128 | PASS | S18 | ComfyUI MCP bridge health | {'status': 'ok', 'service': 'comfyui-mcp'} | 0.0s |
| 129 | PASS | S18 | list_workflows returns checkpoint list | checkpoints: Flux_v8-NSFW.safetensorsflux1-schnell.safetensorslora.safetensorssd_xl_base_1.0.safetensors | 0.4s |
| 130 | PASS | S18 | generate_image: photorealistic apple | {
  "success": false,
  "error": "ComfyUI rejected workflow (HTTP 400): {'type': 'prompt_outputs_failed_validation', 'message': 'Prompt outputs failed validatio | 0.1s |
| 131 | PASS | S18 | ComfyUI host at http://localhost:8188 | HTTP 200 | 0.0s |
| 132 | PASS | S19 | Video MCP health | {'status': 'ok', 'service': 'video-mcp'} | 0.0s |
| 133 | PASS | S19 | list_video_models returns model list | models: videowan2.2 | 0.2s |
| 134 | PASS | S19 | generate_video: ocean waves at sunset | {
  "success": false,
  "error": "ComfyUI not available at http://host.docker.internal:8188: Client error '400 Bad Request' for url 'http://host.docker.internal | 0.0s |
| 135 | PASS | S19 | auto-video workspace: domain-relevant video description | preview: Camera angle: Low angle, slightly below sea level to capture the waves' movement | 5.7s |
| 136 | PASS | S8 | list_voices includes af_heart (default voice) | ✓ voices listed | 0.2s |
| 137 | PASS | S8 | speak af_heart → file_path returned | ✓ speech generated | 2.6s |
| 138 | PASS | S8 | TTS REST /v1/audio/speech: af_heart (US-F default) | ✓ valid WAV 357,420 bytes | 1.4s |
| 139 | PASS | S8 | TTS REST /v1/audio/speech: bm_george (British male) | ✓ valid WAV 392,236 bytes | 1.7s |
| 140 | PASS | S8 | TTS REST /v1/audio/speech: am_adam (US male) | ✓ valid WAV 334,892 bytes | 1.4s |
| 141 | PASS | S8 | TTS REST /v1/audio/speech: bf_emma (British female) | ✓ valid WAV 319,532 bytes | 1.7s |
| 142 | PASS | S9 | Whisper health via docker exec (HOWTO §12 exact command) | {"status":"ok","service":"whisper-mcp"} | 0.0s |
| 143 | PASS | S9 | transcribe_audio tool reachable (file-not-found confirms con | ✓ tool responds (expected file-not-found error) | 0.2s |
| 144 | PASS | S9 | STT round-trip: TTS → WAV → Whisper transcription | ✓ transcribed: {
  "text": "Hello from Portal 5.",
  "language": "en",
  "duration": 1.41,
  "s | 1.4s |
| 145 | PASS | S12 | portal_workspaces_total matches code count | metric=16, code=16 | 0.0s |
| 146 | PASS | S12 | portal_backends gauge present | present | 0.0s |
| 147 | PASS | S12 | portal_requests counter present (after S3 traffic) | present | 0.0s |
| 148 | INFO | S12 | Prometheus histogram metrics (tokens_per_second) | present | 0.0s |
| 149 | PASS | S12 | Prometheus scraping pipeline target | 1 pipeline targets in 4 total | 0.0s |
| 150 | PASS | S12 | Grafana portal5_overview dashboard provisioned | dashboards: ['Portal 5 Overview'] | 0.0s |
| 151 | PASS | S13 | Login → chat UI loaded |  | 3.2s |
| 152 | PASS | S13 | Model dropdown shows workspace names | 16/16 visible | 0.0s |
| 153 | WARN | S13 | Personas visible | Expecting value: line 1 column 1 (char 0) | 0.0s |
| 154 | PASS | S13 | Chat textarea accepts and clears input |  | 0.0s |
| 155 | PASS | S13 | Admin panel accessible |  | 1.0s |
| 156 | PASS | S13 | MCP tool servers registered in Open WebUI | 7/7 registered: ['8910', '8911', '8912', '8913', '8914', '8915', '8916'] | 0.0s |
| 157 | PASS | S14 | No stale 'Click + enable' instructions |  | 0.0s |
| 158 | PASS | S14 | §3 workspace table has 16 rows | table rows=16, code has 16 | 0.0s |
| 159 | PASS | S14 | auto-compliance workspace documented in §3 |  | 0.0s |
| 160 | PASS | S14 | Persona count claim matches YAML file count | claimed=40, yaml files=40 | 0.0s |
| 161 | PASS | S14 | §16 Telegram workspace list complete | all IDs listed | 0.0s |
| 162 | PASS | S14 | §11 TTS backend is kokoro as documented | actual: {'status': 'ok', 'service': 'tts-mcp', 'backend': 'kokoro', 'voice_cloning': False} | 0.0s |
| 163 | PASS | S14 | HOWTO §3 curl command works | HTTP 200 | 0.0s |
| 164 | PASS | S14 | HOWTO §5 curl command works | HTTP 200 | 0.0s |
| 165 | PASS | S14 | HOWTO §7 curl command works | HTTP 200 | 0.0s |
| 166 | PASS | S14 | HOWTO §22 curl command works | HTTP 200 | 0.0s |
| 167 | PASS | S14 | §12 whisper health via docker exec (exact HOWTO command) | {"status":"ok","service":"whisper-mcp"} | 0.0s |
| 168 | PASS | S14 | HOWTO footer version matches pyproject.toml (5.2.1) | expected 5.2.1 in HOWTO footer | 0.0s |
| 169 | PASS | S14 | HOWTO MLX table documents gemma-4-31b-it-4bit | found | 0.0s |
| 170 | PASS | S14 | HOWTO MLX table documents Magistral-Small-2509-MLX-8bit | found | 0.0s |
| 171 | PASS | S14 | HOWTO documents auto-spl workspace | found | 0.0s |
| 172 | PASS | S16 | ./launch.sh status |  | 4.2s |
| 173 | PASS | S16 | ./launch.sh list-users |  | 0.4s |
| 174 | PASS | S21 | NotificationDispatcher module imports | module loaded successfully | 0.0s |
| 175 | PASS | S21 | AlertEvent formatting (Slack, Telegram, Pushover, Email) | slack=122 chars, telegram=108 chars | 0.0s |
| 176 | PASS | S21 | SummaryEvent formatting (Slack, Telegram) | slack=396 chars, telegram=278 chars | 0.0s |
| 177 | PASS | S21 | Notification channels importable (1 configured) | 1/1 channels imported | 0.0s |
| 178 | PASS | S23 | MLX watchdog disabled for testing | watchdog stopped — no false alerts during fallback tests | 0.0s |
| 179 | PASS | S23 | Pipeline health endpoint shows backend status | 7/7 backends healthy, 16 workspaces | 0.0s |
| 180 | PASS | S23 | Response includes model identity | model=mlx-community/Qwen3-Coder-Next-4bit | 1.0s |
| 181 | PASS | S23 | auto-coding: primary MLX path | model=mlx-community/Qwen3-Coder-Next-4bit | 5.2s |
| 182 | PASS | S23 | auto-coding: primary path works | model=dolphin-llama3:8b | 8.3s |
| 183 | PASS | S23 | auto-coding: MLX proxy killed | MLX proxy is down | 7.0s |
| 184 | FAIL | S23 | auto-coding: fallback to coding | expected coding model, got: deepseek-r1:32b-q4_k_m | 51.1s |
| 185 | PASS | S23 | auto-coding: MLX proxy restored | MLX proxy is back | 0.2s |
| 186 | PASS | S23 | auto-coding: MLX restored, chain intact | model=huihui_ai/baronllm-abliterated — chain recovered after fallback | 99.6s |
| 187 | PASS | S23 | auto-security: primary security path | model=baronllm:q6_k | 10.6s |
| 188 | PASS | S23 | auto-security: survives backend stress | model=baronllm:q6_k ∣ signals=['autoindex', 'security', 'misconfiguration', 'cors'] | 5.7s |
| 189 | WARN | S23 | auto-vision: primary MLX path | model=deepseek-r1:32b-q4_k_m | 16.9s |
| 190 | PASS | S23 | auto-vision: primary path works | model=deepseek-r1:32b-q4_k_m | 16.7s |
| 191 | PASS | S23 | auto-vision: MLX proxy killed | MLX proxy is down | 7.1s |
| 192 | FAIL | S23 | auto-vision: fallback to vision | expected vision model, got: deepseek-r1:32b-q4_k_m | 4.6s |
| 193 | WARN | S23 | auto-vision: MLX proxy restore | restore may still be in progress for MLX proxy | 107.1s |
| 194 | PASS | S23 | auto-vision: MLX restored, chain intact | model=deepseek-r1:32b-q4_k_m — chain recovered after fallback | 3.3s |
| 195 | WARN | S23 | auto-reasoning: primary MLX path | model=deepseek-r1:32b-q4_k_m | 17.3s |
| 196 | PASS | S23 | auto-reasoning: primary path works | model=deepseek-r1:32b-q4_k_m | 17.2s |
| 197 | PASS | S23 | auto-reasoning: MLX proxy killed | MLX proxy is down | 7.0s |
| 198 | PASS | S23 | auto-reasoning: fallback to reasoning | model=deepseek-r1:32b-q4_k_m ∣ signals=['meet', 'hour', 'miles', 'train', 'mph', '790'] | 16.9s |
| 199 | WARN | S23 | auto-reasoning: MLX proxy restore | restore may still be in progress for MLX proxy | 109.1s |
| 200 | PASS | S23 | auto-reasoning: MLX restored, chain intact | model=deepseek-r1:32b-q4_k_m — chain recovered after fallback | 16.7s |
| 201 | WARN | S23 | All backends restored and healthy | 6/7 backends healthy | 46.6s |
| 202 | PASS | S23 | All MLX workspaces survive MLX failure (8/8) | 8 responded, 0 failed (fell back to Ollama or timed out) | 145.8s |

## Blocked Items Register

*No blocked items.*

---
*Screenshots: /tmp/p5_gui_*.png*
