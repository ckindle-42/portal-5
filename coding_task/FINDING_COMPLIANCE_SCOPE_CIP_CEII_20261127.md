# FINDING — compliance scope is NERC CIP + CEII, not GDPR (audit + fix)

**Date:** 2026-11-27 · **Lane:** `lane/compliance-scope2` · **Brief:** `BRIEF_COMPLIANCE_SCOPE_CIP_CEII_20261127.md`
**Operator intent:** "We use NERC CIP not GDPR … CEII not GDPR. If [GDPR] is what is expected then all is wrong."
**In-scope (operator, final):** FERC, NERC CIP, CEII as the core; at most also PCI DSS, ISO/IEC 27001, SOC 2, CIS Controls, SOX. GDPR OUT.

---

## 1. What the store actually contains (read-only, live DB on disk)

Read `portal/modules/compliance/data/compliance_store.db` read-only (`immutable=1`) from the live
checkout. **Not** an inference call, not a write, not a live-service probe.

- `source_documents`: **204 rows**. By kind/jurisdiction:
  - US regulatory material: `regulatory_standard` **36**, `technical_rationale` 24, `rsaw` 13, `implementation_plan` 29, `glossary` 1, `lifecycle_registry` 1.
  - Internal operator corpus (LSPG / LS Power Grid): `procedure` 28, `work_instruction` 26, `evidence_specification` 5, `plan` 5, `process` 2, `policy` 1, `unknown` 1.
  - `derived_answer` 30, `operator_note` 2.
- `standard_revisions` families: **CIP-002 … CIP-014 only** (13 families). Confirmed a second way:
  word-boundary title search for `CEII / FERC / GDPR / HIPAA / 18 CFR` returns **0**.
- **ZERO GDPR. ZERO CEII. ZERO FERC. ZERO HIPAA/PCI/ISO/SOC/SOX/CIS regulatory corpus.**
- NIST SP 800-53 / CSF 2.0 exist only as **control-catalog distillations** behind the compliance MCP
  (`lookup_control`, `search_controls`, `map_frameworks`), not as an assessed regulatory corpus.

> Note: the brief cited "44 regulatory docs" (lane compliance-root3). My read-only count of
> `source_kind='regulatory_standard'` is **36**; the difference is a counting definition (the MCP
> inventory tool may count distinct logical docs / revisions differently). The load-bearing fact —
> **NERC CIP only, zero GDPR** — is confirmed by two independent queries.

### Gap list for ingestion (in-scope frameworks the store does NOT hold)
| Framework | Scope tier | In store? |
|---|---|---|
| NERC CIP | core | **YES** (CIP-002…014 register + CIP-007-6 operator corpus) |
| CEII (18 CFR 388.113) | core | **NO — ingest** |
| FERC (orders / 18 CFR) | core | **NO — ingest** |
| PCI DSS | optional | NO |
| ISO/IEC 27001 | optional | NO |
| SOC 2 | optional | NO |
| CIS Controls | optional | NO |
| SOX | optional | NO |

**CEII handling today:** the store and prompts say **nothing** about CEII (0 hits). CEII = FERC's
Critical Energy Infrastructure Information designation (18 CFR 388.113). It is a scope aspiration, not
an implemented capability: until ingested, the product must disclose CEII as unavailable (the
auto-compliance abstention rule already covers "no local corpus"). `nerccipcomplianceanalyst` already
cites FERC Orders; I added CEII/FERC to `complianceanalyst` scope and to routing.

---

## 2. Inventory — where compliance scope/expectations are defined, and match status

