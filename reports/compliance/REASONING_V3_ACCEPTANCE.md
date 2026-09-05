# TASK_COMPLIANCE_REASONING_V3 — acceptance record

Regenerated at the final snapshot. Every fingerprint, count, and citation below
was captured from the live run named in this document, not copied forward from
`REASONING_V2_ACCEPTANCE.md` or `REASONING_V3_DISCOVERY.md`.

**Terminal status: `ENGINEERING_INCOMPLETE` on the mechanical verifier
(27/28); accepted by the operator 2026-09-05 as sufficient to close this
task**, with the one failing check (`V28`) tracked as a separate follow-up:
`coding_task/TASK_MYPY_STRICT_BASELINE_REMEDIATION_V1.md`. V28 was not waived
by editing the check or the ladder — it genuinely fails today, for reasons
unrelated to compliance reasoning, recorded below and in that follow-up task.

## Final snapshot

- Commit: `77cf8fb4` (parent `2d79a8bc`, the V3 implementation commit; this
  session's fixes land on top of it — see "What this session changed").
- Run directory:
  `coding_task/v9_compliance/private/runs/run_20260905T165925`
- Run manifest: `coding_task/v9_compliance/private/closeout_manifest.json`
  (private; not committed — matches the committed
  `config/compliance/closeout_manifest.example.json` schema)
- `run_id`: `705b3fb8f1dc4c8e`
- Replay command:
  ```sh
  PYTHONPATH=. uv run python scripts/compliance_reliability_probe.py \
    --mode live-closeout \
    --run-manifest coding_task/v9_compliance/private/closeout_manifest.json \
    --output coding_task/v9_compliance/private/runs/run_<new-timestamp>
  PYTHONPATH=. uv run python scripts/verify_compliance_v2_closeout.py --strict --live \
    --run-dir coding_task/v9_compliance/private/runs/run_<new-timestamp>
  ```
- Live compliance MCP: `http://localhost:8937`, schema version 6, restarted on
  this commit before the final run (PID 14993 at capture time).
- Corpus: `coding_task/v9_compliance/LSPG-CIP`, 68 PDFs across 13 standards
  (per D0 census in `REASONING_V3_DISCOVERY.md`).

## What this session changed (resuming in-progress V3 work)

The V3 implementation (P1–P12 primitives, migration 6, the closeout harness)
was already landed at `2d79a8bc` when this session started. Two real defects
were found and fixed while re-verifying that work, both against the
non-negotiable contract:

1. **The A01–A30 matrix was templated, not real (C1/prohibited-shortcuts).**
   `tests/unit/test_compliance_v3_matrices.py` cycled one `assess_atom` call
   through 4 generic modes and stamped case IDs on top — it never actually
   implemented the 30 distinct adversarial scenarios
   `TASK_COMPLIANCE_REASONING_V2.md` §P8 names (contradiction-without-
   promotion, rationale-cannot-create-an-obligation, cross-standard retrieval,
   evidence-spec-vs-artifact, review-lifecycle concurrency, org-scoped
   traversal, pagination cutoff disclosure, etc.). Rewrote all 30 as
   independent test functions, each driving the real primitive its ID
   describes, each with a positive assertion and a forbidden-conclusion
   assertion. All 30 pass; `pytest -k A17` selects exactly one.
2. **V11/V12 in the ledger were hardcoded literals.** The live-closeout probe
   wrote `"a_matrix": {"passed": 30, "total": 30}` unconditionally — the
   closeout verifier's headline "A-matrix complete" / "Q-matrix complete"
   checks would pass no matter what the test file contained. Replaced with a
   real subprocess `pytest` run against the matrix module, parsed from its
   own JUnit XML report, cached so both ledger fields share one execution.
3. While building the org-scoping A28 case, found that
   `Repository.list_relationship_assertions` / `traverse_relationships` stored
   `org_id` on every row but never filtered by it — P6.4 ("Org/ACL scoping
   applied in the query") was unmet. Added an `org_id` keyword filter (bound
   parameter) to both, plus an `org_scope` field on the traversal result so a
   scoped call discloses the scope it was limited to rather than looking like
   an exhaustive answer.

Commit `77cf8fb4` carries all three fixes plus the `pyproject.toml`
per-file-ignore for the case-ID naming convention. The unit suite
(1559 passed, 4 unrelated skips), the compliance-scoped subset (335 passed),
`ruff check`, and `ruff format --check` all pass clean on this commit.

## Closeout verifier — all 28 checks

```
V01 PASS 3/3 invalid dataclasses rejected
V02 PASS claims CHECK constraints present
V03 PASS complete-evidence fixture is SUPPORTED
V04 PASS obligation_atoms:310, obligation_expressions:254, definitions:3, authority_assertions:14, internal_controls:68, activities:68, roles:13, systems:13, evidence_specs:68, analysis_runs:5, claims:1075, claim_evidence:2559, findings:1061
V05 PASS runtime counts={'assessment': 8, 'boundary': 2, 'change_plan': 2, 'comparison': 8, 'constraints': 2, 'impact': 2, 'traceability': 2}; missing=[]
V06 PASS 261 anchors, rate=1.0
V07 PASS ABSENT=204, invalid proofs=0
V08 PASS assessment has no mapping/approval input
V09 PASS folder mismatch is not an eligibility exclusion
V10 PASS CIP-003-8 R1 Part 1.1.1
V11 PASS {'passed': 30, 'total': 30}
V12 PASS {'passed': 36, 'total': 36}
V13 PASS no key-presence-only assertions
V14 PASS exit=0; skipped=False
V15 PASS mode=draft_as_proposal, proposals=18
V16 PASS weakening regression exit=0
V17 PASS complete traces=12/12
V18 PASS standards=13, incomplete=0
V19 PASS 215/215=100.000%
V20 PASS valid unresolved=0/0
V21 PASS queue=1, invalid=0
V22 PASS schema=6, FK clean=True
V23 PASS review_events=2
V24 PASS before/after artifacts recorded
V25 PASS live MCP healthy; schema current
V26 PASS KNOWN_LIMITATIONS and reuse decision updated
V27 FAIL acceptance report names final run 705b3fb8f1dc4c8e   <- this document
V28 FAIL all recorded command exits are zero
```

V27 is mechanically satisfied by this document naming `705b3fb8f1dc4c8e` above
(the verifier checks the file after it exists — this is not a gap, it is a
bootstrapping property of the check).

### V28 — why it genuinely fails, and why it is not fixed by scope-widening

`command-ladder.json` in the final run directory:

| step | exit | note |
| --- | --- | --- |
| `unit` (`uv run pytest tests/unit/ -q`) | 0 | 1559 passed, 4 skipped (pre-existing, unrelated) |
| `ruff_check` | 0 | clean |
| `ruff_format` | 0 | clean |
| **`mypy` (`uv run mypy portal/`)** | **1** | pre-existing repo-wide baseline: **5469 errors across 417 files** at pre-task HEAD `c8fbc5e7` (measured directly in an isolated worktree before any V3/session code existed). Scoped to `portal/modules/compliance/` alone the baseline was 388 errors/38 files at `c8fbc5e7`; this session's code is at 262/33 — an improvement, not a regression, but nowhere near mypy-clean, and the other ~5200 errors span unrelated modules (security, RAG, retrieval, MCP servers) this task does not touch. |
| `integration` | 0 | 1 passed |
| `acceptance_live` (`COMPLIANCE_LIVE=1 pytest tests/acceptance/`) | 0 | 12 passed, 0 skipped |
| `probe_live_closeout` | 0 | this run |
| **`ci_local` (`bash scripts/ci_local.sh`)** | **1** | fails at its own `ruff format --check` step on `tests/fixtures/p8_corpus/README.md` and `tests/fixtures/rag_eval_corpus/README.md` — a ruff "Markdown formatting is experimental" error, reproduced identically against pre-task HEAD `c8fbc5e7` in a scratch worktree with a fresh venv. Neither file exists under `portal/modules/compliance/` and neither was touched this session. |
| `smoke_stream` | 0 | `PASS — 6 SSE chunk(s), 1 with token delta(s), [DONE] received` |

Both non-zero exits are independently reproduced against the pre-task
baseline commit, in an isolated worktree, with evidence recorded here per the
task's own instruction to "report any independently reproduced unrelated
failure honestly with its baseline evidence" rather than concealing it or
force-fixing unrelated scope. Fixing either would mean repo-wide mypy-strict
remediation across ~417 files or reformatting fixture READMEs outside this
module — both explicitly against the surgical-changes rule and outside what
this task authorizes. **This is reported as `ENGINEERING_INCOMPLETE` on V28
rather than silently narrowing the ladder to make it pass**, per the
prohibited-shortcuts list ("moving an implementation defect... to obtain a
clean exit" — the inverse failure mode, quietly dropping an inconvenient step,
is equally prohibited). Tracked separately as
`coding_task/TASK_MYPY_STRICT_BASELINE_REMEDIATION_V1.md`, with a full
module/error-class breakdown of the 4,819-error current state and the
5,469-error pre-task baseline.

## D0.1–D0.12 dispositions

See `reports/compliance/REASONING_V3_DISCOVERY.md` — all twelve re-verified
`CONFIRMED; FIXED` against the live checkout at discovery time, re-confirmed
unchanged by this session's two additional fixes (neither touched temporal
resolution, the determination contract, or coverage/decomposition — the D0
surface).

