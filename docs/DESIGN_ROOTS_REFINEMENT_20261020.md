# Design: back to roots — refine Portal 5 in place (draft, 2026-10-20)

**Status:** approved 2026-10-20 (operator: execute end to end, then resume WFE with a one-shot on everything enabled). Revision 3: all open decisions resolved. Supersedes the plan sections of
`docs/DESIGN_ENGINES_AND_PROMPTS_20261019.md`. That doc's Appendices A–D stay the data reference,
with one correction to Appendix D (§C9 below). Nothing changes until this is approved.

**Breaker:** on hold. Nothing here depends on it. The parts of the Breaker work that apply to
Portal as it stands (the defect fixes and the plug-in seam) are carried in as Workstream A.

## Intent

> "Portal itself is basic in the router and modules. That is the product at its foundation.
> Improving or adding capabilities is on brand." — operator, 2026-10-19

> Keep the product as is, go back to roots, refine and clean up, and stop the wiki churn.
> — operator, 2026-10-20

The router and the modules are the product. This work removes no capability. It does three
things:

1. Fixes what is broken in the foundation.
2. Stops the governance layer from generating more change than the product does.
3. Gives the user a small, stable front door: engines, variants and roles.

## What the repository shows (measured at `bd4b7a5b`, last 30 days)

**The product is a small share of what changes.**
- 825 commits in 30 days.
- Lines changed by area:

| Area | Lines changed |
|---|---|
| `reports/` (run artifacts) | 5.19M |
| `tests/wfe` | 99K |
| `tests/benchmarks` | 97K |
| `docs/` | 59K |
| `scripts/` | 54K |
| `portal/modules` + `portal/platform` (the product) | 48K |

**Governance churn.**
- 175 commits touched `portal_wiki/`, for 1,256 file touches.
- 45 commits were `chore(complexity)` budget re-stamps.
- `config/spine_surfaces.yaml` changed in 76 commits.
- 348 commits touched Markdown.

**One model swap fans out to 5–9 files.** Example: `19fc3ccc` (auto-reasoning → K2-Horizon) has
one real change, `config/portal.yaml`. It also edits:
- two wiki fact units: `unit-fact-model-bindings`, `unit-fact-workspace-roster`;
- the generated table in `docs/ADMIN_GUIDE.md`;
- the router baseline (`tests/routing/baseline.json`);
- two tests that pinned the previous model's name (`test_pipeline.py`,
  `test_wfe_reasoning_hard_slice.py`).

**What drives the churn.**
- 419 code files are each bound to one of 124 wiki units by `spine_surfaces.yaml`, and the
  coverage and drift gates enforce those bindings.
- Fact units regenerate from config on every `sync-config`.
- Generated doc blocks are checked against the units.
- The complexity budget is a ratchet that gets re-stamped after nearly every feature.

**Runtime state lives in the wiki.** Whether a module is enabled is read from the fenced
`enabled:` block in `portal_wiki/canonical/unit-module-<name>.md`
(`portal/platform/wiki/adapters/modules.py`). Turning a module on or off is therefore a wiki
write.

**The surface regrows after it is collapsed.** Production workspaces (excluding bench):

| Date | Production workspaces | Personas |
|---|---|---|
| 2026-07-01 | 44 | — |
| 2026-07-20 (after the July collapse) | 22 | — |
| 2026-09-15 | 25 | — |
| 2026-10-19 | 35 | 112 (has ranged 112–138; never consolidated) |

The July collapse also built an alias shim and retired it (`RESULTS_ALIAS_RETIRE_V1_20260713`).
The 10-19 doc proposes aliases again.

**Evidence in git.**
- `reports/` is 97 MB across 513 tracked files.
- Root docs total about 4,300 lines, including `KNOWN_LIMITATIONS.md` at 1,741 lines.
- `portal_wiki/archive/` holds 883 units.

## Requirements

### R1 Capability is preserved
No module capability, tool or engine behaviour is removed by this work. Every merge passes the
10-19 doc's preserve-don't-flatten rules: a differing field survives as a variant field, a tool
route, or module gating, and is never silently dropped.

### R2 Config is the runtime truth; the wiki is derived
Nothing the pipeline reads at runtime lives in `portal_wiki/`. The wiki documents config and
code; it is never their source.

### R3 A product change touches the product
A model swap, a sampling change or a new tool on an existing engine changes only:
- `config/portal.yaml`;
- the runtime artifacts `sync-config` derives from it (`backends.yaml` routing, `.mcp.json`,
  the Open WebUI presets);
- the evidence that decided it.

No wiki file, no prose doc and no budget file changes as a side effect.

