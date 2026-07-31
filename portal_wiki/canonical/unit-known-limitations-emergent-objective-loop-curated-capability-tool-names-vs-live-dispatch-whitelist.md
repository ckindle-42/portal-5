---
id: unit-known-limitations-emergent-objective-loop-curated-capability-tool-names-vs-live-dispatch-whitelist
kind: what
title: "KNOWN_LIMITATIONS \u2014 Emergent Objective Loop \u2014 Curated Capability\
  \ Tool Names vs Live-Dispatch Whitelist"
sources:
- type: doc
  path: KNOWN_LIMITATIONS.md
  commit: 05e42ec2
  section: "Emergent Objective Loop \u2014 Curated Capability Tool Names vs Live-Dispatch\
    \ Whitelist"
- type: code
  path: portal/modules/security/core/lab.py
- type: code
  path: portal/modules/security/core/objective_executor.py
- type: code
  path: portal/modules/security/core/capability/index.py
- type: code
  path: portal/modules/security/tests/test_kali_enable.py
- type: code
  path: portal/modules/security/tests/test_objective_executor.py
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.665378
updated_at: 1785460800
---

- **ID**: P5-EMERGENT-001
- **Status**: PARTIALLY FIXED 2026-07-29 — four root-cause fixes have landed; the underlying gap class remains open for tools not yet safely aliased.
- **Description**: `capability/index.py`'s curated Capability library (used by `capability.query()` and now the emergent objective loop, `TASK_EMERGENT_SLICE1_PERCEPTION_ENTRY_V1`) has two kinds of `tools` values for many entries — real Kali binary names (`nmap`, `impacket-secretsdump`, `bloodhound-ce-python`, ...) for domain-probe capabilities (`smb_probe`, `ldap_probe`, ...), or an **empty list** for several named-technique capabilities (`ad-certificate-abuse`, `kerberos-delegation`, `oauth-oidc-chain`, `file-upload-bypass`, `smb-enumeration`, and others). `lab.py::_lab_dispatch_inner`'s real live-dispatch path only recognizes a small fixed whitelist of ~15 literal tool names — neither the Kali binary names nor the empty-tools capability IDs originally matched that whitelist, so `SecurityExecutor` (Slice 1.2) dispatched them through the synthetic fallback even when the lab was fully live and reachable. A second, compounding cause was found the same day: `capability.query()`'s `applies_when` predicates (e.g. `smb_probe` requires `open_ports` to contain 445) are gated on a flat `observations["open_ports"]` list that predates `LabPerception` — `PerceptionDelta.to_observation()` didn't populate it, and `run_emergent_engagement` started with `observations={}` (no upfront perception call), so on a cold start every real-tooled AD-probe capability was starved out and only the empty-`tools` capabilities (which have no `applies_when` gate) ever matched.
- **Fixes landed** (all live-verified against the real Proxmox lab, portal-lab-dc01/srv01/vulhub, sandbox MCP `lab_exec_active:true`):
  1. `--domain-hint` threaded into `run_emergent_engagement`/CLI (was hardcoded `None`).
  2. `lab.py::_lab_dispatch_inner` now aliases the two real Kali binary names verified correct: `"nmap"` → same path as `run_nmap_scan` (confirmed real: 22/80/8080 open on `10.10.11.50`), `"impacket-GetUserSPNs"` → same path as `exploit_service`/Kerberoast (confirmed real: 3 live TGS hashes captured from `lab-srv01.portal.lab`, then a real offline `john`+rockyou.txt crack attempt inside the sandbox — 0/3 cracked, correctly scored `FAILED` not `PROVEN`, since the passwords aren't in the common wordlist).
  3. `PerceptionDelta.to_observation()` now also derives a flat `open_ports` list (`perception._extract_open_ports`, additive) from either shape the real prober can return, and `run_emergent_engagement` gained a `perception` param that seeds real initial observations before the loop starts (`goal_cli._cmd_emergent` wires this by default via the new shared `perception.default_lab_prober`, replacing a near-duplicate that used to live only in `security_mcp.py`). Confirmed live: after this fix the ranker's first pick against the AD domain moved from an empty-`tools` capability (`ad-certificate-abuse`) to a real-tooled one (`smb_probe`/`ldap_probe`'s `bloodhound-ce-python`) — proving the seed closes the starvation, though `bloodhound-ce-python` itself isn't in the alias table yet (see below).
  4. The platform deterministic fallback now chooses a capability before ranking that capability's tools, consumes both supported history shapes, avoids already-attempted actions while alternatives remain, starts with a recon capability, and progresses to an unattempted oracle-bound action after recon. This fixes the structural dead-end where an empty-`tools` oracle capability could never be selected whenever any other candidate declared a tool.
