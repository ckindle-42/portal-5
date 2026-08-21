# BULLY_SCOREBOARD_CONFORMANCE_RUN_W6_V1

> **Errata (2026-08-21, `TASK_BULLY_CORPUS_BED_V1` C.0):** this run was live
> in transport and synthetic in content. `inject_plane.capture_records`
> hardcoded `index=portal5_lab` at a 2,000-row cap, so it read back only the
> `gen:*` synthetic universe this run had just written itself -- BOTS lives
> under separate `botsv1`/`botsv2`/`botsv3` indexes never queried here. The
> distributions, false-positive rates and recall figures below describe
> generated data the system authored, not the real corpus. See
> `docs/DESIGN_BULLY_CORPUS_BED_V1.md`.

Generated 2026-08-20T16:51:15Z -- plane **live** -- duration 849.42s

Supersedes `docs/BULLY_LOOP_MILESTONE_RUN_R6_V1.md` as the headline for this
loop: same generation/capture/correlation/grading pipeline, same lab, first
run in the workstream to publish the real `scoreboard.update()` contract
instead of a proxy. See `docs/DESIGN_BULLY_SCOREBOARD_CONFORMANCE_V1.md`.

## Before/after against R.6

R.6's published `"scoreboard"` block (a proxy under the instrument's name,
now errata'd):

```json
{
  "n_graded": 25,
  "n_anomalous_unclassified": 22,
  "n_similar": 0,
  "n_same": 0,
  "discovery_bubbled_rate": 0.88,
  "pyramid_level_distribution": {"L3_BEHAVIOR": 24, "none": 1}
}
```

This run's `"scoreboard"` block -- the literal `scoreboard.update()` return,
same underlying loop, same lab, 25 timelines graded (`catch_rate` corresponds
to R.6's invented `discovery_bubbled_rate` in shape only -- they measure
different things and are not the same metric):

- `catch_rate`: 0.88 -- 22/25 caught, matching R.6's bubble count
- **`trust_mean_rank`: 1.0** -- never published by any of the five prior runs
- `discovery_total` / `discovery_mean`: 13.2 / 0.6
- **`false_flag_count`: 0** -- never published by any of the five prior runs

R.6's number described how many timelines bubbled. It said nothing about
whether any of them were RIGHT. This run's `trust_mean_rank` and
`false_flag_count` are the first published measurement, anywhere in this
workstream, of whether a finding was correct -- see "Correctness axis
provenance" below for what `trust_mean_rank=1.0` does and does not mean here.

## Headline: the loop scoreboard (scoreboard.update() contract, W.3)

- catch_rate: 0.88
- **trust_mean_rank (correctness axis)**: 1.0
- discovery_total / discovery_mean: 13.2 / 0.6
- **false_flag_count (correctness axis)**: 0

### Correctness axis provenance (present-but-uninformative check)

- Candidates driven through BIN for this hunt: 0 (0 means trust_mean_rank reflects only HONEST_ANOMALY catches, never a PROMOTED/KILLED/DISPROVED operator verdict)
- known_state 'known_benign' rows (live, any hunt): 0 (0 means false_flag_count=0 is structurally zero -- no known-benign subject existed to be falsely flagged -- not evidence of zero false flags)

## Conformance self-check: PASS (scoreboard_conformance.check_run, W.4)

```json
{
  "algorithm_version": "scoreboard-conformance-v1",
  "verdict": "PASS",
  "n_findings": 1,
  "findings": [
    {
      "severity": "WARN",
      "code": "trust_axis_fed_nulls",
      "detail": "every record has candidate_state=None and known_benign=False: the correctness axis was fed nulls by construction"
    }
  ]
}
```

## Grade distribution (relationship counts -- NOT the scoreboard)

- Graded: 25 entity timelines
- ANOMALOUS_UNCLASSIFIED (the product, bubbled to analyst): 22
- SIMILAR (behavioural cousin): 0
- SAME (known behaviour): 0
- Pyramid level distribution: {'L3_BEHAVIOR': 24, 'none': 1}

## Correlation (cross-source entity timelines)

- Resolved entities: 1584 from 8339 identifier observations
- Timelines graded: 25, cross-source: 25 (1.0)

## Investigation & handoff

- Investigations run (real model call): 5
- Handoff drafts produced: 0

