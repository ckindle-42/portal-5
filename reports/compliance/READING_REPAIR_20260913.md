# Compliance reading repair — 2026-09-13

Status: code repairs under live qualification. The architecture is **not accepted**. This report supplements `docs/TASK_COMPLIANCE_READING_RESUME_20260913.md`; the implementation brief remains the governing contract.

## Failure evidence

The original completed run is `coding_task/v9_compliance/private/reading_acceptance/20260913T120012Z/`. Its summary reported 9 PASS and 17 FAIL, but tested only the returned documentary-coverage word. Cases 13 and 15 therefore passed despite acquisition failures. These are not valid acceptance receipts for their intended conditions.

The associated logs are `/tmp/compliance_acceptance_live_20260913_launchctl.log` and `/tmp/compliance_acceptance_monitor_20260913_launchctl.log`. The repeated later receipt directories were unintended supervisor restarts after nonzero exits, not independent qualifications.

## Code repairs

| Failure | Cause and repair |
| --- | --- |
| Review queue already exists; existing KBs become unknown | LanceDB `table_names()` defaults to ten entries. Shared store lookup, enumeration, rebuild lookup and the review queue now enumerate every page. The installed `list_tables` continuation token also skips an entry; explicit last-returned-name pagination avoids that measured defect. Existing tables are opened without recreating them. |
| Fixture setup errors followed by assessments against unavailable/stale KBs | The live verifier rejects returned ingestion errors, verifies exact stored fixture contents, and records setup failure without executing the case. |
| Case 01 alignment uses the council's 900-token transport | The real-corpus diagnostic now uses the same stage dispatch as asynchronous assessment. Alignment has a bounded output budget that scales with record count. |
| Numeric bindings vanish while coverage is resolved | The prompt omitted the parser's exact binding schema. Real seats returned other field names; a subsequent enum example caused one seat to copy scalar values as arrays. Alignment now supplies a JSON Schema to the model transport. Invalid source/quantity bindings remain UNKNOWN, and unresolved alignment blocks a resolved verdict. |
| Missing population binding treated as comparable | SAME requires source-grounded OVERLAPPING populations. Missing population agreement remains UNKNOWN. |
| Reports see IDs without source text | Reporting now receives the verified source catalog as well as selectable IDs. |
| Invented omission proof accepted | An omission requires a verified section-by-section boundary receipt and the system-generated proof ID supplied to the reporter. Bare completeness flags, arbitrary IDs and invented internal omission quotes are rejected. |
| Failure traces lost | Alignment failures retain raw responses; completed assessments retain the council packet, raw council responses and reporting trace in the canonical repository. The verifier also writes each model attempt, prompt/input hashes, response/error and duration immediately. |
| Importing another process interrupts live jobs | Durable run requests record worker PID and OS process birth time. Recovery preserves live owners and marks abandoned/reused-PID jobs interrupted. A subprocess regression exercises the actual import-time sweep. |
| Result envelope uses today's date or a different scope/KB | The result projection reads the original durable request context. |
| Controlled failures/proposals not exercised | Cases 21–24 use the asynchronous registered route with controlled source/transport faults. Cases 25–26 now execute the proposal overlay and reassessment. Checks include error code, source citations, arithmetic, gap kind/ID and proposal result. |
| Nonzero suite exit restarts repeatedly | Repair jobs use explicit one-shot launchd plists with `KeepAlive=false`; the runner exit code is retained in a separate file and logged. |

No change has been made to the council's prompts, roster, voting/quorum or quantity arithmetic. These repairs do not establish their semantic acceptance.

## Reruns and remaining failures

- `20260913T133123442052Z` / `/tmp/compliance_reading_repair_faults.log`: cases 22 and 24 passed with U03 and U09 through the registered async route. Use the log's first line for its exact receipt directory.
- `20260913T133143866894Z`: interrupted diagnostic. A separate process's import-time sweep interrupted case 08, exposing the worker-ownership defect. It is not a completed acceptance run.
- `20260913T133500430029Z`: completed cases 08 and 10 returned the expected PARTIAL judgments. Strict ID checks rejected generated `gap-001` versus fixture `g08`. Case 10's raw bindings used fields the parser did not accept and produced no arithmetic receipt. Case 23 did not complete before the interactive process ended. These receipts motivated the explicit schema and durable supervisor repairs.
- `20260913T164120807797Z`: cases 08, 10 and 23 completed under the first explicit formatting contract. Case 08 was a **false FULL**: Qwen and Mistral voted SUPPORTED despite the missing patch-source identification duty; Granite identified the omission. The complete governing text and sole A21 candidate are retained in its council packet. Cases 10 and 23 correctly remained unresolved when Granite emitted enum arrays instead of scalars. That trace motivated native JSON Schema enforcement.