- **Still open**: Real Kali binaries seen live but not yet aliased/verified (`bloodhound-ce-python`, `impacket-secretsdump`, `impacket-psexec`, `impacket-wmiexec`, `enum4linux-ng`, `nxc`, `responder`, `impacket-GetNPUsers`, `impacket-dacledit`, `certipy-ad`, `ldap3`, `metasploit`) and the empty-`tools` capabilities (`ad-certificate-abuse`, `kerberos-delegation`, `oauth-oidc-chain`, `file-upload-bypass`, `smb-enumeration`) still dispatch synthetic. Each remaining alias needs its exact CLI invocation verified correct (and, for stateful/destructive ones like `impacket-psexec`/`impacket-wmiexec`/`responder`, reviewed for lab safety) before wiring — not done blind, unlike the two above which were directly confirmed working first.
- **Impact**: Deterministic progression is now structurally reachable and non-repeating, but a selected capability can still be non-dispatchable when its real tool has no verified alias or it declares no tool. That produces an honestly synthetic trajectory even against a live lab and still slows G1 corpus sign-off (`DESIGN_EMERGENT_LAB_AGENT_V2` §9). Synthetic steps remain excluded from `emergent_gaps.gaps_from_trajectory`, and synthetic-derived trajectories are never PROVEN (AX ratchet holds), so the remaining issue is coverage/usefulness rather than correctness or honesty.
- **Resolution path (open)**: Continue verifying and aliasing the remaining real binary names one at a time (never batch-guess CLI syntax for tools with real side effects), and separately decide what the empty-`tools` capabilities should actually dispatch to (populate `capability/index.py` or retire them). Pre-existing architecture gap in the "already-built" composition engine (`DESIGN_EMERGENT_LAB_AGENT_V2` §1's KEEP list assumed this layer was solid); not part of the original Slice 1/2/3 delta, but now partially remediated as part of the same live-verification pass.
- **Continuation checkpoint (2026-07-30)**: The current
  `SecurityExecutor` dispatches the semantic capability `action` instead of
  the selected binary `tool`. That correctly makes `smb_probe`, `ldap_probe`,
  and other `_LAB_SERVICE_PROBES` real, but it also means the ranker's curated
  binary selection is not used. Live, lab-scoped probes verified exact,
  non-mutating invocations for `bloodhound-ce-python` (`-c DCOnly --zip`),
  `enum4linux-ng -A`, anonymous `nxc smb --shares`, and
  `impacket-GetNPUsers` with a bounded users file. No alias code for those four
  has landed yet.
- **Safety finding**: `certipy-ad find` is not read-only in this lab; it
  started/used the Windows Remote Registry dependency while retrieving CA
  configuration. DFS and Remote Registry were returned to their observed
  running state after the probe. Keep Certipy out of the safe allowlist.
  `impacket-secretsdump`, `impacket-psexec`, `impacket-wmiexec`,
  `impacket-dacledit`, `responder`, and `metasploit` also remain deferred
  because they dump credentials, execute remotely, modify ACLs, poison
  traffic, or select arbitrary exploit modules.
- **Exact resume point**: Add an explicit read-only alias allowlist for the
  four verified tools (plus the already-supported `nmap` and
  `impacket-GetUserSPNs`), have `SecurityExecutor` dispatch the selected
  binary only when it is in that allowlist and otherwise retain action-level
  fallback, and add regression tests proving `curl`/unsafe selections still
  use the safe capability probe. Then live-run one AD emergent step and update
  this unit with the measured dispatch.
