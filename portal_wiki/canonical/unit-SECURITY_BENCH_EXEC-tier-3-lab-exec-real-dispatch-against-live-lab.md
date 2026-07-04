---
id: unit-SECURITY_BENCH_EXEC-tier-3-lab-exec-real-dispatch-against-live-lab
kind: why
title: "SECURITY_BENCH_EXEC \u2014 Tier 3 \u2014 Lab-Exec (real dispatch against live\
  \ lab)"
sources:
- type: design
  path: docs/SECURITY_BENCH_EXEC.md
  section: "Tier 3 \u2014 Lab-Exec (real dispatch against live lab)"
last_generated_commit: ''
confidence: high
tags:
- docs
- SECURITY_BENCH_EXEC
created_at: 1783195000.8996532
updated_at: 1783195000.8996532
---


Multi-model chain with real sandbox execution, blue defender, snapshot lifecycle, and lab probe. Copy-paste ready — single command exercises all lab-backed prompts against all targets.

```bash
python3 -m tests.benchmarks.bench_security \
  --skip-workspace-bench \
  --exec-chain-models \
    "hf.co/mradermacher/VulnLLM-R-7B-GGUF:Q4_K_M" \
    "qwen3-coder:30b-a3b-q4_K_M" \
    "huihui_ai/baronllm-abliterated:latest" \
  --blue-defender "hf.co/fdtn-ai/Foundation-Sec-8B-Reasoning-Q8_0-GGUF:Q8_0" \
  --prompt \
    kerberoasting \
    asrep_roasting \
    bloodhound_ad_recon \
    adcs_template_abuse \
    pass_the_hash \
    smb_enum_relay \
    ad_dcsync_golden_ticket \
    rbcd_attack \
    redis_to_rce \
    lfi_to_rce \
    tomcat_manager \
    log4shell_rce \
    nfs_privesc_chain \
    sqli_manual \
    web_shell_upload \
    ssrf_exploitation \
    eternalblue_ms17010 \
    ftp_backdoor \
    mysql_udf_privesc \
    glassfish_deploy \
    es_script_rce \
    iis_webdav_scanner \
    meta3_full_compromise \
    web_to_dc_pivot \
    htb_responder_chain \
    htb_lfi_log_poison \
    htb_sqli_to_shell \
  --lab-exec \
  --blue-active \
  --lab-snapshot \
  --probe-lab \
  --chain-rounds 2 \
  2>&1 | tee /tmp/secbench_labexec.log
```

Target coverage of the Tier 3 command:

| Target | Prompts exercising it |
|---|---|
| portal-lab-dc01 (10.10.11.21) | kerberoasting, asrep_roasting, bloodhound_ad_recon, pass_the_hash, smb_enum_relay, ad_dcsync_golden_ticket, rbcd_attack, adcs_template_abuse, htb_responder_chain |
| portal-lab-meta3-win2k8 (10.10.11.10) | kerberoasting, asrep_roasting, bloodhound_ad_recon, pass_the_hash, smb_enum_relay, eternalblue_ms17010, tomcat_manager, ftp_backdoor, mysql_udf_privesc, glassfish_deploy, es_script_rce, iis_webdav_scanner, meta3_full_compromise |
| portal-lab-vulhub (10.10.11.50) | redis_to_rce, lfi_to_rce, tomcat_manager, log4shell_rce, nfs_privesc_chain, htb_lfi_log_poison |
| VulnerableApp (:80) | sqli_manual, web_shell_upload
