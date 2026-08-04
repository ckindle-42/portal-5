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


Attack chains are grounded in four external sources — every scenario's `red_order`/`red_prompt` in `exec_chain.py`'s `SCENARIOS` dict traces back to one of these:
- **[HTB Writeups](https://github.com/momenbasel/htb-writeups)** — real attack patterns from HackTheBox machines (Responder relay chains, LFI log poisoning, SQLi-to-shell, privilege escalation techniques)
- **[VulnHub](https://github.com/vulhub/vulhub)** — Docker-native vulnerable applications deployed on portal-lab-vulhub (Redis, PHP LFI, Apache Solr Log4Shell, Tomcat, NFS, VulnerableApp); also the source for the ~76 `vuln_*`/`web_*` single-CVE scenarios (Log4Shell, Struts2, Fastjson, Shiro, etc.)
- **[Metasploitable3](https://github.com/rapid7/metasploitable3)** — Windows VM with 12+ vulnerable services (vsftpd backdoor, MySQL UDF, GlassFish WAR deploy, Elasticsearch script RCE, IIS WebDAV, SMB/AD); source for the `meta3_*` scenarios
- **[MBPTL](https://github.com/bayufedra/MBPTL)** ("Most Basic Penetration Testing Lab", Black Hat Arsenal EU 2025) — 17-flag CTF (web, SQLi, post-exploit, pivot, binary) deployed on portal-lab-mbptl (lxc 300); source for `mbptl_ctf_full_chain` and related multi-step web-to-shell scenarios

The bench exercises multi-model multi-chain theory calls, tool calls, and lab execution against all four targets. Cross-target chains (e.g., `web_to_dc_pivot`) test lateral movement from web-facing services to AD infrastructure.

A related but separate component, **[Incalmo](https://github.com/cylabcyberautonomy/Incalmo)** (arXiv 2501.16466), is an optional Dockerized LLM-driven C2 layer (`deploy/portal-5/docker-compose.lab.yml`, `lab` profile) that calls `portal-pipeline` as its OpenAI backend — it is a red-teaming *tool* integration, not a source of scenario/attack-chain definitions, so it is not one of the four sources above.

---
