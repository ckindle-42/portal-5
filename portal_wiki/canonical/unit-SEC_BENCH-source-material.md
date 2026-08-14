---
id: unit-SEC_BENCH-source-material
kind: what
title: 'Attack chain source material: HTB, VulnHub, Metasploitable3, MBPTL'
sources:
- type: code
  path: portal/modules/security/core/exec_chain.py
- type: code
  path: portal/modules/security/core/_data.py
claims: []
confidence: high
tags:
- bench
- security
- sources
- verified-v1
created_at: 1784941806.378324
updated_at: 1784941806.378324
---

Attack chains are grounded in four external sources:

- **HTB Writeups** -- real attack patterns from HackTheBox machines (Responder relay chains, LFI log poisoning, SQLi-to-shell, privilege escalation techniques)
- **VulnHub** -- Docker-native vulnerable applications deployed on portal-lab-vulhub (Redis, PHP LFI, Apache Solr Log4Shell, Tomcat, NFS, VulnerableApp); also the source for the `vuln_*`/`web_*` single-CVE scenarios in `exec_chain.py`'s `SCENARIOS`
- **Metasploitable3** -- Windows VM whose vulnerable service fleet (FTP, MySQL, GlassFish WAR deploy, Elasticsearch script RCE, IIS WebDAV, SMB/AD) anchors the `meta3_*` scenarios
- **MBPTL** ("Most Basic Penetration Testing Lab", Black Hat Arsenal EU 2025) -- 17-flag CTF deployed on portal-lab-mbptl (lxc 300)

A related but separate component, **Incalmo** (arXiv 2501.16466), is an optional Dockerized LLM-driven C2 layer that calls `portal-pipeline` as its OpenAI backend -- it is a red-teaming *tool* integration, not a source of scenario/attack-chain definitions.

## Why

Naming the external sources matters because every `SCENARIOS` red chain is traceable back to one of them, which is how a reviewer validates that a scenario reflects a real technique rather than a synthetic one. VulnHub supplies the bulk of the `vuln_*`/`web_*` cases, Metasploitable3 anchors the `meta3_*` AD/web cases, and MBPTL supplies the web-to-shell chain. Incalmo is excluded deliberately: it drives the pipeline but defines no scenario content, so citing it as a source would be misleading.
