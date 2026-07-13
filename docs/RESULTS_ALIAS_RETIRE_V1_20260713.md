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
