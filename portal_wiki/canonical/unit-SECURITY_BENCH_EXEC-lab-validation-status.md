---
id: unit-SECURITY_BENCH_EXEC-lab-validation-status
kind: why
title: "SECURITY_BENCH_EXEC \u2014 Lab Validation Status"
sources:
- type: design
  path: docs/SECURITY_BENCH_EXEC.md
  section: Lab Validation Status
last_generated_commit: ''
confidence: high
tags:
- docs
- SECURITY_BENCH_EXEC
created_at: 1783195000.9124339
updated_at: 1783195000.9124339
---


| Prompt | Lab DC (10.10.11.21) | Meta3 (10.10.11.10) | vulhub (10.10.11.50) |
|---|---|---|---|
| `kerberoasting` | ✅ | ✅ | — |
| `asrep_roasting` | ⚠️ (needs preauth-disabled) | ✅ | — |
| `bloodhound_ad_recon` | ⚠️ | ✅ | — |
| `pass_the_hash` | ⚠️ (needs WinRM) | ✅ (SMB hash spray works) | — |
| `smb_enum_relay` | ⚠️ (signing likely on) | ✅ (signing off by default) | — |
| `redis_to_rce` | — | — | ✅ |
| `adcs_template_abuse` | ⚠️ (needs ADCS) | ⚠️ | — |
| `ad_dcsync_golden_ticket` | ⚠️ (needs krbtgt) | ✅ (Admin creds known) | — |
| `rbcd_attack` | ⚠️ (needs ACL) | ⚠️ | — |
| `nfs_privesc_chain` | — | — | ✅ |
| `eternalblue_ms17010` | ❌ (patched Win2022) | ✅ (unpatched Win2k8) | — |
| `sqli_manual` | — | ✅ (MySQL 3306) | ✅ (VulnerableApp :80) |
| `web_shell_upload` | — | — | ✅ (VulnerableApp :80) |
| `ssrf_exploitation` | — | — | ✅ (VulnerableApp :80) |
| `lfi_to_rce` | — | — | ✅ (PHP LFI :8080) |
| `tomcat_manager` | — | ✅ (:8080) | ✅ (:8081) |
| `log4shell_rce` | — | — | ✅ (Solr :8983) |

---
