---
id: unit-SECURITY_BENCH_EXEC-tier-3-lab-exec-real-dispatch-all-targets-snapshot
kind: why
title: "SECURITY_BENCH_EXEC \u2014 Tier 3: Lab-Exec (real dispatch, all targets, snapshot\
  \ lifecycle)"
sources:
- type: design
  path: docs/SECURITY_BENCH_EXEC.md
  section: 'Tier 3: Lab-Exec (real dispatch, all targets, snapshot lifecycle)'
last_generated_commit: ''
confidence: high
tags:
- docs
- SECURITY_BENCH_EXEC
created_at: 1783195000.9003751
updated_at: 1783195000.9003751
---

python3 -m tests.benchmarks.bench_security \
  --skip-workspace-bench \
  --exec-chain-models \
    "hf.co/mradermacher/VulnLLM-R-7B-GGUF:Q4_K_M" \
    "qwen3-coder:30b-a3b-q4_K_M" \
    "huihui_ai/baronllm-abliterated:latest" \
  --blue-defender "hf.co/fdtn-ai/Foundation-Sec-8B-Reasoning-Q8_0-GGUF:Q8_0" \
  --prompt kerberoasting asrep_roasting bloodhound_ad_recon adcs_template_abuse \
    pass_the_hash smb_enum_relay ad_dcsync_golden_ticket rbcd_attack \
    redis_to_rce lfi_to_rce tomcat_manager log4shell_rce nfs_privesc_chain \
    sqli_manual web_shell_upload ssrf_exploitation eternalblue_ms17010 \
  --lab-exec --blue-active --lab-snapshot --probe-lab --chain-rounds 2 \
  2>&1 | tee /tmp/secbench_labexec.log
```

---