The routing regression check (AU) today records the *served model* per prompt in
`tests/routing/baseline.json`, so every model swap edits it. Resolution: AU asserts the routing
decision (base workspace and variant); the served model per lane is verified by the serving
conformance audit, which already reads config live. A swap then leaves the baseline unchanged.

### R4 Gates verify; they do not ratchet
A gate passes or fails on the current tree. No gate requires a follow-up commit whose only
purpose is to record the new state (re-stamps, manifest regeneration, ledger bumps).

### R5 Run evidence stays outside git
Raw run output (reports, traces, receipts, bench results) lives under a data root outside the
checkout. Curated outcome summaries are the only evidence committed.

### R6 What CI calls green is green
- CI runs every test in the repo.
- CI type-checks the code the local gate claims to type-check.
- No test writes to tracked or live state.

### R7 The front door stays small
- Users see engines and roles.
- Variants, internal seats and bench lanes are not user-facing.
- Growth is guarded so the surface cannot regrow unnoticed (Workstream C, §C3).

### R8 Tests assert contracts, not current choices
No test pins a model name, a count, or the incumbent of a seat. WFE decides seats; tests check
the lane's properties (thinking on, window, tools, gating).

## Workstream A — fix the foundation (no behaviour change)

Each item was found in Portal's own code; each ships with a test that would have caught it.

| # | Item | Done when |
|---|---|---|
| A1 | Strict typing. `router/trace.py` defines `_int` twice (the environment reader is shadowed by the value parser). The Oct 17–19 router commits (trace, council, power, non_streaming, handlers, model_cards) left strict mypy errors. | `scripts/ci_local.sh` type step passes; the env helper is renamed. |
| A2 | CI collects all tests. `.github/workflows/unit-tests.yml` runs only `tests/unit` and the security tree, so `portal/platform/**/tests` (122 tests) and `tests/wfe/tests` (989 tests) never run in CI. | `testpaths` covers `tests` and `portal`; CI and `ci_local.sh` use the same invocation. |
| A3 | Tests append to the live wiki provenance ledger (hidden by `.gitignore`). | An autouse fixture gives every test a scratch ledger. |
| A4 | `/health` counts every backend healthy before the first health cycle. | A `backends_checked` field is added; anything gating on health waits for it. |
| A5 | LanceDB `table_names()` is deprecated and its replacement `list_tables()` is paginated. | One helper follows `page_token`; no deprecation warnings. |
| A6 | A persona that fails to load disappears at DEBUG level. | Logged at WARNING; startup reports the count of personas skipped. |
| A7 | Open WebUI runs `ghcr.io/open-webui/open-webui:main`, a floating tag (`deploy/portal-5/docker-compose.yml`), and `scripts/image_security_update.py` tracks `:main` on purpose to pick up security fixes. | Pinned to a tested release. `image_security_update.py` becomes the deliberate upgrade path: bump the pin, smoke-test, commit. Prerequisite for C1. |
| A8 | The platform imports module code in five places: the security CLI, the security wiki seeders, eleven compliance/research claim probes, retrieval's `rag_mcp` extraction, and `sync_config` loading `scripts/update_workspace_tools.py` by path. | Modules plug in through `portal/modules/<name>/plugin.py`; the tool → Open WebUI server map becomes config. A test fails if `portal/platform` imports `portal.modules`. |
| A9 | Tests pin incumbent model names and counts. Some have already been fixed one at a time, e.g. `test_reasoning_seats_a_thinking_model`. | A single sweep replaces them with property assertions (R8). |
| A11 | Persona prompts reach only Open WebUI. The pipeline maps a persona slug to its workspace (`preinject._resolve_persona_workspace`) but never injects the persona's system prompt; the prompt lives only in the Open WebUI model preset that `openwebui_init.py` seeds. An API caller using a persona id (for example an opencode provider such as `portal/agenticheavy`) gets the workspace without the persona. | The pipeline injects the persona's system prompt server-side for every client; a test calls a persona id through the API and asserts the prompt is applied. This is also the mechanism C1 builds on. |
| A10 | Stale persona content: the Agent Orchestrator prompt advertises tools by name and calls web search, memory and RAG "future" work. | Rewritten to the current tool set. |

The fixes for A1, A3–A6, A8 and A10 already exist and are verified in the Breaker Part 1 work.
They port to Portal as patches, without the rename.

## Workstream B — stop the churn

