# Wiki Structure — Stable Authored Spine vs. Computed Volatile Facts

Authored units in `portal_wiki/canonical/` document durable architecture, interfaces, contracts, and rationale. Volatile runtime and config state (module enablement, counts, rosters, ports, configured model lists, seat tags) belongs exclusively in computed `unit-fact-*` units derived on demand by `portal/platform/wiki/adapters/seed_facts.py`.

## Pre-Migration Claim Census (`portal_wiki/canonical/`)

Measured at `63520cb9d` across all **627** canonical units (**667** declared claims across **25** probe types; **0** historical units; **0** empty-claim units):

### 1. Stable probes — 15 probe types, 561 claims (allowed on authored units)

| Probe | Claims | Units | Kind of fact |
|---|---:|---:|---|
| `repo.path.exists` | 405 | 404 | Committed path/glob exists in checkout |
| `repo.symbol.exists` | 110 | 110 | Symbol exists in committed source file |
| `retrieval.stages` | 7 | 3 | Stage modules under `portal/platform/retrieval/` |
| `retrieval.stage_set` | 6 | 2 | Stamped stage-set knobs in `rag_multimodal._stage_set()` |
| `compliance.register` | 6 | 3 | NERC CIP standard IDs in `nerc_cip_register.json` |
| `compliance.completeness` | 6 | 2 | Register completeness invariants (`completeness_holes:0`, `denominator_self_derived:False`, etc.) |
| `retrieval.compositions` | 4 | 3 | Modules constructing `pipeline.Composition(` |
| `compliance.store.tables` | 4 | 2 | DDL tables in `compliance/core/migrations/schema.py` |
| `compliance.change_types` | 3 | 1 | `CHANGE_TYPES` enum in `register_diff.py` |
| `compliance.cite_and_scope` | 3 | 1 | Quote/scope invariants in `citation_by_quote.py` & `document_scope.py` |
| `deps.locked` | 2 | 1 | Pinned dependencies in `uv.lock` (`torchvision`, `mlx-embeddings`) |
| `compliance.capture.unit_kinds` | 2 | 1 | `UNIT_KINDS` tuple in `capture.py` |
| `rag.retrieval.routes` | 1 | 1 | `/tools/kb_*` route ownership in `rag_multimodal.py` |
| `vl.embedding.dim` | 1 | 1 | `VL_EMBEDDING_DIM` code default in `scripts/vl-retrieval-server.py` |
| `orchestrate.rate_over_lifetime_counters` | 1 | 1 | Grafana dashboard invariant (no rate/increase on lifetime counters) |

### 2. Count-pinned contract probe — 1 probe type, 1 claim (fixed to invariant)

| Probe | Claims | Units | Defect & resolution |
|---|---:|---:|---|
| `compliance.workspace_tools` | 1 | 1 | Returned `all_reachable:30` (pinning volatile tool count `:30`, while unit body still stated `36`). Changed probe to emit `all_reachable` so wiring across `portal.yaml`, manifest, and `_DISPATCH` is verified without pinning count. |

### 3. Volatile probes — 9 probe types used in `canonical/`, 105 claims (moved out of authored units)

| Probe | Claims | Units | Config owner / Computed alternative |
|---|---:|---:|---|
| `models.configured` | 56 | 56 | `config/*.yaml` model rosters → `unit-fact-model-catalog` |
| `modules.enabled` | 25 | 25 | `config/portal.yaml` `modules.*.enabled` → `unit-fact-module-states` |
| `mcp.fleet.ids` | 17 | 17 | `config/portal.yaml` `mcp_fleet` → `unit-fact-mcp-fleet` |
| `modules.disabled` | 2 | 2 | `config/portal.yaml` `modules.*.enabled` → `unit-fact-module-states` |
| `mcp.fleet.ports` | 1 | 1 | `config/portal.yaml` `mcp_fleet` → `unit-fact-mcp-fleet` |
| `workspaces.exposed` | 1 | 1 | `config/portal.yaml` `workspaces.*.expose_to_owui` → `unit-fact-workspace-roster` |
| `workspaces.bench` | 1 | 1 | `config/bench_workspaces.yaml` count → `unit-fact-workspace-roster` |
| `mcpjson.servers` | 1 | 1 | `.mcp.json` server count → `unit-fact-mcp-fleet` |
| `compliance.served_window.tag_window` | 1 | 1 | `config/portal.yaml` `auto-compliance.variants.reading.model_hint` → `unit-fact-workspace-roster` / `unit-fact-model-bindings` |

Additional registered volatile probes (18 total, used in `seed_facts.py` or unreferenced in `canonical/`): `workspaces.total`, `workspaces.functional`, `modules.enabled.count`, `modules.total`, `mcp.fleet.entries`, `personas.count`, `validate.checks`, `wiki.canonical.units`, `wiki.tier1.docs`, `wiki.generated.blocks`, `backends.groups`, `backends.groups.count`, `backends.ids`, `backends.types`, `launch.commands`, `env.vars`, `config.files`, `dockerfiles`.

### 4. Hardcoded volatile prose in `canonical/` before migration

- **21 units** hardcoded module enable state in titles or prose (`off by default`, `ships disabled`, `modules.<name>.enabled: true|false`, `enabled in repo`, `module off`).
- **2 units** hardcoded volatile platform counts in prose (`currently 22 workspaces`, `currently 30 MCP servers`; `unit-known-limitations-compliance-engine-had-no-route` also stated stale `36 reachable compliance/register tools`).

## Structural Rules (Enforced by `BS`, `GS`, `quality`, and `store.save_unit`)

1. **Volatile facts live only in computed `unit-fact-*` units.**
   `unit-fact-module-states` (module enablement, default posture, gated workspaces/MCPs) and `unit-fact-mcp-fleet` (including `.mcp.json` IDE server count) join `unit-fact-workspace-roster`, `unit-fact-model-catalog`, `unit-fact-model-bindings`, `unit-fact-persona-roster`, and `unit-readme-capability-rollup`. Authored units reference them by ID instead of restating counts, rosters, or enable states.
2. **Authored `claims:` allow stable probes only.**
   `portal/platform/wiki/claims.py` (`STABLE_PROBES`) restricts authored claims to the 16 stable probes above. Both `store.save_unit()` and `BS` (`check_spine_drift`) reject any volatile probe on an authored unit with an error naming the computed `unit-fact-*` alternative.
3. **Hardcoded volatile counts and module enable states in authored prose are a `BS` HARD FAIL.**
   `drift.volatile_prose_violations` scans every non-historical authored unit (title and unfenced body, regardless of whether `claims:` is empty or populated) and fails `BS` if a countable platform figure or module enable-state assertion appears.
4. **"Claims required" means invariant claims are checked, never forced.**
   Narrative, how-to, `why`, module, and model-catalog units with no stable executable invariant declare `claims: []`. They are governed by mandatory `sources:` (`AJ` `audit_units`), `quality.assess` (`BR`/`GR`), and `BS` (zero volatile claims, zero volatile prose, zero dead doc refs), without forcing synthetic `repo.path.exists` or volatile stubs.
5. **Post-migration state.**
   All 105 volatile authored claims removed; `compliance.workspace_tools` migrated to invariant `all_reachable` (562 stable claims remain across the canonical store); hardcoded volatile prose replaced with `unit-fact-*` references across all 22 affected units.
