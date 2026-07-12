# tool_preselect — query-level tool-schema preselection

**Roadmap ID:** `P5-FUT-TOOL-PRESELECT`
**Status:** built, feature-flagged off by default. See
`docs/_archive_execdocs/` for the Phase 5 validation summary once it
lands; see `P5_ROADMAP.md` for the current enable/not-ready status.

## Problem

Tool-heavy workspaces (research/browser/RAG stacks, agentic security
workspaces with MCP fanout, code+web workspaces) ship 15-25+ tool
schemas to the primary model on every turn regardless of what the
user's query actually needs. This wastes prompt tokens on turns that
obviously only need 2-3 specific tools.

## Solution

A small, fast model (the "preselector") receives the user turn plus
the workspace's available tool schema summaries and emits a ranked
subset of the K most relevant tool names. Only those K tools' full
schemas are sent to the primary model.

`preselected ⊆ effective_tools` always. The dispatch-side whitelist
(`_dispatch_tool_call`) is unchanged and continues to protect against
out-of-set tool calls regardless of whether preselection ran.

## Integration point

```
request arrives
  -> workspace resolution                          (existing)
  -> persona resolution                            (existing)
  -> _resolve_persona_tools()  -> effective_tools   (existing)
  -> [NEW] preselect(effective_tools, user_turn, ...) -> preselected
  -> model dispatch with schemas for preselected
  -> _dispatch_tool_call(call, preselected, ...) validates whitelist
```

Wired in `portal/platform/inference/router/handlers.py`'s
`chat_completions`, immediately after
`effective_tools = _resolve_persona_tools(...)`.

## Fallback invariant

If the preselector fails, times out, produces low-confidence output,
or produces an empty set: `preselected = effective_tools`. This
guarantees no regression — worst case the feature is a no-op that
adds a few ms of latency. Every failure mode in the table below falls
back to full-tool-list behavior; none is user-visible.

| Failure | Detection | Behavior |
|---|---|---|
| Ollama call times out (>2s) | HTTP timeout | `fallback_timeout` |
| Unparseable output | Regex fail | `fallback_parse` |
| No valid tool numbers | Empty parse | `fallback_empty` |
| All numbers below confidence floor | Confidence check | `fallback_lowconf` |
| Primary requests tool not in preselected | dispatch-layer `tool_not_allowed` | metric increment, standard error path |
| Miss rate >5% over last 100 turns | runtime counter | auto-disable for that workspace |
| Ollama backend unavailable | connection error | `fallback_timeout` |

## Self-healing auto-disable

`state.py` tracks a per-workspace ring buffer of the last 100 outcomes.
If the miss rate (primary model asked for a filtered-out tool) exceeds
5%, the workspace is auto-disabled **in process memory only** — not
written to `config/portal.yaml`. A restart resets the flag. The
`portal5_toolpreselect_auto_disabled_total` metric is the durable
signal an operator reviews to decide whether to remove the workspace's
opt-in permanently.

## Configuration

```bash
PORTAL5_TOOL_PRESELECT=1                    # global on/off, default 0 (off)
PORTAL5_TOOL_PRESELECT_MODEL=hf.co/...      # default: see config.py DEFAULT_PRESELECT_MODEL
```

```yaml
# config/portal.yaml, per-workspace, opt-in required even when global flag is on:
some-workspace:
  tool_preselect:
    enabled: true          # opt-in
    k: 5                   # override the default K (see K selection below)
    confidence_floor: 0.6  # optional; below this, fall back
```

## K selection

- ≤5 tools total: feature bypassed entirely (no benefit possible).
- 6-15 tools: `K = 5` default.
- 16+ tools: `K = min(8, ceil(total * 0.4))`.

The preselector model emits an *ordered ranking*; the pipeline takes
top-K by rank (`K_plus_slack = K + 3` requested, to absorb a few
malformed lines without under-filling K). K is a pipeline-side
operational parameter, not something the model picks.

## Module layout

- `config.py` — env-var + per-workspace `tool_preselect:` resolution
- `preselector.py` — public `preselect()` interface + `PreselectOutcome`
- `prompts.py` — prompt template builder
- `parser.py` — resilient text-output parser (handles periods, parens,
  trailing tool names, comma/newline separators, preamble/postamble)
- `state.py` — per-workspace miss-rate ring buffer + auto-disable
- `metrics.py` — public `record_*` functions (collectors declared in
  `router/metrics.py`, the sole CollectorRegistry owner)

## Validation

`tests/benchmarks/tool_preselect/` — golden-set-based recall/precision
bench comparing the two candidate models, plus an A/B regression
runner. See that directory's own docs for how to run them and what the
success criteria are.

## Explicit non-scope

This module does not enable itself on any real workspace and does not
promote either candidate preselector model into Portal's general
fleet (`model_hint` catalog). Enabling on a specific workspace is a
follow-up rollout task made after reviewing the validation harness's
results.