The false FULL is a substantive council failure on the supplied packet. It must not be hidden by changing gold labels or retrying until a favorable result appears. The brief's council-change boundary applies.

Fixture gap IDs such as `g08` are still checked exactly. The production reporter generates different identifiers; the existing hermetic transport supplies those fixture IDs from expected results. This protocol/acceptance mismatch remains visible instead of being silently marked PASS.

## Validation receipts

- Fast 26-case suite: 26 PASS after the boundary, alignment and lifecycle repairs.
- Full unit checkpoint: 1,806 passed, 4 skipped (`/tmp/compliance_reading_repair_unit_final.log`). This is superseded by the final consolidated result below.
- System validation: 211 passed, zero failures, one warning, one skip (`--skip-pytest`, with the unit suite run independently). Log: `/tmp/compliance_reading_repair_validation_final.log`.
- Focused mypy: ten modified core/store modules clean at the recorded checkpoint (`/tmp/compliance_reading_repair_mypy_final.log`).
- Complexity was reduced to fit the existing budget; no budget increase was used. Final census also accounts for the two new regression-test files.

Managed repair artifacts are under `/tmp/compliance-reading-repair-20260913/`. The structured-output control job writes `structured.log` and `structured.exit`. Its exact input/code/model manifest and case traces are under the receipt directory printed on the log's first line. A log heartbeat or HTTP 200 is not an acceptance result.

## Latest completed controls and handoff refresh

The native-schema control job completed with child exit code **1**, and launchd
reports it **not running**. Receipt root:
`coding_task/v9_compliance/private/reading_acceptance/20260913T165339037987Z/`.
No full post-repair 26-case sweep has started.

| Case | Run ID | Result | Evidence and next action |
| --- | --- | --- | --- |
| 10 | `c3541a3cc77e4237` | FAIL, U11; 433.98 s, 10 calls | Schema-shaped bindings were emitted, but Granite/Mistral voted L22 DIFFERENT because of the 40-day cadence. L22 was excluded, arithmetic was empty, and the reporter's L22 counterevidence was rejected. Inspect semantic aggregation and binding selection; do not relax citation validation. |
| 23 | `a8ef532c8dd3466d` | FAIL, U09; 236.45 s, 3 calls | Mistral bound 35 days to the Part 2.1 reference without that quantity; Granite used min_retention for a cadence. U09 preceded council invocation, so the intended U10 timeout remains unqualified. |

Correction to intermediate progress: reaching the council did not establish that
35/40-day arithmetic executed. The completed receipt shows no arithmetic because
the majority classified L22 DIFFERENT. Native JSON Schema fixes output shape;
it does not establish correct duty identity, quantity kind or source selection.

Latest consolidated units: **1,803 passed, 6 failed, 4 skipped** in 219.34 seconds
(`/tmp/compliance_reading_repair_unit_consolidated.log`). The failing tests are:

- `test_compliance_operations.py`: shared-result projection, out-of-scope gate,
  closing proposal, and governing-quote non-closure (four tests).
- `test_compliance_change_pipeline.py`: actual closing overlay.
- `test_compliance_scenarios.py`: replacement over one pinned snapshot.

Their fake transports still select alignment by the removed phrase
`narrow clause-alignment reader`. Repair stage dispatch and rerun; do not assume
all assertions will pass until observed. This is a new regression in the repair
sequence, not established baseline debt.

Final complexity census including the two new untracked tests also failed:
**44,228 prose lines vs 44,226 budget**. Lint/format passed. The earlier system
validation and 1,806-pass unit checkpoint do not supersede these latest failures.

The resume task now gives an ordered plan: fix preflight and gap-ID contract,
diagnose these controls, run the full 26 cases plus two extra repetitions each
for 02–05 under a fixed configuration, verify completed deployed HTTP results,
and publish a final evidence-based disposition. Infrastructure is more durable
and failures are more observable; a clean semantic acceptance run remains
unproven. All repair changes remain uncommitted at this handoff.

