# Compliance reasoning V3 discovery

Captured from the working host on 2026-09-05 (America/Chicago). Counts in this
record were queried from the running store or source files; they are not copied
from the V2 reports.

## D0 dispositions

| ID | Disposition | Evidence at discovery / disposition |
|---|---|---|
| D0.1 | CONFIRMED; FIXED | `core/coverage.py::_classify` had only `NEEDS_REVIEW`/`UNRESOLVED` returns. It now calls `assessment.assess_atom` and returns `FULL`, `PARTIAL`, or `NONE` after a completed retrieval. |
| D0.2 | CONFIRMED; FIXED | The only original importer of `evaluate_expression` was `tests/unit/test_compliance_comparison.py`. `core/assessment.py::assess_requirement` now invokes it on the routed analysis/scenario path. |
| D0.3 | CONFIRMED; FIXED FOR REQUIRED LIVE TABLES | At `c8fbc5e`, repository search found no INSERT writer for the named domain tables. `scripts/materialize_compliance_v3.py` populated atoms, expressions, definitions, authority, controls, activities, roles, systems, evidence, runs, claims, evidence links, and findings from the live corpus. Scenario/work/scope/asset rows remain separately measured below. |
| D0.4 | CONFIRMED; FIXED | The old `nerc_cip_requirement(req_id)` read lifecycle strings. `compliance_requirement` now calls `engine.effective_parts`, which uses `_is_enforceable_at`; the wrapper accepts/defaults and discloses `valid_at`. |
| D0.5 | CONFIRMED; FIXED | `change_pipeline.draft_revisions` raised outside `specification_only`. It now defaults to `draft_as_proposal`, emits cited replacement text and a reassessment receipt, and never mutates effective text. |
| D0.6 | CONFIRMED; FIXED | `scenarios.evaluate_scenario` previously compared qualification tokens. It now calls `assess_requirement` for before/after determinations and supplies a change plan. |
| D0.7 | CONFIRMED; FIXED | `_filter_candidates` excluded non-policy candidates whose `standard_hint` differed. It now retains every text-bearing candidate and exposes the folder match only as `folder_rank_prior`. |
| D0.8 | CONFIRMED; FIXED | No selectable A01-A30 parameters existed at discovery. `test_compliance_v3_matrices.py` now exposes exactly A01-A30. |
| D0.9 | CONFIRMED; FIXED | The V2 acceptance module used module-wide `skipif` and key-presence assertions. V3 live mode fails on an unreachable service, and the routed cases assert substantive determinations and citation identifiers. |
| D0.10 | CONFIRMED; FIXED | The probe accepted no live-closeout mode and defaulted `--effective-on` to `2026-09-04`. The extended probe has `--mode live-closeout`; both closeout dates are required from its validated manifest and diagnostic mode has no fixed date default. |
| D0.11 | CONFIRMED | `git log -- KNOWN_LIMITATIONS.md` ends at pre-V2 commit `b103c63e`; V2 commits did not update it. |
| D0.12 | CONFIRMED | `REASONING_V2_ACCEPTANCE.md` names reviewed commit `b5b68333` while its body says the live store is schema 5. V3 fingerprints are regenerated rather than amending that stale table. |

## Live host and build inventory

- Checkout base HEAD: `c8fbc5e77e43bfa4278581d45217b2ab243818d8` (working tree contains the V3 implementation and pre-existing untracked `tests/uat_corpus/`).
- Compliance runtime: host process `.venv/bin/python3 -m portal.modules.compliance.tools.compliance_mcp`, port 8937, restarted on the V3 checkout and answering `/health` and `/tools`.
- Container inventory: Open WebUI, pipeline, browser, RAG, reranker, research, documents, security, sandbox, memory, TTS, Whisper, CAD, binresearch, Prometheus, Grafana, SearXNG, DinD, Slack and Telegram were running. Principal image fingerprints were pipeline `sha256:792db570...`, RAG `sha256:df902d03...`, reranker `sha256:f396f46f...`, and Open WebUI `sha256:8afd2d77...`.
- The live compliance manifest exposes 28 tools. All eight V3 operations are reachable: `compliance_requirement`, `compliance_analyze`, `compliance_compare`, `compliance_impact`, `compliance_trace`, `compliance_scenario`, `compliance_sources`, and `compliance_review_decide`.

## Corpus and register census

Configured operator corpus: `/Users/chris/projects/portal-5/coding_task/v9_compliance/LSPG-CIP`.

The corpus contains 68 PDFs: CIP-002 1, CIP-003 3, CIP-004 11, CIP-005 15,
CIP-006 5, CIP-007 10, CIP-008 2, CIP-009 7, CIP-010 7, CIP-011 2,
CIP-012 1, CIP-013 3, and CIP-014 1.

The register contains 254 nodes across 14 stored standard revisions. At
`valid_at=2026-09-05`, interval selection returns 215 enforceable nodes (197
Part-granularity nodes) across 13 standard revisions.

## Domain-store census after materialization

| Table | Rows |
|---|---:|
| obligation_atoms | 310 |
| obligation_expressions | 254 |
| definitions | 3 |
| authority_assertions | 14 |
| internal_controls | 68 |
| activities | 68 |
| roles | 13 |
| systems | 13 |
| evidence_specs | 68 |
| evidence_artifacts | 0 |
| analysis_runs | 5 |
| claims | 1075 |
| claim_evidence | 2559 |
| findings | 1061 |
| work_items | 14 |
| change_scenarios | 2 |
| scope_revisions | 1 |
| asset_groups | 13 |

The latest materialization run `705b3fb8f1dc4c8e` processed all 254 register nodes,
68 internal documents and 4,357 content-derived internal assertions. Its current
215-obligation sweep produced 11 `SUPPORTED` and 204 proven `ABSENT` answers, with
zero extraction/anchor failures and zero `PRAGMA foreign_key_check` violations.
