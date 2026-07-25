---
id: unit-SEC_BENCH-exercises
kind: what
title: 'What the security bench exercises: prompts and scenarios'
sources:
- type: doc
  path: docs/SECURITY_BENCH_EXEC.md
  commit: ddb1cc61
- type: code
  path: portal/modules/security/core/_data.py
  commit: ddb1cc61
last_generated_commit: ddb1cc61
confidence: high
tags:
- security
- bench
- prompts
created_at: 1784945480.186122
updated_at: 1784945480.186122
---

## EXEC_SEQUENCES — 36 prompts with step definitions

Each step carries: `time_budget_s`, `fallback_techniques`, `depends_on`, `stealth_event_ids`, `condition`, `output_keywords`, `success_indicators`.

Key AD-focused prompts: `kerberoasting`, `asrep_roasting`, `bloodhound_ad_recon`, `pass_the_hash`, `smb_enum_relay`, `redis_to_rce`, `adcs_template_abuse`, `ad_dcsync_golden_ticket`, `rbcd_attack`, `nfs_privesc_chain`, `eternalblue_ms17010`.

Web-focused prompts: `sqli_manual`, `web_shell_upload`, `ssrf_exploitation`, `lfi_to_rce`, `tomcat_manager`, `log4shell_rce`.

Metasploitable3 prompts: `ftp_backdoor`, `mysql_udf_privesc`, `glassfish_deploy`, `es_script_rce`, `iis_webdav_scanner`, `meta3_full_compromise`.

Cross-target chains: `web_to_dc_pivot`, `htb_responder_chain`, `htb_lfi_log_poison`, `htb_sqli_to_shell`.