| # | Requirement | Design | Done when |
|---|---|---|---|
| B1 | Module state is config (R2). | A `modules:` block in `config/portal.yaml` (`name: {enabled: bool}`); `portal module enable/disable` writes it. The resolver reads config. `unit-module-*` units document the switch; they do not hold it. | Toggling a module changes one config line and zero wiki files. |
| B2 | Facts are computed, not stored (R3). | Fact units (roster, bindings, catalog, tool registry, rollups) are computed on demand by the wiki MCP and the claims probes, which already read config live. They are not written to `canonical/`. Docs carry no counts (the rule already exists). | A model swap touches no `unit-fact-*` file; `check_wiki_facts_current` is retired. |
| B3 | Ownership is per module, not per file. | `spine_surfaces.yaml`'s 419 file → unit bindings are replaced by directory ownership: module dir → `unit-module-<name>`, platform package → its unit. Coverage asks whether every module, MCP and platform package has a unit. A code edit inside a module does not demand a unit edit; a contract change does (public tools, config schema, ports). | Adding a file inside a module needs no manifest entry; the manifest stops changing on routine commits. |
| B4 | The budget is a ceiling (R4). | `complexity_budget.yaml` keeps its metrics with explicit headroom. Exceeding a ceiling fails CI. Raising one is an operator decision recorded with a reason, never an automatic re-stamp. Prose and god-function counts are reported, not ratcheted. | No `chore(complexity)` re-stamp commits. |
| B5 | Generated doc blocks regenerate in one step. | `sync-config` regenerates only runtime artifacts. Doc tables (e.g. the ADMIN_GUIDE workspace table) are produced by `portal docs build` at release, or are replaced by a pointer to `portal config show`. | A config commit does not edit `docs/`. |
| B6 | Run evidence moves out of `main` (R5; operator: "summaries yes, but not everything as it is"). | **Inputs stay:** test fixtures, golden files and task suites (`tests/fixtures/`, `tests/data/`, `tests/wfe/suites/`). **Outputs leave `main`:** `reports/` raw run output (97 MB), `tests/benchmarks/results/` (45 MB, 802 files), `tests/wfe/results/` (6.4 MB), and run JSON in `docs/`. They move to `PORTAL_DATA_ROOT`, plus a tagged archive commit so they stay recoverable; git history is not rewritten. **Summaries stay:** decision docs and report Markdown, citing data by data-root path and run id. New runs write only to the data root. Before the move, every test or script that reads a result file is repointed or given a fixture. | `main` carries no raw run output; a pre-commit path rule rejects new raw files; decision docs still resolve their cited runs. |
| B7 | The wiki archive leaves the hot path. | The 883 archived units are excluded from every gate (archive reachability included). They stay in `main` (operator decision 7). | Gates load only `canonical/`. |
| B8 | Root docs consolidate. | Root keeps `README`, `CHANGELOG`, `CLAUDE.md`, `ROADMAP` and a current-only `KNOWN_LIMITATIONS`. Resolved limitations move to the CHANGELOG. `PUNCHLIST`, `P5_ROADMAP`, `WFE_ROOT_FIX_PROGRAM`, `ACCEPTANCE_RESULTS` and `AGENTS_CAMPAIGN_SUPERVISOR` fold into those or into `docs/`. | Root holds those five docs. |

**Churn acceptance for Workstream B.** Replay three recent changes on a branch after B lands:
- a model swap (`19fc3ccc`);
- a module toggle;
- a new tool on an existing engine.

Each must touch only the files R3 allows. Before B, the model swap touched 7 files.

The replay becomes a permanent check, not a one-off: a test applies a synthetic model swap,
module toggle and tool addition to a scratch copy of the config and asserts which files
`sync-config` writes.

## Workstream C — engines and roles (refined from the 10-19 doc)

The 10-19 doc's model stays:
- **Engine:** a user-facing workspace.
- **Variant:** an engine with its own model or tool set.
- **Role:** instructions only.
- **Persona:** kept only where behaviour goes beyond the prompt (tool lists, forced tool choice).

Its engine table, merge families, preserve-don't-flatten rules and Appendix C field diffs stay.
The refinements:

**C1 — Roles are delivered server-side** (builds on A11). Open WebUI prompt-library entries are slash templates
pasted into the user's message; they do not set the system prompt. Delivering 86 roles that way
moves their instructions from the system turn to the user turn and shows the full text in the
chat. The pipeline resolves persona slugs to workspaces today (`preinject.py`, `_PERSONA_MAP`) but does
not inject their prompts; A11 adds that. The design is therefore:
- A message that begins `/slug` is stripped of the token and gets that persona's system prompt,
  server-side.
- The Open WebUI prompt-library entry for each role contains only `/slug `, so the slash menu
  still lists roles.
- The persona YAML stays the single source.
- No Open WebUI source changes (Rule 2).

Verify the slash-menu behaviour on the pinned Open WebUI release (A7) before step C2.

**C2 — Order.**
1. Hide internal seats and move bench lanes to a bench config that the harness reads. No
   behaviour change.
