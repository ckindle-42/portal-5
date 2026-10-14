# Model-evaluation measurement — root causes and root fixes (2026-10-13)

## What the harness is for

WFE exists to answer one question for any model, new or seated: in which production workspaces,
if any, would it do that workspace's job better than what is there now? A model may fit one
workspace, several, one it was not built for, or none, and all four are results (doctrine
2026-09-07, `docs/TASK_WORKSPACE_FITNESS_EVAL_V1.md`: real use decides; diversity is a factor;
each disposition is fold, purpose or remove).

## Why it has not been doing that

Two audits on 2026-10-13 found about 30 instrument defects that decided fleet seats:

- round 1: `docs/WFE_INSTRUMENT_AUDIT_20261013.md`;
- round 2 offline pass, recorded below.

From April to mid-October about 360 commits fixed a bench, probe, harness or grader; 22 of them
landed in the first 13 days of October. Fixing defects one at a time has not converged, because
they are instances of five causes (C1–C5). A sixth (C6) is why the harness never became the
cross-workspace vetting tool it was designed to be. WFE_ROOT_FIX program (P1–P5) implements the fixes.

## The causes

| # | Root cause | Evidence at `2dcc459e` | Fix |
|---|---|---|---|
| C1 | **Two measurement paths.** WFE pipeline mode is the only instrument that measures what production serves, and it could measure only the seated model: a challenger was BLOCKED as drift. Every challenger comparison therefore ran on a re-implemented path, with its own prompt, think setting, budget and engine. | 73 files call a model. 49 talk to Ollama directly and 11 define their own `run_case`. 15 build their own system prompt, 10 force thinking off, and 25 set their own token budget. About 48 workspaces are served by oMLX builds whose GGUF tag is only the failover. | Pipeline mode sends every arm through production's own `?model=` override (`preinject._resolve_model_override`). The challenger is served under the workspace's prompt, tools, think, caps and routing, exactly as if it were seated, and the served model is verified per turn. |
| C2 | **Scorers and keys are never shown to work.** No checker was tested against a known right and a known wrong answer before it scored models. | Two research tasks passed when the seed file was pasted back. Every class-graded compliance task passed a "shotgun" answer naming all five determinations. The research probe's rq03 key names a Fed chair whose term, by the key's own text, ended in May 2026; the run was on 2026-09-07. | `tests/wfe/controls.py`. Every answer-graded task must fail an empty answer, the pipeline placeholder, and an echo of its instruction and seed; must pass a declared gold answer; and must not be past `expires`. `open_campaign` refuses a plan that touches a failing task. |
| C3 | **Decisions do not record what measured them.** | 0 of 203 fleet dispositions record an instrument commit, engine or transport. Five REMOVED_CLOSED dispositions rest on measurements: four on judgment probe v6, one on the research probe. Neither audit's "decisions at risk" table listed them. | Every campaign manifest records `instrument: {commit, harness_dirty, engine}`. A seat-evidence ledger and a validator check tie each seat to the campaign that justifies it, and flag the seat stale when production's served build changes. |
| C4 | **Samples too small to decide anything, and decisions made anyway.** | The coding and research home suites have 3 tasks each. The research probe declared winners with a strict ">" on n=10, and judgment-probe stop rules fired on +0.06 exact (about 2 of 30). Only WFE computes intervals. | A decision floor of at least 30 distinct tasks. A decision must be separated, and must hold with and without tasks marked `arguable`. Below the floor, or when not separated, the status quo stands and the report says "no decision". |
| C5 | **Unit tests reach live services.** | The bench-supervisor test sends `proxmox_container_start(112)` to the portal-proxmox MCP on every run. Its snapshot reverts also go out when the shell exports `LAB_*_VMID`; `tests/conftest.py` blanks those variables only when they are absent. Six WFE tests query Ollama. | A `tests/conftest.py` guard refuses connections to configured service ports and fails the test. The offending tests now stub those calls. |
| C6 | **The jobs are not covered.** The harness was designed as a models × workspaces matrix, with home and discovery suites and cross-lane search. In practice it can measure a few workspaces, and not in their real job. | 6 of 58 workspaces have a workload, and there are 4 job suites. Every run replaces the workspace's declared tools with six generic sandbox tools, so the jobs of auto-documents (create_word_document, create_excel, create_powerpoint), auto-data (execute_python, run_sql), auto-daily and general-fast/deep are never measured. auto-documents' home suite is `research`. Challengers are hand-listed per workspace, so no model is tried where nobody thought to put it. | A job-family map covering every workspace, with `not_vettable` stated where the runner cannot do the job. A `tool_mode: production` option in which the pipeline executes the workspace's own tools and artifact checkers grade the files produced. A suite of 30 or more controlled tasks per family. Eligibility-driven plan generation, so each model is screened in every workspace it could serve. |

## What the fixes close

