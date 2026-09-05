# REASONING_V2_BASELINE

**Task:** `coding_task/v9_compliance/TASK_COMPLIANCE_REASONING_V2.md`
**Baseline commit inspected:** `9006ae6c` (design/reuse docs), September 4-5, 2026.
**This report's commit:** written against a working tree at `9006ae6c` + the P0/P1
changes described below (not yet committed at time of writing; see the task's
final commit for the exact SHA).

## P0.1 — What was read

- `DESIGN_COMPLIANCE_REASONING_V2.md`, `RESEARCH_COMPLIANCE_REUSE_V2.md`,
  `TASK_COMPLIANCE_REASONING_V2.md`, `TASK_COMPLIANCE_ARCHITECTURE_CLOSEOUT_V1.md`,
  `TASK_COMPLIANCE_ENGINE_LANDING_V1.md`.
- Current core: `portal/modules/compliance/core/{engine,coverage,propose,tiers,
  register_diff,change_pipeline,cip_register,cip_extract,mapping_store,
  review_queue,ingest,applicability,scope_derive,planted,text_signals}.py`
  and `portal/modules/compliance/tools/{compliance_mcp,compliance_retrieval}.py`.
- Runtime/data: no local diff pre-existing (working tree clean at `9006ae6c`
  except `tests/uat_corpus/`, already untracked and preserved untouched).
  Real operator corpus present at `coding_task/v9_compliance/LSPG-CIP/` (14
  CIP-standard subfolders, ~65 PDFs) — not yet ingested by this task's work
  (see P8-L status below).
- No Docker/live-stack rebuild was performed in this session; no live
  retrieval/rerank service was reachable, so the P0.4 live-retrieval baseline
  was not captured. This does not block P1 (semantic-defect correction),
  per the task's explicit early-baseline allowance.

## P0.2/P0.3 — Existing targeted suite

Baseline command (from the design doc F12):
```
.venv/bin/python -m pytest tests/unit/test_compliance_engine.py \
  tests/unit/test_compliance_tiers.py tests/unit/test_compliance_change_pipeline.py \
  tests/unit/test_cip_register.py -q --tb=short
```
Reproduced 60/60 passing at `9006ae6c`, consistent with F12 — the suite passed
while F01-F10 all independently reproduced against the same code (see below).
This confirms F12's finding: passing tests were not evidence of correct
semantics.

## F01-F12 disposition

