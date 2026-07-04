---
id: unit-SECURITY_BENCH_EXEC-source-material
kind: why
title: "SECURITY_BENCH_EXEC \u2014 Source Material"
sources:
- type: design
  path: docs/SECURITY_BENCH_EXEC.md
  section: Source Material
last_generated_commit: ''
confidence: high
tags:
- docs
- SECURITY_BENCH_EXEC
created_at: 1783195000.8962638
updated_at: 1783195000.8962638
---


Attack chains are grounded in three sources:
- **[HTB Writeups](https://github.com/momenbasel/htb-writeups)** — real attack patterns from HackTheBox machines (Responder relay chains, LFI log poisoning, SQLi-to-shell, privilege escalation techniques)
- **[VulnHub](https://github.com/vulhub/vulhub)** — Docker-native vulnerable applications deployed on portal-lab-vulhub (Redis, PHP LFI, Apache Solr Log4Shell, Tomcat, NFS, VulnerableApp)
- **[Metasploitable3](https://github.com/rapid7/metasploitable3)** — Windows VM with 12+ vulnerable services (vsftpd backdoor, MySQL UDF, GlassFish WAR deploy, Elasticsearch script RCE, IIS WebDAV, SMB/AD)

The bench exercises multi-model multi-chain theory calls, tool calls, and lab execution against all three targets. Cross-target chains (e.g., `web_to_dc_pivot`) test lateral movement from web-facing services to AD infrastructure.

---
