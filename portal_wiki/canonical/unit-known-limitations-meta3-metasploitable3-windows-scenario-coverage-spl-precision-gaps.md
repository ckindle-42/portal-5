---
id: unit-known-limitations-meta3-metasploitable3-windows-scenario-coverage-spl-precision-gaps
kind: what
title: "KNOWN_LIMITATIONS \u2014 meta3 (Metasploitable3-Windows) \u2014 Scenario Coverage\
  \ + SPL Precision Gaps"
sources:
- type: doc
  path: KNOWN_LIMITATIONS.md
  commit: 05e42ec2
  section: "meta3 (Metasploitable3-Windows) \u2014 Scenario Coverage + SPL Precision\
    \ Gaps"
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.6623669
updated_at: 1784946220.6623669
---

- **ID**: P5-SEC-META3-001
- **Description**: As of commit `cdf080e` (2026-07-04), meta3 (vmid 113, `portal-lab-meta3-win2k8`,
  10.10.11.10) has a real, working evidence pipeline — IIS logs (`web:access`), FTP logs
  (`ftp:access`), and Process Creation events (`windows:security`, 4688 auditing enabled
  live on the box) all collect, ship, and confirm-index correctly. Two gaps remain,
  found while building that pipeline:
  1. **Scenario coverage.** The current 7 `meta3_*` scenarios (`exec_chain.py::SCENARIOS`)
     cover only a subset of meta3's documented vulnerable services. Cross-referenced against
     https://github.com/rapid7/metasploitable3/wiki/Vulnerabilities: still unscripted —
     GlassFish deploy RCE (CVE-2011-0807, admin/sploit creds, port 4848/8080/8181), Struts
     (CVE-2016-3087) and Tomcat manager (CVE-2009-3843/4189, sploit/sploit creds, port 8282),
     Jenkins unauthenticated script console (port 8484), ManageEngine (CVE-2015-8249, port
     8020), Apache Axis2 (CVE-2010-0219, via Tomcat), WebDAV HTTP PUT shell upload (port
     8585), PHPMyAdmin (CVE-2013-3238, port 8585), Ruby on Rails web console (CVE-2015-3224,
     port 3000), JMX (CVE-2015-2342, port 1617), WordPress NinjaForms (CVE-2016-1209, port
     8585), `psexec` weak-password (port 445/139), RDP standard-auth (port 3389). WinRM
     weak-password (port 5985, `vagrant`/`vagrant`) is confirmed live-reachable and is
     already incidentally exercised by our own collection code — a dedicated scenario for it
     would need to be distinguishable from monitoring traffic in the resulting evidence.
  2. **SPL query precision.** `siem/spl_detections.yaml`'s SPL for meta3's own
     `detect_ground_truth` techniques doesn't match meta3's actual traffic shape yet:
     `T1059`/`T1059.004`/`T1548.001`/`T1068`/`T1210`/`T1021.002` are all written against
     `sourcetype="linux:auditd"` fields (copied from the vulhub/Linux template), which will
     never match the `windows:security` 4688 process-creation data now genuinely available
     for meta3 — needs Windows-appropriate SPL (`EventCode=4688`, `NewProcessName=`,
     `CommandLine=`, `Account=`) added, likely as OS-aware variants rather than blind
     replacement, since the same technique IDs are also scored against true Linux vulhub
     targets. `T1190`'s existing SPL (payload-substring matching: `passwd`, `../`,
     `UNION SELECT`, `jndi:`, `.php`, `cmd=`) also doesn't match meta3's actual traffic —
     verified live via `--replay-captured-red` on `meta3_full_chain`: real `web:access` data
     is shipped and indexed, but none of meta3's exploit traffic (plain `GET /`, JSON-body
     `POST /_search`, out-of-band FTP backdoor trigger) contains those literal substrings, so
     it still reports `synthetic-fallback` despite genuine live data being present.
- **Operator action**: Treat as a content-authoring task (new `exec_chain.py::SCENARIOS`
  entries with `target_host=_LAB_META3`, `detect_ground_truth`, `red_prompt` tool_hints; new
  or OS-variant SPL entries in `siem/spl_detections.yaml`), not a plumbing fix — the
  collection/shipping/replay infrastructure itself is confirmed working end-to-end. meta3 has
  a documented history of crashing under load (`qmpstatus: internal-error`, recovered via
  hard stop+start) even from routine investigation traffic, not just live exploitation —
  budget for that when scripting new scenarios against it.
