---
id: unit-SECURITY_BENCH_EXEC-2-cross-prompt-artifact-chaining
kind: why
title: "SECURITY_BENCH_EXEC \u2014 2. Cross-Prompt Artifact Chaining"
sources:
- type: design
  path: docs/SECURITY_BENCH_EXEC.md
  section: 2. Cross-Prompt Artifact Chaining
last_generated_commit: ''
confidence: high
tags:
- docs
- SECURITY_BENCH_EXEC
created_at: 1783195000.901823
updated_at: 1783195000.901823
---

`CHAIN_INHERITANCE` (in `_data.py`) defines which prompts inherit artifacts from prior runs:
- `kerberoasting` → `pass_the_hash`, `ad_dcsync_golden_ticket` (cracked hashes/credentials forwarded)
- `asrep_roasting` → `pass_the_hash`
- `bloodhound_ad_recon` → `rbcd_attack`, `adcs_template_abuse`

Artifacts (NTLM hashes, Kerberos TGS hashes, file paths, credentials) are extracted from real sandbox output and injected into inheriting prompts' starting context.
