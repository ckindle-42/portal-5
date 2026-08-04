# Agent Loop (platform core)

<!-- WIKI:GENERATED unit=unit-agent-loop-agent-loop-platform-core -->
`portal/platform/agent/` is the discipline-agnostic agent loop: a bounded,
grounded, writeback-capable engine that any module drives with its own action
space. It is **platform core** — always present, never a toggleable module;
validate check `AO` imports the package and enforces the inversion guard that
no file under it may import `portal.modules.*`.

- `goal.py` rejects execution without explicit scope (`scope.targets`) and
  iteration, wall-clock, and lab-action budgets (`max_iterations`,
  `max_wall_clock_sec`, `max_lab_actions`).
- `interfaces.py` defines structural capability-provider and executor contracts,
  keeping platform core independent of `portal.modules.*`.
- `decide.py` retrieves grounded candidates before choosing an action;
  `rank.py` supplies the deterministic tool and parameter fallback.
- `loop.py` enforces budgets, stop conditions, confidence gates, and honest
  blocked outcomes while folding each executor result into observations.
- `writeback.py` can propose a cited wiki unit, but never confirms or merges it.
- `tests/test_agent_core.py` exercises those contracts hermetically without a
  live pipeline or network.

## Why

The loop is extracted to platform core so modules never reimplement
goal/decide/rank mechanics and never couple the engine to any module's
capability model. Keeping the package free of `portal.modules.*` imports is
what makes a single engine safe for every module at once — each module
implements the structural contracts and plugs in, which is exactly the
dependency-inversion relationship the AO guard exists to protect.
<!-- /WIKI:GENERATED -->

---

## Shape

<!-- WIKI:GENERATED unit=unit-agent-loop-shape -->
The loop's shape is a single bounded engine over a module's contracts:

```
goal --> [validate_goal bounds] --> loop:
           decide (grounded via provider.query)  ->  execute (module Executor)
             ^                                         ->  fold observation_delta
             +----------- iterate until stop_when / budget -----------+
         record (optional, via record_outcome)  ->  portal_wiki/proposed/
             (CI gate: confirm_unit / reject_unit)
```

`run_loop` validates the goal first (`invalid_goal` short-circuits), then
cycles decide → execute → fold until `stop_when` is satisfied, a budget is
exhausted, or the loop blocks or flags for a human. `record_outcome` is
optional and runs outside the iteration body, so writing never affects the
loop's trajectory.

## Why

The shape is a pipeline with the fold-back arrow exactly where it is because
the loop is event-driven: each executor result becomes the next decide-turn's
observations, and stop/budget conditions are checked after each fold. Keeping
record outside the body means a wiki write can never change what the loop does
next — learning is a side channel, not control flow.
<!-- /WIKI:GENERATED -->

---

## Contracts (the "key" modules implement)

<!-- WIKI:GENERATED unit=unit-agent-loop-contracts-the-key-modules-implement -->
The `interfaces.py` protocols are the contracts every module implements to
unlock the loop:

- `CapabilityProvider.query(observations, *, domain, goal, limit)` grounds the
  decide-turn: `decide.py` calls it to retrieve real candidates, narrowed by
  goal intent first, and the loop chooses only from what it returns — never
  free-form. An empty result stops the loop with `blocked`.
- `Executor.execute(decision, state)` performs one action and returns
  `{"observation_delta", "oracle_result", "raw"}`. Errors ride in the return,
  not exceptions, so the loop can score a failed step instead of crashing.
- `Capability` is structural (`.id`, `.tools`) — modules keep their own rich
  type and still satisfy the engine.

## Why

The contracts are deliberately small and duck-typed so no module pays a
coupling cost to join the loop. Security's `Capability` already carries
`oracle` and `phase`; the protocol only requires `id` and `tools`, letting the
engine reason over candidates without knowing security internals. Returning
errors in-band keeps a failed action a scored observation rather than a crash,
which is what lets the loop report honest outcomes instead of dying mid-run.
<!-- /WIKI:GENERATED -->

---

## Discipline (borrowed from the Campaign Supervisor)

<!-- WIKI:GENERATED unit=unit-agent-loop-discipline-borrowed-from-the-campaign-supervisor -->
`run_loop` enforces the Campaign-Supervisor discipline:

- Caps: `max_iterations` and `max_wall_clock_sec` from `goal.budget` bound the
  loop; exceeding either ends with `budget_exhausted`.
- A confidence floor: `run_loop(confidence_floor=...)` — any decision below the
  floor ends with `flagged_for_human` rather than guessing.