## Further code repairs after handoff review

The user clarified ownership: this agent diagnoses and repairs the program;
the resuming coding agent executes the full multi-hour qualification. Updating
a task file was insufficient while these fixable defects remained.

- Repaired the three fake-transport selectors to use the explicit alignment task
  field. The six unit failures are gone: **1,815 passed, 4 skipped** in 219.26 s
  (`/tmp/compliance_reading_repair_resume_units.log`). Two additional literal
  and pair-transport tests subsequently passed in the 77-test focused suite.
- Supplied each governing slice's exact text, ref and role alongside its ID in
  alignment. Previously the reader saw an ID list with no ID-to-text mapping.
  The wrong Part 2.1 quantity selection therefore exposed packet damage, not
  solely model behavior.
- Recovered missing parent R headers from the register's pinned public PDFs,
  using the existing extractor and checking the file hash against the register.
  CIP-007-6 has Parts but no R2 register node. Its recovered R2 header requires
  documented processes that **collectively** include the applicable Parts.
  The complete header now participates in source IDs and fingerprints.
- Clarified duty identity versus cadence and max_interval versus min_retention;
  removed contradictory record-count instructions. The concise protocol fits
  the existing complexity budget. Council prompts and arithmetic are unchanged.
- Source-invalid numeric votes no longer poison a valid categorical quorum.
  Arithmetic requires quorum agreement on the selected operand pair, quantities,
  qualifiers and constraint kind. Ambiguous bindings remain UNKNOWN.
- Literal validation now checks the actual number/unit/qualifier occurrence;
  it cannot splice a number and a unit from different phrases or invent a
  calendar/business qualifier. Internal-pair requests get the pair response
  schema instead of being forced into a candidate-record schema.
- Resolved the verifier's gap-ID mismatch explicitly: `g08`/`g10` are handles
  authored in the hermetic fixture, not IDs available to a live model. The live
  checker records a one-to-one mapping from each fixture handle to the returned
  ID using exact gap kind, governing ref and counterevidence document identities.
  It still rejects missing/duplicate IDs, wrong sources, ambiguous matches,
  extra/missing gaps and missing omission proof. It does not rename production
  IDs or send gold handles/answers to models. Literal spelling remains asserted
  in the hermetic transport tests, where the injected transport owns that spelling.

Correction: the earlier A21-only false FULL had the complete Part text, but not
its required R2 lead-in. Calling it a failure of a fully assembled packet was
premature. The original receipt is retained; the repaired packet needs its own
live result before the council can be blamed or accepted.

Latest static checks: lint and format pass; focused mypy passes. System validator
reports **211 passed, 0 failed, 1 warning, 1 skip** in 122.22 s
(`/tmp/compliance_reading_repair_resume_validation.log`). The explicit census
including new files passed without increasing any budget (prose 44,204/44,226,
data lines 9,653/9,653 at that checkpoint).

`20260914T005023434854Z` was an interrupted development control using the longer
protocol. It was intentionally stopped with child exit 143 when repairs were
frozen, before final qualification; its partial model responses remain available.
The fresh targeted job is `final-repair-controls` under the existing `/tmp`
artifact directory. It exercises only cases 02,08,10,23. The full 26-case run has
not been started by this agent. Its results will be recorded below when complete.

## Targeted repair controls — completed (2026-09-13/14)

Job `final-repair-controls` (cases 02,08,10,23) completed with child exit **1**.
Receipt root: `coding_task/v9_compliance/private/reading_acceptance/20260914T005617056706Z/`.
Log: `/tmp/compliance-reading-repair-20260913/final-repair-controls.log`.