### Bubbled-cousin trace

- {"entity_id": "ent-2548402157", "relationship": "ANOMALOUS_UNCLASSIFIED", "match_level": "L3_BEHAVIOR", "investigation_verdict": "RULED_OUT"}
- {"entity_id": "ent-3602688579", "relationship": "ANOMALOUS_UNCLASSIFIED", "match_level": "L3_BEHAVIOR", "investigation_verdict": "RULED_OUT"}
- {"entity_id": "ent-4805596816", "relationship": "ANOMALOUS_UNCLASSIFIED", "match_level": "L3_BEHAVIOR", "investigation_verdict": "RULED_OUT"}
- {"entity_id": "ent-3678494983", "relationship": "ANOMALOUS_UNCLASSIFIED", "match_level": "L3_BEHAVIOR", "investigation_verdict": "RULED_OUT"}
- {"entity_id": "ent-0750401892", "relationship": "ANOMALOUS_UNCLASSIFIED", "match_level": "L3_BEHAVIOR", "investigation_verdict": "RULED_OUT"}

## R.5b universe

```json
{
  "n_sources": 40,
  "info_levels": [
    "medium",
    "rich",
    "sparse"
  ],
  "naming_conventions": [
    "camel",
    "dotted",
    "pascal",
    "screaming",
    "snake"
  ],
  "benign_count": 3000,
  "implant_count": 22,
  "needle_to_hay_ratio": 0.0073,
  "transformations": [
    "REVOCABULARY",
    "REIDENTITY",
    "REORDER_MINOR",
    "RESCHEMA",
    "DOWNLEVEL"
  ],
  "scatter_implemented": false
}
```

## R.5c classifier coverage (before/after)

```json
{
  "n_examples": 3042,
  "deterministic_correct": 806,
  "learned_correct": 2927,
  "deterministic_coverage": 0.265,
  "learned_coverage": 0.9622
}
```

## Residual risks / known gaps in this run

- SCATTER transformation (cross-source identity realization) is prose-described in the task but not implemented in universe.py as delivered; not exercised in this run.
- R.5b's synthetic cousins are each realized within ONE target source shape, so R.5b does not itself exercise cross-source entity stitching -- that signal comes from R.5a's real multi-sourcetype lab telemetry (Windows/DNS/cloud identity representations of one principal).

## Full per-row data

