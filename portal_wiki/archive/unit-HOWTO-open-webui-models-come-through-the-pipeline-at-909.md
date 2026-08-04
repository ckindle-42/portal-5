---
id: unit-HOWTO-open-webui-models-come-through-the-pipeline-at-909
kind: why
title: "HOWTO \u2014 Open WebUI models come through the pipeline at :9099"
sources:
- type: design
  path: docs/HOWTO.md
  section: Open WebUI models come through the pipeline at :9099
last_generated_commit: ''
confidence: high
tags:
- docs
- HOWTO
created_at: 1783195000.840158
updated_at: 1783195000.840158
---

curl -s http://localhost:9099/v1/models \
  -H "Authorization: Bearer $(grep PIPELINE_API_KEY .env | cut -d= -f2)" \
  | python3 -c "import sys,json; [print(m['name']) for m in json.load(sys.stdin)['data']]" \
  | grep -i "red.team"
```


**Example — NERC CIP Compliance:**
1. Select `NERC CIP Compliance Analyst` from the model dropdown
2. Type: `Analyze CIP-007-6 R2 Part 2.1 — what evidence is needed?`
3. Example response:
   ```
   For CIP-007-6 R2, evidence is required to support the following: 

(2.1) All events specified in this requirement are available for access by appropriate Information System personnel. This capability
   ```

**Example — Phi-4 Technical Analyst:**
1. Select `Phi-4 Technical Analyst` from the model dropdown
2. Type: `Write a technical design document for a rate-limiting middleware in FastAPI`
3. Routes to `auto-documents` workspace → `granite4.1:8b` (Ollama) — structured document generation

**Example — Phi-4 STEM Analyst:**
1. Select `Phi-4 STEM Analyst` from the model dropdown
2. Type: `Given a Poisson process with rate λ=3 events/hour, what is the probability of exactly 5 events in 2 hours?`
3. Routes to `auto-daily` workspace (this model previously had its own dedicated `auto-*` alias workspace, folded away in BUILD_PROGRAM_COLLAPSE_V1.md Phase 7) → `phi4-reasoning:plus` (Ollama) — RL-trained reasoning, competition-level mathematics

**Example — GPT-OSS Analyst:**
1. Select `GPT-OSS Analyst` from the model dropdown
2. Type: `Compare the architectural trade-offs between event-driven and request-response microservice communication patterns`
3. Routes to `gpt-oss:20b` (Ollama) — OpenAI-lineage open-weight model with RL-trained reasoning

**Example — Gemma 4 Edge Vision (image + audio):**
1. Select `Gemma 4 Edge Vision` from the model dropdown
2. Attach an image or audio clip (up to 30 seconds) and type: `Describe what you see/hear and identify any anomalies`
3. Routes to `auto-daily` workspace (this model previously had its own dedicated `auto-*` alias workspace, folded away in BUILD_PROGRAM_COLLAPSE_V1.md Phase 7) — Gemma 4 E4B (Ollama) — native audio+image+text input, 256K ctx

**Example — Gemma 4 JANG Unfiltered Vision:**
1. Select `Gemma 4 JANG Unfiltered Vision` from the mo