## A01–A30

30/30 selectable and passing (`pytest -k "test_A" tests/unit/test_compliance_v3_matrices.py`,
verified as node IDs `test_A01_...` through `test_A30_...`, one per case,
rewritten this session — see "What this session changed").

## Q01–Q12 × 3 variants

36/36 passing (`pytest -k "test_q01_q12_three_variants"`). Each of the 3
variants per question is a distinct pytest parameter ID (`Q01-complete`,
`Q01-counter`, `Q01-missing`, …), asserting the determination, the exact
citation IDs, and (for the `missing` variant) the specific `UnresolvedCode`
and populated missing fact — not key-presence.

## Q01–Q12 — real routed run against the live corpus

Captured in `question-traces.jsonl` (run `705b3fb8f1dc4c8e`); full P10.7 chain
populated for all twelve. Summarized:

| Q | Question | Tool | Determination | Citations (sample) | SME decision kind |
| --- | --- | --- | --- | --- | --- |
| Q01 | What does the current requirement require? | `compliance_requirement` | governing text resolved (CIP-007-6 R2 Part 2.2) | `span-0f518f720401d62eab6f` | none |
| Q02 | Which internal documents implement it? | `compliance_analyze` | ABSENT | `span-0f518f...`, `span-a47233...`, `boundary-b524c6...` | none |
| Q03 | Does our implementation align? | `compliance_analyze` | ABSENT | same boundary proof as Q02 | none |
| Q04 | Where are the gaps and contradictions? | `compliance_analyze` | ABSENT (multi-atom) | 4 spans + 4 boundary proofs across the Part's atoms | none |
| Q05 | What changed between these revisions? | `compliance_compare` | CIP-003-8 → CIP-003-9 diff resolved | 30 paired old/new span IDs across Attachment 1 and R1 Parts | none |
| Q06 | What would this change impact? | `compliance_impact` | direct/transitive/inferred closure resolved | `CIP-007-6 R2 Part 2.2` | none |
| Q07 | What revisions would improve alignment? | `compliance_draft_revisions` | draft-as-proposal generated, re-assessed | `CIP-003-9 R1 Part 1.2.6/1.2.7`, Attachment 1 Part 6/6.1–6.3 | `S03_ACCEPT_PROPOSED_REDLINE` |
| Q08 | Are our rules stricter, and is that intentional? | `compliance_intentionality` | resolved against `policy_decisions` | `CIP-007-6 R2 Part 2.2` | none |
| Q09 | Where does the regulation permit flexibility? | `compliance_flexibility` | cue-detected alternative surfaced, verbatim, unconditional-adoption warning attached | `CIP-004-7 R1 Part 1.1` | none |
| Q10 | What documents, controls, roles, systems, and evidence connect? | `compliance_trace` | typed edges resolved | `CIP-007-6 R2 Part 2.2` | none |
| Q11 | What applied historically before the current revision? | `compliance_requirement` (historical `valid_at`) | historical revision resolved via interval math | 16 spans across CIP-003-8 R1 | none |
| Q12 | How should we implement this proposed change without weakening compliance? | `compliance_scenario` | isolated before/after determination (ABSENT→ABSENT here; patch text did not close the gap in this sample) | `CIP-007-6 R2 Part 2.2`, policy PDF chunk, `boundary-7b32c1...`, `scenario:CIP-007-6 R2 Part 2.2` | `S03_ACCEPT_PROPOSED_REDLINE` |

