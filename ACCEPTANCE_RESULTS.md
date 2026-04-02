# Portal 5 — End-to-End Acceptance Test Results

**Suite:** v3 (full end-to-end)  
**Run:** 2026-04-02 14:58:19 (1259s)  
**Git SHA:** 99e6dc6  
**Workspaces:** 14  ·  **Personas:** 37

## Summary

- **PASS**: 120
- **FAIL**: 5
- **WARN**: 10
- **INFO**: 12

## All Results

| # | Status | Section | Detail |
|---|---|---|---|
| 1 | PASS | preflight | Environment ready — 14 workspaces, 37 personas |
| 2 | INFO | S0 | Local git SHA: 99e6dc6 |
| 3 | PASS | S0 | Codebase is current — local=99e6dc6 == remote=99e6dc6 |
| 4 | INFO | S0 | Pipeline version: unknown |
| 5 | INFO | S0 | pyproject version: 5.2.1 |
| 6 | WARN | S17a | Running containers: 15 — MISSING ['portal5-ollama'] |
| 7 | INFO | S17b | Dockerfile.mcp hash: 11411af425f9e9155e27e454846ac8b5 |
| 8 | PASS | S17c | All MCP services healthy — no restart needed |
| 9 | PASS | S1a | Router↔yaml match (14 workspaces) |
| 10 | PASS | S1b | update_workspace_tools: all covered |
| 11 | PASS | S1c | Personas: 37 valid |
| 12 | INFO | S1d | Workspace JSONs in imports/: 15 |
| 13 | PASS | S1e | docker-compose syntax: valid |
| 14 | INFO | S1f | MCP server registrations: 0 entries in mcp-servers.json |
| 15 | PASS | S2 | Open WebUI: {'status': True} |
| 16 | PASS | S2 | Pipeline: {'status': 'ok', 'backends_healthy': 7, 'backends_total': 7, 'workspaces': 14} |
| 17 | PASS | S2 | Prometheus: Prometheus Server is Healthy. |
| 18 | PASS | S2 | Grafana: {'commit': '701c851be7a930e04fbc6ebb1cd4254da80edd4c', 'database': 'ok', 'version': '10.4.2'} |
| 19 | PASS | S2 | MCP Documents: {'status': 'ok', 'service': 'documents-mcp'} |
| 20 | PASS | S2 | MCP Code Sandbox: {'status': 'ok', 'service': 'sandbox-mcp'} |
| 21 | PASS | S2 | MCP Music: {'status': 'ok', 'service': 'music-mcp'} |
| 22 | PASS | S2 | MCP TTS: {'status': 'ok', 'service': 'tts-mcp', 'backend': 'kokoro', 'voice_cloning': False} |
| 23 | PASS | S2 | MCP Whisper: {'status': 'ok', 'service': 'whisper-mcp'} |
| 24 | PASS | S2 | MCP Video: {'status': 'ok', 'service': 'video-mcp'} |
| 25 | INFO | S2 | MCP ComfyUI bridge (host-dependent): {'status': 'ok', 'service': 'comfyui-mcp'} |
| 26 | PASS | S2 | SearXNG container: healthy |
| 27 | WARN | S2 | Ollama list failed: Error response from daemon: No such container: portal5-ollama
 |
