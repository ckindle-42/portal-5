# FINDING — `auto-general-uncensored::creative` route (2026-11-20)

Lane: `lane/uncensored-creative-route`. Source brief:
`BRIEF_UNCENSORED_CREATIVE_UNRESOLVED.md`. No live probe was run here (worker
contract §0); the resolution trace below is from config + router code, and the
live command is in the report's ORCHESTRATOR RUNS block.

## What the roster actually reported

`scripts/speed_gate.py::resolve_seats` resolves a seat only through
`omlx_catalog()`, which discards every backend whose `type` is not `omlx`
(`speed_gate.py:168-178`). `resolved? False` therefore means **"no oMLX model in
the routed group"**, not "no backend in the routed group". The full catalog
(both engines) is what a live request uses.

## What a live request resolved to before this fix

`model: auto-creative` → alias `auto-creative: to: auto-general-uncensored::creative`
(`config/portal.yaml:719-722`) → `_resolve_workspace_variant` merges the variant
onto the base and caches a synthetic `WORKSPACES` id (`router/preinject.py:108-150`).

- `get_backend_candidates("auto-general-uncensored::creative")` uses the base's
  routing (`general`), then `fallback_group: general`, then every remaining
  healthy backend as the tier-3 net (`cluster_backends.py:479-550`).
- Streaming promotes the first candidate whose `resolve_model(hint)` is not
  `None` (`router/streaming.py:2764-2786`); non-streaming skips candidates that
  cannot serve the hint (`router/non_streaming.py:1047-1060`).
- The literal hint `fredrezones55/Qwen3.6-35B-A3B-Uncensored-HauhauCS-Aggressive:Q4-ctx8k`
  was already listed on **`ollama-general`**, a `general`-group backend
  (`config/backends.yaml:167`), so the happy path served the declared model on
  Ollama — no substitution, no fall-through. If that backend were unhealthy,
  tier 3 reaches `ollama-creative` (literal tag) or `omlx-creative` (alias),
  which serve the same checkpoint.

So the production serving path was correct; the defect was the **oMLX shadow
coverage** the roster exists to measure.

## Root cause

- `61369a088` added `omlx-creative` as the priority-10 oMLX shadow of
  `auto-creative` (which then routed `creative, general`), with the rule "no
  workspace_routing change".
- `adafe9c35` folded `auto-creative` into `auto-general-uncensored::creative`
  and dropped the `creative, general` routing entry. The variant hints were
  registered on `ollama-general`, but the oMLX conversion
  `Qwen3.6-35B-A3B-HauhauCS-Aggressive-4bit` stayed only in
  `omlx-security`/`omlx-creative`. The general group's oMLX shadow could not
  serve the seat, so `resolve_seats` dropped it.

## Fix

Registered the existing conversion and its GGUF-twin alias on `omlx-general`
(the general group's priority-10 shadow) in the operator-edited `backends:`
block of `config/backends.yaml`. No `workspace_routing` edit (rule 6 — that is
the one derived block in the file, and `sync_config` preserves it), no variant
repoint: the same checkpoint now resolves on the group the workspace routes to.

## Offender census (full catalog: model id or alias on any backend in the routed groups)

99 seats (portal workspaces + variants + bench workspaces): **0 offenders**
before and after. A variant hint that is only in an unreachable group would be
caught by `tests/unit/test_variant_hints_resolve_in_routing.py`.

Under the speed gate's oMLX-only view: **40 before → 39 after**. The remaining
39 are Ollama-only seats by design (GGUF tags with no MLX conversion or no
alias in their routed group: `auto-general-uncensored` base + throwaway
variants, `auto-daily`/`::nemotron`, the `portal5/*` coding alternates,
security/reasoning/vision variants, `task-router`, …). Aliasing those to MLX
without conversion + A/B evidence would be a seat decision, not a routing fix.

## Live check

See the report's ORCHESTRATOR RUNS block: one curl through `:9099` with
`model=auto-general-uncensored::creative`, reading `x-portal-route`. Before the
fix the third field is the literal GGUF tag on `ollama-general`; after the fix
it should be `Qwen3.6-35B-A3B-HauhauCS-Aggressive-4bit` on `omlx-general`.
