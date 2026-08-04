---
id: unit-SECURITY_BENCH_EXEC-5-lab-service-auto-discovery
kind: why
title: "SECURITY_BENCH_EXEC \u2014 5. Lab Service Auto-Discovery"
sources:
- type: design
  path: docs/SECURITY_BENCH_EXEC.md
  section: 5. Lab Service Auto-Discovery
last_generated_commit: ''
confidence: high
tags:
- docs
- SECURITY_BENCH_EXEC
created_at: 1783195000.9025521
updated_at: 1783195000.9025521
---

`--probe-lab` runs 19 service probes (SMB, WinRM, LDAP, Kerberos, RPC, Redis, NFS, HTTP/Solr/Tomcat/MySQL/FTP, VulnerableApp) and prints a reachability report. Auto-filters prompts to only those with reachable backing services.
