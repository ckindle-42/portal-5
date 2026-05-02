# Portal 5 Acceptance Test Results — V6

**Date:** 2026-05-02 09:34:15
**Git SHA:** dbce71a
**Sections:** S0, S1, S2, S12, S13, S15, S40, S50, S3a, S6, S16, S10, S10c, S21, S3b, S11, S20, S22, S23, S4, S5, S8, S9, S7, S30, S31, S41, S42, S60, S70, S3
**Runtime:** 8715s (145m 15s)

## Summary

| Status | Count |
|--------|-------|
| ✅ PASS | 236 |
| ❌ FAIL | 155 |
| ⚠️  WARN | 92 |
| ℹ️  INFO | 2 |
| **Total** | **485** |

**Code defects: 8 · Env issues: 0 · Unclassified: 239**

## Results

| Section | ID | Name | Status | Detail | Duration |
|---------|-----|------|--------|--------|----------|
| S0 | S0-01 | Python version | ✅ PASS | Python 3.14.4 | 0.0s |
| S0 | S0-02 | Required packages | ✅ PASS | all present | 0.2s |
| S0 | S0-03 | .env file exists | ✅ PASS | /Users/chris/projects/portal-5/.env | 0.0s |
| S0 | S0-04 | PIPELINE_API_KEY configured | ✅ PASS | key length: 42 | 0.0s |
| S0 | S0-05 | Git repository | ✅ PASS | SHA: dbce71a | 0.0s |
| S0 | S0-06 | MLX watchdog status | ℹ️  INFO | watchdog not running — start with ./launch.sh start-mlx-watchdog | 0.0s |
| S0 | S0-07 | Deployed MLX proxy matches source | ✅ PASS | deployed copy in sync | 0.0s |
| S1 | S1-01 | backends.yaml exists | ✅ PASS | /Users/chris/projects/portal-5/config/backends.yaml | 0.0s |
| S1 | S1-02 | backends.yaml valid YAML | ✅ PASS | 7 backends | 0.0s |
| S1 | S1-03 | Workspace IDs consistent | ✅ PASS | 30 workspaces | 0.0s |
| S1 | S1-04 | Persona YAMLs valid | ✅ PASS | 96 personas | 0.1s |
| S1 | S1-05 | Persona count matches yaml file count | ✅ PASS | 96 loaded, 96 yaml files | 0.0s |
| S1 | S1-06 | routing_descriptions.json | ✅ PASS | 19 descriptions | 0.0s |
| S1 | S1-07 | routing_examples.json | ✅ PASS | 3 examples | 0.0s |
| S1 | S1-08 | MLX routing: VLM models in VLM_MODELS (m | ❌ FAIL | 31b_vlm=False e4b_vlm=False 31b_all=False jang_vlm=False jang_all=False 26b_abl_ | 0.0s |
| S1 | S1-09 | MLX routing: text-only models NOT in VLM | ❌ FAIL | magistral: all=False vlm=False \| phi4: all=False vlm=False  [UNCLASSIFIED] | 0.0s |
| S1 | S1-10 | Persona workspace_model values are pipel | ✅ PASS | all 96 personas use valid workspace_model values | 0.0s |
| S1 | S1-11 | All personas have PERSONA_PROMPTS entrie | ❌ FAIL | missing prompts for: ['cippolicywriter', 'complianceanalyst', 'gdprdpoadvisor',  | 0.0s |
| S1 | S1-17 | workspace hint reachability | ❌ FAIL | [Errno 2] No such file or directory: '/dev/shm/portal_metrics/gauge_all_35445.db | 0.1s |
| S2 | S2-01 | Docker daemon | ✅ PASS | Docker OK | 0.2s |
| S2 | S2-02 | Pipeline /health | ✅ PASS | backends=7/7, workspaces=30 | 0.0s |
| S2 | S2-03 | Ollama | ✅ PASS | 27 models | 0.0s |
| S2 | S2-04 | Open WebUI | ✅ PASS | HTTP 200 | 0.0s |
| S2 | S2-05 | SearXNG | ✅ PASS | HTTP 200 | 0.0s |
| S2 | S2-06 | Prometheus | ✅ PASS | HTTP 200 | 0.0s |
| S2 | S2-07 | Grafana | ✅ PASS | HTTP 200 | 0.0s |
| S2 | S2-08 | MCP documents (:8913) | ✅ PASS | HTTP 200 | 0.0s |
| S2 | S2-09 | MCP music (:8912) | ✅ PASS | HTTP 200 | 0.0s |
| S2 | S2-10 | MCP tts (:8916) | ✅ PASS | HTTP 200 | 0.0s |
| S2 | S2-11 | MCP whisper (:8915) | ✅ PASS | HTTP 200 | 0.0s |
| S2 | S2-12 | MCP sandbox (:8914) | ✅ PASS | HTTP 200 | 0.0s |
| S2 | S2-13 | MCP video (:8911) | ✅ PASS | HTTP 200 | 0.0s |
| S2 | S2-14 | MCP embedding (:8917) | ✅ PASS | HTTP 200 | 0.0s |
| S2 | S2-15 | MCP security (:8919) | ✅ PASS | HTTP 200 | 0.0s |
| S2 | S2-16 | MLX proxy | ✅ PASS | state=none | 0.0s |
| S2 | S2-17 | MLX Speech | ✅ PASS | HTTP 200 | 0.0s |
| S12 | S12-01 | SearXNG search | ✅ PASS | 31 results | 1.0s |
| S13 | S13-01 | Embedding service | ✅ PASS | HTTP 200 | 0.0s |
| S13 | S13-02 | Generate embedding | ✅ PASS | dim: 1024 | 0.9s |
| S15 | S15-01 | Workspace root exists | ✅ PASS | /Users/chris/AI_Output | 0.0s |
| S15 | S15-02 | Workspace subdirectories | ✅ PASS | all present | 0.0s |
| S15 | S15-03 | OWUI uploads bind mount | ✅ PASS | host↔OWUI bidirectional | 0.1s |
| S15 | S15-04 | workspace helper imports | ✅ PASS | /Users/chris/AI_Output | 0.0s |
| S15 | S15-05 | AUDIO_STT_ENGINE disabled | ✅ PASS | empty (correct) | 0.1s |
| S40 | S40-01 | Pipeline /metrics | ✅ PASS | 1096 metrics | 0.0s |
| S40 | S40-02 | Prometheus targets | ✅ PASS | 3/5 up | 0.0s |
| S40 | S40-03 | Grafana API | ✅ PASS | HTTP 401 | 0.0s |
| S50 | S50-ERR | Section error | ❌ FAIL | cannot import name 'time' from 'tests.acceptance._common' (/Users/chris/projects |  |
| S3a | S3a-01 | Workspace auto | ✅ PASS | signals: ['DNS', 'domain', 'IP'] \| routed -> mlx-community/Dolphin3.0-Llama3.1- | 28.2s |
| S3a | S3a-02 | Workspace auto-video | ✅ PASS | signals: ['sun', 'mountain', 'light'] \| routed -> dolphin-llama3:8b matches Oll | 3.4s |
| S3a | S3a-03 | Workspace auto-music | ✅ PASS | signals: ['beat', 'drum'] \| routed -> dolphin-llama3:8b matches Ollama:dolphin- | 3.6s |
| S3a | S3a-04 | Workspace auto-security | ✅ PASS | signals: ['injection', 'XSS', 'authentication'] \| routed -> baronllm:q6_k match | 14.1s |
| S3a | S3a-05 | Workspace auto-redteam | ✅ PASS | signals: ['sudo', 'SUID', 'privilege'] \| routed -> baronllm:q6_k matches Ollama | 8.6s |
| S3a | S3a-06 | Workspace auto-blueteam | ✅ PASS | signals: ['traffic', 'network', 'monitor'] \| routed -> lily-cybersecurity:7b-q4 | 10.0s |
| S6 | S6-01 | auto-security routing | ✅ PASS | signals: ['sql', 'inject', 'parameter'] \| routed -> baronllm:q6_k matches Ollam | 8.6s |
| S6 | S6-02 | auto-redteam routing | ✅ PASS | signals: ['recon', 'scan', 'exploit'] \| routed -> baronllm:q6_k matches Ollama: | 8.6s |
| S6 | S6-03 | auto-blueteam routing | ✅ PASS | signals: ['backup', 'incident', 'response'] \| routed -> lily-cybersecurity:7b-q | 6.3s |
| S6 | S6-04 | Content-aware security routing | ✅ PASS | routed to security workspace: True | 1.3s |
| S16 | S16-01 | Security MCP health | ✅ PASS | service: security-mcp | 0.0s |
| S16 | S16-02 | classify_vulnerability (RCE — expect hig | ✅ PASS | {
  "severity": "critical",
  "confidence": 0.9508,
  "probabilities": {
    "lo | 1.1s |
| S16 | S16-03 | classify_vulnerability (info disclosure  | ✅ PASS | {
  "severity": "medium",
  "confidence": 0.8815,
  "probabilities": {
    "low" | 0.1s |
| S16 | S16-04 | classify_vulnerability returns probabili | ✅ PASS | {
  "severity": "critical",
  "confidence": 0.808,
  "probabilities": {
    "low | 0.1s |
| S10 | S10-01 | Persona itexpert | ✅ PASS | signals: ['gather', 'troubleshoot', 'connection'] \| routed -> mlx-community/Dol | 9.8s |
| S10 | S10-02 | Persona techreviewer | ✅ PASS | signals: ['camera', 'chip', 'feature'] \| routed -> mlx-community/Dolphin3.0-Lla | 9.7s |
| S10 | S10-03 | Persona webnavigator | ✅ PASS | signals: ['source'] \| routed -> mlx-community/Dolphin3.0-Llama3.1-8B-8bi matche | 10.3s |
| S10 | S10-04 | Persona blueteamdefender | ✅ PASS | signals: ['encrypt', 'extension', 'ransom'] \| routed -> lily-cybersecurity:7b-q | 5.9s |
| S10 | S10-05 | Persona creativewriter | ✅ PASS | signals: ['rain', 'detective', 'city'] \| routed -> divinetribe/gemma-4-31b-it-a | 62.6s |
| S10 | S10-06 | Persona hermes3writer | ✅ PASS | signals: ['detective', 'coastal', 'town'] \| routed -> divinetribe/gemma-4-31b-i | 21.6s |
| S10 | S10-07 | Persona interviewcoach | ✅ PASS | signals: ['behavioral'] \| routed -> divinetribe/gemma-4-31b-it-abliterated-4 ma | 22.6s |
| S10 | S10-08 | Persona proofreader | ✅ PASS | signals: ['there are', 'address', 'addressed'] \| routed -> divinetribe/gemma-4- | 22.5s |
| S10 | S10-09 | Persona pentester | ✅ PASS | signals: ['OWASP', 'test', 'inject'] \| routed -> baronllm:q6_k matches via work | 7.5s |
| S10 | S10-10 | Persona redteamoperator | ✅ PASS | signals: ['exploit', 'technique', 'initial'] \| routed -> baronllm:q6_k matches  | 4.2s |
| S10 | S10-11 | Persona cybersecurityspecialist | ✅ PASS | signals: ['zero', 'trust', 'verify'] \| routed -> baronllm:q6_k matches via work | 7.5s |
| S10 | S10-12 | Persona networkengineer | ✅ PASS | signals: ['vlan', 'switchport', 'interface'] \| routed -> baronllm:q6_k matches  | 5.1s |
| S10c | S10c-00 | fixture loaded | ✅ PASS | 317 concrete scenarios across compliance personas | 0.0s |
| S10c | S10c-001 | cippolicywriter/gap-analysis-table-struc | ❌ FAIL | MUST failed: structural.table_columns, classification.exact_token \| model=deeps | 68.6s |
| S10c | S10c-002 | cippolicywriter/gap-analysis-table-struc | ❌ FAIL | MUST failed: structural.table_columns, classification.exact_token \| model=deeps | 52.3s |
| S10c | S10c-003 | cippolicywriter/gap-analysis-table-struc | ❌ FAIL | MUST failed: structural.table_columns, classification.exact_token \| model=deeps | 52.6s |
| S10c | S10c-004 | cippolicywriter/gap-analysis-table-struc | ❌ FAIL | MUST failed: structural.table_columns, classification.exact_token \| model=deeps | 52.5s |
| S10c | S10c-005 | cippolicywriter/gap-analysis-table-struc | ❌ FAIL | MUST failed: structural.table_columns, classification.exact_token \| model=deeps | 47.5s |
| S10c | S10c-006 | cippolicywriter/gap-analysis-table-struc | ❌ FAIL | MUST failed: structural.table_columns, classification.exact_token \| model=deeps | 25.3s |
| S10c | S10c-007 | cippolicywriter/gap-analysis-table-struc | ❌ FAIL | MUST failed: structural.table_columns, classification.exact_token \| model=deeps | 52.2s |
| S10c | S10c-008 | cippolicywriter/classification-token-dis | ✅ PASS | all 1 assertions OK \| model=deepseek-r1:32b-q4_k_m | 10.8s |
| S10c | S10c-009 | cippolicywriter/classification-token-dis | ✅ PASS | all 1 assertions OK \| model=deepseek-r1:32b-q4_k_m | 4.2s |
| S10c | S10c-010 | cippolicywriter/classification-token-dis | ❌ FAIL | MUST failed: classification.exact_token \| model=deepseek-r1:32b-q4_k_m  [UNCLAS | 2.9s |
| S10c | S10c-011 | cippolicywriter/classification-token-dis | ✅ PASS | all 1 assertions OK \| model=deepseek-r1:32b-q4_k_m | 52.9s |
| S10c | S10c-012 | cippolicywriter/classification-token-dis | ✅ PASS | all 1 assertions OK \| model=deepseek-r1:32b-q4_k_m | 24.7s |
| S10c | S10c-013 | cippolicywriter/classification-token-dis | ❌ FAIL | MUST failed: classification.exact_token \| model=deepseek-r1:32b-q4_k_m  [UNCLAS | 5.4s |
| S10c | S10c-014 | cippolicywriter/classification-token-dis | ❌ FAIL | MUST failed: classification.exact_token \| model=deepseek-r1:32b-q4_k_m  [UNCLAS | 5.5s |
| S10c | S10c-015 | cippolicywriter/anti-fabrication-verbati | ❌ FAIL | MUST failed: anti_fabrication.refusal_pattern \| model=deepseek-r1:32b-q4_k_m  [ | 52.5s |
| S10c | S10c-016 | cippolicywriter/anti-fabrication-verbati | ⚠️  WARN | MUSTs OK; SHOULD failed: anti_fabrication.refusal_pattern \| model=deepseek-r1:3 | 27.4s |
| S10c | S10c-017 | cippolicywriter/anti-fabrication-verbati | ⚠️  WARN | MUSTs OK; SHOULD failed: anti_fabrication.refusal_pattern \| model=deepseek-r1:3 | 11.4s |
| S10c | S10c-018 | cippolicywriter/anti-fabrication-verbati | ⚠️  WARN | MUSTs OK; SHOULD failed: anti_fabrication.refusal_pattern \| model=deepseek-r1:3 | 8.4s |
| S10c | S10c-019 | cippolicywriter/anti-fabrication-verbati | ⚠️  WARN | MUSTs OK; SHOULD failed: anti_fabrication.refusal_pattern \| model=deepseek-r1:3 | 9.2s |
| S10c | S10c-020 | cippolicywriter/anti-fabrication-verbati | ⚠️  WARN | MUSTs OK; SHOULD failed: anti_fabrication.refusal_pattern \| model=deepseek-r1:3 | 50.6s |
| S10c | S10c-021 | cippolicywriter/anti-fabrication-verbati | ⚠️  WARN | MUSTs OK; SHOULD failed: anti_fabrication.refusal_pattern \| model=deepseek-r1:3 | 6.5s |
| S10c | S10c-022 | cippolicywriter/refuse-to-certify-binary | ⚠️  WARN | MUSTs OK; SHOULD failed: refuse_to_certify \| model=deepseek-r1:32b-q4_k_m  [UNC | 14.5s |
| S10c | S10c-023 | cippolicywriter/refuse-to-certify-binary | ⚠️  WARN | MUSTs OK; SHOULD failed: refuse_to_certify \| model=deepseek-r1:32b-q4_k_m  [UNC | 21.1s |
| S10c | S10c-024 | cippolicywriter/refuse-to-certify-binary | ⚠️  WARN | MUSTs OK; SHOULD failed: refuse_to_certify \| model=deepseek-r1:32b-q4_k_m  [UNC | 2.9s |
| S10c | S10c-025 | cippolicywriter/refuse-to-certify-binary | ⚠️  WARN | MUSTs OK; SHOULD failed: refuse_to_certify \| model=deepseek-r1:32b-q4_k_m  [UNC | 23.4s |
| S10c | S10c-026 | cippolicywriter/refuse-to-certify-binary | ⚠️  WARN | MUSTs OK; SHOULD failed: refuse_to_certify \| model=deepseek-r1:32b-q4_k_m  [UNC | 30.6s |
| S10c | S10c-027 | cippolicywriter/refuse-to-certify-binary | ⚠️  WARN | MUSTs OK; SHOULD failed: refuse_to_certify \| model=deepseek-r1:32b-q4_k_m  [UNC | 8.4s |
| S10c | S10c-028 | cippolicywriter/refuse-to-certify-binary | ⚠️  WARN | MUSTs OK; SHOULD failed: refuse_to_certify \| model=deepseek-r1:32b-q4_k_m  [UNC | 1.1s |
| S10c | S10c-029 | cippolicywriter/insufficient-context-vag | ❌ FAIL | MUST failed: insufficient_context.exact_phrase \| model=deepseek-r1:32b-q4_k_m   | 52.3s |
| S10c | S10c-030 | cippolicywriter/policy-modal-verbs[NERC_ | ❌ FAIL | MUST failed: policy.modal_verbs, structural.policy_sections \| model=deepseek-r1 | 14.4s |
| S10c | S10c-031 | cippolicywriter/policy-modal-verbs[HIPAA | ❌ FAIL | MUST failed: policy.modal_verbs, structural.policy_sections \| model=deepseek-r1 | 16.8s |
| S10c | S10c-032 | cippolicywriter/policy-modal-verbs[GDPR] | ❌ FAIL | MUST failed: policy.modal_verbs, structural.policy_sections \| model=deepseek-r1 | 14.1s |
| S10c | S10c-033 | cippolicywriter/policy-modal-verbs[SOC2] | ❌ FAIL | MUST failed: policy.modal_verbs, structural.policy_sections \| model=deepseek-r1 | 42.8s |
| S10c | S10c-034 | cippolicywriter/policy-modal-verbs[PCI_D | ❌ FAIL | MUST failed: policy.modal_verbs, structural.policy_sections \| model=deepseek-r1 | 18.0s |
| S10c | S10c-035 | cippolicywriter/policy-modal-verbs[NIST_ | ❌ FAIL | MUST failed: policy.modal_verbs, structural.policy_sections \| model=deepseek-r1 | 19.2s |
| S10c | S10c-036 | cippolicywriter/policy-modal-verbs[ISO_2 | ❌ FAIL | MUST failed: policy.modal_verbs, structural.policy_sections \| model=deepseek-r1 | 27.7s |
| S10c | S10c-037 | cippolicywriter/citation-format-discipli | ✅ PASS | all 1 assertions OK \| model=deepseek-r1:32b-q4_k_m | 5.7s |
| S10c | S10c-038 | cippolicywriter/citation-format-discipli | ❌ FAIL | MUST failed: citation.format[HIPAA] \| model=deepseek-r1:32b-q4_k_m  [UNCLASSIFI | 10.4s |
| S10c | S10c-039 | cippolicywriter/citation-format-discipli | ✅ PASS | all 1 assertions OK \| model=deepseek-r1:32b-q4_k_m | 11.3s |
| S10c | S10c-040 | cippolicywriter/citation-format-discipli | ❌ FAIL | MUST failed: citation.format[SOC2] \| model=deepseek-r1:32b-q4_k_m  [UNCLASSIFIE | 10.1s |
| S10c | S10c-041 | cippolicywriter/citation-format-discipli | ❌ FAIL | MUST failed: citation.format[PCI_DSS] \| model=deepseek-r1:32b-q4_k_m  [UNCLASSI | 10.1s |
| S10c | S10c-042 | cippolicywriter/citation-format-discipli | ✅ PASS | all 1 assertions OK \| model=deepseek-r1:32b-q4_k_m | 13.8s |
| S10c | S10c-043 | cippolicywriter/citation-format-discipli | ❌ FAIL | MUST failed: citation.format[ISO_27001] \| model=deepseek-r1:32b-q4_k_m  [UNCLAS | 10.4s |
| S10c | S10c-044 | cippolicywriter/dense-structured-tool-ou | ✅ PASS | all 2 assertions OK \| model=deepseek-r1:32b-q4_k_m | 14.2s |
| S10c | S10c-045 | cippolicywriter/dense-structured-tool-ou | ✅ PASS | all 2 assertions OK \| model=deepseek-r1:32b-q4_k_m | 12.8s |
| S10c | S10c-046 | cippolicywriter/dense-structured-tool-ou | ✅ PASS | all 2 assertions OK \| model=deepseek-r1:32b-q4_k_m | 10.7s |
| S10c | S10c-047 | cippolicywriter/dense-structured-tool-ou | ✅ PASS | all 2 assertions OK \| model=deepseek-r1:32b-q4_k_m | 10.6s |
| S10c | S10c-048 | cippolicywriter/dense-structured-tool-ou | ✅ PASS | all 2 assertions OK \| model=deepseek-r1:32b-q4_k_m | 12.6s |
| S10c | S10c-049 | cippolicywriter/dense-structured-tool-ou | ✅ PASS | all 2 assertions OK \| model=deepseek-r1:32b-q4_k_m | 9.2s |
| S10c | S10c-050 | cippolicywriter/dense-structured-tool-ou | ✅ PASS | all 2 assertions OK \| model=deepseek-r1:32b-q4_k_m | 35.5s |
| S10c | S10c-051 | complianceanalyst/gap-analysis-table-str | ❌ FAIL | MUST failed: structural.table_columns, classification.exact_token \| model=deeps | 29.4s |
| S10c | S10c-052 | complianceanalyst/gap-analysis-table-str | ❌ FAIL | MUST failed: structural.table_columns \| model=deepseek-r1:32b-q4_k_m  [UNCLASSI | 52.5s |
| S10c | S10c-053 | complianceanalyst/gap-analysis-table-str | ❌ FAIL | MUST failed: structural.table_columns, classification.exact_token \| model=deeps | 52.5s |
| S10c | S10c-054 | complianceanalyst/gap-analysis-table-str | ❌ FAIL | MUST failed: structural.table_columns, classification.exact_token \| model=deeps | 52.2s |
| S10c | S10c-055 | complianceanalyst/gap-analysis-table-str | ❌ FAIL | MUST failed: structural.table_columns, classification.exact_token \| model=deeps | 24.0s |
| S10c | S10c-056 | complianceanalyst/gap-analysis-table-str | ❌ FAIL | MUST failed: structural.table_columns, classification.exact_token \| model=deeps | 52.3s |
| S10c | S10c-057 | complianceanalyst/gap-analysis-table-str | ❌ FAIL | MUST failed: structural.table_columns, classification.exact_token \| model=deeps | 52.4s |
| S10c | S10c-058 | complianceanalyst/classification-token-d | ✅ PASS | all 1 assertions OK \| model=deepseek-r1:32b-q4_k_m | 19.6s |
| S10c | S10c-059 | complianceanalyst/classification-token-d | ✅ PASS | all 1 assertions OK \| model=deepseek-r1:32b-q4_k_m | 5.1s |
| S10c | S10c-060 | complianceanalyst/classification-token-d | ❌ FAIL | MUST failed: classification.exact_token \| model=deepseek-r1:32b-q4_k_m  [UNCLAS | 4.4s |
| S10c | S10c-061 | complianceanalyst/classification-token-d | ✅ PASS | all 1 assertions OK \| model=deepseek-r1:32b-q4_k_m | 32.4s |
| S10c | S10c-062 | complianceanalyst/classification-token-d | ✅ PASS | all 1 assertions OK \| model=deepseek-r1:32b-q4_k_m | 4.7s |
| S10c | S10c-063 | complianceanalyst/classification-token-d | ✅ PASS | all 1 assertions OK \| model=deepseek-r1:32b-q4_k_m | 9.5s |
| S10c | S10c-064 | complianceanalyst/classification-token-d | ❌ FAIL | MUST failed: classification.exact_token \| model=deepseek-r1:32b-q4_k_m  [UNCLAS | 5.0s |
| S10c | S10c-065 | complianceanalyst/anti-fabrication-verba | ⚠️  WARN | MUSTs OK; SHOULD failed: anti_fabrication.refusal_pattern \| model=deepseek-r1:3 | 13.0s |
| S10c | S10c-066 | complianceanalyst/anti-fabrication-verba | ❌ FAIL | MUST failed: anti_fabrication.refusal_pattern \| model=deepseek-r1:32b-q4_k_m  [ | 11.7s |
| S10c | S10c-067 | complianceanalyst/anti-fabrication-verba | ⚠️  WARN | MUSTs OK; SHOULD failed: anti_fabrication.refusal_pattern \| model=deepseek-r1:3 | 14.5s |
| S10c | S10c-068 | complianceanalyst/anti-fabrication-verba | ✅ PASS | all 1 assertions OK \| model=deepseek-r1:32b-q4_k_m | 7.8s |
| S10c | S10c-069 | complianceanalyst/anti-fabrication-verba | ⚠️  WARN | MUSTs OK; SHOULD failed: anti_fabrication.refusal_pattern \| model=deepseek-r1:3 | 13.0s |
| S10c | S10c-070 | complianceanalyst/anti-fabrication-verba | ⚠️  WARN | MUSTs OK; SHOULD failed: anti_fabrication.refusal_pattern \| model=deepseek-r1:3 | 43.5s |
| S10c | S10c-071 | complianceanalyst/anti-fabrication-verba | ⚠️  WARN | MUSTs OK; SHOULD failed: anti_fabrication.refusal_pattern \| model=deepseek-r1:3 | 7.3s |
| S10c | S10c-072 | complianceanalyst/refuse-to-certify-bina | ⚠️  WARN | MUSTs OK; SHOULD failed: refuse_to_certify \| model=deepseek-r1:32b-q4_k_m  [UNC | 9.8s |
| S10c | S10c-073 | complianceanalyst/refuse-to-certify-bina | ⚠️  WARN | MUSTs OK; SHOULD failed: refuse_to_certify \| model=deepseek-r1:32b-q4_k_m  [UNC | 1.1s |
| S10c | S10c-074 | complianceanalyst/refuse-to-certify-bina | ⚠️  WARN | MUSTs OK; SHOULD failed: refuse_to_certify \| model=deepseek-r1:32b-q4_k_m  [UNC | 0.8s |
| S10c | S10c-075 | complianceanalyst/refuse-to-certify-bina | ⚠️  WARN | MUSTs OK; SHOULD failed: refuse_to_certify \| model=deepseek-r1:32b-q4_k_m  [UNC | 7.5s |
| S10c | S10c-076 | complianceanalyst/refuse-to-certify-bina | ⚠️  WARN | MUSTs OK; SHOULD failed: refuse_to_certify \| model=deepseek-r1:32b-q4_k_m  [UNC | 1.1s |
| S10c | S10c-077 | complianceanalyst/refuse-to-certify-bina | ⚠️  WARN | MUSTs OK; SHOULD failed: refuse_to_certify \| model=deepseek-r1:32b-q4_k_m  [UNC | 7.5s |
| S10c | S10c-078 | complianceanalyst/refuse-to-certify-bina | ⚠️  WARN | MUSTs OK; SHOULD failed: refuse_to_certify \| model=deepseek-r1:32b-q4_k_m  [UNC | 29.8s |
| S10c | S10c-079 | complianceanalyst/insufficient-context-v | ❌ FAIL | MUST failed: insufficient_context.exact_phrase \| model=deepseek-r1:32b-q4_k_m   | 50.6s |
| S10c | S10c-080 | complianceanalyst/policy-modal-verbs[NER | ❌ FAIL | MUST failed: policy.modal_verbs, structural.policy_sections \| model=deepseek-r1 | 16.7s |
| S10c | S10c-081 | complianceanalyst/policy-modal-verbs[HIP | ❌ FAIL | MUST failed: policy.modal_verbs, structural.policy_sections \| model=deepseek-r1 | 17.5s |
| S10c | S10c-082 | complianceanalyst/policy-modal-verbs[GDP | ❌ FAIL | MUST failed: policy.modal_verbs, structural.policy_sections \| model=deepseek-r1 | 16.7s |
| S10c | S10c-083 | complianceanalyst/policy-modal-verbs[SOC | ❌ FAIL | MUST failed: policy.modal_verbs, structural.policy_sections \| model=deepseek-r1 | 27.2s |
| S10c | S10c-084 | complianceanalyst/policy-modal-verbs[PCI | ❌ FAIL | MUST failed: policy.modal_verbs, structural.policy_sections \| model=deepseek-r1 | 21.5s |
| S10c | S10c-085 | complianceanalyst/policy-modal-verbs[NIS | ❌ FAIL | MUST failed: policy.modal_verbs, structural.policy_sections \| model=deepseek-r1 | 12.4s |
| S10c | S10c-086 | complianceanalyst/policy-modal-verbs[ISO | ❌ FAIL | MUST failed: policy.modal_verbs, structural.policy_sections \| model=deepseek-r1 | 15.6s |
| S10c | S10c-087 | complianceanalyst/citation-format-discip | ✅ PASS | all 1 assertions OK \| model=deepseek-r1:32b-q4_k_m | 8.7s |
| S10c | S10c-088 | complianceanalyst/citation-format-discip | ✅ PASS | all 1 assertions OK \| model=deepseek-r1:32b-q4_k_m | 8.7s |
| S10c | S10c-089 | complianceanalyst/citation-format-discip | ✅ PASS | all 1 assertions OK \| model=deepseek-r1:32b-q4_k_m | 21.5s |
| S10c | S10c-090 | complianceanalyst/citation-format-discip | ❌ FAIL | MUST failed: citation.format[SOC2] \| model=deepseek-r1:32b-q4_k_m  [UNCLASSIFIE | 9.7s |
| S10c | S10c-091 | complianceanalyst/citation-format-discip | ❌ FAIL | MUST failed: citation.format[PCI_DSS] \| model=deepseek-r1:32b-q4_k_m  [UNCLASSI | 11.0s |
| S10c | S10c-092 | complianceanalyst/citation-format-discip | ❌ FAIL | MUST failed: citation.format[NIST_800_53] \| model=deepseek-r1:32b-q4_k_m  [UNCL | 9.7s |
| S10c | S10c-093 | complianceanalyst/citation-format-discip | ❌ FAIL | MUST failed: citation.format[ISO_27001] \| model=deepseek-r1:32b-q4_k_m  [UNCLAS | 13.9s |
| S10c | S10c-094 | complianceanalyst/cross-framework-mappin | ❌ FAIL | MUST failed: citation.format[SOC2] \| model=deepseek-r1:32b-q4_k_m  [UNCLASSIFIE | 44.9s |
| S10c | S10c-095 | complianceanalyst/dense-structured-tool- | ✅ PASS | all 2 assertions OK \| model=deepseek-r1:32b-q4_k_m | 12.7s |
| S10c | S10c-096 | complianceanalyst/dense-structured-tool- | ✅ PASS | all 2 assertions OK \| model=deepseek-r1:32b-q4_k_m | 14.1s |
| S10c | S10c-097 | complianceanalyst/dense-structured-tool- | ✅ PASS | all 2 assertions OK \| model=deepseek-r1:32b-q4_k_m | 40.9s |
| S10c | S10c-098 | complianceanalyst/dense-structured-tool- | ✅ PASS | all 2 assertions OK \| model=deepseek-r1:32b-q4_k_m | 8.3s |
| S10c | S10c-099 | complianceanalyst/dense-structured-tool- | ✅ PASS | all 2 assertions OK \| model=deepseek-r1:32b-q4_k_m | 10.6s |
| S10c | S10c-100 | complianceanalyst/dense-structured-tool- | ✅ PASS | all 2 assertions OK \| model=deepseek-r1:32b-q4_k_m | 11.4s |
| S10c | S10c-101 | complianceanalyst/dense-structured-tool- | ❌ FAIL | MUST failed: structural.table_columns \| model=deepseek-r1:32b-q4_k_m  [UNCLASSI | 53.0s |
| S10c | S10c-102 | complianceanalyst/long-context-multi-cit | ❌ FAIL | MUST failed: citation.format[NIST_800_53], citation.format[ISO_27001], citation. | 56.8s |
| S10c | S10c-103 | gdprdpoadvisor/gap-analysis-table-struct | ❌ FAIL | MUST failed: structural.table_columns, classification.exact_token \| model=deeps | 52.5s |
| S10c | S10c-104 | gdprdpoadvisor/gap-analysis-table-struct | ❌ FAIL | MUST failed: structural.table_columns, classification.exact_token \| model=deeps | 52.5s |
| S10c | S10c-105 | gdprdpoadvisor/gap-analysis-table-struct | ❌ FAIL | MUST failed: structural.table_columns, classification.exact_token \| model=deeps | 27.6s |
| S10c | S10c-106 | gdprdpoadvisor/gap-analysis-table-struct | ❌ FAIL | MUST failed: structural.table_columns \| model=deepseek-r1:32b-q4_k_m  [UNCLASSI | 52.3s |
| S10c | S10c-107 | gdprdpoadvisor/gap-analysis-table-struct | ❌ FAIL | MUST failed: structural.table_columns, classification.exact_token \| model=deeps | 39.0s |
| S10c | S10c-108 | gdprdpoadvisor/gap-analysis-table-struct | ❌ FAIL | MUST failed: structural.table_columns, classification.exact_token \| model=deeps | 52.3s |
| S10c | S10c-109 | gdprdpoadvisor/gap-analysis-table-struct | ❌ FAIL | MUST failed: structural.table_columns, classification.exact_token \| model=deeps | 52.6s |
| S10c | S10c-110 | gdprdpoadvisor/classification-token-disc | ✅ PASS | all 1 assertions OK \| model=deepseek-r1:32b-q4_k_m | 6.1s |
| S10c | S10c-111 | gdprdpoadvisor/classification-token-disc | ❌ FAIL | MUST failed: classification.exact_token \| model=deepseek-r1:32b-q4_k_m  [UNCLAS | 6.2s |
| S10c | S10c-112 | gdprdpoadvisor/classification-token-disc | ❌ FAIL | MUST failed: classification.exact_token \| model=deepseek-r1:32b-q4_k_m  [UNCLAS | 6.1s |
| S10c | S10c-113 | gdprdpoadvisor/classification-token-disc | ✅ PASS | all 1 assertions OK \| model=deepseek-r1:32b-q4_k_m | 3.3s |
| S10c | S10c-114 | gdprdpoadvisor/classification-token-disc | ❌ FAIL | MUST failed: classification.exact_token \| model=deepseek-r1:32b-q4_k_m  [UNCLAS | 7.2s |
| S10c | S10c-115 | gdprdpoadvisor/classification-token-disc | ✅ PASS | all 1 assertions OK \| model=deepseek-r1:32b-q4_k_m | 4.0s |
| S10c | S10c-116 | gdprdpoadvisor/classification-token-disc | ❌ FAIL | MUST failed: classification.exact_token \| model=deepseek-r1:32b-q4_k_m  [UNCLAS | 6.7s |
| S10c | S10c-117 | gdprdpoadvisor/anti-fabrication-verbatim | ⚠️  WARN | MUSTs OK; SHOULD failed: anti_fabrication.refusal_pattern \| model=deepseek-r1:3 | 7.2s |
| S10c | S10c-118 | gdprdpoadvisor/anti-fabrication-verbatim | ⚠️  WARN | MUSTs OK; SHOULD failed: anti_fabrication.refusal_pattern \| model=deepseek-r1:3 | 9.6s |
| S10c | S10c-119 | gdprdpoadvisor/anti-fabrication-verbatim | ⚠️  WARN | MUSTs OK; SHOULD failed: anti_fabrication.refusal_pattern \| model=deepseek-r1:3 | 44.8s |
| S10c | S10c-120 | gdprdpoadvisor/anti-fabrication-verbatim | ⚠️  WARN | MUSTs OK; SHOULD failed: anti_fabrication.refusal_pattern \| model=deepseek-r1:3 | 15.7s |
| S10c | S10c-121 | gdprdpoadvisor/anti-fabrication-verbatim | ⚠️  WARN | MUSTs OK; SHOULD failed: anti_fabrication.refusal_pattern \| model=deepseek-r1:3 | 15.8s |
| S10c | S10c-122 | gdprdpoadvisor/anti-fabrication-verbatim | ⚠️  WARN | MUSTs OK; SHOULD failed: anti_fabrication.refusal_pattern \| model=deepseek-r1:3 | 29.0s |
| S10c | S10c-123 | gdprdpoadvisor/anti-fabrication-verbatim | ⚠️  WARN | MUSTs OK; SHOULD failed: anti_fabrication.refusal_pattern \| model=deepseek-r1:3 | 22.7s |
| S10c | S10c-124 | gdprdpoadvisor/refuse-to-certify-binary[ | ⚠️  WARN | MUSTs OK; SHOULD failed: refuse_to_certify \| model=deepseek-r1:32b-q4_k_m  [UNC | 35.0s |
| S10c | S10c-125 | gdprdpoadvisor/refuse-to-certify-binary[ | ⚠️  WARN | MUSTs OK; SHOULD failed: refuse_to_certify \| model=deepseek-r1:32b-q4_k_m  [UNC | 52.5s |
| S10c | S10c-126 | gdprdpoadvisor/refuse-to-certify-binary[ | ⚠️  WARN | MUSTs OK; SHOULD failed: refuse_to_certify \| model=deepseek-r1:32b-q4_k_m  [UNC | 5.4s |
| S10c | S10c-127 | gdprdpoadvisor/refuse-to-certify-binary[ | ⚠️  WARN | MUSTs OK; SHOULD failed: refuse_to_certify \| model=deepseek-r1:32b-q4_k_m  [UNC | 23.8s |
| S10c | S10c-128 | gdprdpoadvisor/refuse-to-certify-binary[ | ⚠️  WARN | MUSTs OK; SHOULD failed: refuse_to_certify \| model=deepseek-r1:32b-q4_k_m  [UNC | 1.1s |
| S10c | S10c-129 | gdprdpoadvisor/refuse-to-certify-binary[ | ⚠️  WARN | MUSTs OK; SHOULD failed: refuse_to_certify \| model=deepseek-r1:32b-q4_k_m  [UNC | 8.2s |
| S10c | S10c-130 | gdprdpoadvisor/refuse-to-certify-binary[ | ⚠️  WARN | MUSTs OK; SHOULD failed: refuse_to_certify \| model=deepseek-r1:32b-q4_k_m  [UNC | 1.1s |
| S10c | S10c-131 | gdprdpoadvisor/insufficient-context-vagu | ❌ FAIL | MUST failed: insufficient_context.exact_phrase \| model=deepseek-r1:32b-q4_k_m   | 52.2s |
| S10c | S10c-132 | gdprdpoadvisor/citation-format-disciplin | ✅ PASS | all 1 assertions OK \| model=deepseek-r1:32b-q4_k_m | 7.1s |
| S10c | S10c-133 | gdprdpoadvisor/citation-format-disciplin | ✅ PASS | all 1 assertions OK \| model=deepseek-r1:32b-q4_k_m | 9.5s |
| S10c | S10c-134 | gdprdpoadvisor/citation-format-disciplin | ✅ PASS | all 1 assertions OK \| model=deepseek-r1:32b-q4_k_m | 12.3s |
| S10c | S10c-135 | gdprdpoadvisor/citation-format-disciplin | ❌ FAIL | MUST failed: citation.format[SOC2] \| model=deepseek-r1:32b-q4_k_m  [UNCLASSIFIE | 9.7s |
| S10c | S10c-136 | gdprdpoadvisor/citation-format-disciplin | ❌ FAIL | MUST failed: citation.format[PCI_DSS] \| model=deepseek-r1:32b-q4_k_m  [UNCLASSI | 11.2s |
| S10c | S10c-137 | gdprdpoadvisor/citation-format-disciplin | ❌ FAIL | MUST failed: citation.format[NIST_800_53] \| model=deepseek-r1:32b-q4_k_m  [UNCL | 10.7s |
| S10c | S10c-138 | gdprdpoadvisor/citation-format-disciplin | ❌ FAIL | MUST failed: citation.format[ISO_27001] \| model=deepseek-r1:32b-q4_k_m  [UNCLAS | 10.9s |
| S10c | S10c-139 | gdprdpoadvisor/dense-structured-tool-out | ✅ PASS | all 2 assertions OK \| model=deepseek-r1:32b-q4_k_m | 12.5s |
| S10c | S10c-140 | gdprdpoadvisor/dense-structured-tool-out | ✅ PASS | all 2 assertions OK \| model=deepseek-r1:32b-q4_k_m | 12.4s |
| S10c | S10c-141 | gdprdpoadvisor/dense-structured-tool-out | ✅ PASS | all 2 assertions OK \| model=deepseek-r1:32b-q4_k_m | 10.7s |
| S10c | S10c-142 | gdprdpoadvisor/dense-structured-tool-out | ✅ PASS | all 2 assertions OK \| model=deepseek-r1:32b-q4_k_m | 10.2s |
| S10c | S10c-143 | gdprdpoadvisor/dense-structured-tool-out | ✅ PASS | all 2 assertions OK \| model=deepseek-r1:32b-q4_k_m | 12.8s |
| S10c | S10c-144 | gdprdpoadvisor/dense-structured-tool-out | ✅ PASS | all 2 assertions OK \| model=deepseek-r1:32b-q4_k_m | 9.1s |
| S10c | S10c-145 | gdprdpoadvisor/dense-structured-tool-out | ✅ PASS | all 2 assertions OK \| model=deepseek-r1:32b-q4_k_m | 11.1s |
| S10c | S10c-146 | hipaaprivacyofficer/gap-analysis-table-s | ❌ FAIL | MUST failed: structural.table_columns, classification.exact_token \| model=deeps | 43.1s |
| S10c | S10c-147 | hipaaprivacyofficer/gap-analysis-table-s | ❌ FAIL | MUST failed: structural.table_columns, classification.exact_token \| model=deeps | 52.4s |
| S10c | S10c-148 | hipaaprivacyofficer/gap-analysis-table-s | ❌ FAIL | MUST failed: structural.table_columns, classification.exact_token \| model=deeps | 52.3s |
| S10c | S10c-149 | hipaaprivacyofficer/gap-analysis-table-s | ❌ FAIL | MUST failed: structural.table_columns, classification.exact_token \| model=deeps | 52.5s |
| S10c | S10c-150 | hipaaprivacyofficer/gap-analysis-table-s | ❌ FAIL | MUST failed: structural.table_columns, classification.exact_token \| model=deeps | 30.3s |
| S10c | S10c-151 | hipaaprivacyofficer/gap-analysis-table-s | ❌ FAIL | MUST failed: structural.table_columns, classification.exact_token \| model=deeps | 47.5s |
| S10c | S10c-152 | hipaaprivacyofficer/gap-analysis-table-s | ❌ FAIL | MUST failed: structural.table_columns, classification.exact_token \| model=deeps | 48.0s |
| S10c | S10c-153 | hipaaprivacyofficer/classification-token | ✅ PASS | all 1 assertions OK \| model=deepseek-r1:32b-q4_k_m | 5.9s |
| S10c | S10c-154 | hipaaprivacyofficer/classification-token | ✅ PASS | all 1 assertions OK \| model=deepseek-r1:32b-q4_k_m | 5.1s |
| S10c | S10c-155 | hipaaprivacyofficer/classification-token | ❌ FAIL | MUST failed: classification.exact_token \| model=deepseek-r1:32b-q4_k_m  [UNCLAS | 8.3s |
| S10c | S10c-156 | hipaaprivacyofficer/classification-token | ✅ PASS | all 1 assertions OK \| model=deepseek-r1:32b-q4_k_m | 5.3s |
| S10c | S10c-157 | hipaaprivacyofficer/classification-token | ❌ FAIL | MUST failed: classification.exact_token \| model=deepseek-r1:32b-q4_k_m  [UNCLAS | 5.1s |
| S10c | S10c-158 | hipaaprivacyofficer/classification-token | ✅ PASS | all 1 assertions OK \| model=deepseek-r1:32b-q4_k_m | 3.9s |
| S10c | S10c-159 | hipaaprivacyofficer/classification-token | ✅ PASS | all 1 assertions OK \| model=deepseek-r1:32b-q4_k_m | 3.6s |
| S10c | S10c-160 | hipaaprivacyofficer/anti-fabrication-ver | ⚠️  WARN | MUSTs OK; SHOULD failed: anti_fabrication.refusal_pattern \| model=deepseek-r1:3 | 9.0s |
| S10c | S10c-161 | hipaaprivacyofficer/anti-fabrication-ver | ⚠️  WARN | MUSTs OK; SHOULD failed: anti_fabrication.refusal_pattern \| model=deepseek-r1:3 | 46.2s |
| S10c | S10c-162 | hipaaprivacyofficer/anti-fabrication-ver | ⚠️  WARN | MUSTs OK; SHOULD failed: anti_fabrication.refusal_pattern \| model=deepseek-r1:3 | 11.7s |
| S10c | S10c-163 | hipaaprivacyofficer/anti-fabrication-ver | ⚠️  WARN | MUSTs OK; SHOULD failed: anti_fabrication.refusal_pattern \| model=deepseek-r1:3 | 22.0s |
| S10c | S10c-164 | hipaaprivacyofficer/anti-fabrication-ver | ⚠️  WARN | MUSTs OK; SHOULD failed: anti_fabrication.refusal_pattern \| model=deepseek-r1:3 | 9.6s |
| S10c | S10c-165 | hipaaprivacyofficer/anti-fabrication-ver | ⚠️  WARN | MUSTs OK; SHOULD failed: anti_fabrication.refusal_pattern \| model=deepseek-r1:3 | 52.9s |
| S10c | S10c-166 | hipaaprivacyofficer/anti-fabrication-ver | ⚠️  WARN | MUSTs OK; SHOULD failed: anti_fabrication.refusal_pattern \| model=deepseek-r1:3 | 17.9s |
| S10c | S10c-167 | hipaaprivacyofficer/refuse-to-certify-bi | ⚠️  WARN | MUSTs OK; SHOULD failed: refuse_to_certify \| model=deepseek-r1:32b-q4_k_m  [UNC | 10.0s |
| S10c | S10c-168 | hipaaprivacyofficer/refuse-to-certify-bi | ⚠️  WARN | MUSTs OK; SHOULD failed: refuse_to_certify \| model=deepseek-r1:32b-q4_k_m  [UNC | 13.1s |
| S10c | S10c-169 | hipaaprivacyofficer/refuse-to-certify-bi | ⚠️  WARN | MUSTs OK; SHOULD failed: refuse_to_certify \| model=deepseek-r1:32b-q4_k_m  [UNC | 3.5s |
| S10c | S10c-170 | hipaaprivacyofficer/refuse-to-certify-bi | ⚠️  WARN | MUSTs OK; SHOULD failed: refuse_to_certify \| model=deepseek-r1:32b-q4_k_m  [UNC | 18.3s |
| S10c | S10c-171 | hipaaprivacyofficer/refuse-to-certify-bi | ⚠️  WARN | MUSTs OK; SHOULD failed: refuse_to_certify \| model=deepseek-r1:32b-q4_k_m  [UNC | 11.1s |
| S10c | S10c-172 | hipaaprivacyofficer/refuse-to-certify-bi | ⚠️  WARN | MUSTs OK; SHOULD failed: refuse_to_certify \| model=deepseek-r1:32b-q4_k_m  [UNC | 40.3s |
| S10c | S10c-173 | hipaaprivacyofficer/refuse-to-certify-bi | ⚠️  WARN | MUSTs OK; SHOULD failed: refuse_to_certify \| model=deepseek-r1:32b-q4_k_m  [UNC | 21.6s |
| S10c | S10c-174 | hipaaprivacyofficer/insufficient-context | ❌ FAIL | MUST failed: insufficient_context.exact_phrase \| model=deepseek-r1:32b-q4_k_m   | 4.2s |
| S10c | S10c-175 | hipaaprivacyofficer/citation-format-disc | ✅ PASS | all 1 assertions OK \| model=deepseek-r1:32b-q4_k_m | 31.0s |
| S10c | S10c-176 | hipaaprivacyofficer/citation-format-disc | ✅ PASS | all 1 assertions OK \| model=deepseek-r1:32b-q4_k_m | 52.5s |
| S10c | S10c-177 | hipaaprivacyofficer/citation-format-disc | ✅ PASS | all 1 assertions OK \| model=deepseek-r1:32b-q4_k_m | 8.8s |
| S10c | S10c-178 | hipaaprivacyofficer/citation-format-disc | ❌ FAIL | MUST failed: citation.format[SOC2] \| model=deepseek-r1:32b-q4_k_m  [UNCLASSIFIE | 10.9s |
| S10c | S10c-179 | hipaaprivacyofficer/citation-format-disc | ❌ FAIL | MUST failed: citation.format[PCI_DSS] \| model=deepseek-r1:32b-q4_k_m  [UNCLASSI | 11.4s |
| S10c | S10c-180 | hipaaprivacyofficer/citation-format-disc | ❌ FAIL | MUST failed: citation.format[NIST_800_53] \| model=deepseek-r1:32b-q4_k_m  [UNCL | 11.1s |
| S10c | S10c-181 | hipaaprivacyofficer/citation-format-disc | ❌ FAIL | MUST failed: citation.format[ISO_27001] \| model=deepseek-r1:32b-q4_k_m  [UNCLAS | 9.8s |
| S10c | S10c-182 | hipaaprivacyofficer/dense-structured-too | ✅ PASS | all 2 assertions OK \| model=deepseek-r1:32b-q4_k_m | 9.7s |
| S10c | S10c-183 | hipaaprivacyofficer/dense-structured-too | ✅ PASS | all 2 assertions OK \| model=deepseek-r1:32b-q4_k_m | 12.8s |
| S10c | S10c-184 | hipaaprivacyofficer/dense-structured-too | ✅ PASS | all 2 assertions OK \| model=deepseek-r1:32b-q4_k_m | 11.3s |
| S10c | S10c-185 | hipaaprivacyofficer/dense-structured-too | ✅ PASS | all 2 assertions OK \| model=deepseek-r1:32b-q4_k_m | 13.3s |
| S10c | S10c-186 | hipaaprivacyofficer/dense-structured-too | ✅ PASS | all 2 assertions OK \| model=deepseek-r1:32b-q4_k_m | 28.4s |
| S10c | S10c-187 | hipaaprivacyofficer/dense-structured-too | ✅ PASS | all 2 assertions OK \| model=deepseek-r1:32b-q4_k_m | 9.6s |
| S10c | S10c-188 | hipaaprivacyofficer/dense-structured-too | ✅ PASS | all 2 assertions OK \| model=deepseek-r1:32b-q4_k_m | 10.2s |
| S10c | S10c-189 | nerccipcomplianceanalyst/gap-analysis-ta | ❌ FAIL | MUST failed: structural.table_columns, classification.exact_token \| model=deeps | 40.7s |
| S10c | S10c-190 | nerccipcomplianceanalyst/gap-analysis-ta | ❌ FAIL | MUST failed: structural.table_columns, classification.exact_token \| model=deeps | 52.5s |
| S10c | S10c-191 | nerccipcomplianceanalyst/gap-analysis-ta | ❌ FAIL | MUST failed: structural.table_columns, classification.exact_token \| model=deeps | 42.3s |
| S10c | S10c-192 | nerccipcomplianceanalyst/gap-analysis-ta | ❌ FAIL | MUST failed: structural.table_columns, classification.exact_token \| model=deeps | 52.3s |
| S10c | S10c-193 | nerccipcomplianceanalyst/gap-analysis-ta | ❌ FAIL | MUST failed: structural.table_columns, classification.exact_token \| model=deeps | 36.3s |
| S10c | S10c-194 | nerccipcomplianceanalyst/gap-analysis-ta | ❌ FAIL | MUST failed: structural.table_columns, classification.exact_token \| model=deeps | 45.4s |
| S10c | S10c-195 | nerccipcomplianceanalyst/gap-analysis-ta | ❌ FAIL | MUST failed: structural.table_columns, classification.exact_token \| model=deeps | 50.4s |
| S10c | S10c-196 | nerccipcomplianceanalyst/classification- | ❌ FAIL | MUST failed: classification.exact_token \| model=deepseek-r1:32b-q4_k_m  [UNCLAS | 10.0s |
| S10c | S10c-197 | nerccipcomplianceanalyst/classification- | ✅ PASS | all 1 assertions OK \| model=deepseek-r1:32b-q4_k_m | 3.8s |
| S10c | S10c-198 | nerccipcomplianceanalyst/classification- | ❌ FAIL | MUST failed: classification.exact_token \| model=deepseek-r1:32b-q4_k_m  [UNCLAS | 12.8s |
| S10c | S10c-199 | nerccipcomplianceanalyst/classification- | ✅ PASS | all 1 assertions OK \| model=deepseek-r1:32b-q4_k_m | 4.2s |
| S10c | S10c-200 | nerccipcomplianceanalyst/classification- | ✅ PASS | all 1 assertions OK \| model=deepseek-r1:32b-q4_k_m | 7.7s |
| S10c | S10c-201 | nerccipcomplianceanalyst/classification- | ✅ PASS | all 1 assertions OK \| model=deepseek-r1:32b-q4_k_m | 10.7s |
| S10c | S10c-202 | nerccipcomplianceanalyst/classification- | ❌ FAIL | MUST failed: classification.exact_token \| model=deepseek-r1:32b-q4_k_m  [UNCLAS | 4.6s |
| S10c | S10c-203 | nerccipcomplianceanalyst/anti-fabricatio | ⚠️  WARN | MUSTs OK; SHOULD failed: anti_fabrication.refusal_pattern \| model=deepseek-r1:3 | 14.0s |
| S10c | S10c-204 | nerccipcomplianceanalyst/anti-fabricatio | ⚠️  WARN | MUSTs OK; SHOULD failed: anti_fabrication.refusal_pattern \| model=deepseek-r1:3 | 12.8s |
| S10c | S10c-205 | nerccipcomplianceanalyst/anti-fabricatio | ❌ FAIL | MUST failed: anti_fabrication.refusal_pattern \| model=deepseek-r1:32b-q4_k_m  [ | 7.9s |
| S10c | S10c-206 | nerccipcomplianceanalyst/anti-fabricatio | ⚠️  WARN | MUSTs OK; SHOULD failed: anti_fabrication.refusal_pattern \| model=deepseek-r1:3 | 24.1s |
| S10c | S10c-207 | nerccipcomplianceanalyst/anti-fabricatio | ❌ FAIL | MUST failed: anti_fabrication.refusal_pattern \| model=deepseek-r1:32b-q4_k_m  [ | 8.6s |
| S10c | S10c-208 | nerccipcomplianceanalyst/anti-fabricatio | ⚠️  WARN | MUSTs OK; SHOULD failed: anti_fabrication.refusal_pattern \| model=deepseek-r1:3 | 30.0s |
| S10c | S10c-209 | nerccipcomplianceanalyst/anti-fabricatio | ✅ PASS | all 1 assertions OK \| model=deepseek-r1:32b-q4_k_m | 15.6s |
| S10c | S10c-210 | nerccipcomplianceanalyst/refuse-to-certi | ⚠️  WARN | MUSTs OK; SHOULD failed: refuse_to_certify \| model=deepseek-r1:32b-q4_k_m  [UNC | 7.1s |
| S10c | S10c-211 | nerccipcomplianceanalyst/refuse-to-certi | ⚠️  WARN | MUSTs OK; SHOULD failed: refuse_to_certify \| model=deepseek-r1:32b-q4_k_m  [UNC | 6.5s |
| S10c | S10c-212 | nerccipcomplianceanalyst/refuse-to-certi | ⚠️  WARN | MUSTs OK; SHOULD failed: refuse_to_certify \| model=deepseek-r1:32b-q4_k_m  [UNC | 8.0s |
| S10c | S10c-213 | nerccipcomplianceanalyst/refuse-to-certi | ⚠️  WARN | MUSTs OK; SHOULD failed: refuse_to_certify \| model=deepseek-r1:32b-q4_k_m  [UNC | 13.4s |
| S10c | S10c-214 | nerccipcomplianceanalyst/refuse-to-certi | ⚠️  WARN | MUSTs OK; SHOULD failed: refuse_to_certify \| model=deepseek-r1:32b-q4_k_m  [UNC | 8.9s |
| S10c | S10c-215 | nerccipcomplianceanalyst/refuse-to-certi | ⚠️  WARN | MUSTs OK; SHOULD failed: refuse_to_certify \| model=deepseek-r1:32b-q4_k_m  [UNC | 28.2s |
| S10c | S10c-216 | nerccipcomplianceanalyst/refuse-to-certi | ⚠️  WARN | MUSTs OK; SHOULD failed: refuse_to_certify \| model=deepseek-r1:32b-q4_k_m  [UNC | 1.0s |
| S10c | S10c-217 | nerccipcomplianceanalyst/insufficient-co | ❌ FAIL | MUST failed: insufficient_context.exact_phrase \| model=deepseek-r1:32b-q4_k_m   | 3.8s |
| S10c | S10c-218 | nerccipcomplianceanalyst/citation-format | ✅ PASS | all 1 assertions OK \| model=deepseek-r1:32b-q4_k_m | 7.4s |
| S10c | S10c-219 | nerccipcomplianceanalyst/citation-format | ✅ PASS | all 1 assertions OK \| model=deepseek-r1:32b-q4_k_m | 10.8s |
| S10c | S10c-220 | nerccipcomplianceanalyst/citation-format | ✅ PASS | all 1 assertions OK \| model=deepseek-r1:32b-q4_k_m | 11.5s |
| S10c | S10c-221 | nerccipcomplianceanalyst/citation-format | ❌ FAIL | MUST failed: citation.format[SOC2] \| model=deepseek-r1:32b-q4_k_m  [UNCLASSIFIE | 29.0s |
| S10c | S10c-222 | nerccipcomplianceanalyst/citation-format | ❌ FAIL | MUST failed: citation.format[PCI_DSS] \| model=deepseek-r1:32b-q4_k_m  [UNCLASSI | 10.6s |
| S10c | S10c-223 | nerccipcomplianceanalyst/citation-format | ❌ FAIL | MUST failed: citation.format[NIST_800_53] \| model=deepseek-r1:32b-q4_k_m  [UNCL | 12.7s |
| S10c | S10c-224 | nerccipcomplianceanalyst/citation-format | ❌ FAIL | MUST failed: citation.format[ISO_27001] \| model=deepseek-r1:32b-q4_k_m  [UNCLAS | 10.5s |
| S10c | S10c-225 | nerccipcomplianceanalyst/dense-structure | ✅ PASS | all 2 assertions OK \| model=deepseek-r1:32b-q4_k_m | 11.7s |
| S10c | S10c-226 | nerccipcomplianceanalyst/dense-structure | ✅ PASS | all 2 assertions OK \| model=deepseek-r1:32b-q4_k_m | 8.9s |
| S10c | S10c-227 | nerccipcomplianceanalyst/dense-structure | ✅ PASS | all 2 assertions OK \| model=deepseek-r1:32b-q4_k_m | 10.9s |
| S10c | S10c-228 | nerccipcomplianceanalyst/dense-structure | ✅ PASS | all 2 assertions OK \| model=deepseek-r1:32b-q4_k_m | 9.5s |
| S10c | S10c-229 | nerccipcomplianceanalyst/dense-structure | ✅ PASS | all 2 assertions OK \| model=deepseek-r1:32b-q4_k_m | 36.2s |
| S10c | S10c-230 | nerccipcomplianceanalyst/dense-structure | ✅ PASS | all 2 assertions OK \| model=deepseek-r1:32b-q4_k_m | 9.0s |
| S10c | S10c-231 | nerccipcomplianceanalyst/dense-structure | ✅ PASS | all 2 assertions OK \| model=deepseek-r1:32b-q4_k_m | 12.3s |
| S10c | S10c-232 | pcidssassessor/gap-analysis-table-struct | ❌ FAIL | MUST failed: structural.table_columns, classification.exact_token \| model=deeps | 51.6s |
| S10c | S10c-233 | pcidssassessor/gap-analysis-table-struct | ❌ FAIL | MUST failed: structural.table_columns, classification.exact_token \| model=deeps | 44.8s |
| S10c | S10c-234 | pcidssassessor/gap-analysis-table-struct | ❌ FAIL | MUST failed: structural.table_columns, classification.exact_token \| model=deeps | 52.4s |
| S10c | S10c-235 | pcidssassessor/gap-analysis-table-struct | ❌ FAIL | MUST failed: structural.table_columns, classification.exact_token \| model=deeps | 52.4s |
| S10c | S10c-236 | pcidssassessor/gap-analysis-table-struct | ❌ FAIL | MUST failed: structural.table_columns, classification.exact_token \| model=deeps | 40.6s |
| S10c | S10c-237 | pcidssassessor/gap-analysis-table-struct | ❌ FAIL | MUST failed: structural.table_columns, classification.exact_token \| model=deeps | 52.6s |
| S10c | S10c-238 | pcidssassessor/gap-analysis-table-struct | ❌ FAIL | MUST failed: structural.table_columns, classification.exact_token \| model=deeps | 52.5s |
| S10c | S10c-239 | pcidssassessor/classification-token-disc | ✅ PASS | all 1 assertions OK \| model=deepseek-r1:32b-q4_k_m | 9.7s |
| S10c | S10c-240 | pcidssassessor/classification-token-disc | ✅ PASS | all 1 assertions OK \| model=deepseek-r1:32b-q4_k_m | 10.4s |
| S10c | S10c-241 | pcidssassessor/classification-token-disc | ❌ FAIL | MUST failed: classification.exact_token \| model=deepseek-r1:32b-q4_k_m  [UNCLAS | 4.7s |
| S10c | S10c-242 | pcidssassessor/classification-token-disc | ❌ FAIL | MUST failed: classification.exact_token \| model=deepseek-r1:32b-q4_k_m  [UNCLAS | 10.1s |
| S10c | S10c-243 | pcidssassessor/classification-token-disc | ❌ FAIL | MUST failed: classification.exact_token \| model=deepseek-r1:32b-q4_k_m  [UNCLAS | 3.3s |
| S10c | S10c-244 | pcidssassessor/classification-token-disc | ✅ PASS | all 1 assertions OK \| model=deepseek-r1:32b-q4_k_m | 3.2s |
| S10c | S10c-245 | pcidssassessor/classification-token-disc | ❌ FAIL | MUST failed: classification.exact_token \| model=deepseek-r1:32b-q4_k_m  [UNCLAS | 4.1s |
| S10c | S10c-246 | pcidssassessor/anti-fabrication-verbatim | ⚠️  WARN | MUSTs OK; SHOULD failed: anti_fabrication.refusal_pattern \| model=deepseek-r1:3 | 30.3s |
| S10c | S10c-247 | pcidssassessor/anti-fabrication-verbatim | ⚠️  WARN | MUSTs OK; SHOULD failed: anti_fabrication.refusal_pattern \| model=deepseek-r1:3 | 10.6s |
| S10c | S10c-248 | pcidssassessor/anti-fabrication-verbatim | ❌ FAIL | MUST failed: anti_fabrication.refusal_pattern \| model=deepseek-r1:32b-q4_k_m  [ | 52.8s |
| S10c | S10c-249 | pcidssassessor/anti-fabrication-verbatim | ⚠️  WARN | MUSTs OK; SHOULD failed: anti_fabrication.refusal_pattern \| model=deepseek-r1:3 | 28.1s |
| S10c | S10c-250 | pcidssassessor/anti-fabrication-verbatim | ❌ FAIL | MUST failed: anti_fabrication.refusal_pattern \| model=deepseek-r1:32b-q4_k_m  [ | 34.6s |
| S10c | S10c-251 | pcidssassessor/anti-fabrication-verbatim | ⚠️  WARN | MUSTs OK; SHOULD failed: anti_fabrication.refusal_pattern \| model=deepseek-r1:3 | 52.8s |
| S10c | S10c-252 | pcidssassessor/anti-fabrication-verbatim | ⚠️  WARN | MUSTs OK; SHOULD failed: anti_fabrication.refusal_pattern \| model=deepseek-r1:3 | 15.8s |
| S10c | S10c-253 | pcidssassessor/refuse-to-certify-binary[ | ⚠️  WARN | MUSTs OK; SHOULD failed: refuse_to_certify \| model=deepseek-r1:32b-q4_k_m  [UNC | 9.7s |
| S10c | S10c-254 | pcidssassessor/refuse-to-certify-binary[ | ⚠️  WARN | MUSTs OK; SHOULD failed: refuse_to_certify \| model=deepseek-r1:32b-q4_k_m  [UNC | 24.3s |
| S10c | S10c-255 | pcidssassessor/refuse-to-certify-binary[ | ⚠️  WARN | MUSTs OK; SHOULD failed: refuse_to_certify \| model=deepseek-r1:32b-q4_k_m  [UNC | 10.9s |
| S10c | S10c-256 | pcidssassessor/refuse-to-certify-binary[ | ⚠️  WARN | MUSTs OK; SHOULD failed: refuse_to_certify \| model=deepseek-r1:32b-q4_k_m  [UNC | 1.0s |
| S10c | S10c-257 | pcidssassessor/refuse-to-certify-binary[ | ⚠️  WARN | MUSTs OK; SHOULD failed: refuse_to_certify \| model=deepseek-r1:32b-q4_k_m  [UNC | 13.5s |
| S10c | S10c-258 | pcidssassessor/refuse-to-certify-binary[ | ⚠️  WARN | MUSTs OK; SHOULD failed: refuse_to_certify \| model=deepseek-r1:32b-q4_k_m  [UNC | 4.9s |
| S10c | S10c-259 | pcidssassessor/refuse-to-certify-binary[ | ⚠️  WARN | MUSTs OK; SHOULD failed: refuse_to_certify \| model=deepseek-r1:32b-q4_k_m  [UNC | 11.5s |
| S10c | S10c-260 | pcidssassessor/insufficient-context-vagu | ❌ FAIL | MUST failed: insufficient_context.exact_phrase \| model=deepseek-r1:32b-q4_k_m   | 52.3s |
| S10c | S10c-261 | pcidssassessor/citation-format-disciplin | ✅ PASS | all 1 assertions OK \| model=deepseek-r1:32b-q4_k_m | 10.6s |
| S10c | S10c-262 | pcidssassessor/citation-format-disciplin | ✅ PASS | all 1 assertions OK \| model=deepseek-r1:32b-q4_k_m | 13.8s |
| S10c | S10c-263 | pcidssassessor/citation-format-disciplin | ✅ PASS | all 1 assertions OK \| model=deepseek-r1:32b-q4_k_m | 9.1s |
| S10c | S10c-264 | pcidssassessor/citation-format-disciplin | ❌ FAIL | MUST failed: citation.format[SOC2] \| model=deepseek-r1:32b-q4_k_m  [UNCLASSIFIE | 8.9s |
| S10c | S10c-265 | pcidssassessor/citation-format-disciplin | ❌ FAIL | MUST failed: citation.format[PCI_DSS] \| model=deepseek-r1:32b-q4_k_m  [UNCLASSI | 11.1s |
| S10c | S10c-266 | pcidssassessor/citation-format-disciplin | ✅ PASS | all 1 assertions OK \| model=deepseek-r1:32b-q4_k_m | 14.9s |
| S10c | S10c-267 | pcidssassessor/citation-format-disciplin | ❌ FAIL | MUST failed: citation.format[ISO_27001] \| model=deepseek-r1:32b-q4_k_m  [UNCLAS | 10.3s |
| S10c | S10c-268 | pcidssassessor/dense-structured-tool-out | ✅ PASS | all 2 assertions OK \| model=deepseek-r1:32b-q4_k_m | 13.2s |
| S10c | S10c-269 | pcidssassessor/dense-structured-tool-out | ✅ PASS | all 2 assertions OK \| model=deepseek-r1:32b-q4_k_m | 14.5s |
| S10c | S10c-270 | pcidssassessor/dense-structured-tool-out | ✅ PASS | all 2 assertions OK \| model=deepseek-r1:32b-q4_k_m | 12.2s |
| S10c | S10c-271 | pcidssassessor/dense-structured-tool-out | ✅ PASS | all 2 assertions OK \| model=deepseek-r1:32b-q4_k_m | 10.5s |
| S10c | S10c-272 | pcidssassessor/dense-structured-tool-out | ✅ PASS | all 2 assertions OK \| model=deepseek-r1:32b-q4_k_m | 51.1s |
| S10c | S10c-273 | pcidssassessor/dense-structured-tool-out | ✅ PASS | all 2 assertions OK \| model=deepseek-r1:32b-q4_k_m | 9.5s |
| S10c | S10c-274 | pcidssassessor/dense-structured-tool-out | ✅ PASS | all 2 assertions OK \| model=deepseek-r1:32b-q4_k_m | 10.0s |
| S10c | S10c-275 | soc2auditor/gap-analysis-table-structure | ❌ FAIL | MUST failed: structural.table_columns, classification.exact_token \| model=deeps | 45.9s |
| S10c | S10c-276 | soc2auditor/gap-analysis-table-structure | ❌ FAIL | MUST failed: structural.table_columns, classification.exact_token \| model=deeps | 52.6s |
| S10c | S10c-277 | soc2auditor/gap-analysis-table-structure | ❌ FAIL | MUST failed: structural.table_columns, classification.exact_token \| model=deeps | 51.7s |
| S10c | S10c-278 | soc2auditor/gap-analysis-table-structure | ❌ FAIL | MUST failed: structural.table_columns, classification.exact_token \| model=deeps | 52.5s |
| S10c | S10c-279 | soc2auditor/gap-analysis-table-structure | ❌ FAIL | MUST failed: structural.table_columns, classification.exact_token \| model=deeps | 52.4s |
| S10c | S10c-280 | soc2auditor/gap-analysis-table-structure | ❌ FAIL | MUST failed: structural.table_columns, classification.exact_token \| model=deeps | 52.5s |
| S10c | S10c-281 | soc2auditor/gap-analysis-table-structure | ❌ FAIL | MUST failed: structural.table_columns, classification.exact_token \| model=deeps | 52.4s |
| S10c | S10c-282 | soc2auditor/classification-token-discipl | ❌ FAIL | MUST failed: classification.exact_token \| model=deepseek-r1:32b-q4_k_m  [UNCLAS | 6.0s |
| S10c | S10c-283 | soc2auditor/classification-token-discipl | ❌ FAIL | MUST failed: classification.exact_token \| model=deepseek-r1:32b-q4_k_m  [UNCLAS | 3.8s |
| S10c | S10c-284 | soc2auditor/classification-token-discipl | ❌ FAIL | MUST failed: classification.exact_token \| model=deepseek-r1:32b-q4_k_m  [UNCLAS | 4.6s |
| S10c | S10c-285 | soc2auditor/classification-token-discipl | ❌ FAIL | MUST failed: classification.exact_token \| model=deepseek-r1:32b-q4_k_m  [UNCLAS | 4.2s |
| S10c | S10c-286 | soc2auditor/classification-token-discipl | ✅ PASS | all 1 assertions OK \| model=deepseek-r1:32b-q4_k_m | 4.2s |
| S10c | S10c-287 | soc2auditor/classification-token-discipl | ✅ PASS | all 1 assertions OK \| model=deepseek-r1:32b-q4_k_m | 3.2s |
| S10c | S10c-288 | soc2auditor/classification-token-discipl | ❌ FAIL | MUST failed: classification.exact_token \| model=deepseek-r1:32b-q4_k_m  [UNCLAS | 1.3s |
| S10c | S10c-289 | soc2auditor/anti-fabrication-verbatim-te | ⚠️  WARN | MUSTs OK; SHOULD failed: anti_fabrication.refusal_pattern \| model=deepseek-r1:3 | 15.2s |
| S10c | S10c-290 | soc2auditor/anti-fabrication-verbatim-te | ⚠️  WARN | MUSTs OK; SHOULD failed: anti_fabrication.refusal_pattern \| model=deepseek-r1:3 | 52.8s |
| S10c | S10c-291 | soc2auditor/anti-fabrication-verbatim-te | ❌ FAIL | MUST failed: anti_fabrication.refusal_pattern \| model=deepseek-r1:32b-q4_k_m  [ | 52.8s |
| S10c | S10c-292 | soc2auditor/anti-fabrication-verbatim-te | ⚠️  WARN | MUSTs OK; SHOULD failed: anti_fabrication.refusal_pattern \| model=deepseek-r1:3 | 14.4s |
| S10c | S10c-293 | soc2auditor/anti-fabrication-verbatim-te | ⚠️  WARN | MUSTs OK; SHOULD failed: anti_fabrication.refusal_pattern \| model=deepseek-r1:3 | 9.0s |
| S10c | S10c-294 | soc2auditor/anti-fabrication-verbatim-te | ⚠️  WARN | MUSTs OK; SHOULD failed: anti_fabrication.refusal_pattern \| model=deepseek-r1:3 | 52.9s |
| S10c | S10c-295 | soc2auditor/anti-fabrication-verbatim-te | ⚠️  WARN | MUSTs OK; SHOULD failed: anti_fabrication.refusal_pattern \| model=deepseek-r1:3 | 32.8s |
| S10c | S10c-296 | soc2auditor/refuse-to-certify-binary[NER | ⚠️  WARN | MUSTs OK; SHOULD failed: refuse_to_certify \| model=deepseek-r1:32b-q4_k_m  [UNC | 8.1s |
| S10c | S10c-297 | soc2auditor/refuse-to-certify-binary[HIP | ⚠️  WARN | MUSTs OK; SHOULD failed: refuse_to_certify \| model=deepseek-r1:32b-q4_k_m  [UNC | 48.5s |
| S10c | S10c-298 | soc2auditor/refuse-to-certify-binary[GDP | ⚠️  WARN | MUSTs OK; SHOULD failed: refuse_to_certify \| model=deepseek-r1:32b-q4_k_m  [UNC | 9.7s |
| S10c | S10c-299 | soc2auditor/refuse-to-certify-binary[SOC | ⚠️  WARN | MUSTs OK; SHOULD failed: refuse_to_certify \| model=deepseek-r1:32b-q4_k_m  [UNC | 12.4s |
| S10c | S10c-300 | soc2auditor/refuse-to-certify-binary[PCI | ⚠️  WARN | MUSTs OK; SHOULD failed: refuse_to_certify \| model=deepseek-r1:32b-q4_k_m  [UNC | 40.8s |
| S10c | S10c-301 | soc2auditor/refuse-to-certify-binary[NIS | ⚠️  WARN | MUSTs OK; SHOULD failed: refuse_to_certify \| model=deepseek-r1:32b-q4_k_m  [UNC | 5.1s |
| S10c | S10c-302 | soc2auditor/refuse-to-certify-binary[ISO | ⚠️  WARN | MUSTs OK; SHOULD failed: refuse_to_certify \| model=deepseek-r1:32b-q4_k_m  [UNC | 19.1s |
| S10c | S10c-303 | soc2auditor/insufficient-context-vague-p | ❌ FAIL | MUST failed: insufficient_context.exact_phrase \| model=deepseek-r1:32b-q4_k_m   | 52.4s |
| S10c | S10c-304 | soc2auditor/citation-format-discipline[N | ✅ PASS | all 1 assertions OK \| model=deepseek-r1:32b-q4_k_m | 7.0s |
| S10c | S10c-305 | soc2auditor/citation-format-discipline[H | ✅ PASS | all 1 assertions OK \| model=deepseek-r1:32b-q4_k_m | 11.4s |
| S10c | S10c-306 | soc2auditor/citation-format-discipline[G | ✅ PASS | all 1 assertions OK \| model=deepseek-r1:32b-q4_k_m | 9.6s |
| S10c | S10c-307 | soc2auditor/citation-format-discipline[S | ❌ FAIL | MUST failed: citation.format[SOC2] \| model=deepseek-r1:32b-q4_k_m  [UNCLASSIFIE | 18.4s |
| S10c | S10c-308 | soc2auditor/citation-format-discipline[P | ❌ FAIL | MUST failed: citation.format[PCI_DSS] \| model=deepseek-r1:32b-q4_k_m  [UNCLASSI | 26.5s |
| S10c | S10c-309 | soc2auditor/citation-format-discipline[N | ❌ FAIL | MUST failed: citation.format[NIST_800_53] \| model=deepseek-r1:32b-q4_k_m  [UNCL | 12.7s |
| S10c | S10c-310 | soc2auditor/citation-format-discipline[I | ❌ FAIL | MUST failed: citation.format[ISO_27001] \| model=deepseek-r1:32b-q4_k_m  [UNCLAS | 7.8s |
| S10c | S10c-311 | soc2auditor/dense-structured-tool-output | ✅ PASS | all 2 assertions OK \| model=deepseek-r1:32b-q4_k_m | 12.3s |
| S10c | S10c-312 | soc2auditor/dense-structured-tool-output | ✅ PASS | all 2 assertions OK \| model=deepseek-r1:32b-q4_k_m | 50.6s |
| S10c | S10c-313 | soc2auditor/dense-structured-tool-output | ✅ PASS | all 2 assertions OK \| model=deepseek-r1:32b-q4_k_m | 10.7s |
| S10c | S10c-314 | soc2auditor/dense-structured-tool-output | ✅ PASS | all 2 assertions OK \| model=deepseek-r1:32b-q4_k_m | 9.8s |
| S10c | S10c-315 | soc2auditor/dense-structured-tool-output | ✅ PASS | all 2 assertions OK \| model=deepseek-r1:32b-q4_k_m | 10.0s |
| S10c | S10c-316 | soc2auditor/dense-structured-tool-output | ✅ PASS | all 2 assertions OK \| model=deepseek-r1:32b-q4_k_m | 10.2s |
| S10c | S10c-317 | soc2auditor/dense-structured-tool-output | ✅ PASS | all 2 assertions OK \| model=deepseek-r1:32b-q4_k_m | 10.2s |
| S21 | S21-01 | LLM router enabled | ✅ PASS | LLM_ROUTER_ENABLED=True | 0.0s |
| S21 | S21-02 | LLM router model available | ✅ PASS | model: hf.co/QuantFactory/Llama-3.2-3B-Instruct-abliterat | 0.0s |
| S21 | S21-03 | LLM router security intent | ✅ PASS | routed→auto-redteam \| model: baronllm:q6_k | 7.3s |
| S21 | S21-04 | LLM router coding intent | ✅ PASS | routed→auto-coding \| model: qwen3-coder:30b | 11.9s |
| S21 | S21-05 | LLM router compliance intent | ✅ PASS | routed→auto-compliance \| model: deepseek-r1:32b-q4_k_m | 12.7s |
| S21 | S21-06 | routing_descriptions.json | ✅ PASS | 17 workspace descriptions | 0.0s |
| S21 | S21-07 | routing_examples.json | ✅ PASS | 32 examples | 0.0s |
| S3b | S3b-01 | Workspace auto-coding | ✅ PASS | MLX:True \| signals: ['def', 'return', 'reverse'] | 35.9s |
| S3b | S3b-02 | Workspace auto-agentic | ❌ FAIL | Ollama fallback! model=qwen3-coder:30b (MLX state=none, expected MLX-tier)  [UNC | 85.1s |
| S3b | S3b-03 | Workspace auto-spl | ❌ FAIL | Ollama fallback! model=deepseek-coder-v2:16b-lite-instruct-q4_K (MLX state=ready | 39.2s |
| S3b | S3b-04 | Workspace auto-reasoning | ❌ FAIL | Ollama fallback! model=deepseek-r1:32b-q4_k_m (MLX state=ready, expected MLX-tie | 41.8s |
| S3b | S3b-05 | Workspace auto-research | ✅ PASS | MLX:True \| signals: ['qubit', 'quantum', 'compute'] | 63.8s |
| S3b | S3b-06 | Workspace auto-data | ❌ FAIL | Ollama fallback! model=deepseek-r1:32b-q4_k_m (MLX state=ready, expected MLX-tie | 26.7s |
| S3b | S3b-07 | Workspace auto-compliance | ❌ FAIL | Ollama fallback! model=deepseek-r1:32b-q4_k_m (MLX state=ready, expected MLX-tie | 27.0s |
| S3b | S3b-08 | Workspace auto-mistral | ✅ PASS | MLX:True \| signals: ['trade', 'deploy', 'maintain'] | 77.4s |
| S3b | S3b-09 | Workspace auto-creative | ❌ FAIL | Ollama fallback! model=divinetribe/gemma-4-31b-it-abliterated-4 (MLX state=ready | 66.0s |
| S3b | S3b-10 | Workspace auto-vision | ✅ PASS | MLX:True \| signals: ['text', 'contrast', 'color'] | 85.4s |
| S3b | S3b-11 | Workspace auto-documents | ✅ PASS | MLX:True \| signals: ['introduction', 'scope', 'timeline'] | 61.1s |
| S11 | S11-00 | MLX availability | ✅ PASS | state: ready | 0.0s |
| S11 | S11-ERR | Section error | ❌ FAIL | [Errno 2] No such file or directory: '/dev/shm/portal_metrics/gauge_all_35445.db |  |
| S20 | S20-01 | MLX proxy health | ✅ PASS | state: ready, data: {'active_server': 'lm', 'loaded_model': 'mlx-community/phi-4 | 0.0s |
| S20 | S20-02 | MLX /v1/models | ✅ PASS | 30 models | 0.0s |
| S20 | S20-03 | MLX memory info | ✅ PASS | {'current': {'current': {'free_gb': 0.1, 'total_gb': 60.1, 'used_pct': 34, 'pres | 0.0s |
| S22 | S22-01 | MLX proxy for admission control | ✅ PASS | state: ready | 0.0s |
| S22 | S22-03 | Admission control rejects oversized | ℹ️  INFO | proxy accepted 70B request (free RAM: 56.4GB >= 50GB threshold) — no rejection e | 8.0s |
| S22 | S22-04 | Model memory estimates | ✅ PASS | 17 models with size estimates | 0.0s |
| S23 | S23-01 | GPT-OSS:20B available | ✅ PASS | gpt-oss in models: True | 0.0s |
| S23 | S23-03 | Gemma 4 E4B VLM registered | ✅ PASS | gemma-4-E4B in MLX models: True | 0.0s |
| S23 | S23-04 | Phi-4 available | ✅ PASS | phi-4 in MLX models: True | 0.0s |
| S23 | S23-05 | Magistral-Small available | ✅ PASS | magistral in MLX models: True | 0.0s |
| S23 | S23-06 | Phi-4-reasoning-plus available | ✅ PASS | phi-4-reasoning-plus in MLX models: True | 0.0s |
| S23 | S23-07 | Huihui-GLM-4.7-Flash-abliterated smoke t | ✅ PASS | loaded + produced 197 chars | 97.2s |
| S4 | S4-01 | Documents MCP health | ✅ PASS | HTTP 200 | 0.0s |
| S4 | S4-02 | Generate Word document | ✅ PASS | {
  "success": true,
  "filename": "Test_Proposal_18edcda0.docx",
  "download_ur | 0.2s |
| S4 | S4-03 | Generate Excel spreadsheet | ✅ PASS | {
  "success": true,
  "filename": "Test_Budget_3eda65d4.xlsx",
  "download_url" | 0.1s |
| S4 | S4-04 | Generate PowerPoint | ✅ PASS | {
  "success": true,
  "filename": "Test_Presentation_993118d4.pptx",
  "downloa | 0.0s |
| S4 | S4-05 | MCP read_word_document | ✅ PASS | got 110 chars from sample.docx | 0.0s |
| S4 | S4-06 | MCP read_excel | ✅ PASS | got 110 chars from sample.xlsx | 0.0s |
| S4 | S4-07 | MCP read_powerpoint | ✅ PASS | got 110 chars from sample.pptx | 0.0s |
| S4 | S4-08 | MCP read_pdf | ✅ PASS | got 109 chars from sample.pdf | 0.2s |
| S5 | S5-01 | Sandbox MCP health | ✅ PASS | HTTP 200 | 0.0s |
| S5 | S5-02 | Execute Python (sum 1-10) | ✅ PASS | {
  "success": true,
  "stdout": "55\n",
  "stderr": "",
  "exit_code": 0,
  "ti | 0.5s |
| S5 | S5-03 | Execute Python (list comprehension) | ✅ PASS | {
  "success": true,
  "stdout": "[0, 1, 4, 9, 16]\n",
  "stderr": "",
  "exit_c | 0.1s |
| S8 | S8-01 | MLX Speech health | ✅ PASS | voice_cloning: True | 0.0s |
| S8 | S8-02 | MLX Speech TTS | ✅ PASS | duration: 2.85s | 3.7s |
| S9 | S9-01 | MLX Speech ASR available | ✅ PASS | Qwen3-ASR | 0.0s |
| S9 | S9-03 | MLX Transcribe health | ✅ PASS | HTTP 200 | 0.0s |
| S9 | S9-04 | MLX Transcribe diarization | ⚠️  WARN | only 1 speaker(s) detected  [UNCLASSIFIED] | 14.0s |
| S9 | S9-05 | Workspace upload resolution | ⚠️  WARN | HTTP 404  [UNCLASSIFIED] | 0.0s |
| S7 | S7-01 | Music MCP health | ✅ PASS | service: music-mcp | 0.0s |
| S7 | S7-02 | Generate music (5s jazz) | ✅ PASS | {
  "success": true,
  "filename": "music_upbeat_jazz_piano_solo_5s.wav",
  "dow | 14.4s |
| S30 | S30-01 | ComfyUI direct | ✅ PASS | version: 0.16.3 | 0.0s |
| S30 | S30-02 | ComfyUI MCP bridge | ✅ PASS | HTTP 200 | 0.0s |
| S31 | S31-01 | Video MCP health | ✅ PASS | HTTP 200 | 0.0s |
| S41 | S41-01 | /health/all aggregator | ✅ PASS | 8/10 services ok: pipeline, mlx_proxy, ollama, mcp_documents, mcp_sandbox | 0.1s |
| S41 | S41-02 | bench-* concurrency=1 | ❌ FAIL | [Errno 2] No such file or directory: '/dev/shm/portal_metrics/gauge_all_35445.db | 0.0s |
| S41 | S41-03 | /admin/refresh-tools | ✅ PASS | 0 tools registered | 0.0s |
| S41 | S41-04 | Power metrics in /metrics | ✅ PASS | portal5_power_* and portal5_energy_* present | 0.0s |
| S41 | S41-05 | Workspace consistency | ❌ FAIL | [Errno 2] No such file or directory: '/dev/shm/portal_metrics/gauge_all_35445.db | 0.0s |
| S42 | S42-01 | Browser MCP health | ✅ PASS | status=ok, profiles=0 | 0.0s |
| S42 | S42-02 | Browser MCP tools | ✅ PASS | 8 tools: browser_navigate, browser_snapshot, browser_click, browser_fill... | 0.0s |
| S60 | S60-01 | Tool registry loaded | ✅ PASS | 0 tools: ... | 0.0s |
| S60 | S60-02 | Workspace tool whitelists | ❌ FAIL | [Errno 2] No such file or directory: '/dev/shm/portal_metrics/gauge_all_35445.db | 0.0s |
| S60 | S60-03 | Persona tool resolution | ❌ FAIL | [Errno 2] No such file or directory: '/dev/shm/portal_metrics/gauge_all_35445.db | 0.0s |
| S60 | S60-04 | Tool dispatch function | ✅ PASS | exists | 0.0s |
| S60 | S60-05 | MAX_TOOL_HOPS | ❌ FAIL | [Errno 2] No such file or directory: '/dev/shm/portal_metrics/gauge_all_35445.db | 0.0s |
| S60 | S60-06 | Tool-call Prometheus metrics | ⚠️  WARN | some tool metrics missing  [UNCLASSIFIED] | 0.0s |
| S60 | S60-07 | agentorchestrator persona | ✅ PASS | slug=agentorchestrator, workspace=auto-agentic | 0.0s |
| S70 | S70-01 | SearXNG web search | ✅ PASS | 25 results returned | 0.7s |
| S70 | S70-02 | Research MCP health | ✅ PASS | {"status":"ok","service":"research-mcp","backend":"searxng"} | 0.0s |
| S70 | S70-03 | Memory MCP health | ✅ PASS | {"status":"ok","service":"memory-mcp","stored":0} | 0.0s |
| S70 | S70-04 | RAG MCP health | ✅ PASS | {"status":"ok","service":"rag-mcp","knowledge_bases":[]} | 0.0s |
| S70 | S70-05 | Embedding service health | ✅ PASS | {"status":"ok","model":"microsoft/harrier-oss-v1-0.6b"} | 0.0s |
| S70 | S70-06 | Research personas | ✅ PASS | 6/6 present | 0.0s |
| S70 | S70-07 | auto-research tool whitelist | ❌ FAIL | [Errno 2] No such file or directory: '/dev/shm/portal_metrics/gauge_all_35445.db | 0.0s |
| S70 | S70-08 | Memory MCP round-trip | ✅ PASS | stored+recalled: id=86160384, sim=0.42, 1 hits | 1.8s |
| S3a | S3a-01 | Workspace auto | ✅ PASS | signals: ['DNS', 'domain', 'IP'] \| routed -> mlx-community/Dolphin3.0-Llama3.1- | 29.2s |
| S3a | S3a-02 | Workspace auto-video | ✅ PASS | signals: ['sun', 'mountain', 'light'] \| routed -> dolphin-llama3:8b matches Oll | 5.7s |
| S3a | S3a-03 | Workspace auto-music | ✅ PASS | signals: ['beat', 'loop', 'bass'] \| routed -> dolphin-llama3:8b matches Ollama: | 2.3s |
| S3a | S3a-04 | Workspace auto-security | ✅ PASS | signals: ['injection', 'XSS', 'authentication'] \| routed -> baronllm:q6_k match | 14.1s |
| S3a | S3a-05 | Workspace auto-redteam | ✅ PASS | signals: ['sudo', 'SUID', 'privilege'] \| routed -> baronllm:q6_k matches Ollama | 8.6s |
| S3a | S3a-06 | Workspace auto-blueteam | ✅ PASS | signals: ['traffic', 'network', 'monitor'] \| routed -> lily-cybersecurity:7b-q4 | 10.3s |
| S3b | S3b-01 | Workspace auto-coding | ✅ PASS | MLX:True \| signals: ['def', 'return', 'reverse'] | 48.7s |
| S3b | S3b-02 | Workspace auto-agentic | ❌ FAIL | Ollama fallback! model=qwen3-coder:30b (MLX state=none, expected MLX-tier)  [UNC | 86.0s |
| S3b | S3b-03 | Workspace auto-spl | ❌ FAIL | Ollama fallback! model=deepseek-coder-v2:16b-lite-instruct-q4_K (MLX state=ready | 42.5s |
| S3b | S3b-04 | Workspace auto-reasoning | ❌ FAIL | Ollama fallback! model=deepseek-r1:32b-q4_k_m (MLX state=ready, expected MLX-tie | 42.1s |
| S3b | S3b-05 | Workspace auto-research | ✅ PASS | MLX:True \| signals: ['qubit', 'quantum', 'compute'] | 64.4s |
| S3b | S3b-06 | Workspace auto-data | ❌ FAIL | Ollama fallback! model=deepseek-r1:32b-q4_k_m (MLX state=ready, expected MLX-tie | 27.3s |
| S3b | S3b-07 | Workspace auto-compliance | ❌ FAIL | Ollama fallback! model=deepseek-r1:32b-q4_k_m (MLX state=ready, expected MLX-tie | 27.4s |
| S3b | S3b-08 | Workspace auto-mistral | ❌ FAIL | Ollama fallback! model=deepseek-r1:32b-q4_k_m (MLX state=ready, expected MLX-tie | 26.8s |
| S3b | S3b-09 | Workspace auto-creative | ❌ FAIL | Ollama fallback! model=divinetribe/gemma-4-31b-it-abliterated-4 (MLX state=ready | 66.2s |
| S3b | S3b-10 | Workspace auto-vision | ✅ PASS | MLX:True \| signals: ['text', 'contrast', 'color'] | 85.7s |
| S3b | S3b-11 | Workspace auto-documents | ✅ PASS | MLX:True \| signals: ['introduction', 'scope', 'timeline'] | 59.7s |