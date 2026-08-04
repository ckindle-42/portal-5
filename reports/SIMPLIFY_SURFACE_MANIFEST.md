# SIMPLIFY_SURFACE_MANIFEST — TASK_PORTAL_SIMPLIFY_V1 R1

**Generated:** live reads at `bd59d4b9` + session start (`02c6e8b2`).
**Input:** `python3 scripts/spine_census.py --surfaces` (36 proposed groups), 8 parallel reader agents over all 571 member units, verified against the coverage machinery (`portal/platform/wiki/coverage.py`), the archive machinery (`archive.py::verify_superseded`), and the spine-intent families (`unit-router-*`, `unit-inference-*`, `unit-sec-core-*`).

## Design principle

One surface per directory **except** where the directory is genuinely one contract with the rest of the tree, or genuinely several. The three largest groups (`security/tests` 80, `tests/unit` 72, `security/core` 47) each become **one** surface: the readers confirmed all members share the same house template ("Unit tests for the security module's X surface" + identical Interfaces/Gotchas), so the only real content is the `## Why` paragraph, which the surface absorbs as a per-family section. Splits were kept to cases where a *directory* (not just a filename prefix) holds distinct contracts — e.g. `tests/` + `tests/lib` merge into one harness surface; `notifications/` + `channels/` merge.

Members carrying a decision that does **not** generalize stay live (left out of the archive group). These are named per surface below.

## The surface plan