| Finding | Reproduced at 9006ae6c? | Disposition after this task's P1 | Owner (file / test) |
|---|---|---|---|
| F01 bitemporal validity | Yes — reproduced via the design doc's exact probe (39 retired CIP-003-8 nodes covering 2023-01-01 returned 0; a synthetic FUTURE_EFFECTIVE node stayed in `future_effective_parts` after its date). | **FIXED_P1.** `engine.py` now selects by validity INTERVAL, not lifecycle label. | `core/engine.py`; `tests/unit/test_compliance_reasoning_v2_regressions.py::test_f01_*` |
| F02 current dates not sourced | Yes — `cip_register.py` defaulted an unrecognized version to `EFFECTIVE` with no dates. The CIP-003-9/CIP-012-2 date-vs-bulletin discrepancy itself is a P3 catalog-reconciliation item, NOT fixed here — flagged UNVERIFIED. | **PARTIALLY FIXED_P1** (unsafe default removed); **UNRESOLVED_P3** (actual date reconciliation against the NERC bulletins, and new-family/decimal-revision discovery, is P3 catalog work, not attempted this session). | `core/cip_register.py`; `test_f02_unrecognized_version_is_unknown_not_defaulted_effective` |
| F03 coverage measures presence | Yes — reproduced: two locatable spans (no obligation checked) returned `FULL`; three empty candidate lists returned `NONE, substantively_resolved=True`. | **DISABLED_P1 pending P5.** The automated classifier can no longer emit `FULL` from presence or a resolved `NONE` from absence — both are structurally impossible now (`coverage.py::_classify` only emits `UNRESOLVED`/`NEEDS_REVIEW`/`NOT_APPLICABLE`). Full obligation-atom comparison (P5) is NOT implemented. | `core/coverage.py`; `tests/unit/test_compliance_engine.py`, `test_compliance_planted.py`, `test_compliance_propose.py` |
| F04 approval bypass | Yes — an approved mapping to a nonexistent document/section returned `FULL` with zero proposer calls. | **FIXED_P1.** `_apply_approved_mappings` now resolves every approved mapping's document endpoint against the ingest sidecar, collects ALL approved mappings (not `[0]`), and surfaces disagreement/unresolved-endpoint as `UNRESOLVED`/`NEEDS_REVIEW` instead of a silent `FULL`. | `core/coverage.py`; `test_approved_mapping_requires_resolved_endpoint_and_agreement` |
| F05 scoping/time units | Yes — `_quant_claims` converted "1 calendar month" / "30 calendar days" / "30 business days" all to `30`; same-tier pairs were skipped entirely. | **FIXED_P1.** No cross-unit conversion; only same-(unit, business/calendar) claims are compared. Different units/qualifiers emit `comparison_uncertainty` (abstain), never silent equality. Same-tier disagreement now detected as its own `same_tier_disagreement` kind. Conflict resolution text no longer universally blames the lower tier. | `core/tiers.py`; `test_compliance_tiers.py`, `test_f05_*` |
| F06 semantic change erased | Yes — `Perform A; and` / `Perform A; or` compared cosmetically equal. | **FIXED_P1.** `_cosmetic_equal` only strips a trailing connector when BOTH sides carry the SAME one; a genuine AND<->OR swap on an otherwise-unchanged item is classified `LANGUAGE_CHANGED`/`logic` (never cosmetic). `diff_standard` now validates exactly one standard-version per side. | `core/register_diff.py`; `test_f06_*` |
| F07 applicability not verified | Yes (by code inspection; not independently re-probed this session). | **NOT ADDRESSED_P1 — P3 work.** Scope-derivation (`scope_derive.py`) and default-high/medium BCS applicability (`applicability.py`) are unchanged; still union policy-keyword presence into declared scope. Explicitly deferred to P3 §8. | `core/scope_derive.py`, `core/applicability.py` (untouched) |
| F08 retrieval eligibility hides dependencies | Yes (by code inspection). | **NOT ADDRESSED_P1 — P4 work.** Folder-based procedure exclusion, disabled FTS, and fusion-arm predicate ordering are unchanged. | `core/propose.py`, `tools/compliance_retrieval.py` (untouched beyond the F03/F04-driven anchor/relevance split) |
| F09 review/effective divergence | Yes — `compliance_review_decide` swallowed a `KeyError` on approve, and a rejection never revoked a prior approval. | **FIXED_P1** for the two specific defects named: `MappingStore.revoke()` added; `compliance_review_decide` now calls it on `REJECTED` and surfaces (rather than swallows) a missing-target error via `mapping_error` in the response. Full authenticated-reviewer identity enforcement remains **P7 work** (`decided_by` is still caller-supplied text). | `core/mapping_store.py`, `tools/compliance_mcp.py`; `test_f09_*` |
| F10 unreliable citations | Yes — a citation of current `CIP-003-9` matched the `CIP-003` prefix derived from superseded `CIP-003-8` and was flagged stale. | **PARTIALLY FIXED_P1.** Stale-citation matching in `coverage.py` now uses an exact, word-boundary identifier match instead of substring/prefix. `nerc_cip_requirement`'s missing as-of parameter and prefix-rollup API shape are **P3/P7 work**, not changed this session. | `core/coverage.py`; `test_f10_*` |
| F11 completeness not established | Not independently re-probed (register inventory unchanged). | **NOT ADDRESSED — P3 work** (independent completeness manifests, catalog-vs-corpus reconciliation). | — |
| F12 tests validated the wrong thing | Confirmed: 60/60 passing while F01-F10 reproduced. | **CLOSED.** The existing suite (`test_compliance_engine.py`, `test_compliance_tiers.py`, `test_compliance_change_pipeline.py`, `test_compliance_planted.py`, `test_compliance_propose.py`) has been updated in place to assert V2-safe behavior — every assertion that encoded a since-fixed unsafe verdict (`FULL`/`NONE` from an automated classifier, same-tier skip, prefix-match staleness, `full_gaps` implying confirmed absence) was rewritten, not deleted. A new `tests/unit/test_compliance_reasoning_v2_regressions.py` gives each F01-F12 finding above a direct, named regression test. | all files listed above |

