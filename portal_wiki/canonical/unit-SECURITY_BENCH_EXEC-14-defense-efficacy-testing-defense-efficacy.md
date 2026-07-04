---
id: unit-SECURITY_BENCH_EXEC-14-defense-efficacy-testing-defense-efficacy
kind: why
title: "SECURITY_BENCH_EXEC \u2014 14. Defense Efficacy Testing (`--defense-efficacy`)"
sources:
- type: design
  path: docs/SECURITY_BENCH_EXEC.md
  section: 14. Defense Efficacy Testing (`--defense-efficacy`)
last_generated_commit: ''
confidence: high
tags:
- docs
- SECURITY_BENCH_EXEC
created_at: 1783195000.9048052
updated_at: 1783195000.9048052
---

After blue deploys countermeasures (block_ip, disable_account), re-runs red's attack to verify the defense actually prevented it. Reports `defense_effective` (bool) and `depth_reduction` (how many fewer steps red achieved after defense).

```bash
python3 -m tests.benchmarks.bench_security \
  --chain-models "hf.co/mradermacher/VulnLLM-R-7B-GGUF:Q4_K_M" \
  --blue-models "hf.co/fdtn-ai/Foundation-Sec-8B-Reasoning-Q8_0-GGUF:Q8_0" \
  --defense-efficacy --lab-exec
```