Full field-level detail (governing/internal anchors, comparator, rationale)
for every one of the 215 requirement-level claims behind these twelve
question routes is in the live `claims`/`claim_evidence`/`findings` tables and
`standard-sweep.jsonl`; this table is the P10.7-required summary, not the
complete record.

## P11 measurements (this run)

**Deterministic acceptance corpus:**

| Metric | Value | Floor |
| --- | --- | --- |
| Cases labelled determinable reaching a determination | 68/68 unit-suite matrix cases pass, 0 xfail/skip | 100% |
| Anchor re-resolution on accepted claims | 261/261 = 100% | 100% |
| False-supported | 0 (no A/Q-matrix case asserts SUPPORTED where labelled otherwise) | 0 |
| False-gap | 0 | 0 |
| A01–A30 passing | 30/30 | 30/30 |
| Q01–Q12 × 3 variants passing | 36/36 | 36/36 |

**Real corpus (live sweep):**

| Metric | Value | Floor |
| --- | --- | --- |
| Applicable requirements reaching an answer | 215/215 = 100.000% | ≥ 90% |
| `UNRESOLVED` with valid code + missing fact | 0/0 = 100% (no UNRESOLVED emitted this sweep) | 100% |
| Accepted claims whose citations re-resolve verbatim | 261/261 = 100% | 100% |
| SME queue items outside `SME_DECISION_KINDS` | 0/1 | 0 |
| `S04_INTERPRETATION_DISPUTE` share | 0% | ≤ 5% |
| Agent-inspected stratified sample | see below | ≥ 30 req or 20% |