- **C1** closes the classes where the instrument and production disagreed: wrong prompt or persona (round 1 rows 1 and 13), think forced off or a short budget (rows 5, 15, 17), incumbent-tuned sampling (row 2), engine parity (R2-26), unverified failover (row 9), and transport non-equivalence (row 14, R2-25). It closes them for every lane at once, because every arm now uses production's code for these things.
- **C2** closes checker weakness (row 10), inconsistent or unstated keys (rows 3, 4), answer-key leakage through readable files, and stale keys. It catches new instances mechanically at campaign open.
- **C3** turns "which decisions does this defect touch" into a lookup.
- **C4** stops "not separated" being written up as a result.
- **C5** removes the live side effects behind row 19 and R2-20/21.
- **C6** makes the harness's purpose reachable: any catalog model, every eligible workspace, its real tools, enough tasks to decide.

## What stays diagnostic

Probes that call an engine directly keep their uses: engine speed, MTP, KV,
concurrency, and template diagnostics. None of them can set a seat or a
disposition any more. No probe is upgraded to decision-grade; defects found
in probes are still fixed (N-1, N-2, N-3, N-9), because a wrong diagnostic misleads its reader. Three things have no production-path instrument yet, so their current
decisions stand as status quo, flagged:

- the compliance council roster (production calls `run_council` on decomposed
  packets, which WFE does not build);
- vision, image, audio and video (the runner has no media I/O);
- computer use.

## Decisions at risk

Every identity in the closeout register is classified by `scripts/wfe_disposition_backfill.py`:
203 items — 82 integrated, 59 removed_restorable, 54 removed_unrestorable, 8 retained_for_purpose. The receipt is `docs/WFE_DISPOSITION_BACKFILL_20261014.json`.

**The five removals that rest on a measurement one of the 2026-10-13 audits found biased.**
Four are judgment-probe-v6 stop-rule verdicts and one is the research probe. None is
reversed here: each is either restorable with the recipe below, or unrestorable and in the
queue with `available: false`, so every cell it could have had is MISSING and its disposition
can only be NO_DECISION.

| Removal | Why it is at risk | Restore |
|---|---|---|
| `ollama:command-r:35b-08-2024-q4_K_M` | judgment probe v6: the stop rule's 'else REMOVED' fired | **unrestorable** — already absent from the store at closeout and the register records no upstream source |
| `ollama:granite4.1:8b-q8_0` | judgment probe v6: stop rule fired on +0.06 exact (about 2 of 30 tasks) | ollama pull granite4.1:8b-q8_0; verify with model_layer_digests (1 layer(s)) |
| `ollama:granite4.2:30b-q4_K_M` | judgment probe v6: stop rule fired on a like-for-like comparator | **unrestorable** — already absent from the store at closeout and the register records no upstream source |
| `ollama:hf.co/bartowski/Qwen_Qwen3.6-27B-GGUF:Q4_K_M` | judgment probe v6: duplicate-quant stop rule fired on exact parity | ollama pull hf.co/bartowski/Qwen_Qwen3.6-27B-GGUF:Q4_K_M; verify with model_layer_digests (1 layer(s)) |
| `ollama:portal5/xyz-aquila-mini:q4_k_m-ctx16k` | research probe: the lane instrument's checkers were weak (defect 10) | ollama pull portal5/xyz-aquila-mini:q4_k_m-ctx16k; verify with model_layer_digests (1 layer(s)) |

The other 52 unrestorable removals carry no measurement at all — they were already absent from the store at
closeout, or they are oMLX directories whose upstream source the register never recorded. They
are in `tests/wfe/candidate_queue.yaml` with `available: false` (54 in total), which makes their cells MISSING.

The remaining 59 removals are restorable with `ollama pull`
and verifiable against the `model_layer_digests` the register recorded, so re-measuring any of
them costs a pull rather than an archaeology exercise.
## Round-2 offline findings, mapped to causes

| Finding | Status | Cause |
|---|---|---|
| R2-20: supervisor test reaches the Proxmox MCP | code-confirmed, now fixed. LXC 112 start went out every run; snapshot reverts went out when the shell exported `LAB_*_VMID`. The 2026-10-13 test window shows 0 container-start, snapshot or rollback entries in the portal-proxmox MCP log, including a run with every `LAB_*_VMID` exported. | C5 |
| R2-21: read-only live calls from tests | code-confirmed, now closed for Python. The sync_config subprocess `/v1/models` call is covered by `PORTAL_SYNC_SKIP_PIPELINE_CHECK`, and the boundary reaches Python subprocesses through `tests/_netguard/sitecustomize.py`. Non-Python subprocesses (curl, docker) stay outside it, as the boundary section records. | C5 |
| R2-22: stalled turns not checked for the served model | latent | C1. Moot once failed turns carry a correlation id; record the id in Phase 2. |
| R2-23: `seat_primary` copies routing | latent; 88/88 agree today | C1 |
| R2-24: card-mode choice | (a)(b) open policy question; (c) withdrawn; (d) latent | C1. Challenger sampling is now caller-sent and recorded per row. |
| R2-25: probe transport differs from the council seat | code-confirmed | C1. Council stays status quo; no production-path instrument. |
| R2-26: engine parity | config-confirmed | C1 |
| R2-27: Fara credits calls found in reasoning | depends on the decision's framing | C1 |
| R2-28: candidates_v10 budgets | suspected | C1 |
| R2-29: failover into 8k/16k windows | config-confirmed | C1, and production P-2 × P-4 |
| Shotgun answers pass compliance tasks | measured on all 52 class-graded tasks | C2. Fixed by class-exclusive `forbid`. 0 of 110 stored rows change. |
| Research tasks pass a pasted seed | measured on 2 of 3 | C2. Fixed by a fixture-header `forbid`. |
| Research probe rq03 key is stale | measured | C2. The probe is diagnostic now. |
| Measured removals missing from the at-risk tables | measured: 5 | C3 |