| Location | Defines | Before | Action |
|---|---|---|---|
| `tests/qat/uat_behavioral.py` `s5-compliance-multiframework` + `_grade_compliance_case` | QAT scenario + grader | required **GDPR Art. 32(1)(a)** citation in answer **and** receipts (out-of-corpus → could never be retrieved) | **FIXED** → CIP-007-6 R2 Part 2.2 vs CIP-010-4 R1 Part 1.1, both graded against retrieved receipts |
| `tests/qat/uat_behavioral.py` `s5-persona-compliance` marker | persona selection | marker `gdpr art. 32(1)(a)` | **FIXED** → `cip-007-6 r2 part 2.2` |
| `tests/qat/uat_behavioral.py` `_grade_compliance` | citation special-case | GDPR alias accept | **REMOVED** |
| `tests/qat/uat_behavioral.py` (new) `s5-compliance-abstention` + grader | abstention check | absent (conflated into multiframe) | **ADDED** — out-of-scope framework must be disclosed unavailable, not cited |
| `config/personas/gdprdpoadvisor.yaml` | GDPR DPO persona | present | **REMOVED** (git rm) |
| `config/personas/complianceanalyst.yaml` | generalist prompt | GDPR/HIPAA/NIS2/CMMC/FedRAMP/state-privacy | **FIXED** → energy in-scope list + SCOPE block |
| `config/personas/dailydriver.yaml` | redirect list | "NERC CIP, HIPAA, GDPR, SOC 2, PCI-DSS" | **FIXED** → "NERC CIP, CEII, FERC, SOC 2, PCI-DSS" |
| `config/portal.yaml` `auto-compliance.system_prompt_append` | workspace prompt | "(including GDPR)" abstention example | **FIXED** → generic "a framework has no local corpus" |
| `config/inference/routing_compliance_keywords.json` | Layer-2 keywords | NERC CIP only (already in-scope) | **ADDED** CEII/FERC signals |
| `config/routing_descriptions.json` `auto-compliance` | Layer-1 description | NERC CIP (already in-scope) | **ADDED** CEII/FERC energy scope |
| `config/routing_examples.json` | Layer-1 few-shot | NERC CIP (already in-scope) | no change needed |
| `tests/fixtures/compliance_scenarios.yaml` `frameworks:` | matrix rotation | GDPR + HIPAA present | **REMOVED** GDPR/HIPAA (now NERC_CIP, SOC2, PCI_DSS, NIST_800_53, ISO_27001) |
| `tests/lib/compliance_assertions.py` `CITATION_PATTERNS` | citation shapes | GDPR + HIPAA patterns | **REMOVED** |
| `tests/data/compliance_assertions_anti_fab_phrases.json` | refusal phrases | "see gdpr-info.eu", "see hhs.gov" | **REMOVED** |
| `tests/fixtures/preset_resolution_snapshot.json` | persona oracle | `persona::gdprdpoadvisor` + stale GDPR prompts | **REMOVED** entry; refreshed complianceanalyst/dailydriver prompts |
| `tests/fixtures/owui_persona_presets_snapshot.json` | persona oracle | `gdprdpoadvisor` + stale GDPR prompts | **REMOVED** entry; refreshed prompts |
| `tests/fixtures/workspaces_snapshot.json` | workspace oracle | stale multi-framework description (GDPR/HIPAA/…) | **REFOCUSED** to energy scope |
| `tests/data/uat_catalog_g_browser_automation.json` | legacy UAT catalog | P-N09 gdprdpoadvisor; P-N03 expects HIPAA+GDPR | **REMOVED** P-N09; **REFOCUSED** P-N03 to NERC CIP |
| `scripts/compliance_acceptance.py` + case file `cip_007_6.yaml` | live acceptance | **already pure CIP-007-6** | no change needed (case file is operator-local, not committed) |
| compliance eval store (:8948) `eval_instance` + planted corpus | WFE eval | NERC CIP register + planted CIP corpus | already in-scope, no GDPR |
| compliance MCP tools / `portal/modules/compliance/**` | product code | no GDPR | no change needed |
| `portal_wiki/canonical/unit-*compliance*` | wiki units | no GDPR/CEII/HIPAA | no change needed |
| `docs/FEATURE_QAT_TRACEABILITY_MATRIX.md` | traceability | gdprdpoadvisor row | **REMOVED** row; registered abstention scenario |
| `docs/USER_VALIDATION_GUIDE.md` | validation guide | "NERC CIP and GDPR citations" | **FIXED** → multi-standard CIP + abstention |
| `tests/PORTAL5_PERSONA_MATRIX_EXECUTE_V1.md` | matrix plan | gdprdpoadvisor, personas:7 | **FIXED** → personas:6, scenarios:198, cells:54 |
| `config/live_check_map.yaml` `module-compliance` | diff→live proof | 2 scenarios | **ADDED** `s5-compliance-abstention` + compliance persona/routing globs |
| `tests/unit/test_catalog_schema.py` | regression | — | **ADDED** 1 test: no GDPR in persona catalog |

