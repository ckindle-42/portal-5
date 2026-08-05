---
id: unit-known-limitations-meta3-metasploitable3-windows-scenario-coverage-spl-precision-gaps
kind: what
title: "KNOWN_LIMITATIONS \u2014 meta3 (Metasploitable3-Windows) \u2014 Scenario Coverage\
  \ + SPL Precision Gaps"
sources:
- type: code
  path: config/lab_targets.yaml
- type: code
  path: portal/modules/security/core/exec_chain.py
- type: code
  path: portal/modules/security/core/siem/spl_detections.yaml
- type: code
  path: portal/modules/security/core/siem/capture_enrichment.py
- type: code
  path: portal/modules/security/core/_data.py
- type: code
  path: portal/modules/security/tests/test_spl_variants.py
- type: code
  path: portal/modules/security/tests/test_coverage_expand.py
last_generated_commit: 1c013743834d850604632980a093809f65c3c3ed
claims: []
confidence: high
tags:
- docs
- resolved
- security
- verified-v1
created_at: 1784946220.6623669
updated_at: 1785505564
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
  credential check. The catalog now covers the full documented Windows surface of the target.
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
  The follow-up image audit expanded this from three Meta3 checks to an
  authoritative lab-exercise contract. WebDAV, GraphQL, Nuclei, relay proxy,
  SNMP, and SSH helpers are now hard image requirements; smuggler and ysoserial
  support files are pinned. The Windows FTP, MySQL, and full-compromise
  `EXEC_SEQUENCES` were reconciled with their scenario contracts, and stale
  target-local Windows commands were moved behind remote-capable clients.
  `impacket-rdp_check` is runtime-verified for the non-interactive RDP check. Metasploit is
  available to these explicit, bounded scenario steps; it remains deliberately
  excluded from the emergent objective loop's read-only binary allowlist.
  All three added Meta3 scenarios were fired in bounded live runs against vmid
  113 on 2026-07-31 and produced 100%-valid scenario-specific captures. Target
  readiness now discovers DHCP drift by MAC and persistently repairs the Rails
  and vulnerable phpMyAdmin services after clean boots.

## Why

Metasploitable3 is a Windows target, so Linux-shaped scenario payloads and SPL written for Unix hosts were silently wrong against it — the original limitation's open list recorded exactly that drift. Re-grounding the catalog to `config/lab_targets.yaml`'s MAC-verified vmid 113 address and to the actual scenario set in `exec_chain.py` makes the coverage claim checkable, while the hardened SPL in `spl_detections.yaml` documents what evidence each technique now requires so a weak rule cannot masquerade as detection.
