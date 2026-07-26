# Blue Closeout P4 Checkpoint — 2026-07-26

## Verdict

**P4 is RED/incomplete. P5 is not cleared.**

P1–P3 are implemented, tested, and committed. Acceptance regressions found by
the first full ALL sweep were repaired, and the merged post-fix acceptance
result has no FAIL or BLOCKED rows. The full UAT sweep is not complete: it was
stopped at the operator-requested boundary after A-01 produced one real failing
assertion. No model cleanup has started.

## Completed closeout phases

| Phase | Commit | Evidence |
|---|---|---|
| P1 council reconciliation | `2bceecce` | Security full-roster quorum delegates to the platform council primitive; focused tests and validation green. |
| P2 platform council bench | `1f216f09` | Council caught 2/2 known flaws, solo caught 2/2; no catch delta, no dead seats, council cost 9.33× latency and 5.44× estimated output tokens. Platform-only posture retained. |
| P3 benign corpus | `d17a5012` | Attack recall 5/5; benign correct silence 2/6; false-flag rate 4/6 (66.7%). Limitation recorded rather than hidden. |

Committed evidence:

- `reports/PLATFORM_COUNCIL_BENCH_20260726.{json,md}`
- `reports/RBP_BENIGN_CORPUS_20260726.{json,md}`

## P4 work completed

### System validation

The post-P1–P3 full validator run completed with 68 PASS, 0 FAIL, 0 WARN, and
1 SKIP. A final full rerun is still required because the P4 regression fixes
landed afterward. Each scoped fix also passed the repository pre-commit
validation and full unit suite.

### Acceptance

The first actual `--section ALL` run completed all 601 rows:

- 389 PASS
- 188 WARN
- 20 FAIL
- 4 INFO
- 0 BLOCKED
- Runtime 10,158 seconds

The 20 failure rows reduced to three defects:

1. Nine stale/missing persona prompt fixtures.
2. Three compliance failures caused by truncating the supplied system prompt
   to 800 characters.
3. Eight duplicated routing failures caused by synthetic workspace/backend
   resolution and streaming model-hint behavior.

Fixes:

- `e432ec5e` — prompt fixtures, full compliance system prompts, synthetic
  backend-group resolution, council heartbeat/cancellation, and evidence-based
  transport windows.
- `7b0dbd6c` — streaming candidate prioritization for model hints across
  eligible backend groups.

The targeted replacement rerun of S1, S3a, S10, and S10c completed with:

- 489 PASS
- 62 WARN
- 4 INFO
- 0 FAIL
- 0 BLOCKED
- 555 merged unique result rows
- Runtime 6,540 seconds

The merged count is smaller than the original ALL run because append-mode
replacement de-duplicates repeated section/test IDs; every original hard
failure was in the rerun scope and is now absent. The current
`ACCEPTANCE_RESULTS.md` is the post-fix merged result.

### UAT harness repairs

The live UAT environment and Open WebUI contract exposed three defects before
the product assertions could be trusted:

1. The host virtualenv lacked Playwright/Chromium. They were installed and all
   Portal/MCP images were rebuilt current.
2. A post-upgrade Open WebUI release-notes overlay covered the composer even
   though the composer existed in the DOM.
3. Tool-enabled turns now store visible assistant text in Responses-API
   `output` blocks while legacy `content` is empty; the frontend stop icon can
   also remain stale after the API records `done=true`.

Repairs:

- `1f4f45d5` — dismiss only the explicit release acknowledgement and extract
  assistant text from both legacy and Responses-API storage.
- `27bda478` — accept the explicit OWUI assistant `done=true` flag as a
  completion signal while retaining legacy DOM/stop-button fallbacks.

Focused UAT tests and the full repository pre-commit suite passed for both
commits. Live targeted reruns passed:

- A-01: 5/5 assertions, 310.9 seconds.
- WS-01: 5/5 assertions, 205.7 seconds.

### Current UAT blocker

The clean 314-case sweep was stopped after A-01, as requested. A-01 finished:

- **FAIL, 5/6 (83%)**
- 2,113.1 seconds
- First attempt returned no committed response after the 900-second streaming
  ceiling plus 450-second recovery poll.
- Attempt two recovered and proved the new API completion path.
- Turn-one length/content, turn-two minimum length, recovery, and routing
  assertions passed.
- The required fixture-content evidence failed: turn two did not contain any
  of `access control`, `rbac`, `authentication`, `authorization`,
  `least privilege`, or `principle of`.

The leading harness-level cause to investigate is that A-01 is named
"Document RAG — Upload, Query, Follow-Up" and is gated on the DOCX fixture, but
its catalog entry does not identify a fixture to attach and the current runner
does not upload `sample.docx` for the case. The passing targeted run appears to
have found matching text through ambient knowledge/tool results, making it
nondeterministic. This is evidence, not yet a completed root-cause fix; P4 must
remain RED until A-01 is made deterministic without weakening its assertions
and the full UAT run completes.

The partial result is preserved in `tests/UAT_RESULTS.md` as 1/314 executed,
1 FAIL.

## Remaining P4 matrix

| Harness | State | Required next action |
|---|---|---|
| System validation | Prior run green; final rerun pending | Run full `scripts/validate_system.py` after all P4 fixes. |
| Acceptance ALL | Initial ALL complete; all hard failures repaired and targeted rerun green | Retain merged evidence; optionally rerun ALL from scratch for a single non-merged artifact. |
| UAT | **RED/incomplete** | Fix deterministic A-01 fixture upload/retrieval, rerun A-01, then run all 314 cases and triage every red. |
| Corpus-replay security bench | Pending | Resume retained closeout checkpoint and smoke one live episode. |
| Notify/benign scoreboard | P3 evidence committed; P4 re-score pending | Run score-only re-score of both axes. |
| Platform council bench | P2 live evidence committed; P4 rerun pending | Rerun the live council-vs-solo bench or explicitly accept the same-day committed live run. |
| Performance TPS | Pending | Run `tests/benchmarks/bench_tps.py` and compare with retained baseline. |

## P5 and final closeout

P5 has not started because P4 is not green. Once P4 is green:

1. Build or verify the catalog-preserving Ollama cleanup tool and safe KEEP
   derivation.
2. Run dry-run and present the exact DELETE/KEEP plan and expected reclaimed
   size.
3. Pause for the mandatory operator confirmation.
4. Only after confirmation, remove the approved disk weights, verify every KEEP
   model remains present/loadable, confirm catalog checksums unchanged, and
   report disk freed.
5. Reconcile canonical limitations and commit the final closeout report.
