# RESUME — compliance reading architecture (one authoritative assessment path)

**Status (2026-09-14 08:48Z):** the full offline qualification **completed** on
fixed revision `36a81bb7` — stage1 26/26 executed (13 PASS / 13 FAIL, exit 1),
stage2 three observations each for cases 01–05 (exit 1), stage3 the deployed
scoped-R2 route **16/16 PASS (exit 0)**. Architecture acceptance is **NOT green**:
the live 26-case criterion in §4 is not met. The §5D route and completed-result
items ARE now closed. Full census, per-case dispositions and the stable-vs-
intermittent split are in `reports/compliance/READING_REPAIR_20260913.md`
("Full offline qualification").
**Branch:** `main`. **Spec:**
`docs/IMPLEMENTATION_BRIEF_COMPLIANCE_READING_20260912.md` (rev 2).
**Baseline commit:** `2ef55701` (the design brief's snapshot).

This is the pickup document. Read it with the spec; the spec is the authority on
*what correct means*, this file records *what is done, what is known, what
failed, and how to finish*.

---

## 1. What is done

One authoritative service now owns every substantive verdict; every projection
derives from its `AssessmentResult`.

| File | State |
|---|---|
| `core/determination.py` | new records (`AssessmentRequest/Result`, `GoverningBundle`, `SourceSlice`, `CandidateSet`, `AlignmentResult`, `CoverageExplanation`, `ScenarioOverlay`, `ConstraintBinding`, `AlignmentRecord`, …); codes U09–U13 |
| `core/migrations/schema.py` | migration 7: `assessment_results` + run lifecycle columns |
| `core/repository.py` | `record_assessment`, `get_assessment`, `assessments_for_run`, `create_run`/`update_run`/`get_run`/`mark_interrupted_runs` |
| `core/assessment_source.py` | governing bundle (complete Part + lead-in + references), `CorpusSnapshot`, full-text `CandidateSet`, exact `materialize_overlay` |
| `core/obligation_alignment.py` | `align_part` — categorical SAME/DIFFERENT/UNKNOWN quorum; every candidate must appear or `valid=False`; constraint bindings with literal validation |
| `core/gate.py` | `compare_aligned` (SAME only; unchanged `compare_constraint`), `run_aligned_gate` (authoritative full governing text; no `"or delegate."`) |
| `core/assessment_report.py` | `explain` — one source-linked report call, IDs only, closed consistency rules |
| `core/assessment.py` | `assess_part(request, context) -> AssessmentResult`; U03/U04/U09/U10/U11/U12 emitted |
| `core/assessment_service.py` | `assess_requirement`/`build_requests` |
| `core/assessment_runs.py` | `start_run`/`run_status`/`run_result`/`cancel_run`; one worker; durable states |
| `core/coverage.py` | `coverage_matrix(context=…)` classifies via `assess_part` |
| `tools/compliance_mcp.py` | gaps/analyze default to `operation=start|status|result|cancel`; trace resolves assessment IDs; exact overlays |
| `core/operations.py`, `scenarios.py`, `change_pipeline.py`, `scripts/materialize_compliance_v3.py` | route through `assess_part`; scenarios use pinned before/overlay-after; no hardcoded SUPPORTED; materialization emits no verdict by default |
| acceptance | `tests/data/compliance_reading_acceptance.json`, `tests/unit/test_compliance_reading_acceptance.py`, `scripts/verify_compliance_reading_acceptance.py` |

## 2. Validation status — latest evidence overrides earlier checkpoints

- Fast acceptance remains 26/26 PASS (hermetic, not live proof).
- The six test-transport regressions are fixed. Consolidated units:
  **1,815 passed, 4 skipped**, 219.26 s, in
  `/tmp/compliance_reading_repair_resume_units.log`. Two later literal/pair-schema
  regressions passed with the alignment/acceptance suite (77 tests).
- Lint/format and focused mypy pass. Complexity including the two new untracked
  tests passes without any budget increase. System validation: **211 passed,
  0 failed, 1 warning, 1 skip**, 122.22 s (`--skip-pytest`, units run separately).
- The latest repair adds the missing governing ID-to-text mapping and recovers
  the missing R2 parent header from the register's hash-verified public PDF.
  It fixes numeric vote aggregation, literal selection and pair response schema.
- Earlier controls `20260913T165339037987Z` failed cases 10 and 23. These are
  diagnosis receipts, superseded for qualification by the repaired packet.
  Development control `20260914T005023434854Z` was intentionally interrupted
  when the final protocol was frozen; do not count it as a completed run.
- Targeted final control job: `/tmp/compliance-reading-repair-20260913/final-repair-controls.log`
  and `.exit`, cases **02,08,10,23** only. Read its printed receipt directory and
  completed summary. Its final disposition is recorded in the repair report.

## 3. What failed live, and what was fixed

A full `--live --runs 1` pass over all 26 cases ran ~2h51m and returned **26/26 FAIL**. Two defects in *our layer* (not the models) dominated:

1. **Council cite-or-drop rejected real citations.** Seats reasoned correctly but cited the human document names (`B21.txt`, `A22.txt`, `L22.txt`); the packet allowlist only held the opaque chunk hash as `commitment_id`, so a correct seat was dropped as "off-packet" (case 07: 2/3 seats dropped; case 02: 1/3). **Fixed:** `gate._build_aligned_candidate` now sets `commitment_id` to the human document name (plus the stable id), and `obligation_alignment` carries `document_id` on every `AlignmentRecord` so `assessment_report._matches_consensus` matches document-name citations. `council.py` internals untouched.
2. **One shared fixture KB leaked decoys.** Every case retrieved top-15 across all 22 fixture docs, so case 02 (A22+B22+V) also saw L22/S22/M22. **Fixed:** the live runner ingests only each case's declared candidate documents into an isolated per-case KB (`<kb>-c<id>`).

Two live defects found earlier and already fixed:
- alignment output truncated at the council's 900-token cap → dedicated 4096-token alignment transport (`obligation_alignment._ollama_alignment_seat`, routed in `assessment_runs._guarded_seat`);
- the reader returned correct relations but omitted the single unambiguous selectable slice ids → `_resolve_slices` fills the system-owned candidate/primary-governing slice (off-packet ids still rejected).

Live case 02 re-run after the fixes passed: **`got=FULL`**.

## 4. What is expected (acceptance, from spec §7/§7.1)

- The 26 cases must pass **live**, with real configured models, per-run receipts, and the exact required citations / excluded decoys / gap ids / resolution flags.
- Cases 02–20 and 25–26 via the routed async `compliance_gaps`; 21–24 via controlled failures on the real route; 01 against the pinned operator corpus (actual derived scope stays UNKNOWN; conditional documentary FULL reported separately).
- Run the positive + three supply-chain decoy cases **three times each**; do not average away a false PARTIAL.
- **No architecture-wide completion claim** until the live suite is green (spec §9).

## 5. Ordered execution plan for the resuming coding agent

Read the implementation brief and `reports/compliance/READING_REPAIR_20260913.md`
first. Current HEAD is `68130a7387dc74262a1c0abfe1b57561c119855e`; the repairs
are in the working tree. Inspect `git status` and concurrent work before edits.
Do not reset the checkout or discard the pre-existing untracked implementation
brief. Do not rerun the original failed supervisor.

### A. Recheck the repaired baseline; do not repeat the diagnosis blindly

The stale test selectors, complexity excess, ID-to-text omission, missing R2
header, numeric binding aggregation and live gap-ID protocol are repaired.
Read the repair report's "Further code repairs" section for exact changes and
regressions. The gap checker now resolves fixture handles to unique live IDs by
kind and exact governing/counterevidence source identity; no expected answers
enter model requests. Preserve those identity checks and the source validators.
Re-run preflight only if the checkout changed or the latest receipts require it.

### B. Understand historical failures and verify the targeted repair results

Receipt root:
`coding_task/v9_compliance/private/reading_acceptance/20260913T165339037987Z/`.
Each case has `run-0.json`, `checks-0.json`, and `trace-0/model-*.json`; the root
has `manifest.json` and a completed `summary.json`.

- Case 10, run `c3541a3cc77e4237`, 433.98 seconds / 10 model calls: native
  JSON Schema fixed scalar formatting, but Granite and Mistral classified the
  40-day L22 cadence as DIFFERENT. L22 was excluded, so arithmetic stayed empty.
  The council returned PARTIAL; the reporter then cited excluded L22 as
  counterevidence and validation correctly returned U11. Inspect alignment
  aggregation/binding selection and packet semantics. The earlier progress
  statement that the arithmetic path was exercised was premature: it was not.
- Case 23, run `a8ef532c8dd3466d`, 236.45 seconds / 3 model calls: Mistral bound
  35 days to the Part 2.1 reference slice, which contains no such quantity;
  Granite called the cadence `min_retention`. Alignment became U09 before the
  council-timeout injection could execute. This does not qualify U10 handling.
- Retain case 08's false FULL in `20260913T164120807797Z`. Two council seats
  missed the source-identification omission despite receiving the full Part. That packet lacked the parent R2 header,
  which is now repaired; do not call the old packet fully assembled. The brief forbids changing council prompts, roster, quorum, overrides or
  arithmetic to force acceptance. Distinguish integration defects from model
  semantic failures; no lexical SAME override or retry-until-green policy.

The diagnosis agent owns the targeted repair controls (02,08,10,23). After any further justified repair, run only the affected controls,
retain every attempt, and record which code fingerprint produced it. An
unresolved semantic/design failure must be documented rather than mislabeled
as an infrastructure block or a pass. It need not prevent collecting the rest
of the full suite once the instrument itself is sound.

### C. Execute and monitor the full qualification on a fixed code revision

Run these sequentially, with no concurrent model acceptance workers:

```sh
uv run python scripts/verify_compliance_reading_acceptance.py --live --runs 1
uv run python scripts/verify_compliance_reading_acceptance.py --live --cases 01,02,03,04,05 --runs 2
```

The first is all 26 cases; the second adds two repetitions of the real-corpus
positive (01), controlled positive (02), and three supply-chain decoys (03–05),
giving three observations each on the same code/model configuration. Case 01
retains actual-scope uncertainty and evaluates conditional documentary support
separately. Its real-corpus model calls can materially extend total duration. Do not use `&&` to suppress repetitions after a
semantic FAIL. If code changes between runs, clearly identify the superseded
qualification and collect the required repeats on the final configuration.
Budget several hours; prior ~3-hour figures are estimates, not a deadline.

Use a fresh **one-shot launchd job** for each stage, using the existing
`/tmp/compliance-reading-repair-20260913/structured.sh` and `structured.plist`
as templates. Give each job a unique label and new log/exit paths, replace the
command, retain `KeepAlive=false`, and bootstrap into `gui/$(id -u)`. The wrapper
must save the child exit code to `.exit` and log it before exiting zero to avoid
supervisor restarts. Never overwrite previous receipts/logs. Those `/tmp`
templates are local artifacts; recreate them if absent using the same settings.

Monitor active run IDs, progress and model-attempt timestamps. Inspect any
stalled call against its bounded transport timeout; do not launch a second
suite simply because a call is slow. Require `.exit` plus `summary.json` with
`complete=true`; HTTP 200 or wrapper exit zero does not mean acceptance passed.
Run receipts are gitignored; never force-add private corpus/model traces.

### D. Route verification, final gates and closeout

- Include a scoped R2 request as well as isolated Part requests, as required by
  brief §7.1. The default verifier exercises isolated Parts; do not claim its
  case labels prove the separate full-R2 request. Capture deployed HTTP
  `compliance_gaps` start with standard `CIP-007-6`, requirement `CIP-007-6 R2`,
  the pinned KB, explicit scope/conditional-scope disclosure and effective date,
  then status/result and all four Part assessment IDs.
- The verifier exercises the registered asynchronous handler in-process, with
  real acquisition and controlled faults. Separately verify the deployed MCP
  HTTP start/status/result lifecycle and original effective date/KB/scope after
  restarting the service with the final code. Completed-result verification
  remains outstanding; earlier HTTP evidence covered only pending status/result.
- Run fast acceptance, full units, lint/format, focused mypy and the system
  validator after the final changes. Refresh wiki coverage if module surfaces
  changed. Full-repo mypy has documented baseline debt; do not hide new errors
  behind it or repair unrelated debt as part of this task.
- Update this file and the repair report with all 26 outcomes, all required
  repeats, exact run IDs, source/code/model fingerprints, elapsed time and model
  call counts. List each remaining failure and its evidence-based disposition.
- No architecture-wide acceptance claim until the required live criteria pass.
  If a prohibited council/design change is needed, report the concrete failure
  and boundary. Keep commit/push status explicit and preserve concurrent work.

## 6. Known deviations / limits

- `coverage.py` keeps the legacy context-less `_shares_topic`/`detect_conflicts`
  path for pre-existing component tests; the product path (`context=`) never
  uses it. Removing it means migrating those legacy tests.
- `assessment_runs.build_requests_for` duplicates the argument composition now
  in `assessment_service.build_requests`; both call the same primitives.
- Real absence claims stay UNRESOLVED until a completed-boundary receipt exists;
  retrieval success alone is not absence (spec §5).
- Operator corpus / private PDFs are never copied into `tests/data/`.
- The architecture brief itself (`docs/IMPLEMENTATION_BRIEF_COMPLIANCE_READING_20260912.md`)
  is the contract; do not weaken it to make a live run pass.

## 7. Fast reference

```
# fast acceptance (hermetic)
uv run pytest tests/unit/test_compliance_reading_acceptance.py -q
uv run python scripts/verify_compliance_reading_acceptance.py        # 26/26

# live acceptance (real models; hours)
uv run python scripts/verify_compliance_reading_acceptance.py --live --runs 1
uv run python scripts/verify_compliance_reading_acceptance.py --live --cases 02,10 --runs 1

# per-commit gate
uv run ruff check . && uv run ruff format --check .
uv run pytest tests/unit/ -q
```

## 8. September 13 repair continuation

Read `reports/compliance/READING_REPAIR_20260913.md` for the diagnosis and rerun
receipts. The latest complete baseline had 9 verdict-word PASS and 17 FAIL,
but two PASS rows were acquisition failures with the expected uncertainty word.
The repaired verifier checks the actual failure codes, source citations,
arithmetic and proposals, and retains each model attempt as it finishes.

Code fixes cover catalog pagination, fixture setup validation, structured
alignment output and stage budgets, invalid-binding uncertainty, source text
for the reporter, verified omission proofs, worker ownership, run-context
projection, and failure trace retention. A post-fix A21-only case produced a
false FULL from two council seats; that substantive failure remains explicit.
The council-change boundary in the implementation brief remains in force.

Use the exact receipt directory printed in each managed job log. Repair jobs
are one-shot launchd jobs under `/tmp/compliance-reading-repair-20260913/`, with
`KeepAlive=false` and explicit `.exit` files; never infer success from launchd's
wrapper exit or restart a failed suite without diagnosing its saved receipts.

Latest handoff refresh: the structured job is complete with exit code 1, not
running. The full 26-case post-repair run and required repetitions are still
outstanding. Follow §5 in order; do not treat the earlier positive checkpoint
or transport-schema repair as proof that the current controls pass.

Ownership clarification: this diagnosis agent repairs code and verifies targeted
controls; the resuming coding agent executes §5C–D, including the full multi-hour
suite and final qualification report. No full suite is running from this thread.

---

## 9. Coding-agent pickup, 2026-09-13 evening — corrections applied, offline run armed

**Everything in §5A–B is now closed.** The targeted controls completed, their
dispositions are recorded in `reports/compliance/READING_REPAIR_20260913.md`
("Targeted repair controls — completed"), and the corrections below are
committed. §5C and §5D are what remains, and they run **offline**.

### Corrections applied on top of the repairs

| # | Correction | Why it was required |
| --- | --- | --- |
| 1 | `case.get("report") or {}` in `_check_live_gap_identities` | Cases 16/21/23/24 carry `"report": null`; the old `.get("report", {})` returned `None` and the `AttributeError` **aborted the entire suite** at the first such case. A 26-case run could not have completed. |
| 2 | `_guarded_live_checks` | A checker defect now records a failed `checker_error` check plus a saved traceback and the suite continues, instead of discarding every remaining case of a multi-hour run. Never a pass, never a skip. |
| 3 | Per-run `run_id` / model-call count / elapsed in every row + `records` in `summary.json` | Brief §9 requires exactly these per case in the final handoff; they were only recoverable by hand from each case directory. |
| 4 | `scripts/verify_compliance_reading_route.py` | §5D's scoped-R2 request over the **deployed** HTTP surface had no implementation. The 26-case verifier only runs isolated Parts in-process. |
| 5 | `scripts/run_compliance_reading_qualification.sh` + `scripts/check_compliance_reading_qualification.sh` | §5C's stages needed a single fixed-revision offline job with per-stage logs/exits that a later agent can inspect without this session. |
| 6 | `build_assessment_context(…, known_at, repository, …)` in `_live_case_direct` and `_proposal_result` | Both live-only call sites omitted `known_at` (and the proposal one also `repository`). Case 01 failed in 5.8 s with a `TypeError` and zero model calls; cases 25/26's proposal reassessment could not build a context. mypy had reported both as `call-arg`; they were wrongly dismissed as this script's baseline typing debt. |
| 7 | `str(item.get(k) or "")` for every optional field in `assessment_report._parse_gaps`/`_parse_*` | A present JSON `null` never hits `.get()`'s default, so `str(None)` became the truthy `"None"`. Live case 26 produced a **correct** PARTIAL report with `boundary_proof_id: null` and our parser rejected it as "an unverified boundary proof id", sinking the assessment to U11. `kind` would likewise have become `"NONE"` and `gap_id` the literal `"None"`. Regression test reproduces the live failure. |

### The offline qualification job

```sh
bash scripts/check_compliance_reading_qualification.sh --install   # start it
bash scripts/check_compliance_reading_qualification.sh             # check on it
bash scripts/check_compliance_reading_qualification.sh --stop      # abandon it
```

Label `com.portal5.compliance.reading.qualification.20260913`, one-shot
(`KeepAlive=false`), artifacts under
`/tmp/compliance-reading-qualification-20260913/`. Three stages run **sequentially
on one revision**, never chained with `&&` (a semantic FAIL must not suppress the
required repetitions):

| Stage | Command | Purpose |
| --- | --- | --- |
| `stage1` | `--live --runs 1` | all 26 cases |
| `stage2` | `--live --cases 01,02,03,04,05 --runs 2` | two further repeats of the real-corpus positive, the controlled positive and the three supply-chain decoys → three observations each |
| `stage3` | `verify_compliance_reading_route.py` | deployed scoped `CIP-007-6 R2` start/status/result, after `launchctl kickstart -k gui/$(id -u)/com.portal5.compliance-mcp` puts the final code behind :8937 |

The wrapper **always exits 0** so launchd never restarts a failed suite, and it
refuses to start if another live acceptance worker is running. Read the per-stage
`.exit` files and each suite's own `summary.json` `"complete": true` — never
launchd's status, never an HTTP 200, never a log heartbeat. Re-running the
installer resumes: a stage with an existing `.exit` is skipped, so a killed job
does not repeat completed stages. Budget several hours for stage1 alone.

### What the resuming agent still owes (§5D closeout)

1. All 26 stage1 outcomes with run IDs, model-call counts and elapsed — read them
   straight out of `summary.json` `records`; no hand aggregation needed now.
2. The three observations each for cases 01–05 from stage1 + stage2; do not
   average away a false PARTIAL.
3. The stage3 checks table, and an explicit statement of which §7.1 contract each
   covers.
4. An evidence-based disposition for every remaining failure, distinguishing
   integration defects from model semantic failures.

### Known substantive failures carried into the run

- **Case 08 — model semantic failure.** The packet defect is repaired (complete
  Part 2.1 text *and* the recovered R2 lead-in), and 2/3 seats still vote
  SUPPORTED on a candidate that omits the patch-source-identification duty. The
  earlier "premature to blame the council" caveat is discharged.
- **Case 10 — model semantic failure, correct system behaviour.** All three seats
  bound the 35-vs-40-day operands correctly, but 2/3 returned `DIFFERENT` for
  L22, contradicting the protocol's twice-stated rule that a changed interval
  does not create a different duty — and contradicting their own bindings. The
  exclusion, the reporter's rejected L22 citation and the resulting U11 are all
  the designed behaviour under a bad upstream vote.
- **Case 23 — control cannot reach its fault.** Its injected council timeout is
  only reachable if alignment resolves; real seats return `UNKNOWN` for A22
  because it states no frequency, so U09 fires first. U10 handling therefore
  remains **unqualified**. Making alignment deterministic or injecting the fault
  after a forced alignment changes acceptance semantics — operator's call, not
  taken here.

None of these was worked around. No council prompt, roster, quorum, override or
arithmetic was changed, and no gold label was moved.