| Case | Run ID | Result | Disposition |
| --- | --- | --- | --- |
| 02 | `81a8c469c7e94276` | **PASS**, `got=FULL` | The repaired packet, per-case KB and document-name `commitment_id` hold on the real route. |
| 08 | `6b0f3054b7ff41cc` | FAIL, false `FULL` (7 model calls) | **Model semantic failure.** The packet is now complete — full Part 2.1 verbatim text *including* “The tracking portion shall include the identification of a source or sources…”, plus the recovered R2 lead-in, with A21 as the sole candidate. Granite voted PARTIAL/WEAK_MAPPING and named the missing source-identification duty; Qwen and Mistral voted SUPPORTED. The earlier “premature” caveat is now discharged: the packet defect is repaired and the failure persists. |
| 10 | `bff74819ac824e4e` | FAIL, `UNRESOLVED` / U11 (10 calls) | **Model semantic failure with correct system behaviour.** All three seats bound the operands correctly (governing 35 calendar days vs internal 40, `max_interval`), but Qwen and Mistral returned `relation=DIFFERENT` for L22 — contradicting the alignment protocol, which states twice that a changed or missing interval does not create a different duty, and contradicting their own emitted bindings. Granite returned SAME. Quorum therefore excluded L22, the council saw only A22 and returned PARTIAL 3/3, the reporter cited the excluded L22 as counterevidence, and validation correctly refused it with `U11_ASSESSMENT_CONTRACT_FAILED`. No layer of ours mis-handled the bad vote. |
| 23 | — | **Suite crash** (instrument defect, now fixed) | `_check_live_gap_identities` read `case.get("report", {}).get("gaps", …)`; cases 16/21/23/24 carry `"report": null`, so the default never applied and the `AttributeError` aborted the whole run. |

## Coding-agent corrections applied on top of the repairs

1. **`report: null` crash (blocker).** `scripts/verify_compliance_reading_acceptance.py` now normalises `case.get("report") or {}`. Without this, a full 26-case run dies at case 16 and discards every later case.
2. **Checker faults no longer end a multi-hour suite.** `_guarded_live_checks` records a checker crash as a failed `checker_error` check plus a saved traceback, and the suite continues. Never a pass, never a skip.
3. **Closeout evidence is now emitted, not reconstructed.** Each live row carries `run_id`, model-call count and elapsed seconds, and `summary.json` gains a structured `records` list — the brief's §9 handoff requires exactly these per case.
4. **Deployed scoped-R2 route verification** — new `scripts/verify_compliance_reading_route.py`. The 26-case verifier only exercises isolated Parts in-process; this issues `CIP-007-6 R2` over the deployed MCP HTTP surface (`POST :8937/tools/compliance_gaps`) with explicit scope, conditional-scope disclosure and a non-today effective date, then asserts four distinct Part assessment IDs under one run id, original-context replay (a deliberately wrong `kb_id` and blank date are sent on the result call), and no further model work on a repeated status/result pair.
5. **Offline qualification runner** — `scripts/run_compliance_reading_qualification.sh` (+ `scripts/check_compliance_reading_qualification.sh` to install/inspect/stop). Three stages run sequentially on one fixed revision, never chained with `&&`, each with its own log, child `.exit` and `status.json` entry; the wrapper always exits 0 so launchd never restarts a failed suite.

### Post-correction live control

`--live --cases 21,22,23,24 --runs 1` on the corrected code
(`coding_task/v9_compliance/private/reading_acceptance/20260914T012351613441Z/`):

| Case | Run ID | Calls | Elapsed | Result |
| --- | --- | --- | --- | --- |
| 21 | `10302d29de794bc0` | 0 | 2.1 s | PASS — `U02_MISSING_GOVERNING_SOURCE` |
| 22 | `3509d2f8f15d491c` | 0 | 2.0 s | PASS — `U03_EXTRACTION_FAILED` |
| 23 | `389cd883bf154c93` | 3 | 258.7 s | FAIL — `U09_SEMANTIC_ALIGNMENT_UNKNOWN`, expected `U10_COUNCIL_UNRESOLVED` |
| 24 | `55d10eca50564fdf` | 1 | 2.0 s | PASS — `U09_SEMANTIC_ALIGNMENT_UNKNOWN` |

The crash is gone and all four cases now complete. Case 23 remains **unqualified for
U10**: its injected council timeout is only reachable if alignment resolves first,
and on this fixture Qwen and Granite returned `UNKNOWN` for A22 because it states no
frequency — again contradicting the protocol's "a changed or missing interval does not
create a different duty". The resulting U09 is correct behaviour; the case simply never
reaches the fault it was written to exercise. This is a **fixture/design limitation of
the control, not an infrastructure block and not a pass**. Fixing it by making
alignment deterministic, or by injecting the council fault after a forced alignment,
changes acceptance semantics and is the operator's call — it was not done here.