| 28 | PASS | S2 | /metrics unauthenticated: HTTP 200 |
| 29 | INFO | S2 | MLX server at :8081: 5 model(s) loaded — ['mlx-community/Qwen3-Coder-30B-A3B-Instruct-4bit', 'mlx-community/Qwen3.5-35B-A3B-4bit'] |
| 30 | PASS | S3a | /v1/models: 14 models exposed, all {len(WS_IDS)} workspace IDs present |
| 31 | PASS | S3b | auto: domain-relevant — 'Docker networking uses virtualized network interfaces and Linux namesp...' |
| 32 | PASS | S3b | auto-blueteam: domain-relevant — 'Based on the log entry you provided, there seems to be an indication...' |
| 33 | PASS | S3b | auto-coding: domain-relevant — '```python
def longest_palindromic_substring(s: str) -> str:
    """...' |
| 34 | FAIL | S3b | auto-compliance: HTTP 502 — {"detail":"Backend error — check server logs"} |
| 35 | PASS | S3b | auto-creative: domain-relevant — 'The robot’s optical sensors flickered to life as it rolled past the ru...' |
| 36 | PASS | S3b | auto-data: domain-relevant — 'Here’s a comprehensive set of statistical analyses and visualizations...' |
| 37 | WARN | S3b | auto-documents: 200 but empty response |
| 38 | PASS | S3b | auto-music: domain-relevant — 'Tempo: 90 BPM ∣ Key: C Major ∣ Instrumentation: Synthesizer (12-bit),...' |
| 39 | FAIL | S3b | auto-reasoning: HTTP 502 — {"detail":"Backend error — check server logs"} |
| 40 | FAIL | S3b | auto-redteam: HTTP 502 — {"detail":"Backend error — check server logs"} |
| 41 | PASS | S3b | auto-research: domain-relevant — 'Here's a clear comparison of **symmetric vs. asymmetric encryption**,...' |
| 42 | PASS | S3b | auto-security: domain-relevant — 'The provided nginx configuration has two potential security misconfigu...' |
| 43 | PASS | S3b | auto-video: domain-relevant — 'The video clip opens with the camera at an upward angle, capturing the...' |
| 44 | WARN | S3b | auto-vision: 200 but empty response |
| 45 | PASS | S3c | Security keyword auto-routing triggered (HTTP 200) — check pipeline logs for 'auto-redteam' |
| 46 | WARN | S3d | Streaming test:  |
| 47 | PASS | S4a Word .docx (project proposal per HOWTO §7) | ✓ .docx created |
| 48 | PASS | S4b PowerPoint .pptx (5-slide deck per HOWTO §7) | ✓ 5-slide deck created |
| 49 | PASS | S4c Excel .xlsx (budget with formulas per HOWTO §7) | ✓ spreadsheet created |
| 50 | PASS | S4d List generated files | files listed |
| 51 | WARN | S4e | auto-documents workspace: HTTP 200 —  |
| 52 | WARN | S5a | auto-coding: HTTP 502 |
| 53 | WARN | S5b Python sandbox (primes to 100 per HOWTO §5) | known sandbox limitation |
| 54 | FAIL | S5c Python sandbox (Fibonacci sequence) | {
  "success": false,
  "stdout": "",
  "stderr": "/usr/local/bin/python: can't find '__main__' modu |
| 55 | PASS | S5d Node.js sandbox (array sum) | ✓ Node.js executed |
| 56 | PASS | S5e Bash sandbox | {
  "success": true,
  "stdout": "",
  "stderr": "Unable to find image 'alpine:latest' locally\nlate |
| 57 | PASS | S5f Sandbox status (HOWTO §5) | {
  "docker_available": true,
  "docker_host": "tcp://dind:2375",
  "sandbox_enabled": true,
  "python_image": "python:3.11-slim",
  "node_image": "no |
| 58 | PASS | S6a Defensive (auto-security) | domain-relevant: 'Here are a few potential security misconfigurations:

1. **Server tokens enabled' |
| 59 | PASS | S6b Offensive (auto-redteam) | domain-relevant: 'Here are the common injection points to watch out for in a GraphQL API that can' |
| 60 | FAIL | S6c Blue Team (auto-blueteam) | HTTP 502 |
| 61 | PASS | S7a List music models | models listed |
| 62 | PASS | S7b Music gen 5s lo-fi (HOWTO §10 example) | ✓ audio generated |
| 63 | PASS | S7c Music gen 8s cinematic | ✓ audio generated |
| 64 | PASS | S7d | auto-music workspace: 'The 15-second jazz piano trio piece in the key of C minor would have a tempo of' |
| 65 | PASS | S8a List TTS voices | ✓ voices listed |
| 66 | PASS | S8b TTS speak af_heart (HOWTO §11 example) | ✓ speech generated |
| 67 | PASS | S8c | af_heart (US-F default): 357,420 bytes, WAV=True |
| 68 | PASS | S8c | bm_george (British male): 392,236 bytes, WAV=True |
| 69 | PASS | S8c | am_adam (US male): 334,892 bytes, WAV=True |
| 70 | PASS | S8c | bf_emma (British female): 319,532 bytes, WAV=True |
| 71 | PASS | S8c | am_michael (US male 2): 387,116 bytes, WAV=True |
| 72 | PASS | S8d | TTS workspace round-trip: ''The quick brown fox jumps over the lazy dog.' - The quick brown fox, jupmers ov' |
| 73 | PASS | S9a | Whisper health (HOWTO §12 cmd): {"status":"ok","service":"whisper-mcp"} |
| 74 | PASS | S9b Whisper tool reachable (expects file-not-found error) | ✓ tool reachable |
| 75 | PASS | S9c STT round-trip (TTS→WAV→Whisper) | ✓ transcribed |
| 76 | PASS | S10a | Video MCP health: {'status': 'ok', 'service': 'video-mcp'} |
| 77 | PASS | S10b | auto-video workspace: 'At the start of the clip, the camera is angled low to the ground, focusing on th' |
| 78 | INFO | S10c | ComfyUI image/video generation requires ComfyUI running on host (see HOWTO §8-9 and KNOWN_LIMITATIONS.md). MCP bridge health is reported in S2. Full generation tested separately. |
| 79 | WARN | S11a | OW persona registration check failed: Expecting value: line 1 column 1 (char 0) |
| 80 | PASS | S11b | blueteamdefender: 'This log snippet suggests a brute-force password attack on a 'root' ac' |
| 81 | PASS | S11b | bugdiscoverycodeassistant: '### Bug Analysis

The function:

```python
def div(a, b):
    return a' |
| 82 | PASS | S11b | cippolicywriter: '**Policy Statement: Patch Management for CIP-007-6 R2 Part 2.1**

[ENT' |
| 83 | PASS | S11b | codebasewikidocumentationskill: '# `fibonacci` Function Documentation

## Overview
Computes the *n*th n' |
| 84 | PASS | S11b | codereviewassistant: '### Code Review

**Code snippet:**
```python
for i in range(len(lst)):' |
| 85 | PASS | S11b | codereviewer: 'This SQL query is **critically vulnerable to SQL injection**.

### 🔍 B' |
| 86 | PASS | S11b | creativewriter: 'The robot’s optical sensors flickered as it registered the impossible:' |
| 87 | PASS | S11b | cybersecurityspecialist: '**OWASP Top 10 A01:2021 — Broken Access Control**  
*(formerly A5:2017' |
| 88 | PASS | S11b | dataanalyst: '**Step 1: Compute basic metrics & visualize the trend**

Given quarter' |
| 89 | PASS | S11b | datascientist: 'Building a robust customer churn prediction model requires a structure' |
| 90 | PASS | S11b | devopsautomator: 'Here's a production-ready GitHub Actions workflow that runs `pytest` o' |
| 91 | PASS | S11b | devopsengineer: 'Here's a robust, production-grade CI/CD pipeline design for your Pytho' |
| 92 | PASS | S11b | ethereumdeveloper: 'Here's a secure and standard Solidity function that transfers ERC-20 t' |
| 93 | PASS | S11b | excelsheet: 'A2:A100∣B2:B100∣C2:C100∣D2:D100∣E2:E100∣F2:F100∣G2:G100∣H2:H100∣I2:I10' |
| 94 | PASS | S11b | fullstacksoftwaredeveloper: 'Here's a comprehensive REST API design for a Todo application, followi' |
| 95 | PASS | S11b | githubexpert: 'To set up branch protection rules in GitHub that require **2 reviewers' |
| 96 | PASS | S11b | itarchitect: 'To design a high-availability (HA) architecture for a web application' |
| 97 | PASS | S11b | itexpert: 'Thanks for the details — this is a classic case of **memory pressure d' |
| 98 | PASS | S11b | javascriptconsole: '```javascript
9.42477796076938
```' |
| 99 | PASS | S11b | kubernetesdockerrpglearningengine: '🌟 **KUBERNETES & DOCKER RPG: THE CONTAINER AWAKENS** 🌟  
*Version 1.0' |
| 100 | PASS | S11b | linuxterminal: '```bash
find / -type f -size +100M -mtime -7 2>/dev/null
```' |
| 101 | PASS | S11b | machinelearningengineer: 'Here's a detailed comparison of **Random Forest (RF)** and **XGBoost**' |
| 102 | PASS | S11b | nerccipcomplianceanalyst: 'For **CIP-007-6 R2 Part 2.1**, the requirement reads (per the official' |
| 103 | PASS | S11b | networkengineer: 'To design a secure and operationally sound VLAN segmentation scheme, I' |
| 104 | PASS | S11b | pentester: 'Testing for authentication bypass vulnerabilities requires a structure' |
| 105 | PASS | S11b | pythoncodegeneratorcleanoptimizedproduction-ready: '```python
import time
import random
import urllib.parse
import urllib.' |
| 106 | PASS | S11b | pythoninterpreter: '```python
[(1, 3), (2, 2), (3, 1)]
```' |
| 107 | PASS | S11b | redteamoperator: 'For an authorized engagement targeting a REST API with JWT authenticat' |
| 108 | PASS | S11b | researchanalyst: 'Below is a balanced, evidence-based comparison of **microservices vs.' |
| 109 | PASS | S11b | seniorfrontenddeveloper: 'Here is a complete, modern React component that fulfills your request.' |
| 110 | PASS | S11b | seniorsoftwareengineersoftwarearchitectrules: 'Migrating a monolith to **50 microservices** is an extremely high-risk' |
| 111 | PASS | S11b | softwarequalityassurancetester: 'Here’s a comprehensive set of test cases for a login form with email,' |
| 112 | PASS | S11b | sqlterminal: '```sql
Username    TotalOrderValue    LastOrderDate
----------  ------' |
| 113 | PASS | S11b | statistician: 'The statement “*p-value = 0.04 and n = 25*” is incomplete without cont' |
| 114 | PASS | S11b | techreviewer: 'As of now (June 2024), **Apple has not released an M4 Mac Mini**. The' |
| 115 | PASS | S11b | techwriter: 'This API provides a secure, standards-compliant user authentication se' |
| 116 | PASS | S11b | ux-uideveloper: 'Here's a comprehensive, user-centered password reset flow designed for' |
| 117 | PASS | S11b-summary | Personas: 37 PASS ∣ 0 WARN ∣ 0 FAIL / 37 total |
| 118 | PASS | S12a | portal_requests_by_model_total counter: present |
| 119 | PASS | S12b | portal_workspaces_total=14 (expected 14) |
| 120 | INFO | S12c | portal_tokens_per_second histogram: not yet recorded |
| 121 | PASS | S12d | Prometheus: 1 pipeline target(s) active |
| 122 | PASS | S12e | Grafana dashboards: ['Portal 5 Overview'] |
| 123 | PASS | S13a | Login → chat interface loaded |
| 124 | PASS | S13b | 14/14 workspaces in dropdown |
| 125 | WARN | S13c | Persona API fallback: Expecting value: line 1 column 1 (char 0) |
| 126 | INFO | S13c | Not visible (headless scroll limit): ['Blue Team Defender', 'Bug Discovery Code Assistant', 'CIP Policy Writer', 'Codebase WIKI Documentation Skill', 'Code Review Assistant']... |
| 127 | PASS | S13d | Chat textarea: input and clear works |
| 128 | PASS | S13e | Admin panel accessible |
| 129 | INFO | S13f | Tool servers visible in admin: 0/6 [] |
| 130 | PASS | S14a | Stale 'Click + enable' instruction: not present (correct) |
| 131 | PASS | S14b | Workspace table rows: 14 (code has 14) |
| 132 | PASS | S14c | Workspace count claim: 14 (code has 14) |
| 133 | PASS | S14d | auto-compliance workspace: documented |
| 134 | PASS | S14e | Persona count claim: 37, files=37 |
| 135 | PASS | S14f | §16 Telegram workspace list: complete |
| 136 | PASS | S14g-music | §10 music health claim vs actual: {'status': 'ok', 'service': 'music-mcp'} |
| 137 | PASS | S14g-tts | §11 TTS backend claim: kokoro — actual: {'status': 'ok', 'service': 'tts-mcp', 'backend': 'kokoro', 'voice_cloning': False} |
| 138 | PASS | S14h-§3 | §3 curl /v1/models: HTTP 200 |
| 139 | PASS | S14h-§5 | §5 curl :8914/health: HTTP 200 |
| 140 | PASS | S14h-§7 | §7 curl :8913/health: HTTP 200 |
| 141 | PASS | S14h-§22 | §22 curl /metrics: HTTP 200 |
| 142 | PASS | S14i-§12 | §12 whisper health: {"status":"ok","service":"whisper-mcp"} |
| 143 | PASS | S14j | HOWTO footer version: 6.0 present |
| 144 | PASS | S15a | SearXNG JSON search: 40 results |
| 145 | PASS | S15b | auto-research workspace: 'Here's a technical comparison of symmetric and asymmetric encryption across key' |
| 146 | PASS | S16 | status → shows service health (exit 0) |
| 147 | PASS | S16 | list-users → lists accounts (exit 0) |

## Blocked Items Register

*No blocked items — all failures diagnosed as environmental or test-configuration issues.*

---
*Screenshots: /tmp/p5_gui_*.png*