### Historical records left intact (NOT rewritten — they record past runs, not expectations)
`tests/UAT_RESULTS.md`, `CHANGELOG.md`, `reports/PENDING_VERDICTS_ANALYSIS_*.md`,
`docs/MODEL_FLEET_CLOSEOUT_20260906.tasks.json`, `docs/DESIGN_ENGINES_AND_PROMPTS_20261019.md`,
`config/grafana/dashboards/portal5_{benchmarks,uat}.json`, `config/TASK_*_V1.md`,
`config/FOLLOWUP_REASONING_OVERHAUL_REMAINING_V1.md`. These mention gdprdpoadvisor/GDPR as historical
fact; rewriting them would falsify the record.

---

## 3. Out-of-scope frameworks found (report-with-location, per brief)

- **HIPAA — `config/personas/hipaaprivacyofficer.yaml`** (whole persona, category compliance). Also its
  entries in the two persona snapshots and a legacy catalog scenario
  (`tests/data/uat_catalog_g_browser_automation.json`, `model_slug: hipaaprivacyofficer`).
  **Recommendation: remove end-to-end exactly like gdprdpoadvisor.** The brief explicitly authorized
  wholesale removal only for gdprdpoadvisor, so I removed HIPAA from the *shared* compliance
  prompts/tests (complianceanalyst, dailydriver, frameworks fixture, citation patterns, anti-fab
  phrases, P-N03) and **left the dedicated persona in place pending orchestrator confirmation** —
  deleting a persona not named in the brief would widen scope. **Orchestrator: confirm removal.**
- **CCPA/CPRA, Texas TDPSA, Connecticut CTDPA, NIS2, CMMC, FedRAMP, FFIEC** — appeared only in the
  stale `workspaces_snapshot.json` description and the old complianceanalyst prompt; removed from the
  live prompt and refocused in the snapshot. No dedicated persona.
- **NIST SP 800-53 / CSF / 800-171, ISA/IEC 62443** — kept. These are **control catalogs / crosswalk
  tool capability** (the compliance MCP's `lookup_control`/`map_frameworks`), analogous to the
  operator-allowed "CIS (Controls)", not a regulatory framework being assessed. **Judgement call —
  flagged for orchestrator** (NIST is not literally in the in-scope list, but removing it would
  misrepresent the module's actual tooling).

---

## 4. Verification (offline gates — merge net, NOT live proof)

- `uv run pytest tests/unit/ -q` → **1884 passed, 36 skipped**.
- `uv run ruff check .` → All checks passed; `uv run ruff format --check .` → 1384 files formatted.
- `uv run mypy portal/` → Success, no issues in 670 files.
- `python3 scripts/complexity_report.py --gate` → GATE OK.
- Offline grader sanity: abstention grader passes on disclosure, fails on cite-from-memory;
  multiframe grader accepts both CIP citations; `reading_assembly.parse_ref` canonicalizes
  `CIP-010-4 R1 Part 1.1`; `expand_scenarios()` → 198 scenarios, frameworks all in-scope.

**UNPROVEN against the live system** (orchestrator runs): the QAT scenarios/graders on the deployed
stack, receipt grounding of CIP-010-4 R1 Part 1.1 via `compliance_ask`, persona reseed dropping
gdprdpoadvisor, and routing of CEII/FERC queries. See ORCHESTRATOR RUNS in the dispatch report.