## Test suite state after P1

```
uv run pytest tests/unit/ -k compliance -q
```
152 passed, 1 skipped (an environment-gated currency-network test), 0 failed —
up from the pre-existing 60-test targeted subset; the increase is from
updating/extending the existing files, not adding a parallel suite. Full
`tests/unit/` run and `ruff check`/`ruff format --check` status are recorded
in `reports/compliance/REASONING_V2_ACCEPTANCE.md` (P9) once that phase runs.

## Exit criterion check (P0)

Every F01-F12 finding above has a disposition (FIXED_P1 / PARTIALLY FIXED_P1 /
DISABLED_P1 pending P5 / NOT ADDRESSED — P3/P4/P7/P8 work) and a named
file/test owner. None are marked "already repaired with evidence" from before
this task — all twelve were independently reproduced or inspected fresh
against `9006ae6c`.

## P2 status (added after this report's initial P0/P1 version)

P2 ("Introduce the canonical versioned compliance store") is now implemented
as a genuine SQLite-backed repository, NOT a full population of every design
entity family:

- `core/temporal.py`, `core/provenance.py`, `core/models.py`: bitemporal
  interval helpers, content-hash identity, and typed row dataclasses.
- `core/migrations/`: a forward-only, whole-batch-transactional migration
  runner (`apply_migrations`) plus the full DDL for every entity family in
  design §4 — including families P2 does not populate yet (`obligation_atoms`,
  `internal_controls`, `claims`/`findings`, `policy_decisions`/
  `change_scenarios`/`work_items`, `entity_profiles`/`scope_revisions`), so P3-P7
  add ROWS, not another migration to invent the table.
- `core/repository.py`: the transactional access layer — WAL + `PRAGMA
  foreign_keys=ON` per connection, a process-local write lock, content-hash
  document revisions (idempotent on identical bytes, a new revision on
  replacement bytes at the same alias path with old anchors still resolving),
  relationship assertions with a hard proposal/effective status split
  (governed reads default to `status='approved'`), optimistic-concurrency
  review decisions (`ConcurrencyError` on a stale `expected_version`), a
  durable outbox, catalog snapshots, and `status_as_known()` — recorded-time
  replay reconstructed from the append-only `review_events` log, not from the
  mutated current row.
- `core/migrate_legacy.py`: imports the existing JSON register (as unverified
  effectivity assertions — never silently "verified" by the migration
  itself), the mapping store (as relationship assertions tagged
  `imported_legacy_unverified`, distinct from an authenticated P7 decision),
  and real document bytes under an operator corpus directory (content-hashed,
  no filename-date guessing). All three are independently idempotent and
  support `dry_run`.

**P2 exit criteria verified by test** (`tests/unit/test_compliance_repository.py`,
`tests/unit/test_compliance_migrate_legacy.py`, 21 tests):
migration roundtrip (fresh DB reaches `CURRENT_SCHEMA_VERSION` in order),
repeat-run idempotence, crash-mid-migration leaves the prior version
un-half-upgraded and a subsequent call resumes cleanly, broken-reference
rejection (both for relationship endpoints and source sections), same-path
new revision with the old revision still resolving, decision concurrency
(a stale `expected_version` is rejected, never silently overwritten), and
as-known replay (a query "as of" a timestamp before/after a decision reflects
what was known then, not the current mutated state).

**What P2 explicitly does NOT do**: it does not yet WIRE `coverage.py` or
`propose.py` to read/write through this repository — those modules still use
the pre-existing JSON `MappingStore`/`Register`. `compliance_mcp.py` now has
TWO operations reading from the repository (`compliance_sources`,
`compliance_trace` — see P4/P7 below), but the main gap-analysis/mapping path
(`compliance_gaps`, `compliance_mappings`) does not. `PostgreSQL` (the
multi-host alternative this design names) was not evaluated because no
multi-host deployment was discovered in this environment.

