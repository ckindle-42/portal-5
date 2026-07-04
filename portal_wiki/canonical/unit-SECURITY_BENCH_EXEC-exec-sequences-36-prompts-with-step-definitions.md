---
id: unit-SECURITY_BENCH_EXEC-exec-sequences-36-prompts-with-step-definitions
kind: why
title: "SECURITY_BENCH_EXEC \u2014 EXEC_SEQUENCES \u2014 36 prompts with step definitions"
sources:
- type: design
  path: docs/SECURITY_BENCH_EXEC.md
  section: "EXEC_SEQUENCES \u2014 36 prompts with step definitions"
last_generated_commit: ''
confidence: high
tags:
- docs
- SECURITY_BENCH_EXEC
created_at: 1783195000.908942
updated_at: 1783195000.908942
---


Each step now carries optional fields:

| Field | Purpose |
|-------|---------|
| `time_budget_s` | Time ceiling for speed scoring |
| `fallback_techniques` | Alternative commands on retry |
| `depends_on` | DAG dependency edges |
| `stealth_event_ids` | Windows Event IDs to query after execution |
| `condition` | Conditional branching — step skipped if condition not met against lab observations |
| `output_keywords` | Result-match scoring — step passes if output contains these (outcome over method) |
| `success_indicators` | Strings that must appear in lab output for the step to count as "proven" (attack confirmed successful) |

Key AD-focused prompts:

| Prompt key | Steps | Tools used | Meta3 valid? |
|---|---|---|---|
| `kerberoasting` | recon → kerberoast → crack | nxc, impacket-GetUserSPNs, hashcat -m 13100 | ✅ |
| `asrep_roasting` | enum_no_preauth → capture → crack | rpcclient, impacket-GetNPUsers, hashcat -m 18200 | ✅ |
| `bloodhound_ad_recon` | collect → shortest_path → exploit_path → dcsync | bloodhound-python | ✅ |
| `pass_the_hash` | dump_hash → pth_spray → lateral → confirm | impacket-secretsdump, evil-winrm | ✅ |
| `smb_enum_relay` | signing_check → null_session → relay (conditional) → responder | nxc, enum4linux-ng, ntlmrelayx | ✅ |
| `redis_to_rce` | connect → ssh_key → cron_write → confirm_rce | redis-cli | — (lxc 112) |
| `adcs_template_abuse` | enum_templates → esc1_exploit → ptt → dcsync | certipy-ad | ⚠️ |
| `ad_dcsync_golden_ticket` | dcsync → golden → verify → persist | impacket-secretsdump, impacket-ticketer | ✅ |
| `rbcd_attack` | enum_delegation → add_computer → set_rbcd → impersonate | impacket-addcomputer, impacket-rbcd, impacket-getST | ⚠️ |
| `nfs_privesc_chain` | enum_nfs → mount → suid → confirm | showmount | — (lxc 112) |
| `eternalblue_ms17010` | scan → exploit → shell → flags | nmap, AutoBlue | ✅ (unpatched Win2k8) |

Web-focused prompts (validated against VulnerableApp + portal-lab-vulhub):

| Prompt key | Target | Service |
|--
