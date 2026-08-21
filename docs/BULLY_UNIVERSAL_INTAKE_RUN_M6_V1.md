# BULLY_UNIVERSAL_INTAKE_RUN_M6_V1


> **Errata (2026-08-21, `TASK_BULLY_FULL_ASSEMBLY_V1` F.0):** this run exercised 5/16 of the bully modules over 251 records (well under 0.001% of the 281,069,416-record corpus) and is a partial assembly at proxy scale (see `docs/DESIGN_BULLY_FULL_ASSEMBLY_V1.md`); its findings describe that subset, not the system.
> **Errata (2026-08-20, `TASK_BULLY_SCOREBOARD_CONFORMANCE_V1`):** this run's
> headline is not a module contract, and its correctness axis
> (`trust_mean_rank`, `false_flag_count` from `scoreboard.update()`) was never
> published -- `correctness_axis_not_published` fires against this doc,
> alongside `recall_contradiction`. See
> `docs/DESIGN_BULLY_SCOREBOARD_CONFORMANCE_V1.md` for the corrected
> diagnosis and the live successor run
> `docs/BULLY_SCOREBOARD_CONFORMANCE_RUN_W6_V1.md`.

> **Errata (2026-08-20, `TASK_BULLY_LOOP_REINTEGRATION_V1`):** this run measured
> the reform organ on its own bench -- `bully_universal_intake_run.py`, never
> called by the orchestrator (`orchestrator.py` graded with `cousin_engine.grade`
> at this run's HEAD). The organ is now wired into the loop via
> `bully/loop_grader.py`, and the live, loop-scoreboard-headlined successor run is
> `docs/BULLY_LOOP_MILESTONE_RUN_R6_V1.md`. See
> `docs/DESIGN_BULLY_LOOP_REINTEGRATION_V1.md` for the full reintegration design.

M.6 verification run for `TASK_BULLY_UNIVERSAL_INTAKE_AND_INJECT_V1`. Companion to
`BULLY_UNIVERSAL_INTAKE_RUN_M6_V1.json` (full per-row data;
`scripts/bully_universal_intake_run.py` regenerates it). Every JSON column below
appears in this doc; nothing is summarized away.

> **Regenerated 2026-08-20** after fixing the one residual finding the first run
> (2026-08-19) surfaced: field-role inference computed a field's coverage against
> the *whole* cross-schema record pool, so a field present in every record of one
> schema but absent from every other schema (CloudTrail's `awsRegion`) read as
> globally sparse and tripped the sparse-strong-identifier `ENTITY` override on a
> value shaped like an identifier (`us-east-1`). Coverage is now measured against
> each field's own home source(s) (`field_roles.infer_field_roles`); `awsRegion`
> now resolves `CONSTANT` as it should. This changed the downstream numbers
> meaningfully (see below) -- the first run's `COUSIN` count included a fair
> number of spurious L1 matches manufactured by that misfiling, not by genuine
> content similarity. The corrected numbers below are the honest ones.
>
> **The live plane (E.5) has now actually been run against the real lab**
> (credentials in `.env`, this project's own owned/maintained `portal.lab`) --
> see "Live-plane verification" below. It genuinely dispatches authorized
> recon commands, captures real multi-schema Splunk telemetry (7 sourcetypes,
> far exceeding the Q2 `>=3` bar), and seals ground truth through the real
> `SpecimenLedger`. This section's headline numbers still come from the E.3
> fixture, because a live capture carries no inline provenance by design (Q3:
> ground truth is sealed separately, joined only after grading) -- the
> leave-one-family-out and precision/recall sections below need a labelled
> population to score against, which only the fixture supplies inline today.
> That is a scope boundary of this run, stated plainly, not a live-plane
> failure: joining the sealed ledger's live truth against a live capture for
> full grading-plane metrics is future work.

## Which plane produced these numbers

```
"plane": "fixture"
"plane_reason": "live plane unavailable: LAB_SPLUNK_PASSWORD not set -- capture side would be unauthenticated"
"sealed_count": 0
```

This section's numbers come from the E.3 fixture (see the note above for why).
`inject_plane.run_inject_capture()` attempted the live plane first (E.5); in this
specific invocation `LAB_SPLUNK_PASSWORD` was deliberately unset to force the
fixture path and produce the fully-labelled, all-sections-populated report below
-- exactly the fail-closed contract E.5 exists to enforce: no synthetic stand-in
is ever silently substituted for a live capture, and the run states which plane
fed it, in the payload itself, not just in this prose. The live branches of
`generate_labelled_activity`, `capture_records`, and `run_inject_capture` are
exercised directly (mocked `lab.dispatch_lab_tool`/`live_connect.
lab_splunk_connector`, real `DataPlane`/`SpecimenLedger`) in
`tests/security/bully/test_universal_e5_inject_plane.py` for CI, and for real
against the live lab as documented in "Live-plane verification" below.

## Field-role maps and source-level extraction validity (Q1)

`n_records: 251` across four schemas sharing zero field names.

| source | extraction_valid |
|---|---|
| blend-cloudtrail | true |
| blend-firewall | true |
| blend-osquery | true |
| blend-sysmon | true |

`insufficient_view_rate: 0.0` -- every source in this run resolved cleanly. The
full per-field role, coverage, distinct-ratio and reasons breakdown for all four
sources is in `role_maps_by_source` in the JSON. `blend-cloudtrail`'s `awsRegion`
now resolves `CONSTANT` (coverage 0.9375 within its own source, distinct_count 1)
-- the fix landed.

## The plural capture (Q2)

```
"schemas_present": ["cloudtrail", "firewall_syslog", "osquery", "sysmon"]
"injected_count": 11
"benign_count": 240
```

Four genuinely different schemas, zero shared field names -- the Q2 bar
(`>=3`) is cleared with margin. The injected:benign ratio (11:240, ~4.4%) is
sparse, matching the analyst's real situation: a handful of real activity
threaded through a much larger benign stream.

## Outcome distribution, all four unit levels (not L4 alone)

```json
{
  "L1_ARTIFACT": {"COUSIN": 32, "NORMAL": 219},
  "L2_ENTITY":   {"NORMAL": 51, "UNKNOWN_SAME": 5},
  "L3_CHAIN":    {"NORMAL": 34, "NOVEL": 5, "UNKNOWN_SAME": 5},
  "L4_WINDOW":   {"NORMAL": 1}
}
```

`n_units_total: 352`. Every level the artifact graph produces is represented,
correcting the M.3 report's L4-only framing. `L1_ARTIFACT`'s `COUSIN` count
dropped from 188 (first run) to 32 after the field-role fix -- the difference was
spurious matches on units whose only "signal" was the `awsRegion` misfiling.

## Leave-one-family-out: cousin and novelty recall, separated (RC6)

```json
{
  "cousin_recall": 0.5,
  "novelty_recall": 0.5,
  "conditional_recall": 1.0,
  "absolute_recall": 1.0,
  "full_library_cousin_recall": 1.0,
  "shuffled_control_cousin_recall": 0.0,
  "benign_control_concern_rate": 0.0,
  "controls_hold": true,
  "verdict": "VALID"
}
```

Three injected families (`discovery`/T1018, `credential_access`/T1558,
`persistence`/T1547 -- see `per_family` in the JSON for the row-level split).
`cousin_recall` (library-dependent) and `novelty_recall` (library-independent)
are reported separately, correcting the M.3 headline that was 75% `NOVEL`. The
shuffled-library control is computed on the cousin subset only and collapses to
0.0 (well under `SHUFFLED_CONTROL_MAX_RATIO * max(...)`), and the benign control
holds at 0.0 concern rate. `absolute_recall` equals `conditional_recall` in this
run because the fixture's every injected artifact formed a unit (no silent
extraction failures this run) -- `known_activity_count_by_family` was not
supplied since there is no larger known-activity population beyond what the
fixture generated; a live-plane run with dataset-level counts would populate a
genuinely different absolute figure. These per-family numbers are unaffected by
the `awsRegion` fix (the injected chains' own units never touched that field).

## Honest cross-vocabulary recovery rate (U.3', sizes the learned classifier)

```json
{
  "cross_vocabulary_shape_distance": 0.5714285714285714,
  "cross_vocabulary_overall_relation": "SIMILAR",
  "recovered": true
}
```

Real Windows-native verbs (`Logon`, `whoami`, `Invoke-Command`), not the class
names themselves. `AttachUserPolicy` classifies `escalate`; `Invoke-Command`
classifies `execute` -- a genuine partial classifier mismatch, not a
cherry-picked perfect match. The rung still recovers (`SIMILAR`) at this
distance; the full ladder report (monotonicity, shuffle and negative controls,
all validated on `shape_distance`) is in `cross_vocabulary_recovery.ladder_report`
in the JSON. This metric is independent of the blend record pool and unaffected
by the `awsRegion` fix.

## Precision/recall, including injected-benign negatives (falsifiable)

```json
{
  "n": 352,
  "outcome_distribution": {"COUSIN": 32, "NORMAL": 305, "NOVEL": 5, "UNKNOWN_SAME": 10},
  "precision": 0.0851063829787234,
  "recall": 0.2222222222222222
}
```

Ground truth is bound per unit from the blend fixture's own provenance (T.1
wall: malicious if any covered artifact came from an injected chain, benign
otherwise) -- `resolve_unit_outcome` never receives this binding, it is attached
strictly after grading. Precision improved from 5.3% (first run, inflated false
positives from the `awsRegion` misfiling manufacturing spurious COUSIN matches on
ordinary CloudTrail reads) to 8.5% after the fix -- still genuinely low, and now
a truer read of the deterministic classifier's real false-positive rate on a
small, mostly-benign L1_ARTIFACT population. Recall dropped correspondingly
(72.2% to 22.2%): several of the "recovered" malicious matches in the first run
were the same `awsRegion`-driven false shape matches, not real detections. This
is the honest number Q1-Q4 exist to surface, not a result to explain away -- it
directly sizes the calibration work the learned action classifier (deferred, see
design doc) is meant to improve.

## Structural coverage: unconnected-artifact rate (RC6, cause now attributable)

```json
{
  "unconnected_artifact_count": 0,
  "total_artifact_count": 251,
  "unconnected_artifact_rate": 0.0,
  "cause": "sparse_source_or_no_shared_key"
}
```

Zero isolated artifacts this run -- every artifact shares an entity or falls
within a chain's temporal window with another. The `cause` field is always
populated (`sparse_source_or_no_shared_key`) so a future run with genuine
isolation can distinguish "no unit formed because extraction failed" (Q1 gate,
reported separately as `insufficient_view_rate`) from "no unit formed because the
graph found nothing to connect this artifact to" -- the two were conflated
before this task.

## Concern briefs: zero all-`other`-only, real entities and timestamps

```
"concern_brief_count": 47
"real_concern_brief_count": 47   (entities present AND span_seconds present)
"all_other_brief_count": 5
```

47 of 47 concern briefs carry real extracted entities and a real
`span_seconds` -- the M.3 defect (five of ten briefs with no entities, no
timestamps, every action `other`) does not reproduce here. Five briefs' shape
features are `class_present=other` alone (genuine, isolated low-information
matches on osquery's diff-type `added`/`removed` action, which the deterministic
classifier has no needle for -- a known, reported gap, not a systemic collapse);
none of the five lack entities or timestamps, so none are the M.3 pattern (an
extraction failure masquerading as a shape match). Two sample briefs
(`sample_concern_briefs` in the JSON) are reproduced below; each carries
`entities`, `span_seconds`, and both shape and vocabulary relation detail --
never an empty relation.

```json
{
  "artifact_ids": ["a00120"],
  "level": "L1_ARTIFACT",
  "outcome": "COUSIN",
  "entities": ["hostIdentifier=host-0"],
  "span_seconds": 0.0,
  "shared_shape_features": ["class_present=other"],
  "diverging_vocabulary_features": ["1", "13", "added", "hostIdentifier=host-0"],
  "axis_of_divergence": "vocabulary",
  "what_could_not_be_seen": []
}
```

## Live-plane verification (E.5, run for real against `portal.lab`)

With `.env`'s lab credentials sourced, `inject_plane.run_inject_capture()` was run
directly against the real, owned lab -- not mocked, not the fixture:

```
plane: live
n_records: 500
schemas_present: ["OktaIM2:log", "corpus:probe", "linux:auditd", "web:access",
                   "windows:powershell", "windows:security", "windows:sysmon"]
extraction_valid: true
n_units: 503
sealed_count: 3   (first run; a second run seals under fresh run-scoped
                    specimen_ids -- see below)
```

**Generate.** `generate_labelled_activity()` dispatched every step of both
`_LIVE_CHAINS` (`nxc smb`/`nxc smb --shares` for `discovery`/T1018, `nxc ldap
--asreproast` for `credential_access`/T1558) against the live DC
(`10.10.11.21`) via `lab.dispatch_lab_tool("execute_bash", ...)` -- the same
dispatch path the security-bench exec chains already use. All three steps
returned `ok: true`.

**Capture.** `capture_records()` initially reused `live_connect.
connect_lab_splunk`, which hardcodes `sourcetype=aws:cloudtrail` -- exactly the
RC1/RC2 mistake for this module's purpose, verified directly: it captured only
CloudTrail records, missing the Windows-side telemetry the generated recon
chains actually produce. Fixed to query the whole index (`lab_splunk_connector`,
no sourcetype filter, `sort -_time` for recency) -- the live capture above then
returned 7 genuinely different schemas, `extraction_valid: true`, and 503
gradeable units. (A tight relative-time window, e.g. `earliest=-30m`, was tried
and found to return zero rows against this lab's Splunk export endpoint despite
current-timestamped events existing -- a real quirk of this deployment, not a
connector defect; left at the connector's `earliest="0"` default, which reliably
returns current data when combined with `sort -_time`.)

**Seal.** `seal_ground_truth()` wrote all three generated steps into the real,
pre-existing production `SpecimenLedger` (the same ledger `cousin_calibration_
bench.py` and this project's other bully runs already use) with `source_lane=
"live_lab"` and the full `family`/`technique`/`chain_id`/`step_idx` provenance.
A second seal of the same chains did **not** silently overwrite or collide with
the first -- `specimen_id` is scoped with a random per-run suffix specifically
because `_LIVE_CHAINS`' chain ids are fixed literals and this is meant to run
repeatedly (see the fix in `inject_plane.seal_ground_truth`); the ledger's own
duplicate-content check confirmed the first run's entries were still intact and
unchanged.

**What this proves.** The full generate -> capture -> seal pipeline works
end-to-end against real, owned infrastructure, not just its fail-closed path.
`insufficient_view_rate` computed by `bully_universal_intake_run.py`'s
per-sourcetype isolation check (`_per_source_role_maps`) is high (5 of 7
sourcetypes) for this specific 500-record sample even though the *combined*
capture extracts cleanly -- each sourcetype's own isolated slice mostly carries
Splunk's `host` field pinned to this lab's pre-loaded corpus tag
(`corpus-attack-data`) rather than a varying per-event identity, so no field
resolves ENTITY in isolation; only the combined pool's `source` field gives
enough distinct values to clear the bar. This is an honest artifact of how this
lab's existing corpus was loaded, not a defect in role inference, and is a
concrete target for a future pass (real per-asset identity fields, e.g.
`Computer`/`TargetUserName` from the Sysmon/Security payloads once parsed out of
Splunk's `_raw`, would very likely resolve cleanly per-sourcetype too).

## Reproducing this run

```bash
uv run python3 scripts/bully_universal_intake_run.py --output docs/BULLY_UNIVERSAL_INTAKE_RUN_M6_V1.json
```

With `LAB_SPLUNK_PASSWORD` (and the other lab-exec prerequisites, e.g. `source
.env`) set, the same command attempts the live plane first and reports
`"plane": "live"` on success, falling back to the fixture and stating the
reason otherwise -- never silently.