| # | Surface unit | Glob(s) | Archives | Words retired | Stays live |
|---|---|---|---|---|---|
| 1 | `unit-surface-sec-tests` | `portal/modules/security/tests/*.py` | 79 | 8,687 | `unit-sec-tests-test_security_mcp` (security MCP server is an independent Rule-3 service; its contract belongs to the MCP surface, not the bench test suite) |
| 2 | `unit-surface-sec-core` | `portal/modules/security/core/*.py` | 44 | 6,232 | `unit-sec-core-decision_engine` (promoted-to-`agent.rank` shim contract), `unit-sec-core-cloud_bench` (no-cloud anti-regression), `unit-sec-core-cred_bench` (folded-into-pentest placement decision) |
| 3 | `unit-surface-tests-unit` | `tests/unit/*.py` | 71 | 7,109 | `unit-tests-unit-test-wiki-search-ranking` (not a mirror — 2 sources), `unit-tests-unit-test-security-corpus-contract` (one specific YAML file's contract) |
| 4 | `unit-surface-tests-harness` | `tests/*.py`, `tests/lib/*.py` | 19 | 2,742 | `unit-tests-frontends-namespace` (OWUI-only GUI decision), `unit-tests-integration-wiki-cycle` (seam knowledge), `unit-tests-memory-guard` (relocation compat shim) |
| 5 | `unit-surface-uat-catalog` | `tests/uat_catalog/*.py` | 36 | 4,960 | — |
| 6 | `unit-surface-acceptance` | `tests/acceptance/*.py` | 31 | 3,234 | `unit-acceptance-runner` (canonical S-order sequencing contract) |
| 7 | `unit-surface-uat` | `tests/uat/*.py` | 11 | 994 | `unit-uat-init` (module-map contract), `unit-uat-config`, `unit-uat-state`, `unit-uat-results`, `unit-uat-health`, `unit-uat-owui_api`, `unit-uat-lifecycle` (attribute-form monkeypatch / co-location / cycle-break rules — the densest authored contracts in any group) |
| 8 | `unit-surface-comfyui-tests` | `tests/comfyui/*.py` | 15 | 1,586 | `unit-comfyui-common` (Apple-Silicon unified-memory eviction contract) |
| 9 | `unit-surface-scripts` | `scripts/*.py` | 29 | 3,681 | `unit-scripts-spine_census` (the census tool's own contract), `unit-scripts-embedding-server`, `unit-scripts-mlx-speech`, `unit-scripts-mlx-transcribe`, `unit-scripts-openwebui_init`, `unit-scripts-portal5-powermetrics`, `unit-scripts-alias_census` (hardware/port/surface-specific servers and bespoke transports) |
| 10 | `unit-surface-scripts-lib` | `scripts/lib/*.py`, `scripts/lib/backup.sh`, `scripts/lib/services.sh` | 12 | 1,619 | — |
| 11 | `unit-surface-scripts-ci` | `scripts/ci/*.py` | 3 | 612 | — (C1 Step B deletes these scripts; the surface glob keeps BR green through the deletion) |
| 12 | `unit-surface-archive-mlx` | `scripts/_archive/mlx-retired-3a0c58e/*.py` | 9 | 1,567 | — (one archival contract: the retired dual-stack inference tier) |
| 13 | `unit-surface-tests-scripts` | `tests/scripts/*.py` | 3 | 724 | `unit-tests-scripts-regen-section-table` (marker-delimited regenerator, welded to the V6 driver) |
| 14 | `unit-surface-persona-matrix` | `portal/modules/eval/persona_matrix/*.py` | 7 | 1,111 | — |
| 15 | `unit-surface-media-tools` | `portal/modules/media/tools/*.py` | 1 | 198 | `unit-fish-speech-setup-model-download*` (hardcoded `models/fish_speech/…` path contract), `unit-media-tools-torch-device` (shared MPS→CUDA→CPU helper) |
| 16 | `unit-surface-siem` | `portal/modules/security/core/siem/*.py` | 6 | 1,137 | — |
| 17 | `unit-surface-investigation` | `portal/modules/security/core/investigation/*.py` | 4 | 849 | — |
| 18 | `unit-surface-security-eval` | `portal/modules/security/eval/*.py` | 3 | 667 | — |
| 19 | `unit-surface-inference` | `portal/platform/inference/*.py` | 7 | 1,392 | `unit-inference-router-pipe` (OWUI manifest pins the literal import path — genuinely file-pinned) |
| 20 | `unit-surface-inference-cli` | `portal/platform/inference/cli/*.py` | 13 | 1,810 | — (resolves the `agent.py` double-coverage duplicate) |
| 21 | `unit-surface-router` | `portal/platform/inference/router/*.py` | 18 | 2,986 | `unit-router-streaming` (FX1 live-smoke mandate, CLAUDE.md-referenced), `unit-performance-llm-router-warmup-at-startup` (Ollama version sharp edge) |
| 22 | `unit-surface-tool-preselect` | `portal/platform/inference/tool_preselect/*.py`, `…/tool_preselect/tests/*.py` | 13 | 2,287 | — |
| 23 | `unit-surface-wiki` | `portal/platform/wiki/*.py` | 6 | 1,208 | `unit-wiki-quality`, `unit-wiki-audit` (gate contracts), `unit-fact-doc-migration-coverage`, `unit-known-limitations-known-limitations`, `unit-readme-documentation` (rendered doc-block sources) |
| 24 | `unit-surface-wiki-adapters` | `portal/platform/wiki/adapters/*.py` | 11 | 1,731 | `unit-wiki-adapter-modules` (module-layer state source, 9 cross-refs), `unit-fact-media-memory-budget` (live derived fact consumed by code) |
| 25 | `unit-surface-portal-wiki` | `portal_wiki/*.py` | 4 | 875 | — |
| 26 | `unit-surface-notifications` | `portal/platform/inference/notifications/*.py`, `…/channels/*.py` | 10 | 1,531 | — |
| 27 | `unit-surface-mcp-host` | `portal/platform/mcp_host/*.py` | 6 | 1,210 | — |
| 28 | `unit-surface-benchmarks` | `tests/benchmarks/*.py`, `tests/benchmarks/bench/*.py` | 19 | 3,042 | `unit-bench-security` (import-path shim), `unit-bench-mlx-hf` (policy exception), `unit-bench-candidates-v10` (one batch record) |
| 29 | `unit-surface-toolpreselect-tests` | `tests/toolpreselect/*.py` | 3 | 658 | — |
| 30 | `unit-surface-deploy-portal5` | `deploy/portal-5/docker-compose.yml` | 2 | 295 | `unit-comfyui-setup-use-docker-comfyui-with-cuda-profile` (launch.sh profile-forwarding correction) |
| 31 | `unit-surface-root` | `launch.sh` | 3 | 623 | `unit-readme-license` (MIT fact), `unit-mcp-dev-tooling-opencode-integration-opencode-jsonc` (config-file contract) |

**Deferred (not in this program's archive set):** `config/` (31 mirrors, 5,465 words) — interacts with `sync_config` derivation and `portal.yaml` single-source-of-truth; needs its own boundaries. Its fact units (`unit-fact-model-catalog`, `unit-fact-mcp-fleet`, `unit-fact-workspace-roster`, `unit-fact-tool-authorizations`, `unit-fact-security-variants`) are natural anchors for a follow-up.

**Not touched:** all singleton mirror groups (<3 members: `portal_channels`, `tests/routing`, `tests/unit/router`, `portal/modules/security/core/commands`, `portal/platform/wiki/tests`, `tests/benchmarks/results`, `scripts/_archive`, `deploy/playwright-mcp`, the `portal/modules/*/config` and `portal/modules/{general,compliance,security}` singles, etc.) — 44 units stay live as-is; they are below consolidation threshold and mostly carry genuine decisions already.

## Totals

| Metric | Before | After |
|---|---|---|
| Canonical units | 1,129 | ~663 (1,129 − 498 archives + 32 surfaces) |
| Mirror units | 606 | 108 (77 stay-live + 31 deferred config) |
| Mirror words | ~86,193 | ~24,157 (19,015 stay-live + 5,142 deferred) |
| Words retired | — | **67,082** |

Glob coverage is confirmed by `_expand_glob` (e.g. `portal/modules/security/tests/*.py` → 87, `tests/unit/*.py` → 82). Every archived member's single cited path is covered by its surface's glob, so `verify_superseded` passes and `BR` stays green throughout. The `unit-sec-tests-test_security_mcp` stay-live is deliberate: the security MCP server is an independent service (Rule 3) and its test belongs to the MCP surface the `tool-registry` fact unit already anchors.
