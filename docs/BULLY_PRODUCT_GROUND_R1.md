# Bully product ground — R1 record (2026-10-08/09)

> **Historical record (pre-T7).** Restored after the T7 consolidation deleted it; it is the
> diagnosis the Bully review program (T0–T7) was built from and T0 reads it. Paths and counts
> describe the tree before the prune — current state is `docs/BULLY_REVIEW_STATE.md`.

TASK_BULLY_PRODUCT_GROUND_AND_HARNESS_V1, R1.1–R1.4. Counts and mechanisms only; per-run rows and
capture contents stay in `/Volumes/data01/portal5_hunt/` and the scratch directory.

## R1.1 Lab Splunk — DONE (operational fix, no commit)

**Root cause.** The Splunk container (`splunk/splunk:10.2`, inside LXC 301) had exited with SIGTERM
on 2026-09-24 while a KVStore version upgrade was in progress. Earlier, on 2026-07-24 the KVStore
had been upgraded to 4.4; the upgrade left an in-progress marker and a post-upgrade journal that the
bundled mongod cannot read (`unsupported WiredTiger file version`). Splunk refuses to start while the
marker is present ("Splunk stop / restart is not allowed").

**Fix.** Restored the KVStore from the Splunk-made pre-upgrade copy (`kvstore/mongo_backup/mongo`,
2026-07-24 23:07). The live KVStore was copied aside first (`kvstore/mongo_live_failed_20261009T022056`,
305 MB); the stale marker was moved, not deleted. Started the container. splunkd is running; 8089 and
8000 listen; KVStore `status: ready`, `storageEngine: wiredTiger`, `versionUpgradeInProgress: 0`.

**Corpus.** The BOTS indexes are on the `splunk-etc` volume (`apps/botsv*_data_set`, 32 GB); nothing
was removed. LXC 301 snapshots: `corpus-loaded` (2026-07-24) and `current`; neither was touched.
`pct listsnapshot 301` was not run through the MCP tool, which mis-routes LXC to the QEMU endpoint;
the node-level `pct listsnapshot` was used instead.

**Counts** (`| eventcount summarize=false`, recorded → now):

| index | recorded | now | delta |
|---|---|---|---|
| botsv1 | 33,413,777 | 33,413,837 | +60 |
| botsv2 | 226,317,740 | 226,337,781 | +20,041 (+0.009%) |
| botsv3 | 1,944,092 | 2,030,855 | +86,763 (+4.5%) — unexplained, open |
| portal5_lab | ≥13,350,000 | 17,782,874 | above floor |

`.env` `LAB_SPLUNK_URL` / `LAB_SPLUNK_PASSWORD` reach it from the host (HTTP 200).

**Open, non-blocking.** Splunk warns that KV store 4.2 is unsupported by 9.4+ and must be migrated.
The botsv3 growth needs an explanation before any lab-count claim relies on it.

## R1.2 Stalled hunts — classified

`hunt_state.db` backed up first (`hunt_state.db.bak_20261009_r1`, 22 MB). No rows deleted.

| group | count | created by | iterations | stage reached | classification |
|---|---|---|---|---|---|
| C.6 live hunt on the real corpus bed | 6 | `scripts/bully_corpus_hunt_run.py` (`store.hunt_create`) | 0 | DRAFT | script record: grades written, stage machine never ran |
| R.6 loop reintegration milestone run | 9 | `scripts/bully_loop_milestone_run.py` | 0 | DRAFT | script record |
| X.6 analyst-loop maturation run | 10 | `scripts/bully_analyst_loop_run.py` | 0 | DRAFT | script record |
| Y.6 truth-joined acceptance re-run | 8 | `scripts/bully_truth_acceptance_run.py` | 0 | DRAFT | script record |
| hunt closeout-authorized-lab | 5 | `orchestrator.run_hunt` (CLI, Aug 15) | 0 | BLOCKED | product path: reached TGT select and MUT overlay, then the episode verdict blocked it; no reason recorded on the hunt row |