### Validation after the corrections

- Fast hermetic acceptance: **26/26 PASS** (3.1 s).
- Full unit suite: **1,817 passed, 4 skipped**, 205.67 s.
- Lint + format: pass. Focused mypy on the new route script: clean. The acceptance
  verifier keeps its nine pre-existing baseline errors and gained none.
- Complexity gate: **OK at budget, no budget increase** (prose 44,226/44,226,
  god_lines 50,210/50,273) — `_run` in the route script was split to stay in budget.
- System validator: **211 pass · 0 fail · 1 warn · 1 skip**, 120.4 s (`--skip-pytest`).

No council prompt, roster, quorum, override or arithmetic was changed.


## Correction 6 — `build_assessment_context` was called with too few arguments

Arming the offline job exposed it immediately: case 01 returned
`TypeError: build_assessment_context() missing 1 required positional argument:
'known_at'` in 5.8 s, with zero model calls. Two live-only call sites in
`scripts/verify_compliance_reading_acceptance.py` omitted `known_at`, and the
proposal path also omitted `repository`:

* `_live_case_direct` — the case 01 real-corpus diagnostic (both the actual-scope
  and conditional-scope runs);
* `_proposal_result` — the cases 25/26 proposal overlay reassessment.

Both now pass `request.known_at` and an explicit `Repository()`, matching
`assessment_runs`' canonical call. This was **already reported by mypy** as a
`call-arg` error on those two lines and was wrongly set aside as part of the
script's documented baseline typing debt; it was a real defect that would have
failed case 01 on every run and broken the 25/26 proposal path. The remaining
seven mypy findings on this file are `no-any-return`/annotation noise, and the
two `call-arg` errors are now gone.

Verified live on the corrected code: case 01 ran a real 486 s alignment seat
against the operator corpus instead of failing in 5.8 s, and case 26 executed the
full initial assessment plus the proposal-overlay reassessment (12+ model calls),
which is exactly the `_proposal_result` path that could not previously build its
context.

Also hardened: `run_stage` archives a stage log that has no `.exit` before
restarting that stage, so a resumed job's log always begins with its own receipt
directory rather than an aborted attempt's.


## Correction 7 — a JSON `null` was read as the string `"None"`

Live case 26 (run `affeefffda744a9a`, 30 model calls, 1322.4 s) returned
`UNRESOLVED` / `U11_ASSESSMENT_CONTRACT_FAILED` with
`"gap cites an unverified boundary proof id"`. The reporter's actual output was
**correct**: `PARTIAL`, one `WEAKER_COMMITMENT` gap for the missing
"at least once every 35 calendar days", L22 as counterevidence, and
`"boundary_proof_id": null` — exactly what the prompt asks for outside an
OMISSION. Alignment had resolved both A22 and L22 as `SAME` and the council
returned PARTIAL.

`_parse_gaps` coerced the field with `str(item.get("boundary_proof_id", ""))`.
`.get()`'s default never applies to a present `null`, so `str(None)` produced the
truthy `"None"`, which then failed `gap.boundary_proof_id != boundary_id`. Every
other optional field in the report parser (`commitment`, `kind`,
`missing_commitment`, `gap_id`, `reason`, `code`) carried the same hazard —
`kind` would have become `"NONE"`, `gap_id` the literal `"None"` instead of the
generated fallback. All seven now use `str(item.get(k) or "")`.

This is the same defect class as the `"report": null` suite crash, and it is
**ours, not the models'**: a correct report was discarded and the assessment
downgraded to an uncertainty code. Regression:
`test_explicit_null_optional_fields_are_not_read_as_values`, which reproduces the
exact live failure (`AssertionError: gap cites an unverified boundary proof id`)
when the coercion is reverted.

The case 26 fix also confirmed correction 6: the run executed the full initial
assessment plus the proposal-overlay reassessment (30 calls) through
`_proposal_result`, the path that previously could not build a context at all.

### Gates after corrections 6 and 7

- Full unit suite: **1,818 passed, 4 skipped**, 204.77 s.
- Fast hermetic acceptance: **26/26 PASS**.
- Lint + format clean repo-wide; focused mypy on `assessment_report.py` clean;
  the two `call-arg` errors on the verifier are gone.
- Complexity gate **OK at budget, no budget increase**.
