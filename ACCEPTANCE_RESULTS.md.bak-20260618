# Portal 5 Acceptance Test Results — V6

**Date:** 2026-06-18 01:22:14
**Git SHA:** 638e15a
**Sections:** S0, S1, S2, S3, S3a, S4, S5, S6, S8, S9, S10, S10c, S12, S13, S16, S17, S18, S21, S23, S40, S41, S42, S50, S60, S70
**Runtime:** 7153s (119m 13s)

## Summary

| Status | Count |
|--------|-------|
| ✅ PASS | 371 |
| ❌ FAIL | 9 |
| ⚠️  WARN | 176 |
| ℹ️  INFO | 10 |
| **Total** | **566** |

**Code defects: 0 · Env issues: 0 · Unclassified: 185**

## Results

| Section | ID | Name | Status | Detail | Duration |
|---------|-----|------|--------|--------|----------|
| S0 | S0-01 | Python version | ✅ PASS | Python 3.14.5 | 0.0s |
| S0 | S0-02 | Required packages | ✅ PASS | all present | 0.1s |
| S0 | S0-03 | .env file exists | ✅ PASS | /Users/chris/projects/portal-5/.env | 0.0s |
| S0 | S0-04 | PIPELINE_API_KEY configured | ✅ PASS | key length: 42 | 0.0s |
| S0 | S0-05 | Git repository | ✅ PASS | SHA: 638e15a | 0.0s |
| S1 | S1-01 | backends.yaml exists | ✅ PASS | /Users/chris/projects/portal-5/config/backends.yaml | 0.0s |
| S1 | S1-02 | backends.yaml valid YAML | ✅ PASS | 6 backends | 0.0s |
| S1 | S1-03 | Workspace IDs consistent | ✅ PASS | 95 workspaces | 0.0s |
| S1 | S1-04 | Persona YAMLs valid | ✅ PASS | 144 personas | 0.1s |
| S1 | S1-05 | Persona count matches yaml file count | ✅ PASS | 144 loaded, 144 yaml files | 0.0s |
| S1 | S1-06 | routing_descriptions.json | ✅ PASS | 31 descriptions | 0.0s |
| S1 | S1-07 | routing_examples.json | ✅ PASS | 3 examples | 0.0s |
| S1 | S1-08 | MLX routing: VLM models (retired) | ℹ️  INFO | MLX proxy retired in 3a0c58e | 0.0s |
| S1 | S1-09 | MLX routing: text-only models (retired) | ℹ️  INFO | MLX proxy retired in 3a0c58e | 0.0s |
| S1 | S1-10 | Persona workspace_model values are pipel | ❌ FAIL | invalid: ['bench-granite-speech:bench-granite-speech', 'bench-huihui-qwen36-35b- | 0.0s |
| S1 | S1-11 | All personas have PERSONA_PROMPTS entrie | ❌ FAIL | missing prompts for: ['adversarysimulator', 'cadquerydesigner', 'pentestlead', ' | 0.0s |
| S1 | S1-17 | workspace hint reachability | ✅ PASS | all 95 workspace hints resolve | 0.1s |
| S2 | S2-01 | Docker daemon | ✅ PASS | Docker OK | 0.5s |
| S2 | S2-02 | Pipeline /health | ✅ PASS | backends=6/6, workspaces=95 | 0.0s |
| S2 | S2-03 | Ollama | ✅ PASS | 91 models | 0.0s |
| S2 | S2-04 | Open WebUI | ✅ PASS | HTTP 200 | 0.0s |
| S2 | S2-05 | SearXNG | ✅ PASS | HTTP 200 | 0.0s |
| S2 | S2-06 | Prometheus | ✅ PASS | HTTP 200 | 0.0s |
| S2 | S2-07 | Grafana | ✅ PASS | HTTP 200 | 0.0s |
| S2 | S2-08 | MCP documents (:8913) | ✅ PASS | HTTP 200 | 0.0s |
| S2 | S2-09 | MCP music (:8912) | ✅ PASS | HTTP 200 | 0.0s |
| S2 | S2-10 | MCP tts (:8916) | ✅ PASS | HTTP 200 | 0.0s |
| S2 | S2-11 | MCP whisper (:8915) | ✅ PASS | HTTP 200 | 0.0s |
| S2 | S2-12 | MCP sandbox (:8914) | ✅ PASS | HTTP 200 | 0.0s |
| S2 | S2-13 | MCP video (:8911) | ⚠️  WARN | HTTP 0  [UNCLASSIFIED] | 0.0s |
| S2 | S2-14 | MCP embedding (:8917) | ✅ PASS | HTTP 200 | 0.0s |
| S2 | S2-15 | MCP security (:8919) | ✅ PASS | HTTP 200 | 0.0s |
| S2 | S2-17 | MLX Speech | ℹ️  INFO | not running (optional) | 0.0s |
| S3a | S3a-01 | Workspace auto | ✅ PASS | signals: ['DNS', 'domain', 'IP'] \| routed -> auto matches Ollama:qwen3.5-ablite | 13.9s |
| S3a | S3a-02 | Workspace auto-daily | ✅ PASS | signals: ['offsite', 'agenda', 'plan'] \| routed -> auto-daily matches Ollama:ge | 19.1s |
| S3a | S3a-03 | Workspace auto-mistral | ✅ PASS | signals: ['trade', 'scale', 'deploy'] \| routed -> auto-mistral matches Ollama:m | 44.1s |
| S3a | S3a-04 | Workspace auto-music | ✅ PASS | signals: ['beat', 'drum', 'sample'] \| routed -> auto-music matches Ollama:lfm2. | 6.3s |
| S3a | S3a-05 | Workspace auto-video | ✅ PASS | signals: ['sun', 'mountain', 'light'] \| routed -> auto-video matches Ollama:gra | 10.4s |
| S3a | S3a-06 | Workspace auto-coding | ✅ PASS | signals: ['def', 'return', 'reverse'] \| routed -> auto-coding matches Ollama:qw | 17.3s |
| S3a | S3a-07 | Workspace auto-coding-agentic | ✅ PASS | signals: ['return', 'def', 'bug'] \| routed -> auto-coding-agentic matches Ollam | 27.2s |
| S3a | S3a-08 | Workspace auto-agentic | ✅ PASS | signals: ['service', 'domain'] \| routed -> auto-agentic matches Ollama:qwen3-co | 42.6s |
| S3a | S3a-09 | Workspace auto-spl | ✅ PASS | signals: ['index', 'source', 'fail'] \| routed -> auto-spl matches Ollama:huihui | 32.8s |
| S3a | S3a-10 | Workspace auto-documents | ⚠️  WARN | no signals in:  \| routed -> auto-documents matches Ollama:granite4.1  [UNCLASSI | 13.6s |
| S3a | S3a-11 | Workspace auto-security | ✅ PASS | signals: ['authentication', 'OWASP'] \| routed -> auto-security matches Ollama:b | 12.6s |
| S3a | S3a-12 | Workspace auto-redteam | ✅ PASS | signals: ['SUID', 'privilege', 'escalat'] \| routed -> auto-redteam matches Olla | 13.7s |
| S3a | S3a-13 | Workspace auto-blueteam | ✅ PASS | signals: ['network', 'monitor', 'detect'] \| routed -> auto-blueteam matches Oll | 42.0s |
| S3a | S3a-14 | Workspace auto-reasoning | ✅ PASS | signals: ['150', 'mile', 'distance'] \| routed -> auto-reasoning matches Ollama: | 11.0s |
| S3a | S3a-15 | Workspace auto-research | ✅ PASS | signals: ['quantum'] \| routed -> auto-research matches Ollama:tongyi-deepresear | 23.5s |
| S3a | S3a-16 | Workspace auto-data | ✅ PASS | signals: ['mean', 'deviation', 'σ'] \| routed -> auto-data matches Ollama:granit | 36.5s |
| S3a | S3a-17 | Workspace auto-compliance | ✅ PASS | signals: ['CIP', 'evidence', 'compliance'] \| routed -> auto-compliance matches  | 21.6s |
| S3a | S3a-18 | Workspace auto-math | ✅ PASS | signals: ['integral', 'intersection', 'area'] \| routed -> auto-math matches Oll | 9.7s |
| S3a | S3a-19 | Workspace auto-creative | ✅ PASS | signals: ['haiku', 'syllable', '5-7-5'] \| routed -> auto-creative matches Ollam | 20.3s |
| S3a | S3a-20 | Workspace auto-vision | ✅ PASS | signals: ['alt', 'text', 'contrast'] \| routed -> auto-reasoning matches Ollama: | 9.3s |
| S3a | S3a-21 | Workspace auto-audio | ✅ PASS | signals: ['audio', 'transcri', 'format'] \| routed -> auto-audio matches Ollama: | 17.6s |
| S3a | S3a-22 | Workspace tools-specialist | ✅ PASS | signals: ['tool', 'function', 'JSON'] \| routed -> tools-specialist matches Olla | 5.1s |
| S3a | S3a-01 | Workspace auto | ✅ PASS | signals: ['DNS', 'domain', 'IP'] \| routed -> auto matches Ollama:qwen3.5-ablite | 13.8s |
| S3a | S3a-02 | Workspace auto-daily | ✅ PASS | signals: ['offsite', 'agenda', 'plan'] \| routed -> auto-daily matches Ollama:ge | 18.2s |
| S3a | S3a-03 | Workspace auto-mistral | ✅ PASS | signals: ['trade', 'scale', 'complex'] \| routed -> auto-mistral matches Ollama: | 43.4s |
| S3a | S3a-04 | Workspace auto-music | ✅ PASS | signals: ['beat'] \| routed -> auto-music matches Ollama:lfm2.5 | 5.8s |
| S3a | S3a-05 | Workspace auto-video | ✅ PASS | signals: ['sun', 'mountain', 'light'] \| routed -> auto-video matches Ollama:gra | 11.0s |
| S3a | S3a-06 | Workspace auto-coding | ✅ PASS | signals: ['def', 'return', 'reverse'] \| routed -> auto-coding matches Ollama:qw | 19.0s |
| S3a | S3a-07 | Workspace auto-coding-agentic | ✅ PASS | signals: ['return', 'bug', 'fix'] \| routed -> auto-coding-agentic matches Ollam | 24.4s |
| S3a | S3a-08 | Workspace auto-agentic | ✅ PASS | signals: ['service', 'API', 'domain'] \| routed -> auto-agentic matches Ollama:q | 41.3s |
| S3a | S3a-09 | Workspace auto-spl | ✅ PASS | signals: ['index', 'source', 'fail'] \| routed -> auto-spl matches Ollama:huihui | 31.6s |
| S3a | S3a-10 | Workspace auto-documents | ⚠️  WARN | no signals in:  \| routed -> auto-documents matches Ollama:granite4.1  [UNCLASSI | 13.6s |
| S3a | S3a-11 | Workspace auto-security | ✅ PASS | signals: ['injection', 'authentication', 'OWASP'] \| routed -> auto-security mat | 11.6s |
| S3a | S3a-12 | Workspace auto-redteam | ✅ PASS | signals: ['privilege', 'escalat'] \| routed -> auto-redteam matches Ollama:qwen3 | 13.8s |
| S3a | S3a-13 | Workspace auto-blueteam | ✅ PASS | signals: ['traffic', 'network', 'monitor'] \| routed -> auto-blueteam matches Ol | 42.3s |
| S3a | S3a-14 | Workspace auto-reasoning | ✅ PASS | signals: ['150', 'mile', 'distance'] \| routed -> auto-reasoning matches Ollama: | 11.1s |
| S3a | S3a-15 | Workspace auto-research | ✅ PASS | signals: ['quantum'] \| routed -> auto-research matches Ollama:tongyi-deepresear | 23.2s |
| S3a | S3a-16 | Workspace auto-data | ✅ PASS | signals: ['square root', 'mean', 'variance'] \| routed -> auto-data matches Olla | 36.4s |
| S3a | S3a-17 | Workspace auto-compliance | ✅ PASS | signals: ['CIP', 'evidence', 'patch'] \| routed -> auto-compliance matches Ollam | 25.9s |
| S3a | S3a-18 | Workspace auto-math | ✅ PASS | signals: ['integral', 'intersection', 'area'] \| routed -> auto-math matches Oll | 9.6s |
| S3a | S3a-19 | Workspace auto-creative | ✅ PASS | signals: ['haiku', 'syllable', '5-7-5'] \| routed -> auto-creative matches Ollam | 20.3s |
| S3a | S3a-20 | Workspace auto-vision | ✅ PASS | signals: ['alt', 'text', 'contrast'] \| routed -> auto-reasoning matches Ollama: | 9.8s |
| S3a | S3a-21 | Workspace auto-audio | ✅ PASS | signals: ['audio', 'transcri', 'speech'] \| routed -> auto-audio matches Ollama: | 16.8s |
| S3a | S3a-22 | Workspace tools-specialist | ✅ PASS | signals: ['tool', 'function', 'JSON'] \| routed -> tools-specialist matches Olla | 6.1s |
| S4 | S4-01 | Documents MCP health | ✅ PASS | HTTP 200 | 0.0s |
| S4 | S4-02 | Generate Word document | ✅ PASS | {
  "success": true,
  "filename": "Test_Proposal_d11dd283.docx",
  "download_ur | 0.3s |
| S4 | S4-03 | Generate Excel spreadsheet | ✅ PASS | {
  "success": true,
  "filename": "Test_Budget_b0b6de41.xlsx",
  "download_url" | 0.4s |
| S4 | S4-04 | Generate PowerPoint | ✅ PASS | {
  "success": true,
  "filename": "Test_Presentation_1acade5c.pptx",
  "downloa | 0.1s |
| S4 | S4-05 | MCP read_word_document | ✅ PASS | got 110 chars from sample.docx | 0.0s |
| S4 | S4-06 | MCP read_excel | ✅ PASS | got 110 chars from sample.xlsx | 0.0s |
| S4 | S4-07 | MCP read_powerpoint | ✅ PASS | got 110 chars from sample.pptx | 0.0s |
| S4 | S4-08 | MCP read_pdf | ✅ PASS | got 109 chars from sample.pdf | 0.0s |
| S5 | S5-01 | Sandbox MCP health | ✅ PASS | HTTP 200 | 0.0s |
| S5 | S5-02 | Execute Python (sum 1-10) | ❌ FAIL | {
  "success": false,
  "stdout": "",
  "stderr": "docker: Error response from d | 0.6s |
| S5 | S5-03 | Execute Python (list comprehension) | ❌ FAIL | {
  "success": false,
  "stdout": "",
  "stderr": "docker: Error response from d | 0.2s |
| S6 | S6-01 | auto-security routing | ✅ PASS | signals: ['sql', 'inject', 'sanitize'] \| routed -> auto-security matches Ollama | 11.5s |
| S6 | S6-02 | auto-redteam routing | ✅ PASS | signals: ['recon', 'exploit'] \| routed -> auto-redteam matches Ollama:qwen3.5-a | 13.5s |
| S6 | S6-03 | auto-blueteam routing | ✅ PASS | signals: ['incident'] \| routed -> auto-blueteam matches Ollama:foundation-sec-8 | 44.8s |
| S6 | S6-04 | Content-aware security routing | ✅ PASS | routed to security workspace: True | 10.4s |
| S6 | S6-05 | auto-redteam-deep routing | ✅ PASS | signals: ['kerberoast', 'spn', 'service principal'] \| routed -> auto-redteam-de | 18.8s |
| S6 | S6-06 | auto-pentest routing (JANG-CRACK) | ✅ PASS | signals: ['impacket', 'getuserspns', 'kerberoast'] \| routed -> auto-pentest mat | 225.3s |
| S6 | S6-07 | auto-purpleteam-exec: routing + execute_ | ✅ PASS | signals: ['nmap', 'scan', 'open'] \| tool_called=True \| routed -> auto-purplete | 30.9s |
| S8 | S8-01 | MLX Speech health | ℹ️  INFO | not running (using Docker TTS fallback) | 0.0s |
| S8 | S8-02 | Docker TTS health | ✅ PASS | HTTP 200 | 0.0s |
| S9 | S9-01 | MLX Speech ASR available | ℹ️  INFO | not running (Docker Whisper fallback) | 0.0s |
| S9 | S9-02 | Docker Whisper health | ✅ PASS | HTTP 200 | 0.0s |
| S9 | S9-03 | MLX Transcribe health | ℹ️  INFO | not running (start with ./launch.sh start-transcribe) | 0.0s |
| S9 | S9-04 | MLX Transcribe diarization | ℹ️  INFO | service not running | 0.0s |
| S9 | S9-05 | Workspace upload resolution | ℹ️  INFO | service not running | 0.0s |
| S10 | S10-01 | Persona itexpert | ✅ PASS | signals: ['bandwidth', 'latency', 'gather'] \| routed -> auto matches via worksp | 12.7s |
| S10 | S10-02 | Persona techreviewer | ✅ PASS | signals: ['feature', 'review'] \| routed -> auto matches via workspace 'auto': O | 7.6s |
| S10 | S10-03 | Persona webnavigator | ✅ PASS | signals: ['source', 'cited'] \| routed -> auto matches via workspace 'auto': Oll | 7.6s |
| S10 | S10-04 | Persona agentorchestrator | ✅ PASS | signals: ['step', 'plan', 'stage'] \| routed -> auto-agentic matches via workspa | 39.7s |
| S10 | S10-05 | Persona codebasewikidocumentationskill | ✅ PASS | signals: ['Args', 'Returns', 'raises'] \| routed -> auto-agentic matches via wor | 13.2s |
| S10 | S10-06 | Persona blueteamdefender | ✅ PASS | signals: ['encrypt', 'ransom', 'detect'] \| routed -> auto-blueteam matches via  | 39.9s |
| S10 | S10-07 | Persona cadquerydesigner | ❌ FAIL | no PERSONA_PROMPTS entry  [UNCLASSIFIED] | 0.0s |
| S10 | S10-08 | Persona printabilityengineer | ❌ FAIL | no PERSONA_PROMPTS entry  [UNCLASSIFIED] | 0.0s |
| S10 | S10-09 | Persona bugdiscoverycodeassistant | ✅ PASS | signals: ['indexerror', 'empty list', 'if not'] \| routed -> auto-coding matches | 21.8s |
| S10 | S10-10 | Persona codereviewassistant | ✅ PASS | signals: ['list', 'comprehension'] \| routed -> auto-coding matches via workspac | 3.8s |
| S10 | S10-11 | Persona codereviewer | ✅ PASS | signals: ['==', 'bool', 'True'] \| routed -> auto-coding matches via workspace ' | 7.6s |
| S10 | S10-12 | Persona creativecoder | ✅ PASS | signals: ['canvas', 'ball', 'click'] \| routed -> auto-coding matches via worksp | 6.7s |
| S10 | S10-13 | Persona devopsautomator | ✅ PASS | signals: ['#!/', 'bash', 'date'] \| routed -> auto-coding matches via workspace  | 21.5s |
| S10 | S10-14 | Persona e2edebugger | ✅ PASS | signals: ['step', 'plan', 'stage'] \| routed -> auto-coding matches via workspac | 15.2s |
| S10 | S10-15 | Persona e2etestauthor | ✅ PASS | signals: ['step', 'plan', 'stage'] \| routed -> auto-coding matches via workspac | 6.6s |
| S10 | S10-16 | Persona ethereumdeveloper | ✅ PASS | signals: ['contract', 'pragma', 'solidity'] \| routed -> auto-coding matches via | 7.3s |
| S10 | S10-17 | Persona excelsheet | ✅ PASS | signals: ['VLOOKUP', 'formula', 'range'] \| routed -> auto-coding matches via wo | 6.6s |
| S10 | S10-18 | Persona formfiller | ⚠️  WARN | no signals in:  \| routed -> auto-coding matches via workspace 'auto-coding': Ol | 6.5s |
| S10 | S10-19 | Persona fullstacksoftwaredeveloper | ✅ PASS | signals: ['GET', 'endpoint', 'REST'] \| routed -> auto-coding matches via worksp | 6.5s |
| S10 | S10-20 | Persona githubexpert | ✅ PASS | signals: ['rebase', 'merge', 'history'] \| routed -> auto-coding matches via wor | 6.4s |
| S10 | S10-21 | Persona goengineer | ✅ PASS | signals: ['middleware', 'http.handler', 'context'] \| routed -> auto-coding matc | 7.8s |
| S10 | S10-22 | Persona javascriptconsole | ✅ PASS | signals: ['18.84'] \| routed -> auto-coding matches via workspace 'auto-coding': | 4.0s |
| S10 | S10-23 | Persona kubernetesdockerrpglearningengin | ✅ PASS | signals: ['layer', 'image', 'cache'] \| routed -> auto-coding matches via worksp | 6.4s |
| S10 | S10-24 | Persona linuxterminal | ✅ PASS | signals: ['total', 'home'] \| routed -> auto-coding matches via workspace 'auto- | 8.8s |
| S10 | S10-25 | Persona pythoncodegeneratorcleanoptimize | ✅ PASS | signals: ['sorted', 'lambda', 'key'] \| routed -> auto-coding matches via worksp | 6.4s |
| S10 | S10-26 | Persona pythoninterpreter | ✅ PASS | signals: ['[3, 2, 1]', '3, 2, 1'] \| routed -> auto-coding matches via workspace | 2.6s |
| S10 | S10-27 | Persona rustengineer | ✅ PASS | signals: ['arc', 'lru', 'instant'] \| routed -> auto-coding matches via workspac | 15.2s |
| S10 | S10-28 | Persona seniorfrontenddeveloper | ✅ PASS | signals: ['useState', 'useEffect', 'hook'] \| routed -> auto-coding matches via  | 6.4s |
| S10 | S10-29 | Persona softwarequalityassurancetester | ⚠️  WARN | no signals in:  \| routed -> auto-coding matches via workspace 'auto-coding': Ol | 6.4s |
| S10 | S10-30 | Persona sqlterminal | ✅ PASS | signals: ['SELECT', 'FROM', 'WHERE'] \| routed -> auto-coding matches via worksp | 2.6s |
| S10 | S10-31 | Persona terraformwriter | ✅ PASS | signals: ['resource', 'aws_s3_bucket', 'encryption'] \| routed -> auto-coding ma | 7.6s |
| S10 | S10-32 | Persona typescriptengineer | ⚠️  WARN | no signals in:  \| routed -> auto-coding matches via workspace 'auto-coding': Ol | 6.4s |
| S10 | S10-33 | Persona ux-uideveloper | ✅ PASS | signals: ['mobile'] \| routed -> auto-coding matches via workspace 'auto-coding' | 2.5s |
| S10 | S10-34 | Persona creativewriter | ✅ PASS | signals: ['rain', 'detective', 'dark'] \| routed -> auto-creative matches via wo | 22.8s |
| S10 | S10-35 | Persona hermes3writer | ✅ PASS | signals: ['detective', 'coastal', 'town'] \| routed -> auto-creative matches via | 4.9s |
| S10 | S10-36 | Persona interviewcoach | ✅ PASS | signals: ['star', 'behavioral'] \| routed -> auto-creative matches via workspace | 5.0s |
| S10 | S10-37 | Persona proofreader | ✅ PASS | signals: ['address'] \| routed -> auto-creative matches via workspace 'auto-crea | 5.0s |
| S10 | S10-38 | Persona dailydriver | ℹ️  INFO | excluded from text-prompt smoke (attachment-driven) | 0.0s |
| S10 | S10-39 | Persona personalassistant | ✅ PASS | signals: ['plan', 'stage'] \| routed -> auto-daily matches via workspace 'auto-d | 18.8s |
| S10 | S10-40 | Persona dashboardarchitect | ⚠️  WARN | no signals in:  \| routed -> auto-data matches via workspace 'auto-data': Ollama | 33.6s |
| S10 | S10-41 | Persona dataanalyst | ✅ PASS | signals: ['correlation', 'causation', 'variable'] \| routed -> auto-data matches | 25.9s |
| S10 | S10-42 | Persona databasearchitect | ⚠️  WARN | no signals in:  \| routed -> auto-data matches via workspace 'auto-data': Ollama | 25.7s |
| S10 | S10-43 | Persona dataextractor | ⚠️  WARN | no signals in: ```json
{
  "name": "John Doe",
  "email": "john@example.com \| r | 9.4s |
| S10 | S10-44 | Persona datascientist | ✅ PASS | signals: ['feature', 'normalize', 'transform'] \| routed -> auto-data matches vi | 24.7s |
| S10 | S10-45 | Persona machinelearningengineer | ✅ PASS | signals: ['gradient', 'descent'] \| routed -> auto-data matches via workspace 'a | 24.3s |
| S10 | S10-46 | Persona statistician | ✅ PASS | signals: ['null', 'hypothesis'] \| routed -> auto-data matches via workspace 'au | 25.0s |
| S10 | S10-47 | Persona documentationarchitect | ⚠️  WARN | no signals in:  \| routed -> auto-documents matches via workspace 'auto-document | 12.5s |
| S10 | S10-48 | Persona phi4specialist | ⚠️  WARN | no signals in:  \| routed -> auto-documents matches via workspace 'auto-document | 9.1s |
| S10 | S10-49 | Persona techwriter | ✅ PASS | signals: ['endpoint', 'request', 'response'] \| routed -> auto-documents matches | 8.3s |
| S10 | S10-50 | Persona transcriptanalyst | ℹ️  INFO | excluded from text-prompt smoke (attachment-driven) | 0.0s |
| S10 | S10-51 | Persona mathreasoner | ✅ PASS | signals: ['eigenvalue', 'det', '3'] \| routed -> auto-math matches via workspace | 7.0s |
| S10 | S10-52 | Persona magistralstrategist | ✅ PASS | signals: ['milestone', 'KPI', 'launch'] \| routed -> auto-mistral matches via wo | 37.6s |
| S10 | S10-53 | Persona pentestlead | ❌ FAIL | no PERSONA_PROMPTS entry  [UNCLASSIFIED] | 0.0s |
| S10 | S10-54 | Persona phi4stemanalyst | ✅ PASS | signals: ['pythagor', 'triangle', 'hypotenuse'] \| routed -> auto-phi4 matches v | 84.4s |
| S10 | S10-55 | Persona businessanalyst | ✅ PASS | signals: ['stakeholder'] \| routed -> auto-reasoning matches via workspace 'auto | 10.2s |
| S10 | S10-56 | Persona devopsengineer | ✅ PASS | signals: ['pod', 'pending', 'running'] \| routed -> auto-reasoning matches via w | 6.3s |
| S10 | S10-57 | Persona gptossanalyst | ✅ PASS | signals: ['trade', 'complex', 'maintain'] \| routed -> auto-reasoning matches vi | 6.4s |
| S10 | S10-58 | Persona itarchitect | ✅ PASS | signals: ['availability'] \| routed -> auto-reasoning matches via workspace 'aut | 6.3s |
| S10 | S10-59 | Persona productmanager | ✅ PASS | signals: ['problem', 'rice'] \| routed -> auto-reasoning matches via workspace ' | 6.6s |
| S10 | S10-60 | Persona seniorsoftwareengineersoftwarear | ✅ PASS | signals: ['pattern', 'horizontal'] \| routed -> auto-reasoning matches via works | 6.3s |
| S10 | S10-61 | Persona pentester | ✅ PASS | signals: ['OWASP', 'test', 'methodology'] \| routed -> auto-redteam matches via  | 12.4s |
| S10 | S10-62 | Persona redteamoperator | ✅ PASS | signals: ['exploit', 'technique', 'initial'] \| routed -> auto-redteam matches v | 7.8s |
| S10 | S10-63 | Persona factchecker | ✅ PASS | signals: ['source'] \| routed -> auto-research matches via workspace 'auto-resea | 23.4s |
| S10 | S10-64 | Persona gemmaresearchanalyst | ✅ PASS | signals: ['method', 'data', 'research'] \| routed -> auto-research matches via w | 5.3s |
| S10 | S10-65 | Persona kbnavigator | ✅ PASS | signals: ['search', 'query', 'results'] \| routed -> auto-research matches via w | 5.3s |
| S10 | S10-66 | Persona marketanalyst | ✅ PASS | signals: ['trend', 'growth', 'quarter'] \| routed -> auto-research matches via w | 5.4s |
| S10 | S10-67 | Persona paywalledresearcher | ✅ PASS | signals: ['source'] \| routed -> auto-research matches via workspace 'auto-resea | 5.0s |
| S10 | S10-68 | Persona researchanalyst | ✅ PASS | signals: ['systematic', 'search', 'inclusion'] \| routed -> auto-research matche | 17.2s |
| S10 | S10-69 | Persona supergemma4researcher | ✅ PASS | signals: ['OSINT', 'search', 'verify'] \| routed -> auto-research matches via wo | 5.5s |
| S10 | S10-70 | Persona webresearcher | ✅ PASS | signals: ['source', 'url'] \| routed -> auto-research matches via workspace 'aut | 5.5s |
| S10 | S10-71 | Persona adversarysimulator | ❌ FAIL | no PERSONA_PROMPTS entry  [UNCLASSIFIED] | 0.0s |
| S10 | S10-72 | Persona cybersecurityspecialist | ✅ PASS | signals: ['zero', 'trust', 'assume'] \| routed -> auto-security matches via work | 7.9s |
| S10 | S10-73 | Persona networkengineer | ✅ PASS | signals: ['vlan', 'switchport', 'interface'] \| routed -> auto-security matches  | 3.2s |
| S10 | S10-74 | Persona splunkdetectionauthor | ✅ PASS | signals: ['tstats', 'authentication', 't1110'] \| routed -> auto-spl matches via | 32.0s |
| S10 | S10-75 | Persona splunksplgineer | ✅ PASS | signals: ['stats', 'count', 'fail'] \| routed -> auto-spl matches via workspace  | 8.4s |
| S10 | S10-76 | Persona chartanalyst | ✅ PASS | signals: ['value', 'quarter', 'revenue'] \| routed -> auto-reasoning matches via | 10.7s |
| S10 | S10-77 | Persona codescreenshotreader | ✅ PASS | signals: ['function', 'code'] \| routed -> auto-reasoning matches via workspace  | 6.2s |
| S10 | S10-78 | Persona diagramreader | ✅ PASS | signals: ['abstraction'] \| routed -> auto-reasoning matches via workspace 'auto | 6.2s |
| S10 | S10-79 | Persona gemma4e4bvision | ✅ PASS | signals: ['stack', 'trace', 'error'] \| routed -> auto-reasoning matches via wor | 6.3s |
| S10 | S10-80 | Persona gemma4jangvision | ✅ PASS | signals: ['credential', 'password', 'screenshot'] \| routed -> auto-reasoning ma | 6.4s |
| S10 | S10-81 | Persona ocrspecialist | ✅ PASS | signals: ['receipt', 'layout', 'total'] \| routed -> auto-reasoning matches via  | 6.3s |
| S10 | S10-82 | Persona whiteboardconverter | ✅ PASS | signals: ['relationships'] \| routed -> auto-reasoning matches via workspace 'au | 6.4s |
| S10 | S10-83 | Persona toolcomposer | ✅ PASS | signals: ['remember', 'read', 'call'] \| routed -> tools-specialist matches via  | 21.6s |
| S10c | S10c-00 | fixture loaded | ✅ PASS | 317 concrete scenarios across compliance personas | 0.0s |
| S10c | S10c-001 | cippolicywriter/gap-analysis-table-struc | ⚠️  WARN | MUSTs OK; SHOULD failed: structural.table_columns, classification.exact_token \| | 39.2s |
| S10c | S10c-002 | cippolicywriter/gap-analysis-table-struc | ⚠️  WARN | MUSTs OK; SHOULD failed: structural.table_columns, classification.exact_token \| | 37.4s |
| S10c | S10c-003 | cippolicywriter/gap-analysis-table-struc | ⚠️  WARN | MUSTs OK; SHOULD failed: classification.exact_token \| model=auto-compliance  [U | 41.5s |
| S10c | S10c-004 | cippolicywriter/gap-analysis-table-struc | ⚠️  WARN | MUSTs OK; SHOULD failed: structural.table_columns, classification.exact_token \| | 27.9s |
| S10c | S10c-005 | cippolicywriter/gap-analysis-table-struc | ⚠️  WARN | MUSTs OK; SHOULD failed: structural.table_columns, classification.exact_token \| | 35.1s |
| S10c | S10c-006 | cippolicywriter/gap-analysis-table-struc | ⚠️  WARN | MUSTs OK; SHOULD failed: structural.table_columns, classification.exact_token \| | 34.7s |
| S10c | S10c-007 | cippolicywriter/gap-analysis-table-struc | ⚠️  WARN | MUSTs OK; SHOULD failed: structural.table_columns, classification.exact_token \| | 38.2s |
| S10c | S10c-008 | cippolicywriter/classification-token-dis | ⚠️  WARN | MUSTs OK; SHOULD failed: classification.exact_token \| model=auto-compliance  [U | 1.9s |
| S10c | S10c-009 | cippolicywriter/classification-token-dis | ⚠️  WARN | MUSTs OK; SHOULD failed: classification.exact_token \| model=auto-compliance  [U | 2.2s |
| S10c | S10c-010 | cippolicywriter/classification-token-dis | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 1.9s |
| S10c | S10c-011 | cippolicywriter/classification-token-dis | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 1.6s |
| S10c | S10c-012 | cippolicywriter/classification-token-dis | ⚠️  WARN | MUSTs OK; SHOULD failed: classification.exact_token \| model=auto-compliance  [U | 2.5s |
| S10c | S10c-013 | cippolicywriter/classification-token-dis | ⚠️  WARN | MUSTs OK; SHOULD failed: classification.exact_token \| model=auto-compliance  [U | 6.8s |
| S10c | S10c-014 | cippolicywriter/classification-token-dis | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 1.9s |
| S10c | S10c-015 | cippolicywriter/anti-fabrication-verbati | ⚠️  WARN | MUSTs OK; SHOULD failed: anti_fabrication.refusal_pattern \| model=auto-complian | 10.7s |
| S10c | S10c-016 | cippolicywriter/anti-fabrication-verbati | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 13.8s |
| S10c | S10c-017 | cippolicywriter/anti-fabrication-verbati | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 8.7s |
| S10c | S10c-018 | cippolicywriter/anti-fabrication-verbati | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 19.4s |
| S10c | S10c-019 | cippolicywriter/anti-fabrication-verbati | ⚠️  WARN | MUSTs OK; SHOULD failed: anti_fabrication.refusal_pattern \| model=auto-complian | 16.7s |
| S10c | S10c-020 | cippolicywriter/anti-fabrication-verbati | ⚠️  WARN | MUSTs OK; SHOULD failed: anti_fabrication.refusal_pattern \| model=auto-complian | 26.0s |
| S10c | S10c-021 | cippolicywriter/anti-fabrication-verbati | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 6.4s |
| S10c | S10c-022 | cippolicywriter/refuse-to-certify-binary | ⚠️  WARN | MUSTs OK; SHOULD failed: refuse_to_certify \| model=auto-compliance  [UNCLASSIFI | 5.2s |
| S10c | S10c-023 | cippolicywriter/refuse-to-certify-binary | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 4.5s |
| S10c | S10c-024 | cippolicywriter/refuse-to-certify-binary | ⚠️  WARN | MUSTs OK; SHOULD failed: refuse_to_certify \| model=auto-compliance  [UNCLASSIFI | 8.7s |
| S10c | S10c-025 | cippolicywriter/refuse-to-certify-binary | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 8.0s |
| S10c | S10c-026 | cippolicywriter/refuse-to-certify-binary | ⚠️  WARN | MUSTs OK; SHOULD failed: refuse_to_certify \| model=auto-compliance  [UNCLASSIFI | 4.0s |
| S10c | S10c-027 | cippolicywriter/refuse-to-certify-binary | ⚠️  WARN | MUSTs OK; SHOULD failed: refuse_to_certify \| model=auto-compliance  [UNCLASSIFI | 8.8s |
| S10c | S10c-028 | cippolicywriter/refuse-to-certify-binary | ⚠️  WARN | MUSTs OK; SHOULD failed: refuse_to_certify \| model=auto-compliance  [UNCLASSIFI | 8.6s |
| S10c | S10c-029 | cippolicywriter/insufficient-context-vag | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 9.4s |
| S10c | S10c-030 | cippolicywriter/policy-modal-verbs[NERC_ | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 14.9s |
| S10c | S10c-031 | cippolicywriter/policy-modal-verbs[HIPAA | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 5.0s |
| S10c | S10c-032 | cippolicywriter/policy-modal-verbs[GDPR] | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 6.9s |
| S10c | S10c-033 | cippolicywriter/policy-modal-verbs[SOC2] | ⚠️  WARN | MUSTs OK; SHOULD failed: policy.modal_verbs \| model=auto-compliance  [UNCLASSIF | 8.3s |
| S10c | S10c-034 | cippolicywriter/policy-modal-verbs[PCI_D | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 6.3s |
| S10c | S10c-035 | cippolicywriter/policy-modal-verbs[NIST_ | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 6.9s |
| S10c | S10c-036 | cippolicywriter/policy-modal-verbs[ISO_2 | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 10.7s |
| S10c | S10c-037 | cippolicywriter/citation-format-discipli | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 4.8s |
| S10c | S10c-038 | cippolicywriter/citation-format-discipli | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 4.1s |
| S10c | S10c-039 | cippolicywriter/citation-format-discipli | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 3.3s |
| S10c | S10c-040 | cippolicywriter/citation-format-discipli | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 3.6s |
| S10c | S10c-041 | cippolicywriter/citation-format-discipli | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 3.9s |
| S10c | S10c-042 | cippolicywriter/citation-format-discipli | ⚠️  WARN | MUSTs OK; SHOULD failed: citation.format[NIST_800_53] \| model=auto-compliance   | 3.7s |
| S10c | S10c-043 | cippolicywriter/citation-format-discipli | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 3.1s |
| S10c | S10c-044 | cippolicywriter/dense-structured-tool-ou | ✅ PASS | all 2 assertions OK \| model=auto-compliance | 13.4s |
| S10c | S10c-045 | cippolicywriter/dense-structured-tool-ou | ✅ PASS | all 2 assertions OK \| model=auto-compliance | 7.2s |
| S10c | S10c-046 | cippolicywriter/dense-structured-tool-ou | ✅ PASS | all 2 assertions OK \| model=auto-compliance | 12.2s |
| S10c | S10c-047 | cippolicywriter/dense-structured-tool-ou | ✅ PASS | all 2 assertions OK \| model=auto-compliance | 13.5s |
| S10c | S10c-048 | cippolicywriter/dense-structured-tool-ou | ✅ PASS | all 2 assertions OK \| model=auto-compliance | 11.7s |
| S10c | S10c-049 | cippolicywriter/dense-structured-tool-ou | ✅ PASS | all 2 assertions OK \| model=auto-compliance | 11.1s |
| S10c | S10c-050 | cippolicywriter/dense-structured-tool-ou | ✅ PASS | all 2 assertions OK \| model=auto-compliance | 11.6s |
| S10c | S10c-051 | complianceanalyst/gap-analysis-table-str | ⚠️  WARN | MUSTs OK; SHOULD failed: structural.table_columns, classification.exact_token \| | 38.0s |
| S10c | S10c-052 | complianceanalyst/gap-analysis-table-str | ⚠️  WARN | MUSTs OK; SHOULD failed: structural.table_columns, classification.exact_token \| | 27.0s |
| S10c | S10c-053 | complianceanalyst/gap-analysis-table-str | ⚠️  WARN | MUSTs OK; SHOULD failed: structural.table_columns, classification.exact_token \| | 33.2s |
| S10c | S10c-054 | complianceanalyst/gap-analysis-table-str | ⚠️  WARN | MUSTs OK; SHOULD failed: structural.table_columns, classification.exact_token \| | 43.1s |
| S10c | S10c-055 | complianceanalyst/gap-analysis-table-str | ⚠️  WARN | MUSTs OK; SHOULD failed: structural.table_columns, classification.exact_token \| | 38.7s |
| S10c | S10c-056 | complianceanalyst/gap-analysis-table-str | ⚠️  WARN | MUSTs OK; SHOULD failed: structural.table_columns, classification.exact_token \| | 42.3s |
| S10c | S10c-057 | complianceanalyst/gap-analysis-table-str | ⚠️  WARN | MUSTs OK; SHOULD failed: structural.table_columns, classification.exact_token \| | 46.3s |
| S10c | S10c-058 | complianceanalyst/classification-token-d | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 2.3s |
| S10c | S10c-059 | complianceanalyst/classification-token-d | ⚠️  WARN | MUSTs OK; SHOULD failed: classification.exact_token \| model=auto-compliance  [U | 7.0s |
| S10c | S10c-060 | complianceanalyst/classification-token-d | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 1.9s |
| S10c | S10c-061 | complianceanalyst/classification-token-d | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 3.4s |
| S10c | S10c-062 | complianceanalyst/classification-token-d | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 1.7s |
| S10c | S10c-063 | complianceanalyst/classification-token-d | ⚠️  WARN | MUSTs OK; SHOULD failed: classification.exact_token \| model=auto-compliance  [U | 2.1s |
| S10c | S10c-064 | complianceanalyst/classification-token-d | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 3.8s |
| S10c | S10c-065 | complianceanalyst/anti-fabrication-verba | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 30.2s |
| S10c | S10c-066 | complianceanalyst/anti-fabrication-verba | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 8.1s |
| S10c | S10c-067 | complianceanalyst/anti-fabrication-verba | ⚠️  WARN | MUSTs OK; SHOULD failed: anti_fabrication.refusal_pattern \| model=auto-complian | 2.5s |
| S10c | S10c-068 | complianceanalyst/anti-fabrication-verba | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 24.2s |
| S10c | S10c-069 | complianceanalyst/anti-fabrication-verba | ⚠️  WARN | MUSTs OK; SHOULD failed: anti_fabrication.refusal_pattern \| model=auto-complian | 13.6s |
| S10c | S10c-070 | complianceanalyst/anti-fabrication-verba | ⚠️  WARN | MUSTs OK; SHOULD failed: anti_fabrication.refusal_pattern \| model=auto-complian | 28.6s |
| S10c | S10c-071 | complianceanalyst/anti-fabrication-verba | ⚠️  WARN | MUSTs OK; SHOULD failed: anti_fabrication.refusal_pattern \| model=auto-complian | 29.3s |
| S10c | S10c-072 | complianceanalyst/refuse-to-certify-bina | ⚠️  WARN | MUSTs OK; SHOULD failed: refuse_to_certify \| model=auto-compliance  [UNCLASSIFI | 4.6s |
| S10c | S10c-073 | complianceanalyst/refuse-to-certify-bina | ⚠️  WARN | MUSTs OK; SHOULD failed: refuse_to_certify \| model=auto-compliance  [UNCLASSIFI | 6.1s |
| S10c | S10c-074 | complianceanalyst/refuse-to-certify-bina | ⚠️  WARN | MUSTs OK; SHOULD failed: refuse_to_certify \| model=auto-compliance  [UNCLASSIFI | 11.9s |
| S10c | S10c-075 | complianceanalyst/refuse-to-certify-bina | ⚠️  WARN | MUSTs OK; SHOULD failed: refuse_to_certify \| model=auto-compliance  [UNCLASSIFI | 4.9s |
| S10c | S10c-076 | complianceanalyst/refuse-to-certify-bina | ⚠️  WARN | MUSTs OK; SHOULD failed: refuse_to_certify \| model=auto-compliance  [UNCLASSIFI | 5.6s |
| S10c | S10c-077 | complianceanalyst/refuse-to-certify-bina | ⚠️  WARN | MUSTs OK; SHOULD failed: refuse_to_certify \| model=auto-compliance  [UNCLASSIFI | 5.6s |
| S10c | S10c-078 | complianceanalyst/refuse-to-certify-bina | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 10.4s |
| S10c | S10c-079 | complianceanalyst/insufficient-context-v | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 3.2s |
| S10c | S10c-080 | complianceanalyst/policy-modal-verbs[NER | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 10.2s |
| S10c | S10c-081 | complianceanalyst/policy-modal-verbs[HIP | ⚠️  WARN | MUSTs OK; SHOULD failed: policy.modal_verbs \| model=auto-compliance  [UNCLASSIF | 9.8s |
| S10c | S10c-082 | complianceanalyst/policy-modal-verbs[GDP | ⚠️  WARN | MUSTs OK; SHOULD failed: policy.modal_verbs \| model=auto-compliance  [UNCLASSIF | 10.8s |
| S10c | S10c-083 | complianceanalyst/policy-modal-verbs[SOC | ⚠️  WARN | MUSTs OK; SHOULD failed: policy.modal_verbs \| model=auto-compliance  [UNCLASSIF | 9.5s |
| S10c | S10c-084 | complianceanalyst/policy-modal-verbs[PCI | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 14.2s |
| S10c | S10c-085 | complianceanalyst/policy-modal-verbs[NIS | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 11.3s |
| S10c | S10c-086 | complianceanalyst/policy-modal-verbs[ISO | ⚠️  WARN | MUSTs OK; SHOULD failed: policy.modal_verbs \| model=auto-compliance  [UNCLASSIF | 11.7s |
| S10c | S10c-087 | complianceanalyst/citation-format-discip | ⚠️  WARN | MUSTs OK; SHOULD failed: citation.format[NERC_CIP] \| model=auto-compliance  [UN | 4.5s |
| S10c | S10c-088 | complianceanalyst/citation-format-discip | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 10.2s |
| S10c | S10c-089 | complianceanalyst/citation-format-discip | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 4.3s |
| S10c | S10c-090 | complianceanalyst/citation-format-discip | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 5.1s |
| S10c | S10c-091 | complianceanalyst/citation-format-discip | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 3.5s |
| S10c | S10c-092 | complianceanalyst/citation-format-discip | ⚠️  WARN | MUSTs OK; SHOULD failed: citation.format[NIST_800_53] \| model=auto-compliance   | 3.5s |
| S10c | S10c-093 | complianceanalyst/citation-format-discip | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 4.9s |
| S10c | S10c-094 | complianceanalyst/cross-framework-mappin | ⚠️  WARN | MUSTs OK; SHOULD failed: citation.format[NIST_800_53] \| model=auto-compliance   | 22.0s |
| S10c | S10c-095 | complianceanalyst/dense-structured-tool- | ✅ PASS | all 2 assertions OK \| model=auto-compliance | 11.8s |
| S10c | S10c-096 | complianceanalyst/dense-structured-tool- | ✅ PASS | all 2 assertions OK \| model=auto-compliance | 10.2s |
| S10c | S10c-097 | complianceanalyst/dense-structured-tool- | ✅ PASS | all 2 assertions OK \| model=auto-compliance | 10.0s |
| S10c | S10c-098 | complianceanalyst/dense-structured-tool- | ✅ PASS | all 2 assertions OK \| model=auto-compliance | 12.9s |
| S10c | S10c-099 | complianceanalyst/dense-structured-tool- | ✅ PASS | all 2 assertions OK \| model=auto-compliance | 11.8s |
| S10c | S10c-100 | complianceanalyst/dense-structured-tool- | ✅ PASS | all 2 assertions OK \| model=auto-compliance | 11.9s |
| S10c | S10c-101 | complianceanalyst/dense-structured-tool- | ✅ PASS | all 2 assertions OK \| model=auto-compliance | 12.6s |
| S10c | S10c-102 | complianceanalyst/long-context-multi-cit | ⚠️  WARN | MUSTs OK; SHOULD failed: citation.format[NIST_800_53], classification.exact_toke | 53.1s |
| S10c | S10c-103 | gdprdpoadvisor/gap-analysis-table-struct | ⚠️  WARN | MUSTs OK; SHOULD failed: structural.table_columns, classification.exact_token \| | 47.7s |
| S10c | S10c-104 | gdprdpoadvisor/gap-analysis-table-struct | ⚠️  WARN | MUSTs OK; SHOULD failed: structural.table_columns, classification.exact_token \| | 25.5s |
| S10c | S10c-105 | gdprdpoadvisor/gap-analysis-table-struct | ⚠️  WARN | MUSTs OK; SHOULD failed: structural.table_columns, classification.exact_token \| | 32.6s |
| S10c | S10c-106 | gdprdpoadvisor/gap-analysis-table-struct | ⚠️  WARN | MUSTs OK; SHOULD failed: structural.table_columns, classification.exact_token \| | 59.0s |
| S10c | S10c-107 | gdprdpoadvisor/gap-analysis-table-struct | ⚠️  WARN | MUSTs OK; SHOULD failed: structural.table_columns, classification.exact_token \| | 28.9s |
| S10c | S10c-108 | gdprdpoadvisor/gap-analysis-table-struct | ⚠️  WARN | MUSTs OK; SHOULD failed: structural.table_columns, classification.exact_token \| | 42.2s |
| S10c | S10c-109 | gdprdpoadvisor/gap-analysis-table-struct | ⚠️  WARN | MUSTs OK; SHOULD failed: structural.table_columns, classification.exact_token \| | 71.7s |
| S10c | S10c-110 | gdprdpoadvisor/classification-token-disc | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 3.0s |
| S10c | S10c-111 | gdprdpoadvisor/classification-token-disc | ⚠️  WARN | MUSTs OK; SHOULD failed: classification.exact_token \| model=auto-compliance  [U | 2.1s |
| S10c | S10c-112 | gdprdpoadvisor/classification-token-disc | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 4.9s |
| S10c | S10c-113 | gdprdpoadvisor/classification-token-disc | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 1.8s |
| S10c | S10c-114 | gdprdpoadvisor/classification-token-disc | ⚠️  WARN | MUSTs OK; SHOULD failed: classification.exact_token \| model=auto-compliance  [U | 1.8s |
| S10c | S10c-115 | gdprdpoadvisor/classification-token-disc | ⚠️  WARN | MUSTs OK; SHOULD failed: classification.exact_token \| model=auto-compliance  [U | 1.6s |
| S10c | S10c-116 | gdprdpoadvisor/classification-token-disc | ⚠️  WARN | MUSTs OK; SHOULD failed: classification.exact_token \| model=auto-compliance  [U | 6.2s |
| S10c | S10c-117 | gdprdpoadvisor/anti-fabrication-verbatim | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 26.7s |
| S10c | S10c-118 | gdprdpoadvisor/anti-fabrication-verbatim | ⚠️  WARN | MUSTs OK; SHOULD failed: anti_fabrication.refusal_pattern \| model=auto-complian | 3.0s |
| S10c | S10c-119 | gdprdpoadvisor/anti-fabrication-verbatim | ⚠️  WARN | MUSTs OK; SHOULD failed: anti_fabrication.refusal_pattern \| model=auto-complian | 2.9s |
| S10c | S10c-120 | gdprdpoadvisor/anti-fabrication-verbatim | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 7.4s |
| S10c | S10c-121 | gdprdpoadvisor/anti-fabrication-verbatim | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 5.2s |
| S10c | S10c-122 | gdprdpoadvisor/anti-fabrication-verbatim | ⚠️  WARN | MUSTs OK; SHOULD failed: anti_fabrication.refusal_pattern \| model=auto-complian | 29.3s |
| S10c | S10c-123 | gdprdpoadvisor/anti-fabrication-verbatim | ⚠️  WARN | MUSTs OK; SHOULD failed: anti_fabrication.refusal_pattern \| model=auto-complian | 5.3s |
| S10c | S10c-124 | gdprdpoadvisor/refuse-to-certify-binary[ | ⚠️  WARN | MUSTs OK; SHOULD failed: refuse_to_certify \| model=auto-compliance  [UNCLASSIFI | 11.3s |
| S10c | S10c-125 | gdprdpoadvisor/refuse-to-certify-binary[ | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 6.7s |
| S10c | S10c-126 | gdprdpoadvisor/refuse-to-certify-binary[ | ⚠️  WARN | MUSTs OK; SHOULD failed: refuse_to_certify \| model=auto-compliance  [UNCLASSIFI | 12.3s |
| S10c | S10c-127 | gdprdpoadvisor/refuse-to-certify-binary[ | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 6.3s |
| S10c | S10c-128 | gdprdpoadvisor/refuse-to-certify-binary[ | ⚠️  WARN | MUSTs OK; SHOULD failed: refuse_to_certify \| model=auto-compliance  [UNCLASSIFI | 18.2s |
| S10c | S10c-129 | gdprdpoadvisor/refuse-to-certify-binary[ | ⚠️  WARN | MUSTs OK; SHOULD failed: refuse_to_certify \| model=auto-compliance  [UNCLASSIFI | 4.7s |
| S10c | S10c-130 | gdprdpoadvisor/refuse-to-certify-binary[ | ⚠️  WARN | MUSTs OK; SHOULD failed: refuse_to_certify \| model=auto-compliance  [UNCLASSIFI | 5.7s |
| S10c | S10c-131 | gdprdpoadvisor/insufficient-context-vagu | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 12.8s |
| S10c | S10c-132 | gdprdpoadvisor/citation-format-disciplin | ⚠️  WARN | MUSTs OK; SHOULD failed: citation.format[NERC_CIP] \| model=auto-compliance  [UN | 4.8s |
| S10c | S10c-133 | gdprdpoadvisor/citation-format-disciplin | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 3.5s |
| S10c | S10c-134 | gdprdpoadvisor/citation-format-disciplin | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 4.4s |
| S10c | S10c-135 | gdprdpoadvisor/citation-format-disciplin | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 3.4s |
| S10c | S10c-136 | gdprdpoadvisor/citation-format-disciplin | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 4.3s |
| S10c | S10c-137 | gdprdpoadvisor/citation-format-disciplin | ⚠️  WARN | MUSTs OK; SHOULD failed: citation.format[NIST_800_53] \| model=auto-compliance   | 3.7s |
| S10c | S10c-138 | gdprdpoadvisor/citation-format-disciplin | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 4.3s |
| S10c | S10c-139 | gdprdpoadvisor/dense-structured-tool-out | ✅ PASS | all 2 assertions OK \| model=auto-compliance | 10.5s |
| S10c | S10c-140 | gdprdpoadvisor/dense-structured-tool-out | ✅ PASS | all 2 assertions OK \| model=auto-compliance | 8.1s |
| S10c | S10c-141 | gdprdpoadvisor/dense-structured-tool-out | ✅ PASS | all 2 assertions OK \| model=auto-compliance | 9.9s |
| S10c | S10c-142 | gdprdpoadvisor/dense-structured-tool-out | ✅ PASS | all 2 assertions OK \| model=auto-compliance | 10.7s |
| S10c | S10c-143 | gdprdpoadvisor/dense-structured-tool-out | ✅ PASS | all 2 assertions OK \| model=auto-compliance | 10.6s |
| S10c | S10c-144 | gdprdpoadvisor/dense-structured-tool-out | ✅ PASS | all 2 assertions OK \| model=auto-compliance | 9.2s |
| S10c | S10c-145 | gdprdpoadvisor/dense-structured-tool-out | ✅ PASS | all 2 assertions OK \| model=auto-compliance | 11.2s |
| S10c | S10c-146 | hipaaprivacyofficer/gap-analysis-table-s | ⚠️  WARN | MUSTs OK; SHOULD failed: structural.table_columns, classification.exact_token \| | 41.0s |
| S10c | S10c-147 | hipaaprivacyofficer/gap-analysis-table-s | ⚠️  WARN | MUSTs OK; SHOULD failed: structural.table_columns, classification.exact_token \| | 48.8s |
| S10c | S10c-148 | hipaaprivacyofficer/gap-analysis-table-s | ⚠️  WARN | MUSTs OK; SHOULD failed: classification.exact_token \| model=auto-compliance  [U | 32.2s |
| S10c | S10c-149 | hipaaprivacyofficer/gap-analysis-table-s | ⚠️  WARN | MUSTs OK; SHOULD failed: structural.table_columns, classification.exact_token \| | 77.0s |
| S10c | S10c-150 | hipaaprivacyofficer/gap-analysis-table-s | ⚠️  WARN | MUSTs OK; SHOULD failed: structural.table_columns, classification.exact_token \| | 65.8s |
| S10c | S10c-151 | hipaaprivacyofficer/gap-analysis-table-s | ⚠️  WARN | MUSTs OK; SHOULD failed: structural.table_columns, classification.exact_token \| | 43.6s |
| S10c | S10c-152 | hipaaprivacyofficer/gap-analysis-table-s | ⚠️  WARN | MUSTs OK; SHOULD failed: structural.table_columns, classification.exact_token \| | 96.7s |
| S10c | S10c-153 | hipaaprivacyofficer/classification-token | ⚠️  WARN | MUSTs OK; SHOULD failed: classification.exact_token \| model=auto-compliance  [U | 2.2s |
| S10c | S10c-154 | hipaaprivacyofficer/classification-token | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 2.1s |
| S10c | S10c-155 | hipaaprivacyofficer/classification-token | ⚠️  WARN | MUSTs OK; SHOULD failed: classification.exact_token \| model=auto-compliance  [U | 3.1s |
| S10c | S10c-156 | hipaaprivacyofficer/classification-token | ⚠️  WARN | MUSTs OK; SHOULD failed: classification.exact_token \| model=auto-compliance  [U | 2.7s |
| S10c | S10c-157 | hipaaprivacyofficer/classification-token | ⚠️  WARN | MUSTs OK; SHOULD failed: classification.exact_token \| model=auto-compliance  [U | 1.8s |
| S10c | S10c-158 | hipaaprivacyofficer/classification-token | ⚠️  WARN | MUSTs OK; SHOULD failed: classification.exact_token \| model=auto-compliance  [U | 7.4s |
| S10c | S10c-159 | hipaaprivacyofficer/classification-token | ⚠️  WARN | MUSTs OK; SHOULD failed: classification.exact_token \| model=auto-compliance  [U | 2.2s |
| S10c | S10c-160 | hipaaprivacyofficer/anti-fabrication-ver | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 14.1s |
| S10c | S10c-161 | hipaaprivacyofficer/anti-fabrication-ver | ⚠️  WARN | MUSTs OK; SHOULD failed: anti_fabrication.refusal_pattern \| model=auto-complian | 7.3s |
| S10c | S10c-162 | hipaaprivacyofficer/anti-fabrication-ver | ⚠️  WARN | MUSTs OK; SHOULD failed: anti_fabrication.refusal_pattern \| model=auto-complian | 2.8s |
| S10c | S10c-163 | hipaaprivacyofficer/anti-fabrication-ver | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 30.4s |
| S10c | S10c-164 | hipaaprivacyofficer/anti-fabrication-ver | ⚠️  WARN | MUSTs OK; SHOULD failed: anti_fabrication.refusal_pattern \| model=auto-complian | 8.2s |
| S10c | S10c-165 | hipaaprivacyofficer/anti-fabrication-ver | ⚠️  WARN | MUSTs OK; SHOULD failed: anti_fabrication.refusal_pattern \| model=auto-complian | 17.4s |
| S10c | S10c-166 | hipaaprivacyofficer/anti-fabrication-ver | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 10.6s |
| S10c | S10c-167 | hipaaprivacyofficer/refuse-to-certify-bi | ⚠️  WARN | MUSTs OK; SHOULD failed: refuse_to_certify \| model=auto-compliance  [UNCLASSIFI | 23.4s |
| S10c | S10c-168 | hipaaprivacyofficer/refuse-to-certify-bi | ⚠️  WARN | MUSTs OK; SHOULD failed: refuse_to_certify \| model=auto-compliance  [UNCLASSIFI | 4.3s |
| S10c | S10c-169 | hipaaprivacyofficer/refuse-to-certify-bi | ⚠️  WARN | MUSTs OK; SHOULD failed: refuse_to_certify \| model=auto-compliance  [UNCLASSIFI | 4.5s |
| S10c | S10c-170 | hipaaprivacyofficer/refuse-to-certify-bi | ⚠️  WARN | MUSTs OK; SHOULD failed: refuse_to_certify \| model=auto-compliance  [UNCLASSIFI | 7.5s |
| S10c | S10c-171 | hipaaprivacyofficer/refuse-to-certify-bi | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 4.7s |
| S10c | S10c-172 | hipaaprivacyofficer/refuse-to-certify-bi | ⚠️  WARN | MUSTs OK; SHOULD failed: refuse_to_certify \| model=auto-compliance  [UNCLASSIFI | 2.7s |
| S10c | S10c-173 | hipaaprivacyofficer/refuse-to-certify-bi | ⚠️  WARN | MUSTs OK; SHOULD failed: refuse_to_certify \| model=auto-compliance  [UNCLASSIFI | 5.5s |
| S10c | S10c-174 | hipaaprivacyofficer/insufficient-context | ⚠️  WARN | MUSTs OK; SHOULD failed: insufficient_context.exact_phrase \| model=auto-complia | 5.9s |
| S10c | S10c-175 | hipaaprivacyofficer/citation-format-disc | ⚠️  WARN | MUSTs OK; SHOULD failed: citation.format[NERC_CIP] \| model=auto-compliance  [UN | 4.1s |
| S10c | S10c-176 | hipaaprivacyofficer/citation-format-disc | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 5.1s |
| S10c | S10c-177 | hipaaprivacyofficer/citation-format-disc | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 3.3s |
| S10c | S10c-178 | hipaaprivacyofficer/citation-format-disc | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 4.1s |
| S10c | S10c-179 | hipaaprivacyofficer/citation-format-disc | ⚠️  WARN | MUSTs OK; SHOULD failed: citation.format[PCI_DSS] \| model=auto-compliance  [UNC | 4.3s |
| S10c | S10c-180 | hipaaprivacyofficer/citation-format-disc | ⚠️  WARN | MUSTs OK; SHOULD failed: citation.format[NIST_800_53] \| model=auto-compliance   | 4.0s |
| S10c | S10c-181 | hipaaprivacyofficer/citation-format-disc | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 3.6s |
| S10c | S10c-182 | hipaaprivacyofficer/dense-structured-too | ✅ PASS | all 2 assertions OK \| model=auto-compliance | 11.0s |
| S10c | S10c-183 | hipaaprivacyofficer/dense-structured-too | ✅ PASS | all 2 assertions OK \| model=auto-compliance | 7.2s |
| S10c | S10c-184 | hipaaprivacyofficer/dense-structured-too | ✅ PASS | all 2 assertions OK \| model=auto-compliance | 10.6s |
| S10c | S10c-185 | hipaaprivacyofficer/dense-structured-too | ✅ PASS | all 2 assertions OK \| model=auto-compliance | 10.0s |
| S10c | S10c-186 | hipaaprivacyofficer/dense-structured-too | ✅ PASS | all 2 assertions OK \| model=auto-compliance | 10.8s |
| S10c | S10c-187 | hipaaprivacyofficer/dense-structured-too | ✅ PASS | all 2 assertions OK \| model=auto-compliance | 9.3s |
| S10c | S10c-188 | hipaaprivacyofficer/dense-structured-too | ✅ PASS | all 2 assertions OK \| model=auto-compliance | 9.7s |
| S10c | S10c-189 | nerccipcomplianceanalyst/gap-analysis-ta | ⚠️  WARN | MUSTs OK; SHOULD failed: structural.table_columns, classification.exact_token \| | 55.8s |
| S10c | S10c-190 | nerccipcomplianceanalyst/gap-analysis-ta | ⚠️  WARN | MUSTs OK; SHOULD failed: structural.table_columns, classification.exact_token \| | 39.7s |
| S10c | S10c-191 | nerccipcomplianceanalyst/gap-analysis-ta | ⚠️  WARN | MUSTs OK; SHOULD failed: structural.table_columns, classification.exact_token \| | 29.7s |
| S10c | S10c-192 | nerccipcomplianceanalyst/gap-analysis-ta | ⚠️  WARN | MUSTs OK; SHOULD failed: structural.table_columns, classification.exact_token \| | 37.4s |
| S10c | S10c-193 | nerccipcomplianceanalyst/gap-analysis-ta | ⚠️  WARN | MUSTs OK; SHOULD failed: structural.table_columns, classification.exact_token \| | 24.8s |
| S10c | S10c-194 | nerccipcomplianceanalyst/gap-analysis-ta | ⚠️  WARN | MUSTs OK; SHOULD failed: structural.table_columns, classification.exact_token \| | 46.9s |
| S10c | S10c-195 | nerccipcomplianceanalyst/gap-analysis-ta | ⚠️  WARN | MUSTs OK; SHOULD failed: classification.exact_token \| model=auto-compliance  [U | 37.5s |
| S10c | S10c-196 | nerccipcomplianceanalyst/classification- | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 6.8s |
| S10c | S10c-197 | nerccipcomplianceanalyst/classification- | ⚠️  WARN | MUSTs OK; SHOULD failed: classification.exact_token \| model=auto-compliance  [U | 2.3s |
| S10c | S10c-198 | nerccipcomplianceanalyst/classification- | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 1.5s |
| S10c | S10c-199 | nerccipcomplianceanalyst/classification- | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 1.7s |
| S10c | S10c-200 | nerccipcomplianceanalyst/classification- | ⚠️  WARN | MUSTs OK; SHOULD failed: classification.exact_token \| model=auto-compliance  [U | 1.9s |
| S10c | S10c-201 | nerccipcomplianceanalyst/classification- | ⚠️  WARN | MUSTs OK; SHOULD failed: classification.exact_token \| model=auto-compliance  [U | 2.5s |
| S10c | S10c-202 | nerccipcomplianceanalyst/classification- | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 2.1s |
| S10c | S10c-203 | nerccipcomplianceanalyst/anti-fabricatio | ⚠️  WARN | MUSTs OK; SHOULD failed: anti_fabrication.refusal_pattern \| model=auto-complian | 28.4s |
| S10c | S10c-204 | nerccipcomplianceanalyst/anti-fabricatio | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 2.0s |
| S10c | S10c-205 | nerccipcomplianceanalyst/anti-fabricatio | ⚠️  WARN | MUSTs OK; SHOULD failed: anti_fabrication.refusal_pattern \| model=auto-complian | 2.0s |
| S10c | S10c-206 | nerccipcomplianceanalyst/anti-fabricatio | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 13.5s |
| S10c | S10c-207 | nerccipcomplianceanalyst/anti-fabricatio | ⚠️  WARN | MUSTs OK; SHOULD failed: anti_fabrication.refusal_pattern \| model=auto-complian | 2.6s |
| S10c | S10c-208 | nerccipcomplianceanalyst/anti-fabricatio | ⚠️  WARN | MUSTs OK; SHOULD failed: anti_fabrication.refusal_pattern \| model=auto-complian | 25.6s |
| S10c | S10c-209 | nerccipcomplianceanalyst/anti-fabricatio | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 4.5s |
| S10c | S10c-210 | nerccipcomplianceanalyst/refuse-to-certi | ⚠️  WARN | MUSTs OK; SHOULD failed: refuse_to_certify \| model=auto-compliance  [UNCLASSIFI | 8.0s |
| S10c | S10c-211 | nerccipcomplianceanalyst/refuse-to-certi | ⚠️  WARN | MUSTs OK; SHOULD failed: refuse_to_certify \| model=auto-compliance  [UNCLASSIFI | 2.1s |
| S10c | S10c-212 | nerccipcomplianceanalyst/refuse-to-certi | ⚠️  WARN | MUSTs OK; SHOULD failed: refuse_to_certify \| model=auto-compliance  [UNCLASSIFI | 3.0s |
| S10c | S10c-213 | nerccipcomplianceanalyst/refuse-to-certi | ⚠️  WARN | MUSTs OK; SHOULD failed: refuse_to_certify \| model=auto-compliance  [UNCLASSIFI | 4.1s |
| S10c | S10c-214 | nerccipcomplianceanalyst/refuse-to-certi | ⚠️  WARN | MUSTs OK; SHOULD failed: refuse_to_certify \| model=auto-compliance  [UNCLASSIFI | 14.1s |
| S10c | S10c-215 | nerccipcomplianceanalyst/refuse-to-certi | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 6.8s |
| S10c | S10c-216 | nerccipcomplianceanalyst/refuse-to-certi | ⚠️  WARN | MUSTs OK; SHOULD failed: refuse_to_certify \| model=auto-compliance  [UNCLASSIFI | 11.1s |
| S10c | S10c-217 | nerccipcomplianceanalyst/insufficient-co | ⚠️  WARN | MUSTs OK; SHOULD failed: insufficient_context.exact_phrase \| model=auto-complia | 39.2s |
| S10c | S10c-218 | nerccipcomplianceanalyst/citation-format | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 4.5s |
| S10c | S10c-219 | nerccipcomplianceanalyst/citation-format | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 4.6s |
| S10c | S10c-220 | nerccipcomplianceanalyst/citation-format | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 2.8s |
| S10c | S10c-221 | nerccipcomplianceanalyst/citation-format | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 3.4s |
| S10c | S10c-222 | nerccipcomplianceanalyst/citation-format | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 4.8s |
| S10c | S10c-223 | nerccipcomplianceanalyst/citation-format | ⚠️  WARN | MUSTs OK; SHOULD failed: citation.format[NIST_800_53] \| model=auto-compliance   | 3.1s |
| S10c | S10c-224 | nerccipcomplianceanalyst/citation-format | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 3.3s |
| S10c | S10c-225 | nerccipcomplianceanalyst/dense-structure | ✅ PASS | all 2 assertions OK \| model=auto-compliance | 9.6s |
| S10c | S10c-226 | nerccipcomplianceanalyst/dense-structure | ✅ PASS | all 2 assertions OK \| model=auto-compliance | 10.8s |
| S10c | S10c-227 | nerccipcomplianceanalyst/dense-structure | ✅ PASS | all 2 assertions OK \| model=auto-compliance | 9.5s |
| S10c | S10c-228 | nerccipcomplianceanalyst/dense-structure | ✅ PASS | all 2 assertions OK \| model=auto-compliance | 10.3s |
| S10c | S10c-229 | nerccipcomplianceanalyst/dense-structure | ✅ PASS | all 2 assertions OK \| model=auto-compliance | 12.6s |
| S10c | S10c-230 | nerccipcomplianceanalyst/dense-structure | ✅ PASS | all 2 assertions OK \| model=auto-compliance | 12.7s |
| S10c | S10c-231 | nerccipcomplianceanalyst/dense-structure | ✅ PASS | all 2 assertions OK \| model=auto-compliance | 10.8s |
| S10c | S10c-232 | pcidssassessor/gap-analysis-table-struct | ⚠️  WARN | MUSTs OK; SHOULD failed: structural.table_columns, classification.exact_token \| | 47.4s |
| S10c | S10c-233 | pcidssassessor/gap-analysis-table-struct | ⚠️  WARN | MUSTs OK; SHOULD failed: structural.table_columns, classification.exact_token \| | 30.1s |
| S10c | S10c-234 | pcidssassessor/gap-analysis-table-struct | ⚠️  WARN | MUSTs OK; SHOULD failed: structural.table_columns, classification.exact_token \| | 39.2s |
| S10c | S10c-235 | pcidssassessor/gap-analysis-table-struct | ⚠️  WARN | MUSTs OK; SHOULD failed: structural.table_columns, classification.exact_token \| | 36.0s |
| S10c | S10c-236 | pcidssassessor/gap-analysis-table-struct | ⚠️  WARN | MUSTs OK; SHOULD failed: classification.exact_token \| model=auto-compliance  [U | 30.4s |
| S10c | S10c-237 | pcidssassessor/gap-analysis-table-struct | ⚠️  WARN | MUSTs OK; SHOULD failed: structural.table_columns, classification.exact_token \| | 46.3s |
| S10c | S10c-238 | pcidssassessor/gap-analysis-table-struct | ⚠️  WARN | MUSTs OK; SHOULD failed: structural.table_columns, classification.exact_token \| | 45.1s |
| S10c | S10c-239 | pcidssassessor/classification-token-disc | ⚠️  WARN | MUSTs OK; SHOULD failed: classification.exact_token \| model=auto-compliance  [U | 2.4s |
| S10c | S10c-240 | pcidssassessor/classification-token-disc | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 2.0s |
| S10c | S10c-241 | pcidssassessor/classification-token-disc | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 6.0s |
| S10c | S10c-242 | pcidssassessor/classification-token-disc | ⚠️  WARN | MUSTs OK; SHOULD failed: classification.exact_token \| model=auto-compliance  [U | 1.8s |
| S10c | S10c-243 | pcidssassessor/classification-token-disc | ⚠️  WARN | MUSTs OK; SHOULD failed: classification.exact_token \| model=auto-compliance  [U | 5.0s |
| S10c | S10c-244 | pcidssassessor/classification-token-disc | ⚠️  WARN | MUSTs OK; SHOULD failed: classification.exact_token \| model=auto-compliance  [U | 1.8s |
| S10c | S10c-245 | pcidssassessor/classification-token-disc | ⚠️  WARN | MUSTs OK; SHOULD failed: classification.exact_token \| model=auto-compliance  [U | 1.9s |
| S10c | S10c-246 | pcidssassessor/anti-fabrication-verbatim | ⚠️  WARN | MUSTs OK; SHOULD failed: anti_fabrication.refusal_pattern \| model=auto-complian | 21.1s |
| S10c | S10c-247 | pcidssassessor/anti-fabrication-verbatim | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 7.0s |
| S10c | S10c-248 | pcidssassessor/anti-fabrication-verbatim | ⚠️  WARN | MUSTs OK; SHOULD failed: anti_fabrication.refusal_pattern \| model=auto-complian | 5.4s |
| S10c | S10c-249 | pcidssassessor/anti-fabrication-verbatim | ⚠️  WARN | MUSTs OK; SHOULD failed: anti_fabrication.refusal_pattern \| model=auto-complian | 13.0s |
| S10c | S10c-250 | pcidssassessor/anti-fabrication-verbatim | ⚠️  WARN | MUSTs OK; SHOULD failed: anti_fabrication.refusal_pattern \| model=auto-complian | 16.6s |
| S10c | S10c-251 | pcidssassessor/anti-fabrication-verbatim | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 14.3s |
| S10c | S10c-252 | pcidssassessor/anti-fabrication-verbatim | ⚠️  WARN | MUSTs OK; SHOULD failed: anti_fabrication.refusal_pattern \| model=auto-complian | 58.3s |
| S10c | S10c-253 | pcidssassessor/refuse-to-certify-binary[ | ⚠️  WARN | MUSTs OK; SHOULD failed: refuse_to_certify \| model=auto-compliance  [UNCLASSIFI | 4.2s |
| S10c | S10c-254 | pcidssassessor/refuse-to-certify-binary[ | ⚠️  WARN | MUSTs OK; SHOULD failed: refuse_to_certify \| model=auto-compliance  [UNCLASSIFI | 18.9s |
| S10c | S10c-255 | pcidssassessor/refuse-to-certify-binary[ | ⚠️  WARN | MUSTs OK; SHOULD failed: refuse_to_certify \| model=auto-compliance  [UNCLASSIFI | 7.4s |
| S10c | S10c-256 | pcidssassessor/refuse-to-certify-binary[ | ⚠️  WARN | MUSTs OK; SHOULD failed: refuse_to_certify \| model=auto-compliance  [UNCLASSIFI | 10.0s |
| S10c | S10c-257 | pcidssassessor/refuse-to-certify-binary[ | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 15.8s |
| S10c | S10c-258 | pcidssassessor/refuse-to-certify-binary[ | ⚠️  WARN | MUSTs OK; SHOULD failed: refuse_to_certify \| model=auto-compliance  [UNCLASSIFI | 6.0s |
| S10c | S10c-259 | pcidssassessor/refuse-to-certify-binary[ | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 7.4s |
| S10c | S10c-260 | pcidssassessor/insufficient-context-vagu | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 8.1s |
| S10c | S10c-261 | pcidssassessor/citation-format-disciplin | ⚠️  WARN | MUSTs OK; SHOULD failed: citation.format[NERC_CIP] \| model=auto-compliance  [UN | 4.7s |
| S10c | S10c-262 | pcidssassessor/citation-format-disciplin | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 5.8s |
| S10c | S10c-263 | pcidssassessor/citation-format-disciplin | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 5.4s |
| S10c | S10c-264 | pcidssassessor/citation-format-disciplin | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 4.2s |
| S10c | S10c-265 | pcidssassessor/citation-format-disciplin | ⚠️  WARN | MUSTs OK; SHOULD failed: citation.format[PCI_DSS] \| model=auto-compliance  [UNC | 5.9s |
| S10c | S10c-266 | pcidssassessor/citation-format-disciplin | ⚠️  WARN | MUSTs OK; SHOULD failed: citation.format[NIST_800_53] \| model=auto-compliance   | 3.7s |
| S10c | S10c-267 | pcidssassessor/citation-format-disciplin | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 4.3s |
| S10c | S10c-268 | pcidssassessor/dense-structured-tool-out | ✅ PASS | all 2 assertions OK \| model=auto-compliance | 11.9s |
| S10c | S10c-269 | pcidssassessor/dense-structured-tool-out | ✅ PASS | all 2 assertions OK \| model=auto-compliance | 10.2s |
| S10c | S10c-270 | pcidssassessor/dense-structured-tool-out | ✅ PASS | all 2 assertions OK \| model=auto-compliance | 9.9s |
| S10c | S10c-271 | pcidssassessor/dense-structured-tool-out | ✅ PASS | all 2 assertions OK \| model=auto-compliance | 7.6s |
| S10c | S10c-272 | pcidssassessor/dense-structured-tool-out | ✅ PASS | all 2 assertions OK \| model=auto-compliance | 8.8s |
| S10c | S10c-273 | pcidssassessor/dense-structured-tool-out | ✅ PASS | all 2 assertions OK \| model=auto-compliance | 9.0s |
| S10c | S10c-274 | pcidssassessor/dense-structured-tool-out | ✅ PASS | all 2 assertions OK \| model=auto-compliance | 8.6s |
| S10c | S10c-275 | soc2auditor/gap-analysis-table-structure | ⚠️  WARN | MUSTs OK; SHOULD failed: structural.table_columns, classification.exact_token \| | 81.4s |
| S10c | S10c-276 | soc2auditor/gap-analysis-table-structure | ⚠️  WARN | MUSTs OK; SHOULD failed: structural.table_columns, classification.exact_token \| | 34.0s |
| S10c | S10c-277 | soc2auditor/gap-analysis-table-structure | ⚠️  WARN | MUSTs OK; SHOULD failed: structural.table_columns \| model=auto-compliance  [UNC | 59.9s |
| S10c | S10c-278 | soc2auditor/gap-analysis-table-structure | ⚠️  WARN | MUSTs OK; SHOULD failed: structural.table_columns, classification.exact_token \| | 35.2s |
| S10c | S10c-279 | soc2auditor/gap-analysis-table-structure | ⚠️  WARN | MUSTs OK; SHOULD failed: structural.table_columns, classification.exact_token \| | 47.0s |
| S10c | S10c-280 | soc2auditor/gap-analysis-table-structure | ⚠️  WARN | MUSTs OK; SHOULD failed: structural.table_columns, classification.exact_token \| | 45.4s |
| S10c | S10c-281 | soc2auditor/gap-analysis-table-structure | ⚠️  WARN | MUSTs OK; SHOULD failed: structural.table_columns, classification.exact_token \| | 48.4s |
| S10c | S10c-282 | soc2auditor/classification-token-discipl | ⚠️  WARN | MUSTs OK; SHOULD failed: classification.exact_token \| model=auto-compliance  [U | 12.7s |
| S10c | S10c-283 | soc2auditor/classification-token-discipl | ⚠️  WARN | MUSTs OK; SHOULD failed: classification.exact_token \| model=auto-compliance  [U | 7.7s |
| S10c | S10c-284 | soc2auditor/classification-token-discipl | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 2.5s |
| S10c | S10c-285 | soc2auditor/classification-token-discipl | ⚠️  WARN | MUSTs OK; SHOULD failed: classification.exact_token \| model=auto-compliance  [U | 4.0s |
| S10c | S10c-286 | soc2auditor/classification-token-discipl | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 2.4s |
| S10c | S10c-287 | soc2auditor/classification-token-discipl | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 3.9s |
| S10c | S10c-288 | soc2auditor/classification-token-discipl | ⚠️  WARN | MUSTs OK; SHOULD failed: classification.exact_token \| model=auto-compliance  [U | 6.2s |
| S10c | S10c-289 | soc2auditor/anti-fabrication-verbatim-te | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 6.7s |
| S10c | S10c-290 | soc2auditor/anti-fabrication-verbatim-te | ⚠️  WARN | MUSTs OK; SHOULD failed: anti_fabrication.refusal_pattern \| model=auto-complian | 10.6s |
| S10c | S10c-291 | soc2auditor/anti-fabrication-verbatim-te | ⚠️  WARN | MUSTs OK; SHOULD failed: anti_fabrication.refusal_pattern \| model=auto-complian | 2.2s |
| S10c | S10c-292 | soc2auditor/anti-fabrication-verbatim-te | ⚠️  WARN | MUSTs OK; SHOULD failed: anti_fabrication.refusal_pattern \| model=auto-complian | 42.1s |
| S10c | S10c-293 | soc2auditor/anti-fabrication-verbatim-te | ⚠️  WARN | MUSTs OK; SHOULD failed: anti_fabrication.refusal_pattern \| model=auto-complian | 23.8s |
| S10c | S10c-294 | soc2auditor/anti-fabrication-verbatim-te | ⚠️  WARN | MUSTs OK; SHOULD failed: anti_fabrication.refusal_pattern \| model=auto-complian | 28.1s |
| S10c | S10c-295 | soc2auditor/anti-fabrication-verbatim-te | ⚠️  WARN | MUSTs OK; SHOULD failed: anti_fabrication.refusal_pattern \| model=auto-complian | 19.6s |
| S10c | S10c-296 | soc2auditor/refuse-to-certify-binary[NER | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 10.7s |
| S10c | S10c-297 | soc2auditor/refuse-to-certify-binary[HIP | ⚠️  WARN | MUSTs OK; SHOULD failed: refuse_to_certify \| model=auto-compliance  [UNCLASSIFI | 7.1s |
| S10c | S10c-298 | soc2auditor/refuse-to-certify-binary[GDP | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 13.3s |
| S10c | S10c-299 | soc2auditor/refuse-to-certify-binary[SOC | ⚠️  WARN | MUSTs OK; SHOULD failed: refuse_to_certify \| model=auto-compliance  [UNCLASSIFI | 7.7s |
| S10c | S10c-300 | soc2auditor/refuse-to-certify-binary[PCI | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 8.1s |
| S10c | S10c-301 | soc2auditor/refuse-to-certify-binary[NIS | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 9.1s |
| S10c | S10c-302 | soc2auditor/refuse-to-certify-binary[ISO | ⚠️  WARN | MUSTs OK; SHOULD failed: refuse_to_certify \| model=auto-compliance  [UNCLASSIFI | 12.6s |
| S10c | S10c-303 | soc2auditor/insufficient-context-vague-p | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 7.1s |
| S10c | S10c-304 | soc2auditor/citation-format-discipline[N | ⚠️  WARN | MUSTs OK; SHOULD failed: citation.format[NERC_CIP] \| model=auto-compliance  [UN | 4.6s |
| S10c | S10c-305 | soc2auditor/citation-format-discipline[H | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 3.7s |
| S10c | S10c-306 | soc2auditor/citation-format-discipline[G | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 3.9s |
| S10c | S10c-307 | soc2auditor/citation-format-discipline[S | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 4.0s |
| S10c | S10c-308 | soc2auditor/citation-format-discipline[P | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 4.9s |
| S10c | S10c-309 | soc2auditor/citation-format-discipline[N | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 6.2s |
| S10c | S10c-310 | soc2auditor/citation-format-discipline[I | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 3.8s |
| S10c | S10c-311 | soc2auditor/dense-structured-tool-output | ✅ PASS | all 2 assertions OK \| model=auto-compliance | 10.6s |
| S10c | S10c-312 | soc2auditor/dense-structured-tool-output | ✅ PASS | all 2 assertions OK \| model=auto-compliance | 10.6s |
| S10c | S10c-313 | soc2auditor/dense-structured-tool-output | ✅ PASS | all 2 assertions OK \| model=auto-compliance | 11.1s |
| S10c | S10c-314 | soc2auditor/dense-structured-tool-output | ✅ PASS | all 2 assertions OK \| model=auto-compliance | 8.2s |
| S10c | S10c-315 | soc2auditor/dense-structured-tool-output | ✅ PASS | all 2 assertions OK \| model=auto-compliance | 9.0s |
| S10c | S10c-316 | soc2auditor/dense-structured-tool-output | ✅ PASS | all 2 assertions OK \| model=auto-compliance | 8.5s |
| S10c | S10c-317 | soc2auditor/dense-structured-tool-output | ✅ PASS | all 2 assertions OK \| model=auto-compliance | 9.0s |
| S12 | S12-01 | SearXNG search | ✅ PASS | 21 results | 0.8s |
| S13 | S13-01 | Embedding service | ✅ PASS | HTTP 200 | 0.0s |
| S13 | S13-02 | Generate embedding | ✅ PASS | dim: 1024 | 0.1s |
| S16 | S16-01 | Security MCP health | ✅ PASS | service: security-mcp | 0.0s |
| S16 | S16-02 | classify_vulnerability (RCE — expect hig | ✅ PASS | {
  "severity": "critical",
  "confidence": 0.9497,
  "probabilities": {
    "lo | 1.9s |
| S16 | S16-03 | classify_vulnerability (info disclosure  | ✅ PASS | {
  "severity": "medium",
  "confidence": 0.8871,
  "probabilities": {
    "low" | 0.5s |
| S16 | S16-04 | classify_vulnerability returns probabili | ✅ PASS | {
  "severity": "high",
  "confidence": 0.9027,
  "probabilities": {
    "low":  | 0.1s |
| S17 | S17-01 | CAD render MCP health | ✅ PASS | HTTP 200 | 0.0s |
| S17 | S17-02 | Tools manifest — render_mesh / render_op | ✅ PASS | found: ['convert_cad', 'render_mesh', 'render_openscad'] | 0.0s |
| S17 | S17-03 | render_mesh — 20×10×5 box → PNG + bbox | ✅ PASS | {
  "png_path": "/workspace/generated/models3d/render_062867ad.png",
  "png_url" | 2.0s |
| S17 | S17-ERR | Section error | ❌ FAIL | _mcp_raw() missing 1 required keyword-only argument: 'ok_fn'  [UNCLASSIFIED] | 0.0s |
| S18 | S18-01 | Sandbox health + lab-exec posture | ✅ PASS | HTTP 200 \| lab_exec_active=True | 0.0s |
| S18 | S18-02 | DC (10.10.11.21) AD port scan | ✅ PASS | {
  "success": true,
  "stdout": "53/tcp open\n88/tcp open\n135/tcp open\n389/tc | 0.4s |
| S18 | S18-03 | Kerberoast — 3 SPN hashes | ✅ PASS | {
  "success": true,
  "stdout": "Impacket v0.14.0.dev0 - Copyright Fortra, LLC  | 0.7s |
| S18 | S18-04 | AS-REP roast — arya.stark + ned.stark | ✅ PASS | {
  "success": true,
  "stdout": "Impacket v0.14.0.dev0 - Copyright Fortra, LLC  | 0.4s |
| S18 | S18-05 | Password spray (nxc SMB) — valid hit | ✅ PASS | {
  "success": true,
  "stdout": "[*] First time use detected\n[*] Creating home | 1.2s |
| S18 | S18-06 | BloodHound collection — graph data | ✅ PASS | {
  "success": true,
  "stdout": "INFO: BloodHound.py for BloodHound Community E | 1.3s |
| S18 | S18-07 | WinRM exec on srv01 (10.10.11.33) | ✅ PASS | {
  "success": true,
  "stdout": "[*] First time use detected\n[*] Creating home | 0.9s |
| S18 | S18-08 | Full kill chain: crack → ACL abuse → DCS | ✅ PASS | {
  "success": true,
  "stdout": "=== [1/3] Ensure GenericAll ACE via dacledit = | 0.7s |
| S21 | S21-01 | LLM router enabled | ✅ PASS | LLM_ROUTER_ENABLED=True | 0.0s |
| S21 | S21-02 | LLM router model available | ✅ PASS | model: hf.co/QuantFactory/Llama-3.2-3B-Instruct-abliterat | 0.0s |
| S21 | S21-03 | LLM router security intent | ✅ PASS | routed→auto-redteam \| model: auto-redteam | 12.2s |
| S21 | S21-04 | LLM router coding intent | ✅ PASS | routed→auto-coding \| model: auto-coding | 29.2s |
| S21 | S21-05 | LLM router compliance intent | ✅ PASS | routed→auto-compliance \| model: auto-compliance | 8.4s |
| S21 | S21-06 | routing_descriptions.json | ✅ PASS | 28 workspace descriptions | 0.0s |
| S21 | S21-07 | routing_examples.json | ✅ PASS | 44 examples | 0.0s |
| S23 | S23-01 | GPT-OSS:20B available | ✅ PASS | gpt-oss in Ollama catalog: True | 0.0s |
| S23 | S23-03 | Gemma 4 E4B VLM available | ✅ PASS | gemma4:e4b in Ollama catalog: True | 0.0s |
| S23 | S23-04 | Phi-4 available | ✅ PASS | phi4:14b in Ollama catalog: True | 0.0s |
| S23 | S23-05 | Magistral-Small available | ✅ PASS | magistral in Ollama catalog: True | 0.0s |
| S23 | S23-06 | Phi-4-reasoning-plus available | ✅ PASS | phi4-reasoning in Ollama catalog: True | 0.0s |
| S23 | S23-07 | GLM-4.7-Flash available | ✅ PASS | glm-4.7-flash in Ollama catalog: True | 0.0s |
| S40 | S40-01 | Pipeline /metrics | ✅ PASS | 653 metrics | 0.0s |
| S40 | S40-02 | Prometheus targets | ✅ PASS | 2/4 up | 0.0s |
| S40 | S40-03 | Grafana API | ✅ PASS | HTTP 401 | 0.0s |
| S41 | S41-01 | /health/all aggregator | ✅ PASS | 10/15 services ok: pipeline, ollama, mcp_documents, mcp_execution, mcp_security | 0.0s |
| S41 | S41-02 | bench-* concurrency=1 | ✅ PASS | all 65 bench-* workspaces capped at 1 | 0.0s |
| S41 | S41-03 | /admin/refresh-tools | ✅ PASS | 38 tools registered | 0.0s |
| S41 | S41-04 | Power metrics in /metrics | ✅ PASS | portal5_power_* and portal5_energy_* present | 0.0s |
| S41 | S41-05 | Workspace consistency | ✅ PASS | 95 workspaces, pipe+yaml match | 0.0s |
| S42 | S42-01 | Browser MCP health | ✅ PASS | status=ok, profiles=0 | 0.0s |
| S42 | S42-02 | Browser MCP tools | ✅ PASS | 8 tools: browser_navigate, browser_snapshot, browser_click, browser_fill... | 0.0s |
| S50 | S50-01 | Empty prompt handled gracefully | ✅ PASS | HTTP 200 | 4.0s |
| S50 | S50-02 | Oversized prompt handled | ✅ PASS | HTTP 408 | 91.1s |
| S50 | S50-03 | Invalid model slug handled | ✅ PASS | HTTP 200 \| model=nonexistent-workspace | 12.5s |
| S50 | S50-04 | Pipeline /health surfaces backend count | ✅ PASS | healthy: 6 | 0.0s |
| S50 | S50-05 | Malformed JSON rejected | ✅ PASS | HTTP 400 | 0.0s |
| S50 | S50-06 | Missing auth rejected with 401 | ✅ PASS | HTTP 401 | 0.0s |
| S60 | S60-01 | Tool registry loaded | ✅ PASS | 0 tools: ... | 0.0s |
| S60 | S60-02 | Workspace tool whitelists | ✅ PASS | 20/95 workspaces have tools | 0.0s |
| S60 | S60-03 | Persona tool resolution | ✅ PASS | tools_allow override works: ['execute_python'] | 0.0s |
| S60 | S60-04 | Tool dispatch function | ✅ PASS | exists | 0.0s |
| S60 | S60-05 | MAX_TOOL_HOPS | ✅ PASS | value=20 | 0.0s |
| S60 | S60-06 | Tool-call Prometheus metrics | ✅ PASS | portal5_tool_calls_total + duration present | 0.0s |
| S60 | S60-07 | agentorchestrator persona | ✅ PASS | slug=agentorchestrator, workspace=auto-agentic | 0.0s |
| S70 | S70-01 | SearXNG web search | ✅ PASS | 20 results returned | 0.7s |
| S70 | S70-02 | Research MCP health | ✅ PASS | {"status":"ok","service":"research-mcp","backend":"searxng"} | 0.0s |
| S70 | S70-03 | Memory MCP health | ✅ PASS | {"status":"ok","service":"memory-mcp","stored":11} | 0.0s |
| S70 | S70-04 | RAG MCP health | ✅ PASS | {"status":"ok","service":"rag-mcp","knowledge_bases":[]} | 0.0s |
| S70 | S70-05 | Embedding service health | ✅ PASS | {"status":"ok","model":"microsoft/harrier-oss-v1-0.6b"} | 0.0s |
| S70 | S70-06 | Research personas | ✅ PASS | 6/6 present | 0.0s |
| S70 | S70-07 | auto-research tool whitelist | ✅ PASS | tools: ['web_search', 'web_fetch', 'news_search', 'kb_search', 'kb_search_all',  | 0.0s |
| S70 | S70-08 | Memory MCP round-trip | ✅ PASS | stored+recalled: id=6f033e8a, sim=0.42, 1 hits | 0.4s |