Script records have no lease, no iterations, no council, no promotion and no SOC rows, and no code
resumes them. They are orphaned, but cancelling them is an operator-gated state change. **Decision:**
not cancelled in R1; recommended for the reviewer to confirm and cancel with `hunt cancel`.

Hunts created by this session (operator `operator:chris-r1-trace`): 7 BLOCKED, all with zero
iterations. Four are dry runs or replay attempts that stopped at the episode gate or at targeting;
the rest are the struts attempts below. None reached grading.

## R1.3 One product iteration — traced; not completed end to end

### Stage trace (what the product does, observed)

Stage names are from `orchestrator.run_hunt_iteration`. "Observed" means a decision-event or code
path was seen in a real run; "not reached" means the run ended before that stage.

| stage | function called | observed in the runs | models invoked | store rows |
|---|---|---|---|---|
| config | `run_hunt` → `hunt_create`, `lease_acquire`, `_record(HUNT_CREATED)` | yes | none | hunts, decision_events |
| LOAD / RECALL | `_resolve_live_investigation_models`, `recall` | no decision event recorded | none observed | none observed |
| TARGETED | `_do_target` → `targeting_mod` (TGT) | yes: `target_select` event | none | decision_events, coverage cells, cost preflight |
| DIRECT | `_do_mutate` → MUT compile | yes: `gate` event, empty overlay | none | decision_events |
| EXECUTING | `lab_driver(target_cell, dry_run)` | yes (see below) | see below | episode evidence refs |
| episode gate | verdict from `episode.derive_verdict` | yes: INDETERMINATE → BLOCKED | — | decision_events |
| ANALYZING | `_do_analyze` → `investigation_arm`, `build_signature`, `retrieve_candidate_axes`, `loop_grader.build_cousin_assessment` | **not reached** | not reached | not reached |
| PROMOTING / COMPOUNDING | `_stage(...)`, `organ.process_outbox` | **not reached** | not reached | not reached |

**EXECUTING, per driver:**
- Live driver (`_default_lab_driver`, the previous default): executed the red chain against the lab
  target; the red model returned text without tool calls at every step (depth 1/9 STALLED); the blue
  model made two tool calls (one with a malformed name, `query_ splunk`) and then returned text.
  Verdict INDETERMINATE → BLOCKED, `RED_EXECUTION_FAILED`, coverage 0. Route resolved through the
  pipeline (`auto-security::security-tool-granite41-8b`, :9099 healthy, 12/12 backends).
- Dry run (live driver): `RED_EXECUTION_FAILED` for a red step that never ran (defect D1, fixed).
- Replay driver (new default): not completed. `load_latest_red_capture` finds one replayable pair in
  the whole capture store, for `vuln_struts2_rce`. The default targeting picks `ad_full_compromise`,
  which has none, so the hunt blocks with "no replayable recorded exercise". Restricting candidates
  to the struts cell fails targeting (`MISSING_COST`, see D5).

### Answers to the four questions

1. **Does `_do_analyze` see detection coverage? Is `defense_response` constant?** No, and yes in
   effect. `_do_analyze` builds `CoverageView(telemetry_healthy=True)` with no detection ids
   (`orchestrator.py`, `_do_analyze`). `loop_grader._defense_response` returns `INDETERMINATE` if not
   observable, otherwise `COVERED` when telemetry is healthy. The product path therefore yields only
   `COVERED` or `INDETERMINATE`, never `MISSED` or `NEAR_MISS`. Confirmed from code (defect D7). No
   product assessment has yet been stored, so there is no empirical distribution to show.
2. **What does `run_hunt` return, and where is the multi-iteration hunt?** It returns
   `"stop_reason": "single-iteration P1 proof"` and `"iterations": 1` as literals
   (`orchestrator.py`, end of `run_hunt`). `run_hunt_iteration` has exactly one caller, `run_hunt`.
   No multi-iteration loop exists on the product path. The product is still a one-iteration proof
   (defect D9).