2. Ship role delivery (C1) and move the 55 plain-prompt personas to roles.
3. Merge engine families one at a time, each with a router re-bench and its WFE and conformance
   evidence re-run.
4. Screen the media dispatcher, then merge media.
5. Move the 31 role-on-variant and 11 model-pin personas once their variants exist.

**C3 — Growth guard (R7).** The July collapse went from 44 to 22 lanes and regrew to 35. Without a
guard, this consolidation regrows too. The guard has three parts:
- A new capability lands as a variant or a tool route of an existing engine by default.
- A new user-facing engine needs `engine: true` plus a one-line reason in config. A test fails
  when the set of user-facing engines differs from that declared list.
- Bench and challenger lanes exist only in the bench config and are never seeded to Open WebUI.
- A new behavioural persona (tool lists, forced tool choice) needs `persona: true` plus a reason,
  like an engine. Roles (instructions only) need no guard. Personas ranged 112–138 and were never
  consolidated.

**C4 — Aliases are time-boxed.** Old ids resolve through aliases only for a stated window. Each
alias carries a removal date and is removed on zero-traffic evidence, as the July retirement
did. No permanent alias layer.

**C5 — Open WebUI chat history.** Removing a model entry orphans past chats that reference it.
Decide one of:
- keep hidden stub entries until the alias removal date; or
- accept the orphaning.

**C6 — What gets simpler, stated plainly.**
- Smaller: what the user sees (about 11 engines and a role list), the persona count, and the
  router's label set.
- Unchanged: what is screened and conformance-checked. The 31 distinct model tags and the
  existing 30 variants still are.
- The 10-19 doc's "fewer lanes to keep card-conformant" is dropped.

**C7 — Cross-module merges are gated per variant.**
- `coding` spans `coding`, `cad` and `general` (bigfix). SPL is its own engine (decision 1).
- `media` spans `media`, `image` and `video`.

Each variant and tool route keeps its own module. A test turns each module off and checks that
its variant or route disappears while the engine stays up.

**C8 — Router re-bench per family.** Each merge re-runs `scripts/router_bench.py` on the
production corpus and re-blesses `tests/routing/baseline.json` in the same commit.

**C9 — Appendix D census, corrected.** Reference counts are dominated by recorded evidence: e.g.
`auto-daily` 397 files, 299 of them in `tests/benchmarks`. Aliases are needed only for live
callers:
- code and config;
- scripts;
- opencode providers;
- `portal_channels`;
- harness plans that still run.

Recorded results are history and are not edited. The census is re-run with live callers counted
separately.

### Merge recipe: reasoning ← auto-math

Move `auto-math`'s distinct model, limits, sampling, thinking, web-search setting and prompts into
`auto-reasoning.variants.math`; let common fields inherit from the engine. Add a time-boxed
`auto-math` alias, point `mathreasoner` at `auto-reasoning` with `variant: math`, and remove the old
label from router descriptions and examples. Check alias traffic before its removal date. For each
family, capture `router_bench.py` on the production corpus before and after, then run
`scripts/routing_regression.py --rebless` and record its diff.

## Sequencing

1. **A first.** Most of the code exists and it changes no behaviour. A7 (pinning Open WebUI) is
   needed before C1.
2. **B next.** B1–B5 change the gates C would otherwise fight; C's merge commits are exactly the
   kind of change that churns today. B6–B8 can run alongside.
3. **C last,** in its own order (§C2), each step shipping green with its evidence.

Every step commits green: `ci_local.sh` plus the step's own acceptance. Every step updates the
README and CHANGELOG in the same commit, or updates nothing.

## Out of scope

- Breaker (on hold).
- Cutting or retiring any capability.
- Security internals (its 16 variants are untouched; the 10-19 doc's scope note stands).
- Rewriting git history.

## Open decisions for the operator

1. **SPL placement.** Resolved: its own engine (23 tools, many security/vulnerability; Splunk is core work).
2. **`auto-council`.** Resolved: utility only (hidden from the dropdown, callable by id).
3. **Media dispatcher.** Resolved: screen the current dispatchers on mixed media prompts and seat the best.
4. **`uncensored`.** Resolved: `auto-creative` folds in; its personas become roles on that engine.
5. **Open WebUI history (C5).** Resolved: remove the old entries and start fresh (operator: "this will be the new going forward"). No stubs; C4 aliases cover live API callers only.
6. **Run evidence (B6).** Resolved: raw output leaves `main` (data root + tagged archive);
   summaries stay; history is not rewritten.
7. **Wiki archive (B7).** Resolved: excluded from gates only.
8. **Role names.** Resolved: persona slugs are role names (`/proofreader`).
