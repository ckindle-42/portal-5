---
id: unit-security-tests-test-kali-enable
kind: what
title: Kali enablement on the main-chain path
sources:
- type: code
  path: portal/modules/security/tests/test_kali_enable.py
last_generated_commit: baca992c674a3cbb36a619e8f62e7e88b8fccfff
claims: []
confidence: high
tags:
- verified-v1
created_at: 1784946220.5
updated_at: 1784946220.5
---

`test_kali_enable.py` locks the main-chain Kali path so the security harness can drive real tooling instead of synthetic stand-ins. It asserts `CHAIN_TOOLS_BASE` exposes exactly `execute_bash` and `execute_python` on top of the original wrapper set, with schemas matching `INLINE_TOOLS` and no further tool proliferation. A second block proves `lab_dispatch` routes those two names to the live Kali box through `_lab_mcp_call`, that read-only aliases like `nmap` and `impacket-GetUserSPNs` reach the same verified dispatch rather than a synthetic fallback, and that `impacket-GetNPUsers` stays bounded to known lab accounts. `accumulate_observations` must extract compromise, port, CVE, and data markers from raw output while empty or erroring output earns no credit — the honesty guard that stops a bare tool call from counting as progress.

## Why

Previously the harness could only replay wrappers against fake environments, which meant the model never exercised the actual Kali binaries it was expected to use and the results did not transfer to a live lab. Enabling real dispatch is only safe if every technique signal still requires a genuine observation, so the suite pairs the capability expansion with an honesty guard: coverage is granted on real output, never on the mere act of calling the tool.