3. **Is `hunt_memory` populated through `Organ.process_outbox` on :8946?** No. `process_outbox` runs
   after COMPOUNDING, which no run reached. `index_outbox` has 0 rows and `hunt_memory` is empty.
   Not exercised (D10).
4. **Do council, promotion or SOC delivery fire?** No. The verdict gate blocks the hunt before
   PROMOTING (`_stage("BLOCKED")` on a non-PROVEN/FAILED episode). Council opinions, promotion queue
   and SOC deliveries are zero for every hunt.

### Defects

| id | defect | status |
|---|---|---|
| D1 | Dry-run iteration recorded `RED_EXECUTION_FAILED` for a red step that never ran (`_run_chain_test` returns no `lab_success` in dry_run) | **fixed** `785f6770`; test `test_r1_dry_run_red_status.py` |
| D2 | Product default ran the live red chain against lab targets; every real run blocked | **fixed** `785f6770`: replay is the default, live needs `hunt run --live-red` |
| D3 | Red and blue models returned text without tool calls on the live chain, and a malformed tool name (`query_ splunk`) | open; observed only on the live chain, which is no longer the default. The reviewer's check says the pipeline returns correct tool calls for the security tool route, so the cause is in the chain prompt or call shape, not the route |
| D4 | BLOCKED hunts carry `stop_reason = None`; the reason exists only in the decision trail | open, non-blocking |
| D5 | Targeting ranks scenarios without replay availability, so it picks a scenario with no replayable exercise; injected candidate cells need a `cost_ref` that matches the hunt's own cost ledger, which does not exist before `run_hunt` creates the hunt (`MISSING_COST`) | **open, blocks the replay trace.** Design decision for the reviewer: replay-eligibility in TGT, or a replay-scoped candidate set with its own cost seed |
| D6 | Recorded exercises are nearly unusable under the current gate: 1 replayable pair in 1,127 captures; 250 of 252 `ad_full_compromise` captures fail the current ground-truth revalidation. The stored `valid: true` on older captures came from an earlier, looser validator: a July capture stored as valid for T1558.003 contains no EventCode 4769 lines | open, blocks replay; needs a data decision (re-certify, or record that the ground-truth set is unverifiable) |
| D7 | `defense_response` is constant on the product path: `telemetry_healthy=True` is hard-coded and no detection ids are passed | open, blocks any response-axis metric (lesson 7.2) |
| D8 | Lab Splunk down: KVStore left mid-upgrade | **fixed operationally** (R1.1); no code change |
| D9 | `run_hunt` returns a literal single-iteration result; no multi-iteration driver | open; R3 scope |
| D10 | `process_outbox` / `hunt_memory` never exercised on the product path | open; not reached |

## R1.4 Modules imported by the product path (runtime)

`python -X importtime -m portal.modules.security.core hunt run --dry-run` (dry-run only; the real
driver's lazy imports are not in this trace). 68 `portal.*` modules imported; 25 under
`security/core/bully/`: behavior_values, config, contracts, costing, cousin_engine, cutover,
drift_engine, events, evidence, investigation, loop_grader, mutation, orchestrator, organ, outbox,
plateau, playbooks, pyramid, scoreboard, series_cousin, signatures, store, targeting, telemetry_behavior.
Full list: scratch `r1/imported_portal_modules.txt`.

## Records

- Commits: `785f6770` (replay default, `--live-red`, D1 fix, tests). Gates: ruff clean; unit 3046
  passed; `tests/security/bully` 1165 passed.
- Scratch: `r1/` (import trace, console output of each run).
- Not done here: R1.3's end-to-end replay trace (blocked by D5/D6); R2 has not started.

## REVIEW STOP 1 — decisions for the reviewer

1. D5: how targeting should respect replay availability (eligibility filter vs. a replay-scoped candidate set).
2. D6: whether the 1,127 captures are re-certified under the current validator, or the ground-truth
   set for `ad_full_compromise` is declared unverifiable and replay is limited to the struts pair.
3. Whether the 33 DRAFT script records and the 5 closeout BLOCKED hunts are cancelled with `hunt cancel`.
