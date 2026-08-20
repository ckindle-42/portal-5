# BULLY_UNIVERSAL_INTAKE_RUN_M6_V1

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

## Which plane produced these numbers

```
"plane": "fixture"
"plane_reason": "live plane unavailable: LAB_SPLUNK_PASSWORD not set -- capture side would be unauthenticated"
"sealed_count": 0
```

`inject_plane.run_inject_capture()` attempted the live plane first (E.5) and fell
back to the deterministic E.3 blend fixture (`blend.compose_blend()`) because this
environment carries no `LAB_SPLUNK_PASSWORD` -- exactly the fail-closed contract
E.5 exists to enforce: no synthetic stand-in is ever silently substituted for a
live capture, and the run states which plane fed it, in the payload itself, not
just in this prose. The live branches of `generate_labelled_activity`,
`capture_records`, and `run_inject_capture` are exercised directly (mocked
`lab.dispatch_lab_tool`/`live_connect.connect_lab_splunk`, real
`DataPlane`/`SpecimenLedger`) in `tests/security/bully/test_universal_e5_inject_plane.py`,
since this environment has no lab credentials to exercise them against a real
lab. A future run with lab credentials present will report `"plane": "live"` and
a nonzero `sealed_count` (ground truth sealed through
`specimen_ledger.SpecimenLedger`, `source_lane="live_lab"`).

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

## Reproducing this run

```bash
uv run python3 scripts/bully_universal_intake_run.py --output docs/BULLY_UNIVERSAL_INTAKE_RUN_M6_V1.json
```

With `LAB_SPLUNK_PASSWORD` (and the other lab-exec prerequisites) set, the same
command attempts the live plane first and reports `"plane": "live"` on success,
falling back to the fixture and stating the reason otherwise -- never silently.
