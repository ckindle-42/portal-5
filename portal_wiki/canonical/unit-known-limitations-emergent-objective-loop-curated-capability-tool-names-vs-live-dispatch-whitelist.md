---
id: unit-known-limitations-emergent-objective-loop-curated-capability-tool-names-vs-live-dispatch-whitelist
kind: what
title: "KNOWN_LIMITATIONS \u2014 Emergent Objective Loop \u2014 Curated Capability\
  \ Tool Names vs Live-Dispatch Whitelist"
sources:
- type: code
  path: portal/modules/security/core/lab.py
- type: code
  path: portal/modules/security/core/objective_executor.py
- type: code
  path: portal/modules/security/core/capability/index.py
- type: code
  path: portal/modules/security/core/goal_decide.py
- type: code
  path: portal/modules/security/core/objective_entry.py
- type: code
  path: portal/modules/security/core/perception.py
- type: code
  path: portal/modules/security/core/goal_cli.py
- type: code
  path: portal/modules/security/core/emergent_gaps.py
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.665378
updated_at: 1785500237
---

- **ID**: P5-EMERGENT-001
- **Status**: RESOLVED 2026-07-31 for the live emergent dispatch boundary. Verified read-only binaries can dispatch; unbound and stateful/destructive capabilities cannot enter a live trajectory.
- **Description**: `capability/index.py`'s curated Capability library (used by `capability.query()` and now the emergent objective loop, `TASK_EMERGENT_SLICE1_PERCEPTION_ENTRY_V1`) has two kinds of `tools` values for many entries — real Kali binary names (`nmap`, `impacket-secretsdump`, `bloodhound-ce-python`, ...) for domain-probe capabilities (`smb_probe`, `ldap_probe`, ...), or an **empty list** for several named-technique capabilities (`ad-certificate-abuse`, `kerberos-delegation`, `oauth-oidc-chain`, `file-upload-bypass`, `smb-enumeration`, and others). `lab.py::_lab_dispatch_inner`'s real live-dispatch path only recognizes a small fixed whitelist of ~15 literal tool names — neither the Kali binary names nor the empty-tools capability IDs originally matched that whitelist, so `SecurityExecutor` (Slice 1.2) dispatched them through the synthetic fallback even when the lab was fully live and reachable. A second, compounding cause was found the same day: `capability.query()`'s `applies_when` predicates (e.g. `smb_probe` requires `open_ports` to contain 445) are gated on a flat `observations["open_ports"]` list that predates `LabPerception` — `PerceptionDelta.to_observation()` didn't populate it, and `run_emergent_engagement` started with `observations={}` (no upfront perception call), so on a cold start every real-tooled AD-probe capability was starved out and only the empty-`tools` capabilities (which have no `applies_when` gate) ever matched.
- **Fixes landed** (all live-verified against the real Proxmox lab, portal-lab-dc01/srv01/vulhub, sandbox MCP `lab_exec_active:true`):
  1. `--domain-hint` threaded into `run_emergent_engagement`/CLI (was hardcoded `None`).
  2. `lab.py::_lab_dispatch_inner` now aliases the two real Kali binary names verified correct: `"nmap"` → same path as `run_nmap_scan` (confirmed real: 22/80/8080 open on `10.10.11.50`), `"impacket-GetUserSPNs"` → same path as `exploit_service`/Kerberoast (confirmed real: 3 live TGS hashes captured from `lab-srv01.portal.lab`, then a real offline `john`+rockyou.txt crack attempt inside the sandbox — 0/3 cracked, correctly scored `FAILED` not `PROVEN`, since the passwords aren't in the common wordlist).
  3. `PerceptionDelta.to_observation()` now also derives a flat `open_ports` list (`perception._extract_open_ports`, additive) from either shape the real prober can return, and `run_emergent_engagement` gained a `perception` param that seeds real initial observations before the loop starts (`goal_cli._cmd_emergent` wires this by default via the new shared `perception.default_lab_prober`, replacing a near-duplicate that used to live only in `security_mcp.py`). Confirmed live: after this fix the ranker's first pick against the AD domain moved from an empty-`tools` capability (`ad-certificate-abuse`) to a real-tooled one (`smb_probe`/`ldap_probe`'s `bloodhound-ce-python`) — proving the seed closes the starvation and motivating the audited allowlist in item 5.
  4. The platform deterministic fallback now chooses a capability before ranking that capability's tools, consumes both supported history shapes, avoids already-attempted actions while alternatives remain, starts with a recon capability, and progresses to an unattempted oracle-bound action after recon. This fixes the structural dead-end where an empty-`tools` oracle capability could never be selected whenever any other candidate declared a tool.
  5. `SecurityExecutor` now honors the ranker's selected binary only through one explicit read-only allowlist: `nmap`, `impacket-GetUserSPNs`, `bloodhound-ce-python`, `enum4linux-ng`, `nxc`, and `impacket-GetNPUsers`. The four new aliases use the previously live-audited command shapes: BloodHound `DCOnly` collection, `enum4linux-ng -A`, anonymous NetExec SMB share enumeration, and a GetNPUsers check bounded to the two known lab accounts. Every non-allowlisted selection retains the semantic capability probe. Regression coverage proves `curl`, Certipy, secretsdump, psexec, wmiexec, Responder, and Metasploit cannot override that fallback.
  6. The live `_SecurityCapabilityProvider` now queries with `live_dispatchable_only=True`. That retains semantic service probes (including probes whose catalog `tools` list is empty but whose action has a concrete `lab.py` route) and retires every unbound challenge-class/lab-target entry from live selection. Catalog queries and dry-run planning remain unchanged. The five named empty-tool examples can no longer produce synthetic live steps.