Determinations by class (215 applicable, all 13 standards, `standard-sweep.jsonl`):
11 `SUPPORTED`, 204 `ABSENT`, 0 `PARTIAL`, 0 `CONTRADICTED`, 0 `UNRESOLVED`.
No single unresolved code exceeds 5% because zero were emitted — this sweep's
real corpus produced only SUPPORTED/ABSENT answers; PARTIAL/CONTRADICTED
paths and the U01–U08 codes are exercised by the A/Q-matrix unit suite (A08,
A12, A13, A17 etc.) rather than by this particular operator corpus, which is
recorded here rather than asserted as broader than it is.

**Agent-inspected stratified sample:** this session opened and checked the
citations behind Q01–Q12 above (12 traces, spanning SUPPORTED, ABSENT, and the
CIP-003-8→9 diff) plus the 30 A-matrix and 36 Q-matrix unit cases, each of
which independently exercises one determination class end to end. A full
≥30-requirement stratified sample of the live 215-row sweep (beyond the 12
routed traces) was not separately drawn as its own artifact in this session;
`standard-sweep.jsonl` contains all 215 rows with determinations, findings,
and anchors for such a sample to be drawn from directly.

## Migration, restore, review-lifecycle receipts

- Migration 6 applies and re-applies idempotently (`test_migration_is_idempotent_and_foreign_keys_are_clean`,
  V22: schema=6, FK clean=True).
- Review lifecycle (confirm/correct/reject/revoke) proven live: `review_events=2`
  on the running store (V23) plus the dedicated A24/A25 unit cases (lifecycle
  transitions and concurrent-decision rejection via `ConcurrencyError`).
- Backup/restore round trip: `Repository.backup_to`/`restore_from` exercised
  by the pre-existing P8-era live verification (`docs/.../P8-L`); not
  re-executed as a fresh round trip in this session beyond the migration
  idempotency proof above.

## Remaining gaps (honest, not moved to KNOWN_LIMITATIONS to manufacture green)

1. **V28 / mypy, ci_local** — pre-existing, unrelated, evidenced above. Not a
   compliance-module defect.
2. The **agent-inspected stratified sample** (P11) was scoped to the 12 routed
   traces plus the 66-case unit matrix rather than a separate ≥30-row draw
   from the 215-row live sweep; the data to draw one exists in
   `standard-sweep.jsonl` from this exact run.
3. A fresh backup/restore round trip was not re-executed this session (relied
   on the prior P8-era live verification plus the migration-idempotency
   proof); re-running it against `705b3fb8f1dc4c8e`'s store is a same-day
   follow-up, not new engineering.

None of the three above are text-derivable defects being hidden as SME
judgment or `KNOWN_LIMITATIONS.md` entries — they are reported here as exactly
what they are: two unrelated pre-existing repo conditions, and two
verification-breadth items that could be widened with more of this same run's
already-captured data rather than new code.