## Production defects that skew real-use evidence (fixed in WFE_ROOT_FIX program (P1–P5) Phase 5)

Measuring through production means these show up in the results, so they are fixed before the
sweep.

| # | Defect | Source | Exposure |
|---|---|---|---|
| P-1 | oMLX streaming drops a malformed `<tool_call>` (an extra brace) and returns empty content, so the pipeline sends the no-answer placeholder | V2 closeout §6 | every oMLX seat with tools |
| P-2 | An oMLX timeout fails over to an Ollama cold load. `load_guard` then frees the seat, and its reloads get 507. Failover targets can be broken (the Laguna Ollama parser 500s) or smaller than the window. | V2 closeout §3; backends.yaml Laguna note; R2-29 | every oMLX seat with an Ollama failover |
| P-3 | Laguna tool-call arguments land in the tool name | V2 closeout §R6 | auto-coding::laguna |
| P-4 | Ollama seats truncate silently past the baked window; the native adapter ignores request `num_ctx` | round-1 row 7; R2-29 | 8 Ollama tool seats at 16k or less, plus small failover targets |

## Other defects noticed (fixed or assigned in Phase 5)

| # | Defect |
|---|---|
| N-1 | Research probe: the rq03 key is stale; errors counted as FAIL; the win label at n=10; text tool calls and reasoning scored as answers |
| N-2 | Fara: tool calls in `thinking` (template), and the probe credits them |
| N-3 | candidates_v10: `max_tokens` overrides the seat's `predict_limit` (to confirm) |
| N-4 | Committed V2 rows hold pre-fix outcomes |
| N-5 | `test_handlers_return_valid_action` swallows every exception — fixed in Phase 1 |
| N-6 | The sync_config test subprocess reaches the pipeline — fixed in Phase 1 (`PORTAL_SYNC_SKIP_PIPELINE_CHECK`) |
| N-7 | The `qwen3.8` card matches any `Qwen3-8B` tag |
| N-8 | `seat_primary` has no drift test against production selection |
| N-9 | The judgment probe does not state that it is not the council path |
| N-10 | MODEL_CATALOG.md and a backends.yaml note contradict the serving config (DeepSeek-R1 MLX, parser watchdog) |
| N-11 | Tracked V2 campaign results hold compliance answers and transcripts; the HK check matches names only |
| N-12 | Pipeline-mode preflight and arm execution unload a GGUF tag production may be serving on Ollama |
| N-13 | `scripts/lab_ready.py` ran its `.env` loader at import, so a unit test that imported it pushed the operator's whole `.env` into `os.environ`. That made the notification channels look configured, and a later, unrelated test sent a real Telegram and Pushover alert. `scripts/lab_targets.py` already had the `UNIT_TEST_MODE` hermetic guard for exactly this; `lab_ready.py` did not. Fixed in Phase 1 by the same guard. |
| N-14 | Three unit tests reached live non-loopback hosts once the boundary could see them: `test_compliance_currency.py::_online()` probed nerc.com from a unit test, and the Telegram and Pushover `test_send_alert_skips_when_not_configured` tests inherited credentials from N-13 and posted to `api.telegram.org` and `api.pushover.net`. Fixed in Phase 1: the currency probe treats the boundary as offline, and the two channel tests pin their own "not configured" precondition. |
| N-15 | Identity froze only under --preflight; execution discarded it, rows copied content from the freeze, and an unobservable build passed as a constant or empty id; fixed in P1R |
| N-16 | --record looked the served build up by arm id and fell back to the pipeline's git sha; no cell named its incumbent; fixed in P1R |
| N-17 | Check HP read seats from workspace_routing (backend groups), so no seat could be covered, and STALE compared a model name with a git sha; fixed in P1R |
| N-18 | The backfill decided restorability from presence at closeout, gave pull recipes for tags no registry serves, and verified nothing; fixed in P1R |
| N-19 | No production suite marks a task `screen: true`, so `--tier screen` selects nothing (Part 3: family suites mark their screen tasks) |
| N-20 | `baseline_reusable` has no caller (Parts 3 and 5: any cross-campaign baseline reuse must call it) |