- **Intentional exclusions**: Stateful/destructive or otherwise unaudited binaries (`impacket-secretsdump`, `impacket-psexec`, `impacket-wmiexec`, `responder`, `impacket-dacledit`, `certipy-ad`, `ldap3`, `metasploit`) remain deliberately unaliased. Unbound challenge-class and lab-target capabilities remain visible in the catalog and dry-run planner but are not live-dispatchable.
- **Residual boundary**: The live emergent loop can now perform honest reconnaissance but will not advance into an exploit capability until that capability receives a separately audited executor binding. It may therefore halt blocked after exhausting applicable probes. That is the intended truthful behavior: no synthetic exploit is represented as live progress, and future capability expansion must land with its dispatch and rollback contract.
- **Resolution**: The selected-binary path is explicit and allowlisted, unsafe selections retain safe action-level fallback, and capabilities with no concrete live binding are retired from the live provider. Synthetic steps remain excluded from `emergent_gaps.gaps_from_trajectory`, and synthetic-derived trajectories can never be PROVEN (AX ratchet).
- **Live completion checkpoint (2026-07-31)**: A bounded one-action AD
  emergent verification seeded fresh perception against `10.10.11.21`,
  observed ports 53/80/88/135/389/445/464/636/3268, and deterministically
  selected `smb_probe` with `bloodhound-ce-python`. `SecurityExecutor`
  dispatched the selected allowlisted binary. The `DCOnly` collection
  completed successfully and returned 13 users, 53 groups, 3 computers, 2
  GPOs, 5 OUs, and 0 trusts before compressing the sandbox-local output.
- **Safety finding**: `certipy-ad find` is not read-only in this lab; it
  started/used the Windows Remote Registry dependency while retrieving CA
  configuration. DFS and Remote Registry were returned to their observed
  running state after the probe. Keep Certipy out of the safe allowlist.
  `impacket-secretsdump`, `impacket-psexec`, `impacket-wmiexec`,
  `impacket-dacledit`, `responder`, and `metasploit` also remain deferred
  because they dump credentials, execute remotely, modify ACLs, poison
  traffic, or select arbitrary exploit modules.
- **Future extension rule**: A retired capability may return to live emergent
  selection only with a separately audited semantic executor binding. Keep
  the stateful/destructive tool set out of the allowlist unless a future task
  explicitly defines containment, rollback, and live-verification
  requirements for that tool.

## Why

The curated capability library and the live dispatch boundary are two different trust levels, and conflating them produced synthetic exploits being reported as real progress. The allowlist is the seam: only a small set of read-only binaries verified against the live lab may dispatch through `_lab_dispatch_inner`, and `live_dispatchable_only` retires everything unbound from the live trajectory while keeping it visible for planning. That asymmetry is deliberate — an unbound capability must never be represented as a live step.
