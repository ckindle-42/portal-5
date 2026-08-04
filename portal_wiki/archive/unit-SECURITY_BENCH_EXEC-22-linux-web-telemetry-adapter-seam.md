---
id: unit-SECURITY_BENCH_EXEC-22-linux-web-telemetry-adapter-seam
kind: why
title: "SECURITY_BENCH_EXEC \u2014 22. Linux/Web Telemetry (Adapter Seam)"
sources:
- type: design
  path: docs/SECURITY_BENCH_EXEC.md
  section: 22. Linux/Web Telemetry (Adapter Seam)
last_generated_commit: ''
confidence: high
tags:
- docs
- SECURITY_BENCH_EXEC
created_at: 1783195000.908709
updated_at: 1783195000.908709
---


Blue telemetry now reads through a backend-agnostic `TelemetryBackend` protocol (defined in `matrix.py`). The first adapter is **Wazuh/OpenSearch** (`LAB_OPENSEARCH_URL` / `wazuh-alerts-*`). A future **Splunk** adapter drops in behind the same protocol — no changes to detection logic or ground truth.

Linux/web targets (vulhub, mbptl, on-demand containers) have telemetry paths:
- **auditd + agent** on vulhub/mbptl hosts: process-exec, file-access, network events.
- **web-server access/error logs**: decoded for web attacks (LFI, SQLi, webshell, OAST).
- Technique→signal ground truth (backend-independent):
  - `T1190` web-exploit → access-log signature
  - `T1059` command-exec → auditd execve
  - `T1505.003` webshell → file-write + subsequent exec

**Validation-integrity gate:** A blue/purple PASS requires real telemetry. Synthetic-fallback scores `indeterminate`, never PASS. This is enforced in code and tested in `test_blue_linux.py`.

---
