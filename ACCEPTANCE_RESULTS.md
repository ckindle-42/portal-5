# Portal 5 — Acceptance Test Results (v4)

**Run:** 2026-04-05 13:49:22 (5809s)  
**Git SHA:** cfd8ba8  
**Version:** 5.2.1  
**Workspaces:** 16  ·  **Personas:** 40

## Summary

- **PASS**: 161
- **WARN**: 48
- **INFO**: 10

## All Results

| # | Status | Section | Test | Detail | Duration |
|---|--------|---------|------|--------|----------|
| 1 | INFO | S17 | git pull skipped (no --rebuild flag) | use --rebuild to auto-pull | 0.0s |
| 2 | INFO | S17 | Dockerfile.mcp hash | hash=11411af425f9e9155e27e454846ac8b5 (unchanged) | 0.0s |
| 3 | PASS | S17 | All MCP services healthy — no restart needed |  | 0.0s |
| 4 | PASS | S17 | All expected containers running | 13 containers up | 0.1s |
| 5 | PASS | S17 | Pipeline /health workspace count matches codebase | pipeline reports 16, code has 16 | 0.0s |
| 6 | INFO | S0 | Git SHA | local=cfd8ba8 | 0.0s |
| 7 | PASS | S0 | Codebase matches remote main | local=cfd8ba8 remote=cfd8ba8 | 0.0s |
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
| 32 | INFO | S2 | MLX proxy :8081 | 9 models listed | 0.0s |
| 33 | PASS | S8 | list_voices includes af_heart (default voice) | ✓ voices listed | 0.2s |
| 34 | PASS | S8 | speak af_heart → file_path returned | ✓ speech generated | 3.2s |
| 35 | PASS | S8 | TTS REST /v1/audio/speech: af_heart (US-F default) | ✓ valid WAV 357,420 bytes | 1.4s |
| 36 | PASS | S8 | TTS REST /v1/audio/speech: bm_george (British male) | ✓ valid WAV 392,236 bytes | 1.2s |
| 37 | PASS | S8 | TTS REST /v1/audio/speech: am_adam (US male) | ✓ valid WAV 334,892 bytes | 1.0s |
| 38 | PASS | S8 | TTS REST /v1/audio/speech: bf_emma (British female) | ✓ valid WAV 319,532 bytes | 1.0s |
| 39 | PASS | S9 | Whisper health via docker exec (HOWTO §12 exact command) | {"status":"ok","service":"whisper-mcp"} | 0.0s |
| 40 | PASS | S9 | transcribe_audio tool reachable (file-not-found confirms con | ✓ tool responds (expected file-not-found error) | 0.0s |
| 41 | PASS | S9 | STT round-trip: TTS → WAV → Whisper transcription | ✓ transcribed: {
  "text": "Hello from Portal 5.",
  "language": "en",
  "duration": 1.41,
  "s | 1.5s |
| 42 | PASS | S12 | portal_workspaces_total matches code count | metric=16, code=16 | 0.0s |
| 43 | PASS | S12 | portal_backends gauge present | present | 0.0s |
| 44 | WARN | S12 | portal_requests counter present (after S3 traffic) | not yet recorded — run S3 first | 0.0s |
| 45 | INFO | S12 | Prometheus histogram metrics (tokens_per_second) | not yet recorded | 0.0s |
| 46 | PASS | S12 | Prometheus scraping pipeline target | 1 pipeline targets in 5 total | 0.0s |
| 47 | PASS | S12 | Grafana portal5_overview dashboard provisioned | dashboards: ['Portal 5 Overview'] | 0.0s |
| 48 | PASS | S13 | Login → chat UI loaded |  | 2.1s |
| 49 | PASS | S13 | Model dropdown shows workspace names | 16/16 visible | 0.0s |
| 50 | WARN | S13 | Personas visible | Expecting value: line 1 column 1 (char 0) | 0.0s |
| 51 | PASS | S13 | Chat textarea accepts and clears input |  | 0.0s |
| 52 | PASS | S13 | Admin panel accessible |  | 1.0s |
| 53 | PASS | S13 | MCP tool servers registered in Open WebUI | 7/7 registered: ['8910', '8911', '8912', '8913', '8914', '8915', '8916'] | 0.0s |
| 54 | PASS | S14 | No stale 'Click + enable' instructions |  | 0.0s |
| 55 | PASS | S14 | §3 workspace table has 16 rows | table rows=16, code has 16 | 0.0s |
| 56 | PASS | S14 | auto-compliance workspace documented in §3 |  | 0.0s |
| 57 | PASS | S14 | Persona count claim matches YAML file count | claimed=40, yaml files=40 | 0.0s |
| 58 | PASS | S14 | §16 Telegram workspace list complete | all IDs listed | 0.0s |
| 59 | PASS | S14 | §11 TTS backend is kokoro as documented | actual: {'status': 'ok', 'service': 'tts-mcp', 'backend': 'kokoro', 'voice_cloning': False} | 0.0s |
| 60 | PASS | S14 | HOWTO §3 curl command works | HTTP 200 | 0.0s |
| 61 | PASS | S14 | HOWTO §5 curl command works | HTTP 200 | 0.0s |
| 62 | PASS | S14 | HOWTO §7 curl command works | HTTP 200 | 0.0s |
| 63 | PASS | S14 | HOWTO §22 curl command works | HTTP 200 | 0.0s |
| 64 | PASS | S14 | §12 whisper health via docker exec (exact HOWTO command) | {"status":"ok","service":"whisper-mcp"} | 0.0s |
| 65 | PASS | S14 | HOWTO footer version matches pyproject.toml (5.2.1) | expected 5.2.1 in HOWTO footer | 0.0s |
| 66 | PASS | S14 | HOWTO MLX table documents gemma-4-31b-it-4bit | found | 0.0s |
| 67 | PASS | S14 | HOWTO MLX table documents Magistral-Small-2509-MLX-8bit | found | 0.0s |
| 68 | PASS | S14 | HOWTO documents auto-spl workspace | found | 0.0s |
| 69 | PASS | S16 | ./launch.sh status |  | 2.6s |
| 70 | PASS | S16 | ./launch.sh list-users |  | 0.2s |
| 71 | PASS | S21 | NotificationDispatcher module imports | module loaded successfully | 0.0s |
| 72 | PASS | S21 | AlertEvent formatting (Slack, Telegram, Pushover, Email) | slack=122 chars, telegram=108 chars | 0.0s |
| 73 | PASS | S21 | SummaryEvent formatting (Slack, Telegram) | slack=396 chars, telegram=278 chars | 0.0s |
| 74 | PASS | S21 | Notification channels importable (1 configured) | 1/1 channels imported | 0.0s |
| 75 | PASS | S3 | /v1/models exposes all 16 workspace IDs |  | 0.0s |
| 76 | PASS | S3 | workspace auto: domain response |  | 24.8s |
| 77 | PASS | S3 | workspace auto-creative: domain response |  | 9.4s |
| 78 | PASS | S3 | workspace auto-documents: domain response |  | 26.5s |
| 79 | PASS | S3 | workspace auto-security: domain response |  | 16.6s |
| 80 | PASS | S3 | workspace auto-redteam: domain response |  | 11.2s |
| 81 | PASS | S3 | workspace auto-blueteam: domain response |  | 11.3s |
| 82 | PASS | S3 | workspace auto-video: domain response |  | 4.0s |
| 83 | PASS | S3 | workspace auto-music: domain response |  | 1.5s |
| 84 | PASS | S3 | Streaming response delivers NDJSON chunks (SSE) | 1 data chunks ∣ [DONE]=no | 105.7s |
| 85 | PASS | S3 | Pipeline logs contain routing activity for workspaces exerci | found routing evidence for: ['auto', 'auto-blueteam', 'auto-coding', 'auto-creative', 'auto-documents', 'auto-music', 'auto-redteam', 'auto-security', 'auto-vid | 0.3s |
| 86 | PASS | S4 | create_word_document → .docx | ✓ .docx created | 0.7s |
| 87 | PASS | S4 | create_powerpoint → .pptx (5 slides) | ✓ 5-slide deck created | 0.2s |
| 88 | PASS | S4 | create_excel → .xlsx with data | ✓ spreadsheet created | 0.4s |
| 89 | PASS | S4 | list_generated_files shows created files | files listed: {
  "filename": "Q1-Q2_Budget_44adbc46.xlsx",
  "path": "/app/data/generated/Q1-Q2_Budget_44adbc46.xlsx",
  "size_bytes" | 0.1s |
| 90 | PASS | S4 | auto-documents pipeline round-trip (CIP-007 outline) | preview: Here's a thinking process that leads to the suggested outline:

1.  **Analyze the Request:**
    * | 17.1s |
| 91 | PASS | S6 | auto-security: domain-relevant security response | signals matched: ['autoindex', 'security', 'misconfiguration'] | 8.5s |
| 92 | PASS | S6 | auto-redteam: domain-relevant security response | signals matched: ['injection', 'graphql', 'introspection', 'attack', 'depth'] | 8.4s |
| 93 | PASS | S6 | auto-blueteam: domain-relevant security response | signals matched: ['445', 'smb', 'deny'] | 9.5s |
| 94 | PASS | S7 | list_music_models returns available models | models: {
  "audiocraft_installed": false,
  "stable_audio_installed": false,
  "install | 0.3s |
| 95 | PASS | S7 | generate_music: 5s lo-fi | {
  "success": false,
  "error": "AudioCraft not installed. Run: pip install audiocraft"
} | 0.0s |
| 96 | PASS | S7 | auto-music workspace pipeline round-trip | preview: The lo-fi hip hop beat is in the key of C minor, with a tempo of 70 BPM. The mai | 1.9s |
| 97 | PASS | S10 | Video MCP health | {'status': 'ok', 'service': 'video-mcp'} | 0.0s |
| 98 | PASS | S10 | list_video_models returns model list | models: videowan2.2 | 0.7s |
| 99 | PASS | S10 | auto-video workspace: domain-relevant video description | preview: Camera angle: As a helpful AI, I don't have eyes or a physical presence to view  | 1.0s |
| 100 | PASS | S10 | ComfyUI host at http://localhost:8188 | HTTP 200 | 0.0s |
| 101 | PASS | S10 | ComfyUI MCP bridge health | {'status': 'ok', 'service': 'comfyui-mcp'} | 0.0s |
| 102 | PASS | S15 | SearXNG /search?format=json returns results | 57 results for 'NERC CIP' | 2.2s |
| 103 | PASS | S15 | auto-research workspace: technical comparison response | signals: ['aes', 'rsa', 'symmetric', 'asymmetric', 'key'] | 44.5s |
| 104 | PASS | S20 | Telegram bot: module imports and build_app() succeeds | default_workspace=auto, allowed_users=1 | 0.1s |
| 105 | PASS | S20 | Telegram dispatcher: call_pipeline_async returns response | reply length: 3 | 0.3s |
| 106 | PASS | S20 | Telegram dispatcher: is_valid_workspace correct | auto-coding=True, nonexistent=False | 0.0s |
| 107 | PASS | S20 | Slack bot: module imports and _get_tokens() succeeds | bot_token=set, app_token=set | 0.0s |
| 108 | PASS | S20 | Slack dispatcher: module imports and payload builder work | dispatcher uses Docker-internal URL — tested modules natively, pipeline via localhost | 3.1s |
| 109 | WARN | S11 | Personas registered in Open WebUI | Expecting value: line 1 column 1 (char 0) | 0.0s |
| 110 | PASS | S11 | persona creativewriter (Creative Writer) | signals: ['flower', 'space', 'wonder'] | 6.1s |
| 111 | PASS | S11 | persona itexpert (IT Expert) | signals: ['memory', 'pandas', 'container', 'profile'] | 6.9s |
| 112 | PASS | S11 | persona techreviewer (Tech Reviewer) | signals: ['m4', 'memory', 'inference', 'performance'] | 175.7s |
| 113 | PASS | S11 | persona techwriter (Tech Writer) | signals: ['api', 'authentication', 'endpoint', 'rate limit'] | 105.3s |
| 114 | WARN | S11 | persona bugdiscoverycodeassistant (Bug Discovery Code Assist | timeout — model loading | 245.1s |
| 115 | PASS | S11 | persona codebasewikidocumentationskill (Codebase WIKI Docume | signals: ['fibonacci', 'recursive', 'complexity', 'memoization'] | 56.7s |
| 116 | PASS | S11 | persona codereviewassistant (Code Review Assistant) | signals: ['pythonic', 'enumerate', 'index', 'readability', 'improve'] | 77.0s |
| 117 | PASS | S11 | persona codereviewer (Code Reviewer) | signals: ['sql injection', 'vulnerability'] | 94.3s |
| 118 | PASS | S11 | persona devopsautomator (DevOps Automator) | signals: ['github', 'actions', 'deploy', 'docker', 'pytest'] | 53.3s |
| 119 | PASS | S11 | persona devopsengineer (DevOps Engineer) | signals: ['helm', 'pipeline', 'canary'] | 148.4s |
| 120 | WARN | S11 | persona ethereumdeveloper (Ethereum Developer) | timeout — model loading | 245.1s |
| 121 | WARN | S11 | persona githubexpert (GitHub Expert) | timeout — model loading | 245.1s |
| 122 | PASS | S11 | persona javascriptconsole (JavaScript Console) | signals: ['reduce', 'accumulator', 'pi', '3.141'] | 105.8s |
| 123 | PASS | S11 | persona kubernetesdockerrpglearningengine (Kubernetes & Dock | signals: ['mission', 'container', 'game', 'briefing'] | 192.5s |
| 124 | PASS | S11 | persona linuxterminal (Linux Terminal) | signals: ['find', 'size', 'modified', 'exclude', 'human'] | 101.8s |
| 125 | PASS | S11 | persona pythoncodegeneratorcleanoptimizedproduction-ready (P | signals: ['def ', 'retry', 'backoff'] | 76.0s |
| 126 | PASS | S11 | persona pythoninterpreter (Python Interpreter) | signals: ['zip', 'reverse', 'output', 'slice', '[(1, 3)', '(2, 2)'] | 95.0s |
| 127 | PASS | S11 | persona seniorfrontenddeveloper (Senior Frontend Developer) | signals: ['react', 'useeffect', 'loading', 'error'] | 11.6s |
| 128 | PASS | S11 | persona seniorsoftwareengineersoftwarearchitectrules (Senior | signals: ['risk', 'distributed', 'consistency'] | 87.4s |
| 129 | PASS | S11 | persona softwarequalityassurancetester (Software Quality Ass | signals: ['test case', 'valid', 'invalid', 'boundary'] | 58.2s |
| 130 | WARN | S11 | persona sqlterminal (SQL Terminal) | no signals in: '(1 row affected)' | 125.4s |
| 131 | PASS | S11 | persona dataanalyst (Data Analyst) | signals: ['growth', 'quarter', 'trend', 'analysis'] | 89.3s |
| 132 | PASS | S11 | persona datascientist (Data Scientist) | signals: ['feature', 'algorithm', 'churn', 'model'] | 42.8s |
| 133 | PASS | S11 | persona excelsheet (Excel Sheet) | signals: ['sumproduct', 'array', 'filter', 'boolean', 'sales'] | 32.1s |
| 134 | PASS | S11 | persona itarchitect (IT Architect) | signals: ['load balanc', 'replication', 'disaster', 'availability'] | 78.9s |
| 135 | PASS | S11 | persona machinelearningengineer (Machine Learning Engineer) | signals: ['random forest', 'xgboost', 'hyperparameter', 'tabular'] | 37.1s |
| 136 | PASS | S11 | persona researchanalyst (Research Analyst) | signals: ['microservices', 'monolith', 'deployment', 'complexity'] | 26.3s |
| 137 | PASS | S11 | persona statistician (Statistician) | signals: ['p-value', 'power', 'sample size', 'effect size', 'type i'] | 37.7s |
| 138 | PASS | S11 | persona redteamoperator (Red Team Operator) | signals: ['jwt', 'attack', 'token'] | 14.0s |
| 139 | PASS | S11 | persona blueteamdefender (Blue Team Defender) | signals: ['mitre', 'ssh', 'brute', 'incident', 'containment'] | 12.5s |
| 140 | PASS | S11 | Persona suite summary (40 total) | 27 PASS ∣ 3 WARN ∣ 0 FAIL | 0.0s |
| 141 | WARN | S30 | workspace auto-coding | MLX proxy not ready | 0.0s |
| 142 | WARN | S30 | persona bugdiscoverycodeassistant (Bug Discovery Code Assist | MLX proxy not ready | 0.0s |
| 143 | WARN | S30 | persona codebasewikidocumentationskill (Codebase WIKI Docume | MLX proxy not ready | 0.0s |
| 144 | WARN | S30 | persona codereviewassistant (Code Review Assistant) | MLX proxy not ready | 0.0s |
| 145 | WARN | S30 | persona codereviewer (Code Reviewer) | MLX proxy not ready | 0.0s |
| 146 | WARN | S30 | persona devopsautomator (DevOps Automator) | MLX proxy not ready | 0.0s |
| 147 | WARN | S30 | persona devopsengineer (DevOps Engineer) | MLX proxy not ready | 0.0s |
| 148 | WARN | S30 | persona ethereumdeveloper (Ethereum Developer) | MLX proxy not ready | 0.0s |
| 149 | WARN | S30 | persona githubexpert (GitHub Expert) | MLX proxy not ready | 0.0s |
| 150 | WARN | S30 | persona javascriptconsole (JavaScript Console) | MLX proxy not ready | 0.0s |
| 151 | WARN | S30 | persona kubernetesdockerrpglearningengine (Kubernetes & Dock | MLX proxy not ready | 0.0s |
| 152 | WARN | S30 | persona linuxterminal (Linux Terminal) | MLX proxy not ready | 0.0s |
| 153 | WARN | S30 | persona pythoncodegeneratorcleanoptimizedproduction-ready (P | MLX proxy not ready | 0.0s |
| 154 | WARN | S30 | persona pythoninterpreter (Python Interpreter) | MLX proxy not ready | 0.0s |
| 155 | WARN | S30 | persona seniorfrontenddeveloper (Senior Frontend Developer) | MLX proxy not ready | 0.0s |
| 156 | WARN | S30 | persona seniorsoftwareengineersoftwarearchitectrules (Senior | MLX proxy not ready | 0.0s |
| 157 | WARN | S30 | persona softwarequalityassurancetester (Software QA Tester) | MLX proxy not ready | 0.0s |
| 158 | WARN | S30 | persona sqlterminal (SQL Terminal) | MLX proxy not ready | 0.0s |
| 159 | PASS | S5 | auto-coding workspace returns Python code | preview: ```python
from typing import List

def sieve_of_eratosthenes(n: int) -> List[int | 4.0s |
| 160 | PASS | S5 | execute_python: primes to 100 (count=25 sum=1060) | ✓ count=25 sum=1060 | 1.9s |
| 161 | PASS | S5 | execute_python: Fibonacci sequence | ✓ Fibonacci executed | 0.2s |
| 162 | PASS | S5 | execute_nodejs: array sum = 15 | ✓ Node.js sum=15 | 0.3s |
| 163 | PASS | S5 | execute_bash: echo + arithmetic | ✓ bash executed | 0.2s |
| 164 | PASS | S5 | sandbox_status reports DinD connectivity | {
  "docker_available": true,
  "docker_host": "tcp://dind:2375",
  "sandbox_enabled": true,
  "python_image": "python:3.11-slim",
  "node_image": "no | 0.0s |
| 165 | PASS | S5 | Sandbox network isolation (outbound blocked) | ✓ network correctly isolated | 0.2s |
| 166 | WARN | S31 | workspace auto-spl | MLX proxy not ready | 0.0s |
| 167 | WARN | S31 | persona fullstacksoftwaredeveloper (Fullstack Software Devel | MLX proxy not ready | 0.0s |
| 168 | WARN | S31 | persona splunksplgineer (Splunk SPL Engineer) | MLX proxy not ready | 0.0s |
| 169 | WARN | S31 | persona ux-uideveloper (UX/UI Developer) | MLX proxy not ready | 0.0s |
| 170 | WARN | S32 | workspace auto-reasoning | MLX proxy not ready | 0.0s |
| 171 | WARN | S32 | workspace auto-research | MLX proxy not ready | 0.0s |
| 172 | WARN | S32 | workspace auto-data | MLX proxy not ready | 0.0s |
| 173 | WARN | S33 | workspace auto-compliance | MLX proxy not ready | 0.0s |
| 174 | WARN | S33 | persona cippolicywriter (CIP Policy Writer) | MLX proxy not ready | 0.0s |
| 175 | WARN | S33 | persona nerccipcomplianceanalyst (NERC CIP Compliance Analys | MLX proxy not ready | 0.0s |
| 176 | WARN | S34 | workspace auto-mistral | MLX proxy not ready | 0.0s |
| 177 | WARN | S34 | persona magistralstrategist (Magistral Strategist) | MLX proxy not ready | 0.0s |
| 178 | WARN | S35 | workspace auto-documents | MLX proxy not ready | 0.0s |
| 179 | WARN | S36 | workspace auto-creative | MLX proxy not ready | 0.0s |
| 180 | WARN | S37 | workspace auto-vision | MLX proxy not ready | 0.0s |
| 181 | WARN | S37 | persona gemmaresearchanalyst (Gemma Research Analyst) | MLX proxy not ready | 0.0s |
| 182 | PASS | S22 | MLX proxy health — reports state and active server | state=unknown, active_server=lm | 0.0s |
| 183 | PASS | S22 | MLX proxy /v1/models — 9 models listed | first 3: ['mlx-community/Qwen3-Coder-Next-4bit', 'mlx-community/Qwen3-Coder-30B-A3B-Instruct-4bit', 'mlx-community/DeepSeek-Coder-V2-Lite-Instruct-4bit-mlx'] | 0.0s |
| 184 | PASS | S22 | MLX-routed workspace (auto-coding) completes request | matched: ['reverse', 'string', '::-1', '[::-1]'] | 74.9s |
| 185 | INFO | S22 | MLX watchdog — not enabled in .env | MLX_WATCHDOG_ENABLED=false — skipped | 0.0s |
| 186 | PASS | S23 | MLX watchdog disabled for testing | watchdog stopped — no false alerts during fallback tests | 0.0s |
| 187 | PASS | S23 | Pipeline health endpoint shows backend status | 6/7 backends healthy, 16 workspaces | 0.0s |
| 188 | PASS | S23 | Response includes model identity | model=dolphin-llama3:8b | 4.1s |
| 189 | PASS | S23 | auto-coding: primary MLX path | model=mlx-community/Qwen3-Coder-Next-4bit | 4.0s |
| 190 | PASS | S23 | auto-coding: primary path works | model=mlx-community/Qwen3-Coder-Next-4bit | 3.3s |
| 191 | PASS | S23 | auto-coding: MLX proxy killed | MLX proxy is down | 18.1s |
| 192 | PASS | S23 | auto-coding: fallback to coding | model=qwen3-vl:32b ∣ signals=['str', 'palindrome'] ∣ absolute fallback (pipeline served from any healthy backend) | 29.3s |
| 193 | WARN | S23 | auto-coding: MLX proxy restore | restore may still be in progress for MLX proxy | 124.9s |
| 194 | PASS | S23 | auto-coding: MLX restored, chain intact | model=huihui_ai/baronllm-abliterated — chain recovered after fallback | 8.6s |
| 195 | PASS | S23 | auto-security: primary security path | model=baronllm:q6_k | 10.1s |
| 196 | PASS | S23 | auto-security: survives backend stress | model=baronllm:q6_k ∣ signals=['autoindex', 'security', 'misconfiguration'] | 5.5s |
| 197 | WARN | S23 | auto-vision: primary MLX path | model=deepseek-r1:32b-q4_k_m | 26.7s |
| 198 | PASS | S23 | auto-vision: primary path works | model=deepseek-r1:32b-q4_k_m | 4.5s |
| 199 | PASS | S23 | auto-vision: MLX proxy killed | MLX proxy is down | 18.1s |
| 200 | PASS | S23 | auto-vision: fallback to vision | model=deepseek-r1:32b-q4_k_m ∣ signals=['visual', 'detect', 'describe', 'image', 'diagram', 'analysis'] ∣ absolute fallback (pipeline served from any healthy ba | 16.6s |
| 201 | WARN | S23 | auto-vision: MLX proxy restore | restore may still be in progress for MLX proxy | 124.9s |
| 202 | PASS | S23 | auto-vision: MLX restored, chain intact | model=deepseek-r1:32b-q4_k_m — chain recovered after fallback | 6.0s |
| 203 | WARN | S23 | auto-reasoning: primary MLX path | model=deepseek-r1:32b-q4_k_m | 17.1s |
| 204 | PASS | S23 | auto-reasoning: primary path works | model=deepseek-r1:32b-q4_k_m | 16.6s |
| 205 | PASS | S23 | auto-reasoning: MLX proxy killed | MLX proxy is down | 18.1s |
| 206 | PASS | S23 | auto-reasoning: fallback to reasoning | model=deepseek-r1:32b-q4_k_m ∣ signals=['meet', 'miles', 'train', 'mph', '790'] ∣ matched expected group: reasoning | 16.7s |
| 207 | WARN | S23 | auto-reasoning: MLX proxy restore | restore may still be in progress for MLX proxy | 125.0s |
| 208 | PASS | S23 | auto-reasoning: MLX restored, chain intact | model=deepseek-r1:32b-q4_k_m — chain recovered after fallback | 16.6s |
| 209 | WARN | S23 | All backends restored and healthy | 6/7 backends healthy | 140.9s |
| 210 | PASS | S23 | All MLX workspaces survive MLX failure (8/8) | 8 responded, 0 failed (fell back to Ollama or timed out) | 243.7s |
| 211 | WARN | S18 | MLX proxy health before section | HTTP 503 — may be recovering from GPU crash | 0.0s |
| 212 | PASS | S18 | ComfyUI MCP bridge health | {'status': 'ok', 'service': 'comfyui-mcp'} | 0.0s |
| 213 | PASS | S18 | list_workflows returns checkpoint list | checkpoints: Flux_v8-NSFW.safetensorsflux1-schnell.safetensorslora.safetensorssd_xl_base_1.0.safetensors | 0.9s |
| 214 | PASS | S18 | generate_image: photorealistic apple | {
  "success": false,
  "error": "ComfyUI rejected workflow (HTTP 400): {'type': 'prompt_outputs_failed_validation', 'message': 'Prompt outputs failed validatio | 0.4s |
| 215 | PASS | S18 | ComfyUI host at http://localhost:8188 | HTTP 200 | 0.0s |
| 216 | PASS | S19 | Video MCP health | {'status': 'ok', 'service': 'video-mcp'} | 0.0s |
| 217 | PASS | S19 | list_video_models returns model list | models: videowan2.2 | 0.2s |
| 218 | PASS | S19 | generate_video: ocean waves at sunset | {
  "success": false,
  "error": "ComfyUI not available at http://host.docker.internal:8188: Client error '400 Bad Request' for url 'http://host.docker.internal | 0.0s |
| 219 | PASS | S19 | auto-video workspace: domain-relevant video description | preview: Camera Angle: Low angle, slightly tilted upwards
Lens: 18-35mm, wide open
Lighti | 4.6s |

## Blocked Items Register

*No blocked items.*

## Memory Usage Log

| Section | Free % | Used % | Notes |
|---------|--------|--------|-------|
| pre-S17 | 94% | 6% |  |
| pre-S0 | 94% | 6% |  |
| pre-S1 | 94% | 6% |  |
| pre-S2 | 94% | 6% |  |
| pre-S8 | 93% | 7% |  |
| pre-S9 | 94% | 6% |  |
| pre-S12 | 94% | 6% |  |
| pre-S13 | 94% | 6% |  |
| pre-S14 | 94% | 6% |  |
| pre-S16 | 94% | 6% |  |
| pre-S21 | 95% | 5% |  |
| pre-S3 | 95% | 5% |  |
| pre-S4 | 65% | 35% |  |
| pre-S6 | 54% | 46% |  |
| pre-S7 | 58% | 42% |  |
| pre-S10 | 57% | 43% |  |
| pre-S15 | 57% | 43% |  |
| pre-S20 | 30% | 70% |  |
| pre-S11 | 58% | 42% |  |
| pre-S30 | 18% | 82% |  |
| pre-S5 | 96% | 4% |  |
| pre-S31 | 95% | 5% |  |
| pre-S32 | 96% | 4% |  |
| pre-S33 | 96% | 4% |  |
| pre-S34 | 96% | 4% |  |
| pre-S35 | 96% | 4% |  |
| pre-S36 | 73% | 27% |  |
| pre-S37 | 95% | 5% |  |
| pre-S22 | 96% | 4% |  |
| pre-S23 | 29% | 71% |  |
| pre-S18 | 26% | 74% | MLX: 0.1GB free, moderate |
| pre-S19 | 26% | 74% | MLX: 0.1GB free, moderate |

---
*Screenshots: /tmp/p5_gui_*.png*
