# RESULTS — Legacy Workspace Alias Retirement (V1)

**Program:** `coding_task/cleanup/BUILD_PROGRAM_ALIAS_RETIRE_V1.md`, per
`DESIGN_ALIAS_RETIRE_V1.md` and `DESIGN_ROUTER_CANONICALIZATION_V1.md`.
**Grounded against:** HEAD `f5d3a87` (pre-program baseline, 2026-07-12).
**Completed:** 2026-07-13.
**Status:** Complete, modulo 3 documented holdouts that keep the legacy
shim live (see § Shim status).

---

## 1. Census — before / after

| | Live refs | Frozen refs (untouched) | Files with live refs |
|---|--:|--:|--:|
| **Before** (Phase 0 baseline) | 970 | 5,485 | 139 |
| **After** (Phase 9) | 730 | 5,535 | 98 |

Live refs dropped **970 → 730** (-24%), files with any live reference
**139 → 98** (-29%). Frozen-artifact count grew slightly (5,485 → 5,535) only
because new dated run files were produced by test/bench activity during the
program — none of the 5,485 originally-frozen refs were ever touched.

The remaining 730 live refs break down as:

| Category | Count | Why they remain |
|---|--:|---|
| `tests` | 262 | Tests of the shim's own resolution behavior (legitimate — the shim is still live), plus the security bench harness's test coverage of its own not-yet-migrated vocabulary |
| `config` | 138 | `config/portal.yaml`/`MODEL_CATALOG.md` historical bench-provenance entries (CHANGELOG-equivalent, deliberately preserved per DESIGN §1), `routing_examples.json`/`routing_descriptions.json` example data retained for corpus continuity, Grafana dashboards with zero functional query risk |
| `docs` | 121 | `CHANGELOG.md` (30, historical, out of scope by design), archived point-in-time reports moved to `docs/_archive_execdocs/` but not rewritten (frozen-in-spirit) |
| `shim` | 56 | `preinject.py`'s own `_LEGACY_WORKSPACE_ALIASES` dict + `routing.py`'s explanatory `# was auto-X` comments (historical grounding, not live vocabulary) |
| `integration` | 59 | The 3 documented holdouts below |
| `personas` | 2 | Deliberate "formerly the auto-mistral/auto-phi4 alias" pointers in 2 persona comments |
| `other` | 92 | `.env.example`, task-planning docs (`coding_task/`, gitignored), bench review docs — historical/reference, not live routing |

## 2. What changed — the four canonical addressing forms

Every alias now resolves through one of these, matching
`DESIGN_ALIAS_RETIRE_V1.md` §3:

| Alias class | Canonical form | Example |
|---|---|---|
| Coding variants | `auto-coding` + `?variant=<v>` | `auto-coding?variant=heavy` (was `auto-agentic`) |
| Security roles | `auto-security` + `?variant=<v>` | `auto-security?variant=redteam` (was `auto-redteam`) |
| Model-tied (coding-family) | `auto-coding` + `?model=<hint>` | was `auto-devstral`/`auto-glm`/`auto-glm-thinking` |
| Model-tied (general/vision) | `auto-daily`/`auto-vision` + `?model=<hint>` | was `auto-phi4`, `auto-gemma-*` |