## Follow-on tasks (assigned, not dropped)

- Council roster instrument.
- Media harness.
- Computer-use environment.
- UAT harness audit.

## Review of the task's first version (2026-10-13), and how V2 answers it

An independent review of TASK_WFE_ROOT_FIX_V1 found eight defects in the task itself. Each was
checked against the code before it was accepted, and all eight hold.

| # | Finding | Checked | V2 answer |
|---|---|---|---|
| R-1 | `REMOVE` fired on "no BETTER anywhere", so a not-separated or incomplete record could become a removal. FOLD and PURPOSE overlapped. | yes | `decision.dispose()`: a fixed precedence. Incomplete, inconclusive or unmeasured evidence is NO_DECISION. All not-separated is REDUNDANT (a resource choice) or RETAIN_DIVERSITY, never REMOVE. FOLD and PURPOSE are mutually exclusive. |
| R-2 | The controls gate ran only when a campaign was created. Resume and append returned before it; `--smoke` never called `open_campaign`; `--dry-run` only counted rows. | yes, reproduced offline | The gate runs on open, append, every execution after resume, smoke and dry-run. Receipts go to `controls_receipts.jsonl` with suite digests. Resume writes nothing, so `--status`, `--watch` and `--health` stay read-only. |
| R-3 | Screen and confirm tiers, baseline joining and run identity were unspecified. `expand_matrix` runs every task; rows are `stage="full"`; the report compares arms within one campaign. | yes | Incumbents and candidates share one sweep campaign, so there is no cross-campaign join. `run_id` is unchanged; screen rows are repeat 1 of the screen tasks and are reused as confirm repeat 1. The interfaces are specified, with an offline end-to-end test. |
| R-4 | The statistics rule was ambiguous: population, repeats, missing rows, the 31 → 28 case. | yes | `decision.py`. The unit is the task, compared paired with an exact sign test. More than 10% excluded is NO_DECISION. The floor is on the compared set. Arguable tasks are counted against the leader in a worst case, so the set stays at 31. |
| R-5 | Production tool mode had no fixture or isolation contract. The documents MCP fixes `OUTPUT_DIR` at service start and publishes every file to Open WebUI. | yes | A contract covering fixture path mapping, per-run directories, artifact ownership through the trace, publication suppression or cleanup, rollback, and acceptance proofs. |
| R-6 | The test guard blocked only listed ports on four local host strings; `host.docker.internal`, remote addresses and subprocesses got through. | yes, reproduced offline | Default-deny for non-loopback addresses and service ports, extended to Python subprocesses. The sync_config switch moved into Phase 1. |
| R-7 | Provenance was one creation-time record with a dirty boolean, and rescoring overwrote evidence. | yes | A per-row and per-segment `instrument` fingerprint: commit, uncommitted-diff digest, config digest, engine. The report refuses mixed instruments. Rescoring preserves the original. |
| R-8 | Checkout path; "never drop a hunk" against a newer HEAD; no per-phase rollback or receipts; scope contradictions. | yes | The checkout is pinned and HEAD wins. Every phase has Preflight/Build/Verify/Rollback/Commit, with PASS, NOT_APPLICABLE, FAIL or BLOCKED receipts and a terminal acceptance ledger. There is one commit per cause, and the probe rule is reworded. |

## Specifications of the root fixes

These sections are the specifications that the code points to. They are kept here rather than
in docstrings, so that the code stays within the complexity ratchet.

### Decision rule (`tests/wfe/decision.py`, cause C4)

`decision.py` is the only implementation; its tests pin every case below.

**Population.**
- The unit is the task, identified as `(suite, task_id)`.
- A cell's expected task set comes from the campaign matrix, not from the rows that happen to
  exist.
- A row for a task outside that set is an error.
- A task is scored for an arm only when the arm has every stored repeat (zero-based,
  `0..repeats-1`) and every one has a model-quality outcome. BLOCKED, HARNESS_ERROR,
  PENDING_REVIEW or a missing repeat excludes the task.
- A task's score is passes divided by repeats.
- The compared set is the expected tasks that both arms scored.
- Every other expected task is excluded with its reason, including tasks that are missing from
  both arms.

**Confirm verdict**, first match wins:
1. More than 10% of the expected tasks excluded → NO_DECISION (excluded).
2. Fewer than 30 compared tasks → NO_DECISION (floor).
3. Exact two-sided sign test on the tasks where the arms differ gives p ≥ 0.05 →
   NOT_SEPARATED.
4. Re-scoring the arguable tasks against the leading arm (the worst case) makes the result no
   longer significant, or flips its direction → NO_DECISION (arguable-sensitive). Arguable tasks
   stay in the compared set, so the floor counts them.
5. Otherwise BETTER (the candidate leads) or WORSE.