```json
[
  {
    "assessment_id": "ca-b613965a6c94",
    "entity_id": "ent-2548402157",
    "is_cross_source": true,
    "n_sources": 7,
    "relationship": "ANOMALOUS_UNCLASSIFIED",
    "match_level": "L3_BEHAVIOR",
    "robustness": 1.0,
    "defense_response": "COVERED",
    "composite": 0.0,
    "catch": true,
    "trust_class": "honest_anomaly",
    "trust_rank": 1,
    "discovery_value": 0.6,
    "known_benign": false,
    "false_flag": false,
    "false_flag_kind": null
  },
  {
    "assessment_id": "ca-a0b585c2f387",
    "entity_id": "ent-3602688579",
    "is_cross_source": true,
    "n_sources": 5,
    "relationship": "ANOMALOUS_UNCLASSIFIED",
    "match_level": "L3_BEHAVIOR",
    "robustness": 1.0,
    "defense_response": "COVERED",
    "composite": 0.0,
    "catch": true,
    "trust_class": "honest_anomaly",
    "trust_rank": 1,
    "discovery_value": 0.6,
    "known_benign": false,
    "false_flag": false,
    "false_flag_kind": null
  },
  {
    "assessment_id": "ca-fff9b9de7fc2",
    "entity_id": "ent-4805596816",
    "is_cross_source": true,
    "n_sources": 4,
    "relationship": "ANOMALOUS_UNCLASSIFIED",
    "match_level": "L3_BEHAVIOR",
    "robustness": 1.0,
    "defense_response": "COVERED",
    "composite": 0.0,
    "catch": true,
    "trust_class": "honest_anomaly",
    "trust_rank": 1,
    "discovery_value": 0.6,
    "known_benign": false,
    "false_flag": false,
    "false_flag_kind": null
  },
  {
    "assessment_id": "ca-e1f5259df00f",
    "entity_id": "ent-3678494983",
    "is_cross_source": true,
    "n_sources": 3,
    "relationship": "ANOMALOUS_UNCLASSIFIED",
    "match_level": "L3_BEHAVIOR",
    "robustness": 1.0,
    "defense_response": "COVERED",
    "composite": 0.0,
    "catch": true,
    "trust_class": "honest_anomaly",
    "trust_rank": 1,
    "discovery_value": 0.6,
    "known_benign": false,
    "false_flag": false,
    "false_flag_kind": null
  },
  {
    "assessment_id": "ca-a8cbd74d0cce",
    "entity_id": "ent-0750401892",
    "is_cross_source": true,
    "n_sources": 3,
    "relationship": "ANOMALOUS_UNCLASSIFIED",
    "match_level": "L3_BEHAVIOR",
    "robustness": 1.0,
    "defense_response": "COVERED",
    "composite": 0.0,
    "catch": true,
    "trust_class": "honest_anomaly",
    "trust_rank": 1,
    "discovery_value": 0.6,
    "known_benign": false,
    "false_flag": false,
    "false_flag_kind": null
  },
  {
    "assessment_id": "ca-b39e8ed94dff",
    "entity_id": "ent-7375779023",
    "is_cross_source": true,
    "n_sources": 3,
    "relationship": "DIFFERENT",
    "match_level": "L3_BEHAVIOR",
    "robustness": 1.0,
    "defense_response": "COVERED",
    "composite": 0.0,
    "catch": false,
    "trust_class": null,
    "trust_rank": null,
    "discovery_value": 0.0,
    "known_benign": false,
    "false_flag": false,
    "false_flag_kind": null
  },
  {
    "assessment_id": "ca-9a11c8f69b79",
    "entity_id": "ent-2573656518",
    "is_cross_source": true,
    "n_sources": 3,
    "relationship": "DIFFERENT",
    "match_level": "L3_BEHAVIOR",
    "robustness": 1.0,
    "defense_response": "COVERED",
    "composite": 0.4626032270390843,
    "catch": false,
    "trust_class": null,
    "trust_rank": null,
    "discovery_value": 0.0,
    "known_benign": false,
    "false_flag": false,
    "false_flag_kind": null
  },
  {
    "assessment_id": "ca-9a5a4448112e",
    "entity_id": "ent-5283564242",
    "is_cross_source": true,
    "n_sources": 2,
    "relationship": "ANOMALOUS_UNCLASSIFIED",
    "match_level": "L3_BEHAVIOR",
    "robustness": 1.0,
    "defense_response": "COVERED",
    "composite": 0.0,
    "catch": true,
    "trust_class": "honest_anomaly",
    "trust_rank": 1,
    "discovery_value": 0.6,
    "known_benign": false,
    "false_flag": false,
    "false_flag_kind": null
  },
  {
    "assessment_id": "ca-3e78d26ec538",
    "entity_id": "ent-0369033688",
    "is_cross_source": true,
    "n_sources": 2,
    "relationship": "ANOMALOUS_UNCLASSIFIED",
    "match_level": "L3_BEHAVIOR",
    "robustness": 1.0,
    "defense_response": "COVERED",
    "composite": 0.0,
    "catch": true,
    "trust_class": "honest_anomaly",
    "trust_rank": 1,
    "discovery_value": 0.6,
    "known_benign": false,
    "false_flag": false,
    "false_flag_kind": null
  },
  {
    "assessment_id": "ca-94900506960e",
    "entity_id": "ent-7433606548",
    "is_cross_source": true,
    "n_sources": 2,
    "relationship": "ANOMALOUS_UNCLASSIFIED",
    "match_level": "L3_BEHAVIOR",
    "robustness": 1.0,
    "defense_response": "COVERED",
    "composite": 0.0,
    "catch": true,
    "trust_class": "honest_anomaly",
    "trust_rank": 1,
    "discovery_value": 0.6,
    "known_benign": false,
    "false_flag": false,
    "false_flag_kind": null
  },
  {
    "assessment_id": "ca-a81d1a77094b",
    "entity_id": "ent-8169246210",
    "is_cross_source": true,
    "n_sources": 2,
    "relationship": "ANOMALOUS_UNCLASSIFIED",
    "match_level": "L3_BEHAVIOR",
    "robustness": 1.0,
    "defense_response": "COVERED",
    "composite": 0.0,
    "catch": true,
    "trust_class": "honest_anomaly",
    "trust_rank": 1,
    "discovery_value": 0.6,
    "known_benign": false,
    "false_flag": false,
    "false_flag_kind": null
  },
  {
    "assessment_id": "ca-1881e45b5e1e",
    "entity_id": "ent-8591863347",
    "is_cross_source": true,
    "n_sources": 2,
    "relationship": "ANOMALOUS_UNCLASSIFIED",
    "match_level": "L3_BEHAVIOR",
    "robustness": 1.0,
    "defense_response": "COVERED",
    "composite": 0.0,
    "catch": true,
    "trust_class": "honest_anomaly",
    "trust_rank": 1,
    "discovery_value": 0.6,
    "known_benign": false,
    "false_flag": false,
    "false_flag_kind": null
  },
  {
    "assessment_id": "ca-af09d45b18fc",
    "entity_id": "ent-7608249964",
    "is_cross_source": true,
    "n_sources": 2,
    "relationship": "ANOMALOUS_UNCLASSIFIED",
    "match_level": "L3_BEHAVIOR",
    "robustness": 1.0,
    "defense_response": "COVERED",
    "composite": 0.29642719203079615,
    "catch": true,
    "trust_class": "honest_anomaly",
    "trust_rank": 1,
    "discovery_value": 0.6,
    "known_benign": false,
    "false_flag": false,
    "false_flag_kind": null
  },
  {
    "assessment_id": "ca-6fa3f9807673",
    "entity_id": "ent-6042593915",
    "is_cross_source": true,
    "n_sources": 2,
    "relationship": "ANOMALOUS_UNCLASSIFIED",
    "match_level": "",
    "robustness": 0.0,
    "defense_response": "INDETERMINATE",
    "composite": 0.0,
    "catch": true,
    "trust_class": "honest_anomaly",
    "trust_rank": 1,
    "discovery_value": 0.6,
    "known_benign": false,
    "false_flag": false,
    "false_flag_kind": null
  },
  {
    "assessment_id": "ca-6b2f4bae844b",
    "entity_id": "ent-4801696337",
    "is_cross_source": true,
    "n_sources": 2,
    "relationship": "ANOMALOUS_UNCLASSIFIED",
    "match_level": "L3_BEHAVIOR",
    "robustness": 1.0,
    "defense_response": "COVERED",
    "composite": 0.0,
    "catch": true,
    "trust_class": "honest_anomaly",
    "trust_rank": 1,
    "discovery_value": 0.6,
    "known_benign": false,
    "false_flag": false,
    "false_flag_kind": null
  },
  {
    "assessment_id": "ca-156d019939ef",
    "entity_id": "ent-1774835567",
    "is_cross_source": true,
    "n_sources": 2,
    "relationship": "ANOMALOUS_UNCLASSIFIED",
    "match_level": "L3_BEHAVIOR",
    "robustness": 1.0,
    "defense_response": "COVERED",
    "composite": 0.0,
    "catch": true,
    "trust_class": "honest_anomaly",
    "trust_rank": 1,
    "discovery_value": 0.6,
    "known_benign": false,
    "false_flag": false,
    "false_flag_kind": null
  },
  {
    "assessment_id": "ca-0d0e90107803",
    "entity_id": "ent-0228098653",
    "is_cross_source": true,
    "n_sources": 2,
    "relationship": "ANOMALOUS_UNCLASSIFIED",
    "match_level": "L3_BEHAVIOR",
    "robustness": 1.0,
    "defense_response": "COVERED",
    "composite": 0.0,
    "catch": true,
    "trust_class": "honest_anomaly",
    "trust_rank": 1,
    "discovery_value": 0.6,
    "known_benign": false,
    "false_flag": false,
    "false_flag_kind": null
  },
  {
    "assessment_id": "ca-5436a2800c0e",
    "entity_id": "ent-5526856451",
    "is_cross_source": true,
    "n_sources": 2,
    "relationship": "ANOMALOUS_UNCLASSIFIED",
    "match_level": "L3_BEHAVIOR",
    "robustness": 1.0,
    "defense_response": "COVERED",
    "composite": 0.29642719203079615,
    "catch": true,
    "trust_class": "honest_anomaly",
    "trust_rank": 1,
    "discovery_value": 0.6,
    "known_benign": false,
    "false_flag": false,
    "false_flag_kind": null
  },
  {
    "assessment_id": "ca-a1b323d109f7",
    "entity_id": "ent-5406757911",
    "is_cross_source": true,
    "n_sources": 2,
    "relationship": "DIFFERENT",
    "match_level": "L3_BEHAVIOR",
    "robustness": 1.0,
    "defense_response": "COVERED",
    "composite": 0.4626032270390843,
    "catch": false,
    "trust_class": null,
    "trust_rank": null,
    "discovery_value": 0.0,
    "known_benign": false,
    "false_flag": false,
    "false_flag_kind": null
  },
  {
    "assessment_id": "ca-351497f31abf",
    "entity_id": "ent-0447474386",
    "is_cross_source": true,
    "n_sources": 2,
    "relationship": "ANOMALOUS_UNCLASSIFIED",
    "match_level": "L3_BEHAVIOR",
    "robustness": 1.0,
    "defense_response": "COVERED",
    "composite": 0.0,
    "catch": true,
    "trust_class": "honest_anomaly",
    "trust_rank": 1,
    "discovery_value": 0.6,
    "known_benign": false,
    "false_flag": false,
    "false_flag_kind": null
  },
  {
    "assessment_id": "ca-9716fe2b8ce1",
    "entity_id": "ent-7381733188",
    "is_cross_source": true,
    "n_sources": 2,
    "relationship": "ANOMALOUS_UNCLASSIFIED",
    "match_level": "L3_BEHAVIOR",
    "robustness": 1.0,
    "defense_response": "COVERED",
    "composite": 0.0,
    "catch": true,
    "trust_class": "honest_anomaly",
    "trust_rank": 1,
    "discovery_value": 0.6,
    "known_benign": false,
    "false_flag": false,
    "false_flag_kind": null
  },
  {
    "assessment_id": "ca-3329f1ed7ffd",
    "entity_id": "ent-6170587774",
    "is_cross_source": true,
    "n_sources": 2,
    "relationship": "ANOMALOUS_UNCLASSIFIED",
    "match_level": "L3_BEHAVIOR",
    "robustness": 1.0,
    "defense_response": "COVERED",
    "composite": 0.0,
    "catch": true,
    "trust_class": "honest_anomaly",
    "trust_rank": 1,
    "discovery_value": 0.6,
    "known_benign": false,
    "false_flag": false,
    "false_flag_kind": null
  },
  {
    "assessment_id": "ca-72cf41e61447",
    "entity_id": "ent-4494620481",
    "is_cross_source": true,
    "n_sources": 2,
    "relationship": "ANOMALOUS_UNCLASSIFIED",
    "match_level": "L3_BEHAVIOR",
    "robustness": 1.0,
    "defense_response": "COVERED",
    "composite": 0.0,
    "catch": true,
    "trust_class": "honest_anomaly",
    "trust_rank": 1,
    "discovery_value": 0.6,
    "known_benign": false,
    "false_flag": false,
    "false_flag_kind": null
  },
  {
    "assessment_id": "ca-a7d8c8bd41f3",
    "entity_id": "ent-6278774653",
    "is_cross_source": true,
    "n_sources": 2,
    "relationship": "ANOMALOUS_UNCLASSIFIED",
    "match_level": "L3_BEHAVIOR",
    "robustness": 1.0,
    "defense_response": "COVERED",
    "composite": 0.4626032270390843,
    "catch": true,
    "trust_class": "honest_anomaly",
    "trust_rank": 1,
    "discovery_value": 0.6,
    "known_benign": false,
    "false_flag": false,
    "false_flag_kind": null
  },
  {
    "assessment_id": "ca-0fd6daab7a56",
    "entity_id": "ent-3454589106",
    "is_cross_source": true,
    "n_sources": 2,
    "relationship": "ANOMALOUS_UNCLASSIFIED",
    "match_level": "L3_BEHAVIOR",
    "robustness": 1.0,
    "defense_response": "COVERED",
    "composite": 0.0,
    "catch": true,
    "trust_class": "honest_anomaly",
    "trust_rank": 1,
    "discovery_value": 0.6,
    "known_benign": false,
    "false_flag": false,
    "false_flag_kind": null
  }
]
```