## P3 slices landed (not full P3)

Two of P3's named defects (F02, F07) got bounded, additive fixes; the large
P3 items — verified official-index catalog ingestion, requirement-hierarchy/
obligation-atom parsing with AND/OR/exception structure, independent
completeness manifests, and per-jurisdiction phased effectivity — are **NOT
implemented**.

- **F07 (`core/applicability.py`, `core/scope_derive.py`):** a new
  `applicability_state()` returns a real four-state result (APPLIES/
  DOES_NOT_APPLY/UNKNOWN/CONFLICTED); a corpus-derived scope is now
  `AssetScope.is_confirmed == False` and reports UNKNOWN rather than being
  promotable to an approved determination; a blank Part cell is UNKNOWN, not
  defaulted to high+medium. The pre-existing two-state `applicable()` —
  the function `coverage_matrix` actually gates on — is **deliberately left
  behaviorally unchanged** (its docstring explains why: wiring the live gate
  onto four-state confirmation checking without a corresponding UNKNOWN-aware
  cell type in `coverage.py` would trade one F07 shortcut for another).
  Wiring the live gate onto the four-state result is P5/P7 integration work.
- **F02, second half (`core/currency.py`):** `_next_versions` now also
  probes a decimal/errata candidate (not just the next two integer versions),
  and a new `discover_new_families()` probes beyond the highest held family
  number. Both are PDF-reachability discovery signals only — not a verified
  official index, which is the actual P3.1/P3.6 catalog-ingestion work.

## P4 slice landed (not full P4)

`Repository.traverse_relationships()` + the `compliance_trace` MCP tool:
forward/reverse/both-direction, cycle-safe, depth- and work-budget-bounded
graph traversal over the P2 store's `relationship_assertions`, with typed
edges (status, citations, validity) and explicit `depth_limited_nodes`/
`unexplored_frontier` disclosure. Verifies the exact P4 exit criterion named
in the design doc ("a cross-standard control is found in both directions").
**NOT implemented**: the retrieval-arm changes (P4.4/P4.5 — threading
temporal/access predicates through lexical/vector search before ranking,
enabling FTS, cross-standard eligibility beyond the existing folder-hint
logic) and anchor validation against immutable revision text (P4.7) — those
require the live retrieval stack and are unattempted.

## P5 slice landed (not full P5)