**Screen.** Uses repeat 0 of the screen tasks only. DROP when the candidate loses at least 3
more tasks than it wins, over at least 8 compared tasks; otherwise ADVANCE. A screen DROP is a
cost filter, never a decision on its own.

**Eligibility.** `eligibility(facts)` reads a table, first match wins:
1. Not-vettable family, and the model verifiably lacks the capability → INELIGIBLE.
2. Not-vettable family → NOT_VETTABLE.
3. Not in the catalog → MISSING.
4. Not installed or not restorable → MISSING.
5. The family has no suite at the floor → MISSING.
6. Verified no tool support where tools are needed → INELIGIBLE.
7. Tool support unknown or unverified → MISSING.
8. Context unknown or unverified → MISSING.
9. Verified context below the workspace's → INELIGIBLE.
10. Memory footprint unknown → MISSING.
11. Verified not to fit beside the pinned services → INELIGIBLE.
12. Otherwise ELIGIBLE.

An unknown fact is MISSING, never INELIGIBLE.

**Disposition**, `dispose()`, first match wins:
1. No intended workspace recorded → NO_DECISION.
2. An intended workspace is INELIGIBLE or absent from the cells → NO_DECISION (fix the queue).
3. BETTER in an intended workspace → FOLD.
4. An intended workspace not confirmed → NO_DECISION.
5. BETTER only outside the intended workspaces → PURPOSE.
6. Any cell MISSING, ADVANCE, NO_DECISION or NOT_VETTABLE → NO_DECISION.
7. NOT_SEPARATED somewhere, and the model is the only member of its lineage → RETAIN_DIVERSITY.
8. NOT_SEPARATED somewhere → REDUNDANT. This is a resource choice, not evidence of harm.
9. WORSE in every intended workspace, and WORSE or DROP everywhere else → REMOVE.

INELIGIBLE cells take no part in rules 3–9.

### Known-answer controls (`tests/wfe/controls.py`, cause C2)

```text
Known-answer controls for WFE tasks: a checker has to be shown to tell a
right answer from a wrong one before any campaign can score a model with it.

Every scoring defect the 2026-10-13 audits found in a checker or an answer key
was of one kind: the instrument scored something that was not a model's
correct answer as a PASS, or the reverse. Examples include a stub passing, the
placeholder text passing, an echo of a readable file passing, a shotgun answer
naming every class passing, and a key going stale. None of these needs a model
to detect. This module runs each task's checkers against fixed control answers
offline, and `open_campaign` refuses to open a campaign whose plan touches a
task that fails its controls.

Controls:
  automatic, on every answer-graded task (must NOT pass):
    empty        — ""
    placeholder  — the pipeline's no-answer message
    echo         — the instruction plus every seed file, which catches answer
                   keys a model could read instead of derive
  declared on the task (`"controls": {"pass": [...], "fail": [...]}`):
    pass         — each must PASS (a gold answer; required on any task with an
                   `exact` key, so a key that no answer can satisfy is caught)
    fail         — each must NOT pass (shotguns, near misses)
  `expires` (ISO date) on a task with a time-sensitive key: past it, the task
  fails its controls until the key is re-verified and the date moved.

File-graded tasks (pytest, file checks) carry their own stub checks in
test_wfe_contracts; controls skip them rather than fake a sandbox.
```

### Offline boundary (`tests/_netguard/netguard.py`, cause C5)

```text
Offline boundary for unit tests (WFE_ROOT_FIX program (P1–P5), cause C5).

Policy, applied to every TCP connect in the test process and in any Python
subprocess it starts:
  - any non-loopback destination is refused (remote hosts, LAN addresses,
    host.docker.internal, any hostname other than localhost);
  - a loopback destination on a configured Portal service port is refused;
  - other loopback ports are allowed, so a test may run its own local server;
  - Unix sockets are allowed.
Refused connections raise ConnectionRefusedError, so no traffic flows, and are
recorded. The pytest fixture in tests/conftest.py fails the test unless it is
marked `live_port_ok`. Subprocesses record into the file named by
PORTAL_NETGUARD_LOG, which the fixture reads.
Non-Python subprocesses (curl, docker) are outside this boundary.
```

### Instrument identity, the fitness ledger and check HP (`tests/wfe/campaign.py`, `tests/wfe/report.py`, `scripts/validation/wfe.py`; causes C1 and C3; corrected by P1R)

The build that served a row, observed, frozen per pair, checked on every row, and
carried into the ledger, where check HP compares it with what production serves.