**Operator decision made during the program:** `auto-mistral`'s intent now
routes to `auto-reasoning`, not `auto-coding` (the shim's original mapping).
`_MISTRAL_KEYWORDS`, the LLM router's own description, and the
`magistralstrategist` persona's system prompt were all 100%
reasoning-flavored with zero coding terms — `auto-coding` was a
collapse-era filing artifact, not a deliberate choice.

## 3. The routing-regression proof (§9 safety gate)

The one edit that could silently change routing decisions — canonicalizing
both auto-routing layers' output vocabulary (Phase 7) — was proven
behavior-preserving two ways:

- **Layer 2 (keyword scorer), deterministic hard gate:** 62 of 63 corpus
  prompts identical to the pre-Phase-7 baseline. The one changed decision
  (`routing_examples[39]`, "use Magistral to reason through this strategic
  decision": `auto-coding` → `auto-reasoning`) is the approved mistral
  reassignment above, not a regression.
- **Layer 1 (LLM router), accuracy check against the real live router
  model** (`hf.co/QuantFactory/Llama-3.2-3B-Instruct-abliterated-GGUF`, the
  actual production `LLM_ROUTER_MODEL`, via the running `portal5-pipeline`'s
  Ollama): **34.1% → 38.6%** on the 44-item labeled corpus — a net
  improvement, comfortably inside the ±2% margin (one description on
  `auto-coding` was tightened mid-program after an initial run showed a
  borderline single-example regression).

Verified end-to-end against the real rebuilt, running pipeline (not mocks):
a live `write me a metasploit exploit for CVE-2024-12345` request resolved
to `auto-security::redteam` via the keyword layer
(`portal5_router_layer_total` confirms it), served HTTP 200, and triggered
zero `ALIAS_RESOLVED` log lines.

## 4. Deprecation-trip gate (Phase 6)

`PORTAL_ALIAS_TRIP=1` armed across `validate_system.py` (45/45 pass) and
`pytest tests/` (721 passed, 1 pre-existing unrelated failure requiring a
live API key) — **zero `ALIAS_RESOLVED` hits** on every testable code path.
Separately verified against the real rebuilt pipeline: canonical and
legacy-alias workspaces both route and respond correctly; the trip is
silent by default in production (not declared in `docker-compose.yml`, so
unset/off as designed).

## 5. Shim status — 3 documented holdouts

The shim (`_LEGACY_WORKSPACE_ALIASES` / `_resolve_legacy_workspace_alias`
in `preinject.py`) **was not removed**. Three call sites still send a bare
pre-collapse alias id as their literal `model=` value with no verified way
to attach a `?variant=` query param:

1. **Incalmo's `OPENAI_MODEL` default** (`deploy/portal-5/docker-compose.lab.yml`) — third-party OpenAI-compatible client.
2. **`opencode.jsonc`'s model picker + `pipeline_mcp.py`'s `get_workspace_recommendation()`** — same constraint, kept in sync.
3. **The security bench harness's own workspace vocabulary** (`portal/modules/security/core/_data.py`'s `EXECUTION_WORKSPACES`/`PER_WORKSPACE_TIMEOUT`, threaded bare through `call_pipeline()`/`call_pipeline_exec()` across ~100+ call sites in `cli.py`, `commands/run.py`, `chain.py`, `matrix.py`, `blue.py`, `exec_chain.py`).

Removing the shim today would silently break all three. Instead, Phase 8
landed a **growth-only ratchet**: `validate_system.py` check `AT` fails if
any file's live alias-reference count exceeds its recorded baseline
(`config/.alias_retire_baseline.json`, 730 refs / 98 files) — further
migration always passes, nothing can silently regress what's already been
cleaned up. Full investigation: `docs/_archive_execdocs/
PHASE6_TRIP_FINDINGS_20260713.md`.

**Follow-on filed:** `P5-FUT-ALIAS-SHIM-RETIRE` in `P5_ROADMAP.md`, with the
concrete next step for each holdout.

## 6. Program summary — commits

| Phase | Commit(s) | Summary |
|---|---|---|
| 0 | `0a4e139` | Census tool, routing-regression harness, deprecation trip |
| 1 | `9fdc12b`, `9adc51a`, `fda7ee0` | Docs/wiki/Grafana — 3 stale reports archived, 47 orphaned wiki units deleted |
| 2 | `74b6f53`, `7317888` | Config — portal.yaml, backends.yaml, promptfoo, personas |
| 3+4 | `6671c60`, `831e854`, `fc0477d` | UAT catalog (25 tests) + bench config, check K → hard-fail |
| 5 | `6d05f42` | Production integration — blue_triage, Slack/Telegram, deploy |
| 6 | `0a02245` | Deprecation-trip gate — verified against live rebuilt pipeline |
| 7 | `f58ae30` | Router two-layer output canonicalization (the §9 work) |
| 8 | `5a8f366` | Growth-only ratchet in place of shim removal |
| 9 | *(this commit)* | Final green, retrospective, tag |

## 7. Not in scope (unchanged from the program's own charter)

Frozen historical artifacts (5,535 refs / preserved as-is), router keyword
tuning (thresholds/keywords unchanged except the approved mistral
reassignment), new workspaces/modules, repo rename, semantic versioning.

---

## 8. Finish — the 3 holdouts resolved, shim removed, zero-live-alias enforced (2026-07-13)

`CLOSEOUT_ALIAS_REMOVAL.md` / `BUILD_PROGRAM_ALIAS_FINISH_V1.md`,
run to completion the same day as the Stage 8 ratchet above. This closes
`P5-FUT-ALIAS-SHIM-RETIRE`.

### Holdout 1 — Incalmo
`docker-compose.lab.yml`'s `OPENAI_MODEL` default: `auto-redteam` →
`auto-security::redteam`. Non-interactive caller, canonical `::` form.
Live-verified: `model=auto-security::redteam` → HTTP 200, served
`huihui_ai/qwen3.5-abliterated:9b-ctx8k`.

### Holdout 2 — opencode / Claude Code
Resolved per `DESIGN_OPENCODE_ADDRESSING_V1.md`'s option B (persona slugs),
not the originally-sketched `::` string-swap — a human-facing picker needs
clean, self-documenting keys, and opencode's `::`-survival was unverified
anyway. 8 new + 3 reused thin variant-personas bind the picker's 11
variant-carrying entries; 9 entries stay on bare base ids. `PersonaSpec`
gained `ide_expose: bool`; `/v1/models` now advertises those personas
alongside the 21 base workspaces, fixing the discovery/jsonc divergence the
design flagged. `pipeline_mcp.py`'s `get_workspace_recommendation()` and
`trigger_backend_warmup()` return persona slugs. CLI contract
(`MCP_DEV_TOOLING.md`, `cc-local.sh`) migrated with a visible old→new
table. Live-verified via the actual `opencode` CLI (`opencode run --model
portal/<persona>`) and direct API calls.

### Holdout 3 — security bench harness
`DEFAULT_WORKSPACES`, `PER_WORKSPACE_TIMEOUT`, `EXECUTION_WORKSPACES`
(`_data.py`) re-keyed to canonical `auto-security::<variant>` strings —
keyed on the **pre-resolution** string specifically, so `auto-security::
redteam` and `auto-security::purpleteam-deep` (both resolve to the same
base) keep their distinct timeout caps. `call_pipeline()`/
`call_pipeline_exec()` needed no signature change (they already forward
`workspace` verbatim as `model=`). `validation.py`'s separate
`_call_pipeline` had its defaults migrated too. One dead entry
(`auto-phi4`, unreferenced by anything live in this module) removed rather
than migrated.

### Phase 4 — live-traffic deprecation trip
`PORTAL_ALIAS_TRIP=1` armed on the running `portal-pipeline` container
(temporarily; net-zero diff on `docker-compose.yml` after). Driven: an
Incalmo-style `::` request, an opencode-style persona-slug request, two
security-bench `call_pipeline()` calls with different `::` workspaces
(both returned real, role-appropriate responses), and Slack/Telegram
confirmed via `docker exec ... env` to default to `SLACK_DEFAULT_WORKSPACE=
auto` / `TELEGRAM_DEFAULT_WORKSPACE=auto` — structurally incapable of
tripping the gate since they never send a bare alias.
`docker logs portal5-pipeline | grep -c ALIAS_RESOLVED` = **0** across the
full window.

### Phase 5 — shim removed
`_LEGACY_WORKSPACE_ALIASES` deleted from `preinject.py`.
`_resolve_legacy_workspace_alias` renamed to `_unpack_synthetic_workspace`
— it now only unpacks the canonical `"base::variant"` form (kept, since
both routing layers depend on it). `_alias_resolved_total` metric and the
`PORTAL_ALIAS_TRIP` env check removed. All call sites (`handlers.py`,
`validation.py`, `routing_regression.py`, `tests/routing/measure.py`, 2
unit test files) updated to the renamed function and canonical inputs.
Two more live-code holdouts found and fixed during the grep-for-references
pass (not caught by the per-holdout work since they're default-argument
values, not the primary path each holdout touched):
`pipeline_mcp.py`'s `trigger_backend_warmup` default and one operator
warning string in `commands/run.py`.

### Phase 6 — check AT: growth-ratchet → hard zero-live-alias assertion
`scripts/alias_census.py`'s alias vocabulary is now a frozen historical
list (previously read live from the now-deleted shim table). Added a
comment/docstring-aware classifier that distinguishes a bare alias id
appearing as **live code** (a default arg, a dispatched dict value) from
one in a **comment/docstring explaining history**. Check AT hard-fails on
any non-comment hit in Python serving-path files
(shim/integration/personas categories) — verified 0. Scope note (recorded
in the check's own docstring, since it's a real design decision): this is
*not* a zero-occurrence-anywhere-in-the-repo assertion — `docs/`, `tests/`,
and `config/`'s narrative JSON/YAML (`MODEL_CATALOG.md`,
`routing_descriptions.json`'s `_note`, Grafana dashboards, this very
`coding_task/` design-doc corpus) legitimately reference retired ids by
name when explaining collapse/retirement history, at a scale (~717 refs)
where a blanket ban would demand rewriting the historical record rather
than catching a regression. `config/.alias_retire_baseline.json` retired.

