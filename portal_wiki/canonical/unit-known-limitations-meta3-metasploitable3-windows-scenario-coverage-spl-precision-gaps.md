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
- type: code
  path: portal/modules/security/core/candidate_eval.py
- type: code
  path: portal/modules/security/core/exec_chain.py
- type: code
  path: Dockerfile.attack
- type: code
  path: portal/modules/coding/tools/code_sandbox_mcp.py
- type: config
  path: config/portal.yaml
- type: code
  path: portal/modules/security/core/siem/spl_detections.py
- type: config
  path: portal/modules/security/core/siem/spl_detections.yaml
- type: code
  path: portal/modules/security/tests/test_coverage_expand.py
- type: code
  path: portal/modules/security/tests/test_spl_variants.py
- type: code
  path: tests/unit/test_lab_exec_posture.py
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
- security
- resolved
created_at: 1784946220.6623669
updated_at: 1785500996
---

- **ID**: P5-SEC-META3-001
- **Status**: RESOLVED 2026-07-31 for catalog coverage and SPL content.
- **Reconciliation**: The original limitation described seven scenarios and
  target `10.10.11.10`. The current spine identifies vmid 113 at
  `10.10.11.13`, and the repository had already expanded to 21 `meta3_*`
  scenarios plus Windows-aware SPL variants for `T1059`, `T1548.001`,
  `T1068`, `T1210`, `T1021.002`, and IIS-aware `T1190`. Those landed changes
  made most of the old open list stale.
- **Scenario completion**: Cross-checking the current 21-scenario catalog
  against Rapid7's Metasploitable3 vulnerability wiki left three documented
  Windows surfaces. `meta3_phpmyadmin_rce` now covers CVE-2013-3238 on 8585
  with Metasploit's canonical `exploit/multi/http/phpmyadmin_preg_replace`
  module and blank root credential;
  `meta3_rails_console_rce` covers CVE-2015-3224 on 3000 with the exact
  `exploit/multi/http/rails_web_console_v2_code_exec` module after a bounded
  exposed-console preflight; and
  `meta3_rdp_standard_auth` covers RDP on 3389 with a non-interactive standard
  credential check. The catalog now has 24 scenarios.
- **Legacy correction**: Four historical entries had been copied from a Linux
  target even though `_LAB_META3` is Windows. FTP no longer attempts the
  vsftpd port-6200 backdoor, MySQL no longer loads `udf.so`,
  `meta3_linux_privesc` performs bounded Windows token inspection while
  retaining its ID for result compatibility, and `meta3_full_chain` no longer
  reads `/etc`, searches SUID files, or uses a Unix shell technique. Regression
  coverage rejects those Linux-only payload markers anywhere in the meta3
  catalog.
- **SPL completion**: The existing OS-aware variants are retained, and
  `T1021.001` now adds the missing Windows RDP signature
  (`EventCode=4624`, `LogonType=10`). `T1557` was also hardened separately:
  generic 4624 volume is no longer enough; its rule requires correlated NTLM
  network logons and privileged-share access across multiple targets.
- **Validation**: The focused scenario, SPL-variant, and corpus suites pass.
  The attack image now installs `metasploit-framework`, fails its build if
  `msfconsole` or either required module is absent, and records all three
  capabilities in its image manifest. A fresh image build and load into the
  lab's DinD runtime reported Framework 6.4.146-dev, true manifest entries,
  and successfully loaded both modules with their expected option sets.
  The sandbox now also injects the Meta3 target and credential contract into
  each lab-exec container; the FTP and RDP scenarios consume those variables
  instead of embedding credentials in commands.
  `nxc rdp` remains installed for the non-interactive RDP check. Metasploit is
  available to these explicit, bounded scenario steps; it remains deliberately
  excluded from the emergent objective loop's read-only binary allowlist.
  New exploit scenarios are catalog/test verified but have not been fired
  against vmid 113 in this change set; the VM's documented instability still
  requires bounded live runs and recovery planning before such execution.
