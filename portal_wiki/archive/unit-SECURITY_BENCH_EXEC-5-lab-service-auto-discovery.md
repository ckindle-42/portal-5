---
id: unit-SECURITY_BENCH_EXEC-5-lab-service-auto-discovery
historical: true
kind: why
title: "SECURITY_BENCH_EXEC \u2014 5. Lab Service Auto-Discovery"
sources:
- type: design
  path: docs/SECURITY_BENCH_EXEC.md
  section: 5. Lab Service Auto-Discovery
confidence: high
tags:
- docs
- SECURITY_BENCH_EXEC

---

`--probe-lab` runs 19 service probes (SMB, WinRM, LDAP, Kerberos, RPC, Redis, NFS, HTTP/Solr/Tomcat/MySQL/FTP, VulnerableApp) and prints a reachability report. Auto-filters prompts to only those with reachable backing services.
