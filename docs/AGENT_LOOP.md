# Agent Loop (platform core)

<!-- WIKI:GENERATED unit=unit-agent-loop-agent-loop-platform-core -->
`portal/platform/agent/` is the discipline-agnostic agent loop: a bounded,
grounded, writeback-capable engine that any module drives with its own action
space. It is **platform core** — always present, never a toggleable module.

- `goal.py` rejects execution without explicit scope and iteration, wall-clock,
  and lab-action budgets.
- `interfaces.py` defines structural capability-provider and executor contracts,
  keeping platform core independent of `portal.modules.*`.
- `decide.py` retrieves grounded candidates before choosing an action;
  `rank.py` supplies the deterministic tool and parameter fallback.
- `loop.py` enforces budgets, stop conditions, confidence gates, and honest
  blocked outcomes while folding each executor result into observations.
- `writeback.py` can propose a cited wiki unit, but never confirms or merges it.
- `tests/test_agent_core.py` exercises those contracts hermetically without a
  live pipeline or network.
<!-- /WIKI:GENERATED -->

---

## Shape

<!-- WIKI:GENERATED unit=unit-agent-loop-shape -->
```
goal --> [validate bounds] --> loop:
           decide (grounded)  ->  execute (module Executor)  ->  fold observations
             ^                                                      |
             +---------------- iterate until stop / budget ---------+
         record (optional)  ->  portal_wiki/proposed/  (CI gate: confirm/reject)
```
<!-- /WIKI:GENERATED -->

---

## Contracts (the "key" modules implement)

<!-- WIKI:GENERATED unit=unit-agent-loop-contracts-the-key-modules-implement -->
- `CapabilityProvider.query(observations, *, domain, goal, limit)` — grounds the
  decide-turn. The loop chooses only from returned candidates; never free-form.
- `Executor.execute(decision, state) -> {observation_delta, oracle_result, raw}`
  — performs one action, returns what changed. Errors ride in the return.
- `Capability` is structural (`.id`, `.tools`) — modules keep their own type.
<!-- /WIKI:GENERATED -->

---

## Discipline (borrowed from the Campaign Supervisor)

<!-- WIKI:GENERATED unit=unit-agent-loop-discipline-borrowed-from-the-campaign-supervisor -->
Caps (`max_iterations`, `max_wall_clock_sec`), a confidence floor
(`flag_for_human` below it), a clean `blocked` stop when nothing is applicable,
and honest outcomes (`completed` / `blocked` / `budget_exhausted` /
`flagged_for_human` / `invalid_goal`) — never faked-green.
<!-- /WIKI:GENERATED -->

---

## Record path (writing enabled, CI-gated)

<!-- WIKI:GENERATED unit=unit-agent-loop-record-path-writing-enabled-ci-gated -->
`agent.writeback.record_outcome(...)` proposes a cited unit into
`portal_wiki/proposed/` via `portal.platform.wiki.writeback.propose_unit`.
Promotion is the gate: `confirm_unit` / `reject_unit`. Nothing auto-merges.
<!-- /WIKI:GENERATED -->

---

## Operator surface

<!-- WIKI:GENERATED unit=unit-agent-loop-operator-surface -->
- `portal agent explain <goal.yaml>` — one dry decide-turn.
- `portal agent proposed [--status ...]` — list pending writebacks (gate view).
<!-- /WIKI:GENERATED -->

---

## Consumers

<!-- WIKI:GENERATED unit=unit-agent-loop-consumers -->
Security is the first consumer: `security.core.goal` / `decision_engine` /
`goal_decide` re-home onto this core while keeping their public symbols. Other
modules (compliance, research, coding) implement `CapabilityProvider` +
`Executor` to unlock the loop. Full-loop runtime wiring + MCP/OWUI entry are
slices 2-3 (see `coding_task/TASK_AGENT_LOOP_PLATFORM_V1.md`).
<!-- /WIKI:GENERATED -->

---
