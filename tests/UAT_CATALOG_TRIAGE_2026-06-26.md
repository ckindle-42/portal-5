# UAT catalog triage (operator decision required)
# HEAD: see git log -1

## Uncovered live workspaces (31)
# For each: decide UAT-scope or out-of-scope

### auto-* (user-facing — likely in scope unless bench-only)
  [ ] auto-agentic-lite
  [ ] auto-coding-uncensored
  [ ] auto-coding-uncensored-agentic
  [ ] auto-devstral
  [ ] auto-extract-uncensored
  [ ] auto-gemma-e4b
  [ ] auto-gemma-fast
  [ ] auto-gemma-vision
  [ ] auto-general-uncensored
  [ ] auto-glm
  [ ] auto-glm-thinking
  [ ] auto-security-uncensored

### bench-* (bench-only — likely out of UAT scope by design)
  [ ] bench-agentworld
  [ ] bench-devstral
  [ ] bench-e2b-pentest
  [ ] bench-exec-exploit
  [ ] bench-exec-reasoning
  [ ] bench-exec-recon
  [ ] bench-fastcontext
  [ ] bench-glm-reap
  [ ] bench-glm-z1-rumination
  [ ] bench-lfm-micro-1p2b
  [ ] bench-lfm-micro-230m
  [ ] bench-lfm-micro-350m
  [ ] bench-qwen36-27b-optiq
  [ ] bench-qwen36-27b-ud
  [ ] bench-supergemma4-sec
  [ ] bench-sylink
  [ ] bench-vulnllm-r7b

## Stale references (22) — workspaces in UAT catalog but not in portal.yaml
# Likely renamed or removed; either update the UAT group or remove the reference

  [ ] auto-docs    (referenced by: g_auto_docs, g_browser_automation)
  [ ] bench-apriel-nemotron    (referenced by: g_benchmark)
  [ ] bench-deepseek-coder-v2    (referenced by: g_benchmark)
  [ ] bench-dolphin-r1    (referenced by: g_benchmark)
  [ ] bench-dolphin8b    (referenced by: g_benchmark)
  [ ] bench-foundation-sec    (referenced by: g_benchmark)
  [ ] bench-gemma4-12b-coder    (referenced by: g_benchmark)
  [ ] bench-harness1    (referenced by: g_benchmark)
  [ ] bench-lfm2-moe    (referenced by: g_benchmark)
  [ ] bench-llama33-70b    (referenced by: g_benchmark)
  [ ] bench-magistral    (referenced by: g_benchmark)
  [ ] bench-mistral-small32    (referenced by: g_benchmark)
  [ ] bench-negentropy    (referenced by: g_benchmark)
  [ ] bench-phi4    (referenced by: g_benchmark)
  [ ] bench-phi4-mini-reasoning    (referenced by: g_benchmark)
  [ ] bench-phi4-reasoning    (referenced by: g_benchmark)
  [ ] bench-qwable-27b    (referenced by: g_benchmark)
  [ ] bench-qwopus-coder-mtp    (referenced by: g_benchmark)
  [ ] bench-r1-0528-abliterated    (referenced by: g_benchmark)
  [ ] bench-r1-0528-qwen3-8b    (referenced by: g_benchmark)
  [ ] bench-starcoder2    (referenced by: g_benchmark)
  [ ] bench-wrn8b    (referenced by: g_benchmark)
