# Portal Surface Collapse V1 — Results (2026-07-12)

Executed `STRATEGY_COLLAPSE_V1.md` / `DESIGN_COLLAPSE_V1.md` /
`BUILD_PROGRAM_COLLAPSE_V1.md` (M0 preflight through Phase 11 final gate) in one
session, directly following `TASK_AGENT_LOOP_PLATFORM_V1.md`. Tagged
`collapse-v1-complete`.

## Before / After

| Metric | Before | After | Delta |
|---|---|---|---|
| Workspaces declared in `config/portal.yaml` | 104 | 81 | −23 |
| Workspaces loaded at default boot (eval + non-eval disabled) | 104 | 21 | −83 |
| Personas (files in `config/personas/`) | 130 | 130 | 0 |
| Duplicate persona system prompts | 3 groups | 0 | −3 |
| Modules with a wiki `enabled:` field | 0/9 | 9/9 | +9 |
| Workspaces tagged `module:` | 0 | 81 | +81 |
| Personas tagged `module:` | 0 | 130 | +130 |
| MCP fleet entries tagged `module:` | 0 | 24 | +24 |
| `portal module` CLI | none | `list`/`status`/`enable`/`disable` (confirm-gated, `--yes`) | new |

**Personas note — deviation from the build program's own estimate.** Phase 11's
own spec projected personas dropping to ~89 (assuming file consolidation
alongside dedup). What Phases 8-10 actually implemented was a `prompt_template`
indirection: 27 bench personas that previously each carried an identical
verbatim system prompt now point at one of 3 shared template files
(`portal/modules/eval/persona_matrix/prompts/`) via a `prompt_template:` field,
plus a computed `preferred_models:` chain. This kills the *content* duplication
(3 duplicate-prompt groups → 0, the number the drift gate actually measures)
without deleting any persona file — each remains a distinct, individually
selectable Open WebUI model preset. No persona files were removed; 130 → 130 is
correct, not a shortfall.

## What moved where

- **Coding** (Phase 5): `auto-coding-agentic`, `auto-coding-uncensored(-agentic)`,
  `auto-agentic(-lite/-ornith)`, `auto-coding-northmini` (7 workspaces) folded
  into `auto-coding`'s `variants:` block — `laguna`, `uncensored`,
  `uncensored-agentic`, `heavy`, `lite`, `ornith`, `northmini`.
- **Security** (Phase 6): `auto-security-uncensored`, `auto-pentest`,
  `auto-blueteam`, `auto-redteam(-deep)`, `auto-purpleteam(-deep/-exec)` (8
  workspaces) folded into `auto-security`'s `variants:` block.
- **Deleted outright** (Phase 7, model-tied, no longer needed once `?model=`
  override + persona `preferred_models` chains exist): `auto-devstral`,
  `auto-mistral`, `auto-phi4`, `auto-glm`, `auto-glm-thinking`,
  `auto-gemma-e4b`, `auto-gemma-fast`, `auto-gemma-vision` (8 workspaces).
- All pre-collapse workspace ids above still resolve unchanged through
  `_resolve_legacy_workspace_alias()` in
  `portal/platform/inference/router/preinject.py` — the LLM/keyword classifier
  in `routing.py` (explicitly off-limits to edit, DESIGN §9) still emits these
  names, and any external script/doc/bench command using them keeps working.

## New mechanisms

- `_resolve_workspace_variant()` — merges a named `variants:` override onto a
  base workspace, caching the merged dict under a synthetic
  `f"{workspace_id}::{variant}"` key (idempotent; variant-name space is small
  and config-declared, so no growth risk).
- `_resolve_model_override()` — explicit `?model=` query param override, same
  caching pattern, bounded to `_known_backend_models()` (~150 ids declared
  across `config/backends.yaml`) to prevent unbounded key growth from
  arbitrary user input.
- `_WorkspaceCatalog(dict)` — filters synthetic `"::"` keys out of
  `WORKSPACES`'s iteration/`len()`/`keys()`/`items()`/`values()` so the merge
  mechanism's caching never pollutes code that enumerates "all real
  workspaces" (lifespan hint validation, `/metrics`, Rule 6 cross-checks).
- `get_workspace_dict()` now excludes workspaces belonging to *any* disabled
  module (not just `eval`) — closing a gap found live during Phase 9
  verification where `portal module disable media --yes` had no runtime
  effect on `WORKSPACES`.
- `portal.platform.inference.cli.module` — `list` (per-module
  workspace/persona/mcp counts), `status <name>` (detail view), `enable`/
  `disable` (confirm-gated wiki write-back, `--yes` to bypass + auto
  `sync-config`).

## Bugs found and fixed along the way

1. **`_resolve_persona_workspace()` `AttributeError`** — called
   `.get("workspace_model")` on a `PersonaSpec` pydantic instance instead of
   `.workspace_model`; confirmed live against the running pipeline
   (`POST /v1/chat/completions {"model":"adversarysimulator"}` → 500). Fixed
   and regression-tested independently of the collapse work (`c4b07b6`).
2. **`get_workspace_dict()` only gated `module: eval`** — every other module's
   `enabled:false` state was cosmetic (visible in `modules.generated.yaml` but
   had zero effect on the live `WORKSPACES` dict). Found and fixed in Phase 9
   (`fc29dec`).

## Verification (final gate)

```
python3 scripts/validate_system.py        # 43 pass / 0 fail / 1 warn / 0 skip
pytest tests/unit/ -q                     # 707 passed, 16 skipped, 1 xpassed
./scripts/smoke_stream.sh                 # PASS — 65 SSE chunks, [DONE] received
sync-config x2                            # byte-identical (idempotent)
```

One pre-existing, unrelated failure noted and left alone:
`tests/frontend/test_reasoning_display.py::test_pipeline_reasoning_response`
fails with `401 Invalid API key` — the test's docstring embeds a stale literal
`PIPELINE_API_KEY` example that no longer matches the current `.env`. This is
a live-integration test outside `tests/unit/` (the CI-gated suite, which is
100% green) and outside this task's scope.

## Commits

`214a16f` (Phase 8 part 2, preferred_models chain) → `fc29dec` (Phase 9,
CLI + general module gate) → `212e5ac` (Phase 10, doc reconciliation) → this
retrospective (Phase 11) → tag `collapse-v1-complete`.
