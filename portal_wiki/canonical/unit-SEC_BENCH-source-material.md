---
id: unit-SEC_BENCH-source-material
kind: what
title: 'Attack chain source material: HTB, VulnHub, Metasploitable3, MBPTL'
sources:
- type: doc
  path: docs/SECURITY_BENCH_EXEC.md
  commit: d869257b
- type: code
  path: portal/modules/security/core/exec_chain.py
  commit: d869257b
last_generated_commit: d869257b
confidence: high
tags:
- security
- bench
- sources
created_at: 1784941806.378324
updated_at: 1784941806.378324
---

Attack chains are grounded in four external sources:

- **HTB Writeups** -- real attack patterns from HackTheBox machines (Responder relay chains, LFI log poisoning, SQLi-to-shell, privilege escalation techniques)
- **VulnHub** -- Docker-native vulnerable applications deployed on portal-lab-vulhub (Redis, PHP LFI, Apache Solr Log4Shell, Tomcat, NFS, VulnerableApp); also the source for the ~76 `vuln_*`/`web_*` single-CVE scenarios
- **Metasploitable3** -- Windows VM with 12+ vulnerable services (vsftpd backdoor, MySQL UDF, GlassFish WAR deploy, Elasticsearch script RCE, IIS WebDAV, SMB/AD)
- **MBPTL** ("Most Basic Penetration Testing Lab", Black Hat Arsenal EU 2025) -- 17-flag CTF deployed on portal-lab-mbptl (lxc 300)

A related but separate component, **Incalmo** (arXiv 2501.16466), is an optional Dockerized LLM-driven C2 layer that calls `portal-pipeline` as its OpenAI backend -- it is a red-teaming *tool* integration, not a source of scenario/attack-chain definitions.