```text
A seat decision rests on rows that must have been served by the build the
decision names. Two things make that non-obvious:

  - the instrument fingerprint answers "what measured this?" and is shared by
    every arm in a campaign. Putting the served build in it would give two arms
    in one comparison different fingerprints and block the comparison;
  - one model is legitimately served by different builds in different
    workspaces (granite4.1:8b-ctx8k is granite-4.1-8b-mxfp8 on oMLX in
    auto-coding and the Ollama tag in auto-research). A per-model freeze would
    reject that as drift.

So identity is keyed "<workspace>|<model tag>" and holds:
  backend  the backends.yaml entry id the pipeline's trace reports;
  model    the served model id the trace reports;
  content  observed in the engine's own store, never assumed:
           Ollama: the tag's manifest digest from /api/tags (changes when a tag
             is re-pulled, re-quantised or re-baked under the same name);
           oMLX: a sha256 over config.json, tokenizer_config.json,
             chat_template.jinja and generation_config.json, the name and size
             of every *.safetensors file, and the model's model_settings.json
             entry, in the directory oMLX's own settings list (model_dirs).
  An identity whose content cannot be observed has content "" and a reason.
  It is never frozen, and preflight reports it as a finding, so the arm is
  blocked. (Before P1R a missing oMLX directory hashed to one constant shared
  by every model, and an unreachable Ollama gave "": both passed as identities.)

Where it is enforced:
  every arm's preflight (execute and --preflight alike) freezes each pair on
    first sight and turns any later change into IDENTITY DRIFT: the arm is
    blocked (exit 6). Before P1R only --preflight froze, and execution
    discarded what it observed;
  after every row the row's identity is observed again (backend and model from
    its own trace, content from the store) and compared with the freeze; a
    difference quarantines the row and stops the arm (exit 5), exactly as
    instrument drift does. Turns served by two models match nothing. Before
    P1R the row copied the frozen content, so a rebuild under the same name
    could never show up;
  the report refuses a pipeline campaign whose scored rows lack an identity or
    disagree with the freeze; a missing identity is a refusal, never a pass;
  --record refuses a campaign with no frozen identities, and every cell names
    its incumbent and carries both sides' identity (served, incumbent_served),
    looked up by model tag. Before P1R the lookup used the arm id, missed for
    card arms, and wrote the pipeline's git sha as the served build;
  check HP reads each seat as portal.yaml's model_hint for every workspace
    backends.yaml routes (workspace_routing holds backend groups, not models;
    before P1R every one of the 58 "seats" was a group list, so no seat could
    ever be covered). A seat is covered by a cell it won (model) or defended
    (incumbent). A cell is STALE when production now serves another model for
    it, or the same model with different content; a build HP cannot observe is
    a warning, not a pass.

The same key is what Part 3's eligibility receipts use.
```

### Restorability of removals (`scripts/wfe_disposition_backfill.py`, cause C3; corrected by P1R)

```text
Whether a removal can be undone is a question for the registry, not for what was
installed at closeout. For each removed Ollama identity the backfill asks the
registry for the manifest of the tag `ollama pull` would fetch and compares its
layers with the model_layer_digests the register recorded:
  verified (the measured artifact), differs (the registry now serves another
  build), unrecorded (no digest was recorded), unrestorable (no registry serves
  it), unverified (the registry could not be asked). --write refuses while any
  removal is unverified; HTTP 403 is a proxy or a gated repo, never "absent".
Portal's -ctxNk tags are made locally by `models apply-params` FROM a base tag with
PARAMETER num_ctx: the recipe pulls the base and recreates the variant, and the
base is what the registry is asked about. RESTORE_SOURCES maps an identity the
register recorded without a source to a pullable tag; it is verified like any other.
Before P1R: "absent at closeout" meant unrestorable (command-r:35b-08-2024-q4_K_M and
granite4.2:30b-q4_K_M among the five at risk), nine recipes pulled local -ctxNk or
portal5/ tags no registry serves, and "verify with model_layer_digests" was text,
not a check.
```

### Failure traceability (`tests/wfe/runner.py`, R2-22 and R-7)

```text
Two pieces of evidence a decision needs, both of which used to be destroyed:

  - a turn that stalls or errors has no `served` record. Its pipeline trace is
    then the only evidence of what answered the request, and the correlation id
    is the only way to reach that trace. `chat()` attaches the id to whatever a
    call raises, and the turn loop records it. Direct-engine rows have no trace
    and record no empty id.
  - re-grading a campaign offline (`rescore_debug_dir`) used to overwrite the
    row's outcome, notes and evidence, so the verdict the run actually produced
    became unrecoverable and nothing recorded which checkers replaced it. A
    rescored row now keeps `original: {outcome, notes, instrument}` — written
    once, so a second pass cannot bury the run's own verdict — and records
    `rescore: {outcome, grader: instrument_fingerprint()}`. The report pools
    rescored outcomes only when every row in the comparison was graded by the
    same instrument.
```

## Review of the task's second version (2026-10-13), and how V3 answers it

A second independent review of V2 found seven defects. Each was checked against the code
before it was accepted, and all seven hold.