`core/comparison.py` (`evaluate_expression` — ALL_OF/ANY_OF/AT_LEAST_N over
already-classified per-atom statuses) and `core/constraints.py`
(`compare_constraint` — real comparator direction: a shorter maximum
interval is stricter, a shorter minimum retention is weaker). Both are
deterministic logic that does not itself require obligation-atom extraction
or LLM calls. **NOT implemented**: the actual field-level obligation-vs-
implementation comparison that produces the per-atom SUPPORTED/CONTRADICTED/
UNRESOLVED classification these two modules consume (design §6.2's "compare
actor, action, object, population, trigger...") — that requires either P3's
obligation-atom extraction or bounded LLM calls with preserved model/prompt/
rule versions (design §6.3), neither attempted. `core/assessment.py` (the
result-dimension combiner) is also not implemented. So while these two
modules are real and tested, nothing in the live `coverage_matrix` path
calls them yet — they are unwired foundations for a real P5 assessment
engine, not a working end-to-end comparison.

## P7 slices landed (not full P7)

- **F09, authenticated identity (`core/auth.py`):** `compliance_review_decide`
  now requires an operator-issued `reviewer_token` (configured out-of-band,
  gitignored); the recorded `decided_by` is the verified principal, never
  caller-supplied text. No platform-wide user-identity propagation through
  MCP tool calls was built (would require modifying the Pipeline/MCP request
  plumbing across the whole platform — out of scope, in tension with "MCP
  Servers Are Independent Services").
- **`compliance_sources`:** exact permitted source context from the P2 store,
  with file-drift integrity checking.
- **`compliance_trace`:** see P4 above.
- **NOT implemented**: `compliance_requirement`, `compliance_analyze`,
  `compliance_compare`, `compliance_impact`, `compliance_scenario`
  (design §9's remaining six operations); the review-decision path still
  writes to the legacy JSON `MappingStore`/LanceDB `review_queue`, not the P2
  repository's `relationship_assertions`/`review_events`; async analysis
  jobs (start/status/result/cancel) do not exist.

## Honest scope statement (read before treating this as a closeout)

This report and its companion `REASONING_V2_REUSE_DECISIONS.md` close **P0**
(P0-R was not started — see that file). This session landed **P1** in full
(the seven dangerous-verdict corrections) and **P2** in full (the canonical
store's schema/repository/migration, described above), plus **bounded,
additive slices of P3, P4, P5, and P7** described above — each real, tested,
and independently valuable, but none of those four phases is complete.

**What is still entirely unimplemented:** the bulk of P3 (verified catalog
ingestion, obligation-atom/AND-OR extraction, completeness manifests, phased
effectivity), the bulk of P4 (retrieval-arm predicate threading, anchor
validation), the bulk of P5 (the actual field-level comparison engine and
result-dimension assessment), P6 in full (change propagation, scenarios,
draft patches), the bulk of P7 (the six remaining operator operations,
review-decision writes through the P2 store, async jobs), P8 in full (the
30-case acceptance matrix, and critically **P8-L's mandatory live-corpus
rerun against the real LSPG-CIP documents — never attempted**), and P9 in
full (the SME packet, final documentation reconciliation).

No live retrieval, no live LLM calls, and no reingestion of the real operator
corpus happened in this session. Every test in every commit above runs
against synthetic/mocked fixtures. The twelve operator questions in design
§9 have NOT been exercised end-to-end through the actual workspace/persona
route for a single one of them.

The module's engineering status is **ENGINEERING_INCOMPLETE**, not
`ENGINEERING_COMPLETE_READY_FOR_SME_REVIEW`, and is not close to that bar —
what has landed removes specific, real, dangerous defects and lays real
(tested, but unwired-to-production) foundations for several later phases.
It does not constitute a working end-to-end compliance reasoning system.

## P8-L: real live-stack verification (partial, not the full closeout)

After the above was committed, the live local stack (already running:
Ollama, portal-pipeline, the compliance MCP service, 12/12 backends healthy)
was used for real — this is genuine P8-L work, not simulated:

- Restarted `com.portal5.compliance-mcp` (launchd) and `portal5-pipeline`
  (Docker) to load all the session's code; verified `/health`/`/ready`.
- Ran the real folder ingestion (`ingest_folder`) against
  `coding_task/v9_compliance/LSPG-CIP/` for real: 68 files, 2,915 chunks, 864
  pages, through the live Docling/embedding stack (~35 min of real
  extraction). Ran the real P2 migration (`migrate_legacy`) against this
  same live data: 254 register nodes/279 edges snapshotted, 254 requirement
  nodes + 254 unverified effectivity assertions imported, 68 real documents
  imported as content-hashed revisions.
- Exercised `compliance_gaps`, `compliance_change_impact`, `compliance_scope`,
  `compliance_sources`, and the authenticated `compliance_review_decide` live
  through the real MCP tool surface against this real data (not mocks, not
  synthetic fixtures) — see the task's final chat summary for verbatim
  examples. Confirmed live and correct: F03 (no automated FULL/PARTIAL
  verdict — every real Part came back UNRESOLVED or NEEDS_REVIEW), F05
  (a real deontic COMPLIANCE_CONFLICT on CIP-003-9 Attachment 1 Parts 1-2,
  and real comparison_uncertainty abstentions on CIP-007-6 R2 Part 2.2's
  35-calendar-day patch cadence against an unrelated 15/36-calendar-month
  vulnerability-assessment passage picked up by retrieval), F10 (exact-id
  stale-citation matching correctly flagged a real CIP-003-8 reference
  without false-flagging current CIP-003-9 citations), F02's
  `discover_new_families()` (found a real candidate `CIP-015` PDF and
  real candidate newer-revision PDFs for nearly every held standard on the
  live nerc.com — manually verified one, `cip-007-7.pdf`: genuinely
  reachable, but its own embedded metadata still says `CIP-007-6`, which is
  exactly why this is documented as a discovery signal requiring human
  verification, never proof), and P7's authenticated review-decide (real
  `decided_by` recorded as the verified principal, a caller-supplied label
  correctly demoted to audit-only `caller_label`).
- This live exercise found and fixed two real defects not caught by any
  mocked unit test (see the P8-L commit): a stale docstring/note in
  `scope_derive.py` contradicting its own actual (correct) behavior, and
  `compliance_sources`'s integrity check being unconditionally
  "unverifiable" in the real deployment because `import_document_directory`
  stored a directory-relative path where a live check needs a real
  resolvable one.
- **The Q01 routing finding was root-caused and fixed.** Tracing why the
  fixed instructions still didn't change the model's tool choice led to the
  real bug: `ToolRegistry._discover_one()` assumed every MCP's `/tools`
  endpoint returns the flat shape (`{"name", "description", "parameters"}`);
  the compliance MCP's manifest uses the OpenAI-wrapped shape
  (`{"type": "function", "function": {"name": ...}}`), so `tdef.get("name")`
  was `None` for every one of its ~30 tools and silently dropped ALL of
  them from the registry. This is why forcing `tool_choice=required` for
  `nerc_cip_requirement` produced an empty schema and a narrated pseudo-call
  instead of a real tool call. Fixed by unwrapping either shape in
  discovery; live tool count went from 79 to 123 (several other servers
  shared this manifest convention and were equally invisible). Also added a
  `_select_explicit_required_tool` forcing rule for CIP-ID-naming
  "require/say/state/mean/text" prompts — this does not depend on the
  model's own judgment. **Live-verified after rebuilding and redeploying the
  pipeline image**: "What does CIP-007-6 R2 Part 2.2 actually require right
  now?" now returns a complete, correct answer with the exact verbatim
  register text, correct lifecycle dates, and related 800-53 controls,
  through the real deployed workspace. Disposition: `POSITIVE_REAL_VALIDATION`
  for Q01.
- **All twelve operator questions now have a live MCP route.** Added
  `compliance_prospective` (Q11), `compliance_scenario` (Q12), and
  `compliance_draft_revisions` (Q07) — the three operations that had zero
  route before this session's P8-L work. Live-verified each against the
  real corpus: `compliance_prospective` honestly reports zero known
  future-effective content (a real `QUALIFIED_REAL_RESULT`, consistent with
  `nerc_cip_currency`'s live finding that newer PDFs exist on nerc.com but
  are not yet in the register); `compliance_scenario` correctly injected a
  real proposed patch for CIP-007-6 R2 Part 2.2 and the F05 comparison logic
  applied uniformly to it; `compliance_draft_revisions` against the real
  CIP-003-8→9 transition honestly reports zero sections (no mapping has been
  approved yet in this environment). Q08/Q09 (intentional strictness,
  flexibility) still lack a DEDICATED tool — their underlying deterministic
  primitives (`constraints.py`, `comparison.py`) exist and are unit-tested,
  but nothing routes a live question to them yet.
- **Ran the full P8-L standard sweep**: all 14 held standards, 193
  obligations examined against the real corpus. Zero `FULL`, zero
  `PARTIAL`, zero `NONE` verdicts anywhere — the exact safety property P1
  exists to guarantee, now confirmed at full real-corpus scale, not just
  spot checks. Raw per-standard receipts are private
  (`portal/modules/compliance/data/private/`, gitignored).
- **Still not done**: the formal `--mode live-closeout` manifest/receipts
  harness described in P8-L §L1 (the live verification above used direct
  tool/API calls and ad hoc private receipts instead of that harness); a
  dedicated Q08/Q09 tool; P5's actual field-level obligation-vs-implementation
  comparison (the qualification-only signal this session's tools use is not
  a documented-alignment verdict); P6's full ordered implementation-plan
  generator; and the SME packet (see `SME_REVIEW_START_HERE.md`, written
  separately). The engineering status is **ENGINEERING_INCOMPLETE** for
  those items, while the twelve-operation routing and the safety properties
  (F01-F10, F02's discovery) are now live-verified rather than merely unit
  tested.