- A clean `blocked` stop: when `decide.py` finds no applicable capability the
  loop stops immediately — nothing grounded to try is a stop, not a flail.
- Honest outcomes, never faked-green: `LoopResult.outcome` is one of
  `completed` / `blocked` / `budget_exhausted` / `flagged_for_human` /
  `invalid_goal`, and an invalid goal short-circuits before any iteration.

## Why

The discipline matters because the loop's whole value is that a module can
point it at a goal and trust the verdict. If low-confidence guesses ran anyway,
or an ungrounded decide turn invented actions, "completed" would be meaningless
for an engagement or a code change. Budgets and the confidence floor are the
backstops that keep bounded execution honest, and the explicit invalid-goal
exit surfaces a bad spec instead of burning its budget on nothing.
<!-- /WIKI:GENERATED -->

---

## Record path (writing enabled, CI-gated)

<!-- WIKI:GENERATED unit=unit-agent-loop-record-path-writing-enabled-ci-gated -->
`agent.writeback.record_outcome(...)` is the loop's write path: it distills an
outcome into a cited unit and proposes it via
`portal.platform.wiki.writeback.propose_unit`, landing in
`portal_wiki/proposed/` with status `proposed`. Promotion is the gate —
`confirm_unit` / `reject_unit` in the same module decide whether a proposal
reaches canon. Nothing the agent loop proposes auto-merges:
`record_outcome` never passes `auto_confirm`, and a failed writeback returns
`None` rather than blocking the loop.

## Why

The record path is separated from the loop so that learning is confirm-gated
and provenance-required. A loop that could write straight into the canonical
wiki would certify its own outcomes; staging proposals first means every unit
passes through a human gate, and the `sources` requirement in `propose_unit`
forces a loop to cite real evidence before its learning can be recorded.
<!-- /WIKI:GENERATED -->

---

## Operator surface

<!-- WIKI:GENERATED unit=unit-agent-loop-operator-surface -->
The `portal agent` CLI (`portal/platform/inference/cli/agent.py`) is the
operator surface for the loop:

- `portal agent explain <goal.yaml>` — one dry decide-turn: loads the goal
  spec, validates it, and reports a missing module `provider` rather than
  faking a decide-turn.
- `portal agent proposed [--status ...]` — lists pending loop writebacks via
  `wiki.writeback.list_proposed`; this is the CI-gate view over `proposed` /
  `confirmed` / `rejected`.

There is intentionally no `run` command that fakes an engagement: a full loop
needs a module-supplied `provider` and `executor`, so `explain` is the honest
dry-run surface until slice-2 wiring lands.

## Why

The operator surface exists so a human can inspect what the loop would do
without letting it act. `explain` proves a goal spec is valid and shows the
grounding requirement, while `proposed` exposes the confirm/reject gate — the
only way a loop's learning reaches the canonical wiki. Both commands are
read-only, keeping operator power bounded until a module actually wires a live
executor.
<!-- /WIKI:GENERATED -->

---

## Consumers

<!-- WIKI:GENERATED unit=unit-agent-loop-consumers -->
Security is the only live consumer: `security.core.goal` / `decision_engine`
/ `goal_decide` re-home onto this core while keeping their public symbols —
`EngagementGoal` subclasses the platform `Goal`, `decision_engine` re-exports
the `rank` functions, and `goal_decide` delegates its decide-turn to
`portal.platform.agent.decide`.

Security also supplies the two concrete contract implementations: the
`_SecurityCapabilityProvider` adapter (wraps `capability.query`) and
`SecurityExecutor`, which implements the platform `Executor` over
`lab.lab_dispatch` + `oracles.verify_finding`. `objective_entry.py` wires the
platform `run_loop` live against the lab behind `PORTAL_EMERGENT`.

No other module implements the contracts yet. Generalizing beyond security is
named follow-on work: re-homing security's orchestration onto `run_loop` and
standing up the `portal-agent` MCP server plus OWUI entry remain open slices
of the `portal/platform/agent/` surface.

## Why

Security was the proving ground because it already owned the pieces a loop
needs — a capability index, a decision engine, and a lab — so re-homing it
first validated the platform contracts without any module-coupling risk. The
security shims stay byte-compatible so the existing suite and CLI never notice
the engine moved. Other modules are deliberately not claimed as consumers
until they actually implement the contracts; a roadmap is not an implementation.
<!-- /WIKI:GENERATED -->

---