| # | Finding | Checked | V3 answer |
|---|---|---|---|
| V2-1 | `confirm()` counted only tasks that had rows. A task missing from both arms never counted, so 30 of 50 tasks completed returned BETTER. | reproduced | `confirm()` takes the expected `(suite, task)` set from the matrix. Missing-from-both, missing-from-one and missing-repeat tasks all count against the 10% limit. Unexpected ids raise an error. There is a test for each case. |
| V2-2 | The fingerprint hashed the names of untracked files, not their contents. Result writes under `tests/wfe/results` changed it mid-campaign. Local HEAD said nothing about the deployed pipeline. | yes | The fingerprint is a content digest of the instrument with results excluded, plus HEAD's `portal/` tree. A dirty instrument is refused. The pipeline image carries `PORTAL_BUILD_SHA` and `/health` reports it; preflight refuses a deployed `portal/` tree that is not HEAD's. Tests prove that result writes do not change the fingerprint and source changes do. |
| V2-3 | A path seen in a tool result does not prove the row created the file; reads and listings return existing files. | yes | A creation-receipt contract (Phase 4.2): only `create_*` results count, the path must resolve inside the run's namespace, the file must not exist in the pre-run inventory, and cleanup deletes only receipted files. Tests cover pre-existing files, read/list paths, symlink escapes and interrupted cleanup. |
| V2-4 | "MISSING or out of scope" left removal-changing choices to the executor. | yes | `eligibility()` is a deterministic table with named data sources; an unknown fact is MISSING. `dispose()` refuses an intended workspace that is ineligible or absent. |
| V2-5 | Stored repeats are zero-based (0–2), but the rule assumed 1–3, so current-format rows were all excluded. | reproduced (72/72/71 stored rows at repeats 0/1/2) | The rule uses the stored zero-based indices, and the screen uses repeat 0. One test feeds rows from the real `expand_matrix`. |
| V2-6 | Screen-only families could not satisfy Phase 7's completion rule. Creative had no adjudication. | yes | Mandatory families for this release are enumerated, and an incomplete in-scope family is BLOCKED. Creative and the other deferrals are explicit NOT_APPLICABLE items with named follow-ons. |
| V2-7 | Bare `pytest`/`ruff`/`python`; no CI or streaming gate; stop rules unenforced; no watchdog or interruption test. | yes (the runner aborted only when the engine was unreachable) | `uv run` throughout, the CLAUDE.md verification ladder (`ci_local.sh`, `smoke_stream.sh`), `arm_stop_reason()` enforced in code, `memory_safety_watch.py` named with its PID file, an interruption-and-resume drill, and process exits recorded. |

## Review of the task's third version (2026-10-13), and how V4 answers it

A third independent review of V3 found eight defects. Each was checked against the code before
it was accepted, and all eight hold.

| # | Finding | Checked | V4 answer |
|---|---|---|---|
| V3-1 | Phase 3's end-to-end gate needed the queue and generator that only arrive in Phase 4.4, a circular dependency. | yes | Phase 3 runs a component test on a hand-written plan; the full queue-to-ledger test is Phase 4's gate. |
| V3-2 | Mandatory families other than documents and data had no production tool surface, so they could still be measured through the sandbox substitute. | yes: `workspace_context()` swaps tools and adds a harness note; real tools include compliance-store writes, live Splunk, live web and a review service | An eval marker makes the pipeline expose only a per-family allowlist, add no harness note, and forward the marker to MCPs. Every mandatory family has a tool mode and an isolation check. Proxy verdicts count only for `proxy_ok` coding. Two proof traces are kept per family. |
| V3-3 | The data contract assumed `read_*` tools and documents paths; the data MCP keeps DuckDB sessions under `_SESS_DIR`. | yes | A data session contract: a marker-bound `session_id`, the fixture digest recorded at `attach_source`, query-result checks, a campaign-scoped session directory and connection key, and `close_session` cleanup. A receipt is required only for exported artifacts. |
| V3-4 | Eligibility evidence could come from the wrong backend. Behavioral probes always call Ollama, and `model_sizes()` reads only Ollama disk sizes. | yes | Production selection resolves the serving backend first, and every fact comes from it. Tool support is measured through the pipeline. Memory is measured resident at the workspace's context against `load_guard`'s ceiling. |
| V3-5 | The arm launcher used `$BASHPID` (unset in zsh) and returned `tee`'s status; a stopped arm still exited 0. | yes: `main()` returned 0 after a stop | `tests/wfe/run_arm.py`, a Python supervisor, registers the real PID, forwards signals and returns the child's status. The CLI exits 5 on a stop. Tests use fake processes. |
| V3-6 | Phase 4 rollback ran `rm -rf $AI_OUTPUT_DIR/wfe`, deleting other campaigns. | yes | Receipt-based cleanup only, under a validated campaign root, with the default output directory handled exactly as `docker-compose.yml` does. |
| V3-7 | Per-arm identity inside the shared fingerprint would block every two-model comparison. | yes | Identity is a separate, frozen per-arm `identity_map`, checked within each arm. Tests accept two models and reject a change within an arm. |
| V3-8 | Reused screen rows keep `tier=screen`; a confirm filtered by tier lost 10 of 30 tasks. | reproduced by the reviewer | `tier` records only how a row was created and never decides membership. A test runs a 10-task screen then a 30-task, three-repeat confirm and expects 30 compared tasks. |

