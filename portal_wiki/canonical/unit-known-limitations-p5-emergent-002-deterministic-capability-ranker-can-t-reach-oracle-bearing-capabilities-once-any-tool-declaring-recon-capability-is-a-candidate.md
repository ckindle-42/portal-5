---
id: unit-known-limitations-p5-emergent-002-deterministic-capability-ranker-can-t-reach-oracle-bearing-capabilities-once-any-tool-declaring-recon-capability-is-a-candidate
kind: what
title: "KNOWN_LIMITATIONS \u2014 P5-EMERGENT-002 \u2014 Deterministic capability ranker\
  \ can't reach oracle-bearing capabilities once any tool-declaring recon capability\
  \ is a candidate"
sources:
- type: doc
  path: KNOWN_LIMITATIONS.md
  commit: 05e42ec2
  section: "P5-EMERGENT-002 \u2014 Deterministic capability ranker can't reach oracle-bearing\
    \ capabilities once any tool-declaring recon capability is a candidate"
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.676039
updated_at: 1784946220.676039
---

Found live during `TASK_SECURITY_ARM_CLOSE_LOOP_V1` Phase 8 (`goal emergent`
run against the reconciled `10.10.11.50` target, `objective_class=host_foothold`,
2026-07-16). `portal.platform.agent.decide._decide_via_deterministic_fallback`
picks a tool first (`rank.select_tools`), then finds the first candidate
capability whose `tools` list contains that tool
(`_pick_capability_for_tool`). Recon-phase service-probe capabilities (from
`capability/index.py`'s `_from_service_probes`) always declare real tools
(`curl`, `redis-cli`, …); exploit-phase capabilities from `_from_lab_targets`
and `_from_challenge_classes` — the ones carrying a real `oracle` — always
declare `tools=[]`. Once ANY tool-declaring capability is among the
candidates, `available_tools` is non-empty and the ranker takes the
tools-based branch, which structurally can never select a `tools=[]`
capability (`_pick_capability_for_tool` only matches on declared tools). The
loop lands real, live actions (confirmed: `redis_probe` → real `redis-cli`
PONG against the vulhub redis stack) but then halts on the I4 no-progress
gate because the ranker keeps re-selecting the same top recon capability
every turn — no state tracks "already probed this port", and exploit-phase
capabilities with oracles are never reachable to prove AX (state-oracle
verdict) end-to-end.

Two real, separate fixes are already applied in this task's run (both
correctness fixes, not workarounds): (1) `SecurityExecutor.execute` now
dispatches on `decision["action"]` (the semantic capability id) instead of
`decision["tool"]` (the raw binary name) — `lab.lab_dispatch`'s fn_name
routing is action-keyed, so dispatching on `tool` silently fell through to
the synthetic catch-all the moment any capability had a declared tool; (2)
`lab.py`'s `run_nmap_scan`/`nmap` fixed port list only covered AD-lab ports
and missed the WEB target's own vulhub ports (6379/8081/8983) — perception
never discovered those services even though they're live.

**Not fixed here** (deliberately out of scope for a bounded "close the loop"
task): the ranker's tool-first-then-capability selection order in
`portal/platform/agent/decide.py`/`rank.py`. That module is
discipline-agnostic platform code shared by every future agent-loop consumer
(security is only the first), so changing its selection algorithm needs its
own design pass — a "prefer exploit-phase / oracle-bearing capabilities once
recon has already observed the relevant port" policy, or a no-repeat memory
of already-attempted (capability, target) pairs — rather than a
security-scoped patch. Until fixed, a live emergent run against a target
whose exploit-phase capabilities require ports already open in the first
perception pass will halt at I4 before ever attempting the exploit.
