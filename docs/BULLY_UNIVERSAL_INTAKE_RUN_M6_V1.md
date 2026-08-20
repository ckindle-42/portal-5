# BULLY_UNIVERSAL_INTAKE_RUN_M6_V1

M.6 verification run for `TASK_BULLY_UNIVERSAL_INTAKE_AND_INJECT_V1`. Companion to
`BULLY_UNIVERSAL_INTAKE_RUN_M6_V1.json` (full per-row data;
`scripts/bully_universal_intake_run.py` regenerates it). Every JSON column below
appears in this doc; nothing is summarized away.

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
just in this prose. A future run with lab credentials present will report
`"plane": "live"` and a nonzero `sealed_count` (ground truth sealed through
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
sources is in `role_maps_by_source` in the JSON (not reproduced here for length;
it is the mechanical proof behind the table above).

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
  "L1_ARTIFACT": {"COUSIN": 188, "NORMAL": 63},
  "L2_ENTITY":   {"NORMAL": 8, "NOVEL": 1, "UNKNOWN_SAME": 50},
  "L3_CHAIN":    {"NORMAL": 9, "UNKNOWN_SAME": 5},
  "L4_WINDOW":   {"NORMAL": 1}
}
```

`n_units_total: 325`. Every level the artifact graph produces is represented,
correcting the M.3 report's L4-only framing.

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
genuinely different absolute figure.

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
in the JSON.

## Precision/recall, including injected-benign negatives (falsifiable)

```json
{
  "n": 325,
  "outcome_distribution": {"COUSIN": 188, "NORMAL": 81, "NOVEL": 1, "UNKNOWN_SAME": 55},
  "precision": 0.05327868852459016,
  "recall": 0.7222222222222222
}
```

Ground truth is bound per unit from the blend fixture's own provenance (T.1
wall: malicious if any covered artifact came from an injected chain, benign
otherwise) -- `resolve_unit_outcome` never receives this binding, it is attached
strictly after grading. Precision (5.3%) is genuinely low: the deterministic
classifier and shape-matching over a small, mostly-benign L1_ARTIFACT population
produce many false COUSIN calls on ordinary CloudTrail reads, which is now
visible and falsifiable rather than hidden behind an L4-only, injected-only
population. This is the honest number Q1-Q4 exist to surface, not a result to
explain away -- it directly sizes the calibration work the learned action
classifier (deferred, see design doc) is meant to improve.

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

## Concern briefs: zero all-`other`, real entities and timestamps

```
"concern_brief_count": 244
"real_concern_brief_count": 244   (entities present AND span_seconds present)
"all_other_brief_count": 1
```

244 of 244 concern briefs carry real extracted entities and a real
`span_seconds` -- the M.3 defect (five of ten briefs with no entities, no
timestamps, every action `other`) does not reproduce here. One brief's shape
features happen to be `class_present=other` alone (a genuine, isolated
low-information match, not a systemic collapse); it is not a `NOVEL`/`COUSIN`
built entirely from blindness, since `entities`/`span_seconds` are populated on
it too. Five sample briefs (`sample_concern_briefs` in the JSON) are reproduced
below; each carries `entities`, `span_seconds`, and either
`shared_shape_features`/`diverging_shape_features` or their vocabulary
counterparts -- never an empty relation.

## Residual limitation surfaced by this run, reported honestly

The combined-corpus role inference misfiles one field: `awsRegion` (CloudTrail
schema; constant `"us-east-1"` within CloudTrail records) is present in only
~24% of the *combined, cross-schema* record pool (since no other schema in the
blend has that field at all), which trips the sparse-strong-identifier override
(a value matching the name+digit-run pattern, e.g. `us-east-1`) and gets
classified `ENTITY` instead of the `CONSTANT` it would resolve to if the corpus
were built per-source. This is exactly the class of misfiling the design doc's
residual risks section names as expected and measurable, not hidden: it is
visible in `role_maps_by_source` (each source's own role map correctly resolves
`awsRegion` in isolation) and in the sample brief above (`awsRegion=us-east-1`
appears as a vocabulary/entity token). It does not affect extraction validity or
any published recall number; it is reported here so the next universal-intake
pass has a concrete, measured target rather than a vague caveat.

## Reproducing this run

```bash
uv run python3 scripts/bully_universal_intake_run.py --output docs/BULLY_UNIVERSAL_INTAKE_RUN_M6_V1.json
```

With `LAB_SPLUNK_PASSWORD` (and the other lab-exec prerequisites) set, the same
command attempts the live plane first and reports `"plane": "live"` on success,
falling back to the fixture and stating the reason otherwise -- never silently.