## Review of the task's fourth version (2026-10-13), and how the split program answers it

A fourth independent review of V4 found seven defects plus five contract tightenings. Each was
checked against the code before it was accepted, and all of them hold. The single task file is
replaced by a program of five part-tasks (`WFE_ROOT_FIX_PROGRAM.md`). Each part is executable on
its own, against the receipts of the parts before it.

| # | Finding | Checked | Answer |
|---|---|---|---|
| V4-1 | 30 of the 31 `compliance_agentic_full` tasks read `packet.json` with `file_read`, which is not on the production compliance allowlist. | yes | P3: compliance suite migration (synthetic fixtures through allowlisted compliance tools, trace-grounded checkers). The packet tasks stay as a labelled diagnostic. The known-open cell runs on the migrated suite. |
| V4-2 | Identity frozen per arm, but the same arm is served by different builds in different workspaces. | yes | P2: identity keyed by `(workspace, arm)`, recording backend, served id and build/content identity, outside the shared fingerprint. |
| V4-3 | `lru_cache` hid instrument changes during a run. | reproduced | P1 patch 7: an uncached observation against a frozen baseline, enforced at execute, append, smoke and after every row. A drifted row is quarantined. |
| V4-4 | The KB has no deletion route; graph memory uses `DEFAULT_USER = "default"` in every query. | yes (`rag_mcp.py` routes; `graph_memory.py` lines 290–451) | P2: marker-bound campaign KB and memory scope, with create/ingest/lookup/expand/list/delete, a foreign-id refusal, no fallback to all KBs or the default user, and interrupted cleanup. |
| V4-5 | Data session ids must match `^[A-Za-z_][A-Za-z0-9_]{0,63}$`; one `<id>.duckdb` per session. | yes (`data_mcp.py:49`, `_db_path`) | P2: a digest-derived session token `wfe_<digest>` with a recorded mapping and the existing single-file layout. Validation is not weakened. |
| V4-6 | data-mcp (and compliance-mcp) are host-native LaunchAgents (`com.portal5.data-mcp`); `launch.sh rebuild` neither stamps nor restarts them. | yes (`scripts/native-mcp-service.sh`, `scripts/lib/util.sh:584`) | P2: native launch-time stamp, the `launchctl kickstart` lifecycle, per-service build observed in preflight and receipts, and service-specific rollback. |
| V4-7 | A blocked arm and an empty selection exited 0. | reproduced | P1 patch 8: exit codes 0, 5, 6 and 7, `--verify-complete` (8 when incomplete), tested through the real CLI under the supervisor. |
| + | Coding proof criteria; full incumbent confirm coverage; private trace storage and the public-text scan; an enumerated acceptance matrix; stale prose. | yes | The program index's acceptance matrix; P5's coverage, storage and scan rules; this document corrected. |

## Review of Part 1's execution (2026-10-14), and how P1R answers it

Part 1's twelve embedded patches landed intact (every added line is on main or was
superseded within the series; the hand-resolved patch 9 lost nothing; the rig passes
12/12 on main). The defects were all in the build steps the task specified in a
paragraph each and accepted on synthetic tests. The task asked for one live smoke per
arm, whose checklist did not include identity, and for no live run of the decision
chain. The live output showed two of the defects (the smoke's identity had no content;
HP warned that 58 of 58 seats had no cell, which could never clear), and the
acceptance criteria let both through. The executor did what the task said.

| Row | Defect | Why the task let it through | P1R |
|---|---|---|---|
| P1-2.4 (N-15) | Identity: execution discarded what preflight observed; rows copied content from the freeze; an unobservable build passed as a constant or "" | the spec said "preflight records" without naming execution; the three required tests were synthetic dicts | observed, frozen at every arm's preflight, checked after every row; unobservable blocks |
| P1-3.6 (N-16) | Ledger: `served` looked up by arm id, falling back to the pipeline's git sha; no incumbent | "served build" undefined; the component test never read it | both sides' identity by model tag; refuses without a freeze |
| P1-3.7 (N-17) | HP: seats were backend-group lists; STALE compared a model name with a git sha | the seat's source was never stated; tests used a routing shape production lacks | seats from model_hint; coverage by model or incumbent; STALE by identity |
| P1-3.9 (N-18) | Backfill: restorability from presence at closeout; recipes for tags no registry serves; "verified" unchecked | "exact pull or import recipe" with no verification step | registry manifests compared by digest; ctx recipes; --write refuses unverified |
| P1-3.2 (N-19) | No production suite marks `screen: true`, so `--tier screen` selects nothing | Part 3 builds the suites | assigned to Part 3 |
| P1-3.4 (N-20) | `baseline_reusable` has no caller | no cross-campaign reuse path exists yet | assigned to Parts 3 and 5: any reuse must call it |

Every build step in a task file now carries its own live acceptance line, run on the
production stack, not only named tests.
