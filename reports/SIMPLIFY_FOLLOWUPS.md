# SIMPLIFY_FOLLOWUPS — deferred items, TASK_PORTAL_SIMPLIFY_V1

## Impure data literals (need a resolver, out of C2 scope)

These module-level literals contain Call/Name/Lambda/Attribute/comprehension
nodes and cannot be extracted with the JSON-dump equality proof. They need a
resolver (e.g. a build step that evaluates then serializes, or refactoring the
references out).

- `portal/modules/security/core/exec_chain.py`: SCENARIOS (~1,980L), _MISSION_SCENARIOS (~154L)
- `tests/uat_catalog/g_benchmark.py`: TESTS (~1,591L, references _CC01/_GC assertions)
- `portal/modules/security/core/capture_recipes.py`: CAPTURE_RECIPES (~878L, Call+Name)
- `portal/modules/security/core/ability_port.py`: PROBE_DEFS (~322L, Name)
- `tests/uat_catalog/g_auto*.py` (impure set): g_auto, g_auto_daily, g_auto_pentest, g_auto_purpleteam, g_auto_purpleteam_deep, g_auto_redteam, g_auto_redteam_deep (TESTS reference REFUSAL_PHRASES)
- `portal/modules/security/core/investigation/bench_investigation.py`: ADVERSARIAL_SCENARIOS (~63L)
- `portal/modules/security/core/council_review_bench.py`: TASKS (~50L)
- `portal/modules/media/tools/video_mcp.py`: _WAN22_*_WORKFLOW family (~9 literals, Name/Attribute)
- `portal/platform/inference/router/routing.py`: _WORKSPACE_ROUTING, _SECURITY_VARIANT_SIGNALS
- `portal/modules/security/core/blue_orchestrate.py`: _FREETEXT_STOPWORDS

## Untouched security-engine god functions (deliberately out of scope, per §7)

`exec_chain.py`, `blue.py`, `blue_orchestrate.py` internals — 4,539 combined god
lines in the live security bench engine. C7's ratchet holds them; a dedicated
task follows.

## Deferred config/ mirror units

31 config/ mirror units were deferred in R2 (interact with sync_config
derivation and portal.yaml single-source-of-truth). Their fact units
(unit-fact-model-catalog, unit-fact-mcp-fleet, unit-fact-workspace-roster,
unit-fact-tool-authorizations, unit-fact-security-variants) are natural anchors
for a follow-up regrain.

## Ruff complexity debt

**82 files** recorded in `pyproject.toml` `[tool.ruff.lint.per-file-ignores]` under the C90/PLR0912/PLR0915 block, dated 2026-08-05. Entries may only be **removed** (as a file is refactored below the complexity threshold), never added. The largest debt clusters: the security engine (`exec_chain.py`, `blue.py`, `blue_orchestrate.py` — deliberately out of scope per §7), the MCP tool servers, and `tests/uat/*`.

## C5.4 (deferred)

The 21 over-budget check bodies in `scripts/validation/` were moved verbatim (not decomposed). They now live in the family modules; C7's ratchet holds them. A follow-up can decompose them like C3/C4.