### Final state
- `pytest tests/unit/ -q` — 717 passed.
- `scripts/validate_system.py` — 48/48 checks pass (AT hard-zero included).
- `python3 scripts/routing_regression.py --assert-baseline` — 86/86 corpus
  prompts match.
- `python3 scripts/persona_intent_audit.py` — 0 hard failures.
- `./scripts/smoke_stream.sh` — PASS (live streaming gate against the
  rebuilt pipeline).
- Live: `::` requests, persona-slug requests, and a genuinely-retired bare
  alias (`auto-redteam`) all return HTTP 200 — the retired id is now
  treated as an unresolved/unknown workspace (falls through to a default),
  not silently mapped back to its old target.

### Commits (this Finish pass)
| Step | Commit | Summary |
|---|---|---|
| Holdout 1 | `36c30e6` | Incalmo canonical `::` default |
| Holdout 2 (personas) | `5dd8523` | 8 new + 3 reused variant-personas |
| Holdout 2 (`/v1/models`) | `0ffbe68` | Persona discovery endpoint |
| Holdout 2 (jsonc) | `63c3683` | opencode.jsonc re-keyed |
| Holdout 2 (mcp) | `1eb3d77` | pipeline_mcp recommendation + warmup |
| Holdout 2 (CLI docs) | `40e3fd3` | MCP_DEV_TOOLING.md, cc-local.sh |
| Holdout 3 | `edcaa8b` | Security bench harness canonical `::` |
| Phase 4 | `6d4212d` | Live-traffic trip gate — zero hits |
| Phases 5+6 | `86f61a7` | Shim removed; check AT hard zero-alias |

**Tag:** `alias-retire-complete`.
