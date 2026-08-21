# BULLY_TRUTH_ACCEPTANCE_RUN_Y6_V1

> **Errata (2026-08-21, `TASK_BULLY_CORPUS_BED_V1` C.0):** this run was live
> in transport and synthetic in content. `inject_plane.capture_records`
> hardcoded `index=portal5_lab` at a 2,000-row cap, so it read back only the
> `gen:*` synthetic universe this run had just written itself -- BOTS lives
> under separate `botsv1`/`botsv2`/`botsv3` indexes never queried here. The
> distributions, false-positive rates and recall figures below describe
> generated data the system authored, not the real corpus. See
> `docs/DESIGN_BULLY_CORPUS_BED_V1.md`.

Generated 2026-08-20T22:18:02Z -- plane **live** -- duration 181.99s

**Scripted verdicts note:** analyst verdicts in this run are a deterministic CONFIRMED/BENIGN/UNSURE cycle sealed from the grader, standing in for a human reviewer, GUARDED against sealed truth (Y.4) -- a scripted verdict that contradicts truth is refused write-back and reported in `poisoning_report`, never written as knowledge.

## Acceptance report (Y.1 headline -- joined against sealed truth; `both_classes_notified` is DELETED, not demoted)

```json
{
  "cycle_1": {
    "algorithm_version": "truth-acceptance-v1",
    "verdict": "FAIL",
    "detection": {
      "n_rows": 25,
      "n_implants_graded": 5,
      "n_background_graded": 20,
      "true_positives": 5,
      "false_positives": 20,
      "false_negatives": 0,
      "precision": 0.2,
      "recall": 1.0,
      "background_false_positive_rate": 1.0,
      "by_implant_class": {
        "known_bad": {
          "graded": 2,
          "detected": 2,
          "missed": 0
        },
        "unknown_cousin": {
          "graded": 3,
          "detected": 3,
          "missed": 0
        }
      },
      "verdict": "FAIL",
      "reasons": [
        "background_false_positive_rate_1.000>0.1"
      ]
    },
    "poisoning": {
      "n_verdicts": 25,
      "confirmed_on_background": 7,
      "benign_on_implant": 2,
      "poisoning_rate": 0.28,
      "verdict": "FAIL",
      "reasons": [
        "confirmed_on_background_7/25: benign patterns written to the library as ANALYST_CONFIRMED malicious knowledge",
        "benign_verdict_on_2_real_implants:suppressing_true_positives"
      ]
    },
    "selection": {
      "n_implants_shipped": 32,
      "n_implant_entities_available": 5,
      "n_implant_entities_selected": 5,
      "selection_recall": 1.0,
      "verdict": "PASS",
      "reasons": []
    }
  },
  "cycle_2": {
    "algorithm_version": "truth-acceptance-v1",
    "verdict": "FAIL",
    "detection": {
      "n_rows": 25,
      "n_implants_graded": 5,
      "n_background_graded": 20,
      "true_positives": 5,
      "false_positives": 16,
      "false_negatives": 0,
      "precision": 0.23809523809523808,
      "recall": 1.0,
      "background_false_positive_rate": 0.8,
      "by_implant_class": {
        "known_bad": {
          "graded": 2,
          "detected": 2,
          "missed": 0
        },
        "unknown_cousin": {
          "graded": 3,
          "detected": 3,
          "missed": 0
        }
      },
      "verdict": "FAIL",
      "reasons": [
        "background_false_positive_rate_0.800>0.1"
      ]
    },
    "poisoning": {
      "n_verdicts": 25,
      "confirmed_on_background": 7,
      "benign_on_implant": 2,
      "poisoning_rate": 0.28,
      "verdict": "FAIL",
      "reasons": [
        "confirmed_on_background_7/25: benign patterns written to the library as ANALYST_CONFIRMED malicious knowledge",
        "benign_verdict_on_2_real_implants:suppressing_true_positives"
      ]
    },
    "selection": {
      "n_implants_shipped": 32,
      "n_implant_entities_available": 5,
      "n_implant_entities_selected": 5,
      "selection_recall": 1.0,
      "verdict": "PASS",
      "reasons": []
    }
  }
}
```

## Selection report (Y.3 -- did implants reach the grader)

```json
{
  "n_implants_shipped": 32,
  "n_implant_entities_available": 5,
  "n_implant_entities_selected": 5,
  "selection_recall": 1.0,
  "verdict": "PASS",
  "reasons": []
}
```

Production-ordering selection (richest-first, no priority set) alongside for comparison -- a detection benchmark is not a production sample:

```json
{
  "n_implants_shipped": 32,
  "n_implant_entities_available": 5,
  "n_implant_entities_selected": 0,
  "verdict": "FAIL",
  "reasons": [
    "selection_recall_0.000<0.5: implants were shipped but selection excluded them (richest-first bias)"
  ],
  "production_ordering_implant_fraction_reached": 0.0
}
```

## Poisoning report (Y.4 -- did any verdict write knowledge contradicting truth)

```json
{
  "n_verdicts": 25,
  "confirmed_on_background": 7,
  "benign_on_implant": 2,
  "poisoning_rate": 0.28,
  "verdict": "FAIL",
  "reasons": [
    "confirmed_on_background_7/25: benign patterns written to the library as ANALYST_CONFIRMED malicious knowledge",
    "benign_verdict_on_2_real_implants:suppressing_true_positives"
  ]
}
```

## Quarantine report -- 0 anchor(s) quarantined

```json
{
  "n_quarantined": 0,
  "anchor_ids": []
}
```

## Cycle 1 vs Cycle 2 (relationship distribution)

```json
Cycle 1: {
  "concerns_raised": 25,
  "n_relationships": {
    "SAME": 3,
    "SIMILAR": 21,
    "ANOMALOUS_UNCLASSIFIED": 1,
    "DIFFERENT": 0,
    "NEW": 0
  }
}
```
```json
Cycle 2: {
  "concerns_raised": 21,
  "n_relationships": {
    "SAME": 13,
    "SIMILAR": 11,
    "ANOMALOUS_UNCLASSIFIED": 1,
    "DIFFERENT": 0,
    "NEW": 0
  }
}
```

## Maturation report -- TRUE POSITIVES ONLY (headline; suppression of false positives on background is not maturation)

```json
{
  "concerns_before": 5,
  "concerns_after": 5,
  "suppressed_entities": [],
  "n_suppressed": 0,
  "still_raised": [
    "ent-1051696542",
    "ent-1094444755",
    "ent-4099741506",
    "ent-5389142738",
    "ent-7877106935"
  ],
  "newly_raised": [],
  "noise_reduction": 0.0
}
```

## Maturation report -- all concerns (NOT the headline, published for comparison)

```json
{
  "concerns_before": 25,
  "concerns_after": 21,
  "suppressed_entities": [
    "ent-2992551527",
    "ent-6797309659",
    "ent-8010106372",
    "ent-8259551446"
  ],
  "n_suppressed": 4,
  "still_raised": [
    "ent-0650734559",
    "ent-0983363439",
    "ent-1051696542",
    "ent-1094444755",
    "ent-1246908570",
    "ent-1870412855",
    "ent-2597790770",
    "ent-2645458010",
    "ent-3581189792",
    "ent-3966517958",
    "ent-4099741506",
    "ent-5389142738",
    "ent-6917430556",
    "ent-7517791242",
    "ent-7705980220",
    "ent-7855681328",
    "ent-7877106935",
    "ent-8071441321",
    "ent-8222603546",
    "ent-8512599023",
    "ent-8615652741"
  ],
  "newly_raised": [],
  "noise_reduction": 0.16
}
```

## Classifier output distribution and entropy on real verbs (Y.5)

```json
{
  "n_examples": 3052,
  "deterministic_correct": 811,
  "learned_correct": 2939,
  "deterministic_coverage": 0.2657,
  "learned_coverage": 0.963,
  "real_verb_output_distribution": {
    "collect": 3354,
    "enumerate": 81,
    "auth": 56,
    "execute": 9
  },
  "real_verb_class_entropy_bits": 0.3022,
  "real_verb_max_entropy_bits": 2.0,
  "real_verb_degenerate": true
}
```

## Scripted verdicts and anchors written

```json
[
  {
    "concern_id": "cn-0b509bdbcc4b",
    "concern_class": "unknown_cousin",
    "verdict": "CONFIRMED",
    "implant_class_ground_truth": "known_bad",
    "anchor_outcome": "ESCALATE",
    "anchor_tier": "ANALYST_CONFIRMED",
    "write_refused_reason": null
  },
  {
    "concern_id": "cn-2dc7a83f4633",
    "concern_class": "unknown_cousin",
    "verdict": "BENIGN",
    "implant_class_ground_truth": "unknown_cousin",
    "anchor_outcome": null,
    "anchor_tier": null,
    "write_refused_reason": "scripted_verdict_refused: BENIGN on ground_truth='unknown_cousin' contradicts sealed truth -- a scripted stand-in must not manufacture knowledge it cannot justify"
  },
  {
    "concern_id": "cn-32744cfa499c",
    "concern_class": "known_bad",
    "verdict": "UNSURE",
    "implant_class_ground_truth": "background",
    "anchor_outcome": "ANOMALOUS_UNCLASSIFIED",
    "anchor_tier": "SYSTEM_GENERATED",
    "write_refused_reason": null
  },
  {
    "concern_id": "cn-3654579bcb33",
    "concern_class": "unknown_cousin",
    "verdict": "CONFIRMED",
    "implant_class_ground_truth": "background",
    "anchor_outcome": null,
    "anchor_tier": null,
    "write_refused_reason": "scripted_verdict_refused: CONFIRMED on ground_truth='background' contradicts sealed truth -- a scripted stand-in must not manufacture knowledge it cannot justify"
  },
  {
    "concern_id": "cn-3b50af340157",
    "concern_class": "unknown_cousin",
    "verdict": "BENIGN",
    "implant_class_ground_truth": "background",
    "anchor_outcome": "BENIGN_CLOSE",
    "anchor_tier": "ANALYST_CONFIRMED",
    "write_refused_reason": null
  },
  {
    "concern_id": "cn-44c4d4f44dec",
    "concern_class": "known_bad",
    "verdict": "UNSURE",
    "implant_class_ground_truth": "background",
    "anchor_outcome": "ANOMALOUS_UNCLASSIFIED",
    "anchor_tier": "SYSTEM_GENERATED",
    "write_refused_reason": null
  },
  {
    "concern_id": "cn-48ba11f9bae5",
    "concern_class": "unknown_cousin",
    "verdict": "CONFIRMED",
    "implant_class_ground_truth": "background",
    "anchor_outcome": null,
    "anchor_tier": null,
    "write_refused_reason": "scripted_verdict_refused: CONFIRMED on ground_truth='background' contradicts sealed truth -- a scripted stand-in must not manufacture knowledge it cannot justify"
  },
  {
    "concern_id": "cn-4ffe78194e06",
    "concern_class": "unknown_cousin",
    "verdict": "BENIGN",
    "implant_class_ground_truth": "unknown_cousin",
    "anchor_outcome": null,
    "anchor_tier": null,
    "write_refused_reason": "scripted_verdict_refused: BENIGN on ground_truth='unknown_cousin' contradicts sealed truth -- a scripted stand-in must not manufacture knowledge it cannot justify"
  },
  {
    "concern_id": "cn-5367c468cff1",
    "concern_class": "unknown_cousin",
    "verdict": "UNSURE",
    "implant_class_ground_truth": "background",
    "anchor_outcome": "ANOMALOUS_UNCLASSIFIED",
    "anchor_tier": "SYSTEM_GENERATED",
    "write_refused_reason": null
  },
  {
    "concern_id": "cn-565a66d6517c",
    "concern_class": "unknown_cousin",
    "verdict": "CONFIRMED",
    "implant_class_ground_truth": "background",
    "anchor_outcome": null,
    "anchor_tier": null,
    "write_refused_reason": "scripted_verdict_refused: CONFIRMED on ground_truth='background' contradicts sealed truth -- a scripted stand-in must not manufacture knowledge it cannot justify"
  },
  {
    "concern_id": "cn-5fd3881370f3",
    "concern_class": "unknown_cousin",
    "verdict": "BENIGN",
    "implant_class_ground_truth": "background",
    "anchor_outcome": "BENIGN_CLOSE",
    "anchor_tier": "ANALYST_CONFIRMED",
    "write_refused_reason": null
  },
  {
    "concern_id": "cn-62a841e35e54",
    "concern_class": "unknown_cousin",
    "verdict": "UNSURE",
    "implant_class_ground_truth": "background",
    "anchor_outcome": "ANOMALOUS_UNCLASSIFIED",
    "anchor_tier": "SYSTEM_GENERATED",
    "write_refused_reason": null
  },
  {
    "concern_id": "cn-7cf1c4e0c7d9",
    "concern_class": "unknown_cousin",
    "verdict": "CONFIRMED",
    "implant_class_ground_truth": "background",
    "anchor_outcome": null,
    "anchor_tier": null,
    "write_refused_reason": "scripted_verdict_refused: CONFIRMED on ground_truth='background' contradicts sealed truth -- a scripted stand-in must not manufacture knowledge it cannot justify"
  },
  {
    "concern_id": "cn-8165f1a12a91",
    "concern_class": "unknown_cousin",
    "verdict": "BENIGN",
    "implant_class_ground_truth": "background",
    "anchor_outcome": "BENIGN_CLOSE",
    "anchor_tier": "ANALYST_CONFIRMED",
    "write_refused_reason": null
  },
  {
    "concern_id": "cn-855d9a3f612a",
    "concern_class": "unknown_cousin",
    "verdict": "UNSURE",
    "implant_class_ground_truth": "background",
    "anchor_outcome": "ANOMALOUS_UNCLASSIFIED",
    "anchor_tier": "SYSTEM_GENERATED",
    "write_refused_reason": null
  },
  {
    "concern_id": "cn-8945adc12f59",
    "concern_class": "unknown_cousin",
    "verdict": "CONFIRMED",
    "implant_class_ground_truth": "background",
    "anchor_outcome": null,
    "anchor_tier": null,
    "write_refused_reason": "scripted_verdict_refused: CONFIRMED on ground_truth='background' contradicts sealed truth -- a scripted stand-in must not manufacture knowledge it cannot justify"
  },
  {
    "concern_id": "cn-9a7e8d21d5e6",
    "concern_class": "unknown_cousin",
    "verdict": "BENIGN",
    "implant_class_ground_truth": "background",
    "anchor_outcome": "BENIGN_CLOSE",
    "anchor_tier": "ANALYST_CONFIRMED",
    "write_refused_reason": null
  },
  {
    "concern_id": "cn-a6687cee907a",
    "concern_class": "unknown_cousin",
    "verdict": "UNSURE",
    "implant_class_ground_truth": "background",
    "anchor_outcome": "ANOMALOUS_UNCLASSIFIED",
    "anchor_tier": "SYSTEM_GENERATED",
    "write_refused_reason": null
  },
  {
    "concern_id": "cn-b905c92c522d",
    "concern_class": "unknown_cousin",
    "verdict": "CONFIRMED",
    "implant_class_ground_truth": "background",
    "anchor_outcome": null,
    "anchor_tier": null,
    "write_refused_reason": "scripted_verdict_refused: CONFIRMED on ground_truth='background' contradicts sealed truth -- a scripted stand-in must not manufacture knowledge it cannot justify"
  },
  {
    "concern_id": "cn-c37054bfcbfd",
    "concern_class": "known_bad",
    "verdict": "BENIGN",
    "implant_class_ground_truth": "background",
    "anchor_outcome": "BENIGN_CLOSE",
    "anchor_tier": "ANALYST_CONFIRMED",
    "write_refused_reason": null
  },
  {
    "concern_id": "cn-c9e6a0e190ee",
    "concern_class": "unknown_cousin",
    "verdict": "UNSURE",
    "implant_class_ground_truth": "background",
    "anchor_outcome": "ANOMALOUS_UNCLASSIFIED",
    "anchor_tier": "SYSTEM_GENERATED",
    "write_refused_reason": null
  },
  {
    "concern_id": "cn-cb443c31b5b5",
    "concern_class": "unknown_cousin",
    "verdict": "CONFIRMED",
    "implant_class_ground_truth": "known_bad",
    "anchor_outcome": "ESCALATE",
    "anchor_tier": "ANALYST_CONFIRMED",
    "write_refused_reason": null
  },
  {
    "concern_id": "cn-e001414e02f7",
    "concern_class": "unknown_cousin",
    "verdict": "BENIGN",
    "implant_class_ground_truth": "background",
    "anchor_outcome": "BENIGN_CLOSE",
    "anchor_tier": "ANALYST_CONFIRMED",
    "write_refused_reason": null
  },
  {
    "concern_id": "cn-e34ec587b340",
    "concern_class": "unknown_cousin",
    "verdict": "UNSURE",
    "implant_class_ground_truth": "unknown_cousin",
    "anchor_outcome": "ANOMALOUS_UNCLASSIFIED",
    "anchor_tier": "SYSTEM_GENERATED",
    "write_refused_reason": null
  },
  {
    "concern_id": "cn-e41c4df1713c",
    "concern_class": "unknown_cousin",
    "verdict": "CONFIRMED",
    "implant_class_ground_truth": "background",
    "anchor_outcome": null,
    "anchor_tier": null,
    "write_refused_reason": "scripted_verdict_refused: CONFIRMED on ground_truth='background' contradicts sealed truth -- a scripted stand-in must not manufacture knowledge it cannot justify"
  }
]
```

## Concern briefs (sample)

- **unknown_cousin** (cn-4ffe78194e06): ent-7877106935 resembles a known technique but is not one we know (resembles anchor-47ca1e46570e): behaviour collect -> collect -> collect -> collect -> collect -> collect -> collect -> collect -> collect -> collect -> collect -> collect, seen across 1 source(s) ['lab-splunk'] within unknown span.
- **unknown_cousin** (cn-0b509bdbcc4b): ent-5389142738 resembles a known technique but is not one we know (resembles anchor-47ca1e46570e): behaviour collect -> collect -> collect -> collect -> collect -> collect -> collect -> collect -> collect, seen across 1 source(s) ['lab-splunk'] within unknown span.
- **unknown_cousin** (cn-e34ec587b340): ent-1094444755 resembles a known technique but is not one we know (resembles anchor-47ca1e46570e): behaviour collect -> collect -> collect -> collect -> collect -> collect -> collect -> collect -> collect, seen across 1 source(s) ['lab-splunk'] within unknown span.
- **unknown_cousin** (cn-cb443c31b5b5): ent-4099741506 resembles a known technique but is not one we know (resembles anchor-47ca1e46570e): behaviour collect -> collect -> collect -> collect -> collect -> collect -> collect -> collect -> collect, seen across 1 source(s) ['lab-splunk'] within unknown span.
- **unknown_cousin** (cn-2dc7a83f4633): ent-1051696542 resembles a known technique but is not one we know (resembles anchor-47ca1e46570e): behaviour collect -> collect -> collect -> collect -> collect -> collect -> collect -> collect -> collect, seen across 1 source(s) ['lab-splunk'] within unknown span.
- **unknown_cousin** (cn-b905c92c522d): ent-3966517958 resembles a known technique but is not one we know (resembles anchor-47ca1e46570e): behaviour collect -> collect -> collect -> collect -> collect -> collect -> collect -> collect -> collect -> collect -> collect -> collect -> collect -> collect -> collect -> collect -> collect -> collect, seen across 8 source(s) ['lab-splunk'] within unknown span.

## Scoreboard.update() contract (W.3) -- PASS

```json
{
  "hunt_id": "hunt-20260820T221736Z-fec3f687",
  "n_records": 50,
  "catch_count": 50,
  "catch_rate": 1.0,
  "trust_mean_rank": 1.0,
  "discovery_total": 1.2,
  "discovery_mean": 0.6,
  "false_flag_count": 0
}
```

## Conformance self-check (W.4)

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

## Correlation

```json
{
  "n_observations": 13763,
  "n_resolved_entities": 2843,
  "n_timelines": 25,
  "n_priority_entity_ids": 5
}
```

## Residual risks

- Scripted verdicts stand in for a human analyst -- they prove the mechanism, not analyst agreement.
- `MIN_OBSERVED_COVERAGE`/`MIN_DISTINCT_RATIO` (Y.2) are judgement and will cost recall on long, genuinely-mixed timelines where a real technique is a minority of an entity's activity -- the honest trade against a 100% background false-positive rate.
- Truth-aware selection (Y.3) makes this run a detection benchmark, not a production sample -- `selection_report_production_ordering` above is the number an operator would actually see with no priority set.
- Quarantine is supersede-not-delete: a future corpus export must filter quarantined anchors explicitly.
- The learned classifier still has no measured real-world accuracy; Y.5 reports its output distribution and entropy on this run's real captured verbs, not accuracy against labelled real telemetry.
- `implant_class_ground_truth` attribution (per_row) is best-effort via entity canonical-value match against the sealed injected identity.

## Full per-row data (both cycles)

```json
[
  {
    "cycle": 1,
    "assessment_id": "ca-e48a3b54cdda",
    "entity_id": "ent-7877106935",
    "implant_class_ground_truth": "unknown_cousin",
    "relationship": "SIMILAR",
    "defense_response": "INDETERMINATE",
    "composite": 0.23333333333333334,
    "concern_class": "unknown_cousin",
    "concern_raised": true,
    "concern_id": "cn-4ffe78194e06",
    "should_escalate": true,
    "n_sources": 1,
    "catch": true,
    "trust_class": null,
    "trust_rank": null,
    "discovery_value": 0.0,
    "known_benign": false,
    "false_flag": false,
    "false_flag_kind": null
  },
  {
    "cycle": 1,
    "assessment_id": "ca-4e1129dc4592",
    "entity_id": "ent-5389142738",
    "implant_class_ground_truth": "known_bad",
    "relationship": "SIMILAR",
    "defense_response": "INDETERMINATE",
    "composite": 0.23333333333333334,
    "concern_class": "unknown_cousin",
    "concern_raised": true,
    "concern_id": "cn-0b509bdbcc4b",
    "should_escalate": true,
    "n_sources": 1,
    "catch": true,
    "trust_class": null,
    "trust_rank": null,
    "discovery_value": 0.0,
    "known_benign": false,
    "false_flag": false,
    "false_flag_kind": null
  },
  {
    "cycle": 1,
    "assessment_id": "ca-b44f40deba98",
    "entity_id": "ent-1094444755",
    "implant_class_ground_truth": "unknown_cousin",
    "relationship": "SIMILAR",
    "defense_response": "INDETERMINATE",
    "composite": 0.23333333333333334,
    "concern_class": "unknown_cousin",
    "concern_raised": true,
    "concern_id": "cn-e34ec587b340",
    "should_escalate": true,
    "n_sources": 1,
    "catch": true,
    "trust_class": null,
    "trust_rank": null,
    "discovery_value": 0.0,
    "known_benign": false,
    "false_flag": false,
    "false_flag_kind": null
  },
  {
    "cycle": 1,
    "assessment_id": "ca-062f916f9032",
    "entity_id": "ent-4099741506",
    "implant_class_ground_truth": "known_bad",
    "relationship": "SIMILAR",
    "defense_response": "INDETERMINATE",
    "composite": 0.23333333333333334,
    "concern_class": "unknown_cousin",
    "concern_raised": true,
    "concern_id": "cn-cb443c31b5b5",
    "should_escalate": true,
    "n_sources": 1,
    "catch": true,
    "trust_class": null,
    "trust_rank": null,
    "discovery_value": 0.0,
    "known_benign": false,
    "false_flag": false,
    "false_flag_kind": null
  },
  {
    "cycle": 1,
    "assessment_id": "ca-d29d5e036902",
    "entity_id": "ent-1051696542",
    "implant_class_ground_truth": "unknown_cousin",
    "relationship": "SIMILAR",
    "defense_response": "INDETERMINATE",
    "composite": 0.23333333333333334,
    "concern_class": "unknown_cousin",
    "concern_raised": true,
    "concern_id": "cn-2dc7a83f4633",
    "should_escalate": true,
    "n_sources": 1,
    "catch": true,
    "trust_class": null,
    "trust_rank": null,
    "discovery_value": 0.0,
    "known_benign": false,
    "false_flag": false,
    "false_flag_kind": null
  },
  {
    "cycle": 1,
    "assessment_id": "ca-a6b9b3b89643",
    "entity_id": "ent-3966517958",
    "implant_class_ground_truth": "background",
    "relationship": "SIMILAR",
    "defense_response": "INDETERMINATE",
    "composite": 0.23333333333333334,
    "concern_class": "unknown_cousin",
    "concern_raised": true,
    "concern_id": "cn-b905c92c522d",
    "should_escalate": true,
    "n_sources": 8,
    "catch": true,
    "trust_class": null,
    "trust_rank": null,
    "discovery_value": 0.0,
    "known_benign": false,
    "false_flag": false,
    "false_flag_kind": null
  },
  {
    "cycle": 1,
    "assessment_id": "ca-d5160fb161b1",
    "entity_id": "ent-1870412855",
    "implant_class_ground_truth": "background",
    "relationship": "ANOMALOUS_UNCLASSIFIED",
    "defense_response": "INDETERMINATE",
    "composite": 0.22499999999999998,
    "concern_class": "unknown_cousin",
    "concern_raised": true,
    "concern_id": "cn-7cf1c4e0c7d9",
    "should_escalate": true,
    "n_sources": 7,
    "catch": true,
    "trust_class": "honest_anomaly",
    "trust_rank": 1,
    "discovery_value": 0.6,
    "known_benign": false,
    "false_flag": false,
    "false_flag_kind": null
  },
  {
    "cycle": 1,
    "assessment_id": "ca-d3d97c707e78",
    "entity_id": "ent-6917430556",
    "implant_class_ground_truth": "background",
    "relationship": "SIMILAR",
    "defense_response": "INDETERMINATE",
    "composite": 0.23333333333333334,
    "concern_class": "unknown_cousin",
    "concern_raised": true,
    "concern_id": "cn-48ba11f9bae5",
    "should_escalate": true,
    "n_sources": 7,
    "catch": true,
    "trust_class": null,
    "trust_rank": null,
    "discovery_value": 0.0,
    "known_benign": false,
    "false_flag": false,
    "false_flag_kind": null
  },
  {
    "cycle": 1,
    "assessment_id": "ca-70bac597ba14",
    "entity_id": "ent-8222603546",
    "implant_class_ground_truth": "background",
    "relationship": "SAME",
    "defense_response": "INDETERMINATE",
    "composite": 0.0,
    "concern_class": "known_bad",
    "concern_raised": true,
    "concern_id": "cn-32744cfa499c",
    "should_escalate": true,
    "n_sources": 6,
    "catch": true,
    "trust_class": null,
    "trust_rank": null,
    "discovery_value": 0.0,
    "known_benign": false,
    "false_flag": false,
    "false_flag_kind": null
  },
  {
    "cycle": 1,
    "assessment_id": "ca-c6c152fce294",
    "entity_id": "ent-1246908570",
    "implant_class_ground_truth": "background",
    "relationship": "SIMILAR",
    "defense_response": "INDETERMINATE",
    "composite": 0.08333333333333334,
    "concern_class": "unknown_cousin",
    "concern_raised": true,
    "concern_id": "cn-8945adc12f59",
    "should_escalate": true,
    "n_sources": 6,
    "catch": true,
    "trust_class": null,
    "trust_rank": null,
    "discovery_value": 0.0,
    "known_benign": false,
    "false_flag": false,
    "false_flag_kind": null
  },
  {
    "cycle": 1,
    "assessment_id": "ca-b069b0172f45",
    "entity_id": "ent-8259551446",
    "implant_class_ground_truth": "background",
    "relationship": "SIMILAR",
    "defense_response": "INDETERMINATE",
    "composite": 0.23333333333333334,
    "concern_class": "unknown_cousin",
    "concern_raised": true,
    "concern_id": "cn-3b50af340157",
    "should_escalate": true,
    "n_sources": 6,
    "catch": true,
    "trust_class": null,
    "trust_rank": null,
    "discovery_value": 0.0,
    "known_benign": false,
    "false_flag": false,
    "false_flag_kind": null
  },
  {
    "cycle": 1,
    "assessment_id": "ca-78e677fbd789",
    "entity_id": "ent-7855681328",
    "implant_class_ground_truth": "background",
    "relationship": "SIMILAR",
    "defense_response": "INDETERMINATE",
    "composite": 0.23333333333333334,
    "concern_class": "unknown_cousin",
    "concern_raised": true,
    "concern_id": "cn-3654579bcb33",
    "should_escalate": true,
    "n_sources": 6,
    "catch": true,
    "trust_class": null,
    "trust_rank": null,
    "discovery_value": 0.0,
    "known_benign": false,
    "false_flag": false,
    "false_flag_kind": null
  },
  {
    "cycle": 1,
    "assessment_id": "ca-b57d983feaaa",
    "entity_id": "ent-2597790770",
    "implant_class_ground_truth": "background",
    "relationship": "SIMILAR",
    "defense_response": "INDETERMINATE",
    "composite": 0.23333333333333334,
    "concern_class": "unknown_cousin",
    "concern_raised": true,
    "concern_id": "cn-855d9a3f612a",
    "should_escalate": true,
    "n_sources": 6,
    "catch": true,
    "trust_class": null,
    "trust_rank": null,
    "discovery_value": 0.0,
    "known_benign": false,
    "false_flag": false,
    "false_flag_kind": null
  },
  {
    "cycle": 1,
    "assessment_id": "ca-0f867b1bd9b0",
    "entity_id": "ent-6797309659",
    "implant_class_ground_truth": "background",
    "relationship": "SIMILAR",
    "defense_response": "INDETERMINATE",
    "composite": 0.23333333333333334,
    "concern_class": "unknown_cousin",
    "concern_raised": true,
    "concern_id": "cn-9a7e8d21d5e6",
    "should_escalate": true,
    "n_sources": 6,
    "catch": true,
    "trust_class": null,
    "trust_rank": null,
    "discovery_value": 0.0,
    "known_benign": false,
    "false_flag": false,
    "false_flag_kind": null
  },
  {
    "cycle": 1,
    "assessment_id": "ca-9f0e50055173",
    "entity_id": "ent-3581189792",
    "implant_class_ground_truth": "background",
    "relationship": "SIMILAR",
    "defense_response": "INDETERMINATE",
    "composite": 0.23333333333333334,
    "concern_class": "unknown_cousin",
    "concern_raised": true,
    "concern_id": "cn-565a66d6517c",
    "should_escalate": true,
    "n_sources": 6,
    "catch": true,
    "trust_class": null,
    "trust_rank": null,
    "discovery_value": 0.0,
    "known_benign": false,
    "false_flag": false,
    "false_flag_kind": null
  },
  {
    "cycle": 1,
    "assessment_id": "ca-0e1dd86cffbd",
    "entity_id": "ent-7517791242",
    "implant_class_ground_truth": "background",
    "relationship": "SIMILAR",
    "defense_response": "INDETERMINATE",
    "composite": 0.23333333333333334,
    "concern_class": "unknown_cousin",
    "concern_raised": true,
    "concern_id": "cn-62a841e35e54",
    "should_escalate": true,
    "n_sources": 6,
    "catch": true,
    "trust_class": null,
    "trust_rank": null,
    "discovery_value": 0.0,
    "known_benign": false,
    "false_flag": false,
    "false_flag_kind": null
  },
  {
    "cycle": 1,
    "assessment_id": "ca-bc2681d8d36c",
    "entity_id": "ent-8071441321",
    "implant_class_ground_truth": "background",
    "relationship": "SIMILAR",
    "defense_response": "INDETERMINATE",
    "composite": 0.23333333333333334,
    "concern_class": "unknown_cousin",
    "concern_raised": true,
    "concern_id": "cn-e41c4df1713c",
    "should_escalate": true,
    "n_sources": 6,
    "catch": true,
    "trust_class": null,
    "trust_rank": null,
    "discovery_value": 0.0,
    "known_benign": false,
    "false_flag": false,
    "false_flag_kind": null
  },
  {
    "cycle": 1,
    "assessment_id": "ca-291b12381580",
    "entity_id": "ent-8615652741",
    "implant_class_ground_truth": "background",
    "relationship": "SAME",
    "defense_response": "INDETERMINATE",
    "composite": 0.0,
    "concern_class": "known_bad",
    "concern_raised": true,
    "concern_id": "cn-44c4d4f44dec",
    "should_escalate": true,
    "n_sources": 6,
    "catch": true,
    "trust_class": null,
    "trust_rank": null,
    "discovery_value": 0.0,
    "known_benign": false,
    "false_flag": false,
    "false_flag_kind": null
  },
  {
    "cycle": 1,
    "assessment_id": "ca-71a735988b89",
    "entity_id": "ent-2645458010",
    "implant_class_ground_truth": "background",
    "relationship": "SIMILAR",
    "defense_response": "INDETERMINATE",
    "composite": 0.23333333333333334,
    "concern_class": "unknown_cousin",
    "concern_raised": true,
    "concern_id": "cn-a6687cee907a",
    "should_escalate": true,
    "n_sources": 6,
    "catch": true,
    "trust_class": null,
    "trust_rank": null,
    "discovery_value": 0.0,
    "known_benign": false,
    "false_flag": false,
    "false_flag_kind": null
  },
  {
    "cycle": 1,
    "assessment_id": "ca-827076bc9afc",
    "entity_id": "ent-8010106372",
    "implant_class_ground_truth": "background",
    "relationship": "SIMILAR",
    "defense_response": "INDETERMINATE",
    "composite": 0.23333333333333334,
    "concern_class": "unknown_cousin",
    "concern_raised": true,
    "concern_id": "cn-5fd3881370f3",
    "should_escalate": true,
    "n_sources": 6,
    "catch": true,
    "trust_class": null,
    "trust_rank": null,
    "discovery_value": 0.0,
    "known_benign": false,
    "false_flag": false,
    "false_flag_kind": null
  },
  {
    "cycle": 1,
    "assessment_id": "ca-399f36ac6dd3",
    "entity_id": "ent-2992551527",
    "implant_class_ground_truth": "background",
    "relationship": "SIMILAR",
    "defense_response": "INDETERMINATE",
    "composite": 0.23333333333333334,
    "concern_class": "unknown_cousin",
    "concern_raised": true,
    "concern_id": "cn-8165f1a12a91",
    "should_escalate": true,
    "n_sources": 6,
    "catch": true,
    "trust_class": null,
    "trust_rank": null,
    "discovery_value": 0.0,
    "known_benign": false,
    "false_flag": false,
    "false_flag_kind": null
  },
  {
    "cycle": 1,
    "assessment_id": "ca-418a5fad8b67",
    "entity_id": "ent-8512599023",
    "implant_class_ground_truth": "background",
    "relationship": "SAME",
    "defense_response": "INDETERMINATE",
    "composite": 0.0,
    "concern_class": "known_bad",
    "concern_raised": true,
    "concern_id": "cn-c37054bfcbfd",
    "should_escalate": true,
    "n_sources": 6,
    "catch": true,
    "trust_class": null,
    "trust_rank": null,
    "discovery_value": 0.0,
    "known_benign": false,
    "false_flag": false,
    "false_flag_kind": null
  },
  {
    "cycle": 1,
    "assessment_id": "ca-65dfd5f94c62",
    "entity_id": "ent-0983363439",
    "implant_class_ground_truth": "background",
    "relationship": "SIMILAR",
    "defense_response": "INDETERMINATE",
    "composite": 0.1625,
    "concern_class": "unknown_cousin",
    "concern_raised": true,
    "concern_id": "cn-5367c468cff1",
    "should_escalate": true,
    "n_sources": 6,
    "catch": true,
    "trust_class": null,
    "trust_rank": null,
    "discovery_value": 0.0,
    "known_benign": false,
    "false_flag": false,
    "false_flag_kind": null
  },
  {
    "cycle": 1,
    "assessment_id": "ca-1ddc6b29bd1d",
    "entity_id": "ent-0650734559",
    "implant_class_ground_truth": "background",
    "relationship": "SIMILAR",
    "defense_response": "INDETERMINATE",
    "composite": 0.23333333333333334,
    "concern_class": "unknown_cousin",
    "concern_raised": true,
    "concern_id": "cn-c9e6a0e190ee",
    "should_escalate": true,
    "n_sources": 6,
    "catch": true,
    "trust_class": null,
    "trust_rank": null,
    "discovery_value": 0.0,
    "known_benign": false,
    "false_flag": false,
    "false_flag_kind": null
  },
  {
    "cycle": 1,
    "assessment_id": "ca-4795bd219a6f",
    "entity_id": "ent-7705980220",
    "implant_class_ground_truth": "background",
    "relationship": "SIMILAR",
    "defense_response": "INDETERMINATE",
    "composite": 0.23333333333333334,
    "concern_class": "unknown_cousin",
    "concern_raised": true,
    "concern_id": "cn-e001414e02f7",
    "should_escalate": true,
    "n_sources": 6,
    "catch": true,
    "trust_class": null,
    "trust_rank": null,
    "discovery_value": 0.0,
    "known_benign": false,
    "false_flag": false,
    "false_flag_kind": null
  },
  {
    "cycle": 2,
    "assessment_id": "ca-fa4e7826bc70",
    "entity_id": "ent-7877106935",
    "implant_class_ground_truth": "unknown_cousin",
    "relationship": "SIMILAR",
    "defense_response": "INDETERMINATE",
    "composite": 0.1,
    "concern_class": "unknown_cousin",
    "concern_raised": true,
    "concern_id": "cn-fd0fa80011a6",
    "should_escalate": true,
    "n_sources": 1,
    "catch": true,
    "trust_class": null,
    "trust_rank": null,
    "discovery_value": 0.0,
    "known_benign": false,
    "false_flag": false,
    "false_flag_kind": null
  },
  {
    "cycle": 2,
    "assessment_id": "ca-c828a2d9b80c",
    "entity_id": "ent-5389142738",
    "implant_class_ground_truth": "known_bad",
    "relationship": "SAME",
    "defense_response": "INDETERMINATE",
    "composite": 0.0,
    "concern_class": "known_bad",
    "concern_raised": true,
    "concern_id": "cn-d119feba539d",
    "should_escalate": true,
    "n_sources": 1,
    "catch": true,
    "trust_class": null,
    "trust_rank": null,
    "discovery_value": 0.0,
    "known_benign": false,
    "false_flag": false,
    "false_flag_kind": null
  },
  {
    "cycle": 2,
    "assessment_id": "ca-fb1d6ca0a611",
    "entity_id": "ent-1094444755",
    "implant_class_ground_truth": "unknown_cousin",
    "relationship": "SIMILAR",
    "defense_response": "INDETERMINATE",
    "composite": 0.1,
    "concern_class": "unknown_cousin",
    "concern_raised": true,
    "concern_id": "cn-4ea6f6b70303",
    "should_escalate": true,
    "n_sources": 1,
    "catch": true,
    "trust_class": null,
    "trust_rank": null,
    "discovery_value": 0.0,
    "known_benign": false,
    "false_flag": false,
    "false_flag_kind": null
  },
  {
    "cycle": 2,
    "assessment_id": "ca-762f6df6ef02",
    "entity_id": "ent-4099741506",
    "implant_class_ground_truth": "known_bad",
    "relationship": "SIMILAR",
    "defense_response": "INDETERMINATE",
    "composite": 0.1,
    "concern_class": "unknown_cousin",
    "concern_raised": true,
    "concern_id": "cn-71f171037c8f",
    "should_escalate": true,
    "n_sources": 1,
    "catch": true,
    "trust_class": null,
    "trust_rank": null,
    "discovery_value": 0.0,
    "known_benign": false,
    "false_flag": false,
    "false_flag_kind": null
  },
  {
    "cycle": 2,
    "assessment_id": "ca-0427505fa033",
    "entity_id": "ent-1051696542",
    "implant_class_ground_truth": "unknown_cousin",
    "relationship": "SIMILAR",
    "defense_response": "INDETERMINATE",
    "composite": 0.1,
    "concern_class": "unknown_cousin",
    "concern_raised": true,
    "concern_id": "cn-dca689fb6526",
    "should_escalate": true,
    "n_sources": 1,
    "catch": true,
    "trust_class": null,
    "trust_rank": null,
    "discovery_value": 0.0,
    "known_benign": false,
    "false_flag": false,
    "false_flag_kind": null
  },
  {
    "cycle": 2,
    "assessment_id": "ca-92bbab5640d5",
    "entity_id": "ent-3966517958",
    "implant_class_ground_truth": "background",
    "relationship": "SIMILAR",
    "defense_response": "INDETERMINATE",
    "composite": 0.1,
    "concern_class": "unknown_cousin",
    "concern_raised": true,
    "concern_id": "cn-8c89084ebbf3",
    "should_escalate": true,
    "n_sources": 8,
    "catch": true,
    "trust_class": null,
    "trust_rank": null,
    "discovery_value": 0.0,
    "known_benign": false,
    "false_flag": false,
    "false_flag_kind": null
  },
  {
    "cycle": 2,
    "assessment_id": "ca-bf8ae8825e50",
    "entity_id": "ent-1870412855",
    "implant_class_ground_truth": "background",
    "relationship": "SIMILAR",
    "defense_response": "INDETERMINATE",
    "composite": 0.1,
    "concern_class": "unknown_cousin",
    "concern_raised": true,
    "concern_id": "cn-a885df88afa9",
    "should_escalate": true,
    "n_sources": 7,
    "catch": true,
    "trust_class": null,
    "trust_rank": null,
    "discovery_value": 0.0,
    "known_benign": false,
    "false_flag": false,
    "false_flag_kind": null
  },
  {
    "cycle": 2,
    "assessment_id": "ca-af4725449673",
    "entity_id": "ent-6917430556",
    "implant_class_ground_truth": "background",
    "relationship": "SIMILAR",
    "defense_response": "INDETERMINATE",
    "composite": 0.1,
    "concern_class": "unknown_cousin",
    "concern_raised": true,
    "concern_id": "cn-5c6ad9e409c9",
    "should_escalate": true,
    "n_sources": 7,
    "catch": true,
    "trust_class": null,
    "trust_rank": null,
    "discovery_value": 0.0,
    "known_benign": false,
    "false_flag": false,
    "false_flag_kind": null
  },
  {
    "cycle": 2,
    "assessment_id": "ca-e18fb39141cc",
    "entity_id": "ent-8222603546",
    "implant_class_ground_truth": "background",
    "relationship": "SAME",
    "defense_response": "INDETERMINATE",
    "composite": 0.0,
    "concern_class": "known_bad",
    "concern_raised": true,
    "concern_id": "cn-0dae4634a198",
    "should_escalate": true,
    "n_sources": 6,
    "catch": true,
    "trust_class": null,
    "trust_rank": null,
    "discovery_value": 0.0,
    "known_benign": false,
    "false_flag": false,
    "false_flag_kind": null
  },
  {
    "cycle": 2,
    "assessment_id": "ca-c8e342d89399",
    "entity_id": "ent-1246908570",
    "implant_class_ground_truth": "background",
    "relationship": "ANOMALOUS_UNCLASSIFIED",
    "defense_response": "INDETERMINATE",
    "composite": 0.0,
    "concern_class": "unknown_cousin",
    "concern_raised": true,
    "concern_id": "cn-0d5fe8939de4",
    "should_escalate": true,
    "n_sources": 6,
    "catch": true,
    "trust_class": "honest_anomaly",
    "trust_rank": 1,
    "discovery_value": 0.6,
    "known_benign": false,
    "false_flag": false,
    "false_flag_kind": null
  },
  {
    "cycle": 2,
    "assessment_id": "ca-7ae1108e5add",
    "entity_id": "ent-8259551446",
    "implant_class_ground_truth": "background",
    "relationship": "SAME",
    "defense_response": "INDETERMINATE",
    "composite": 0.0,
    "concern_class": "known_bad",
    "concern_raised": false,
    "concern_id": null,
    "should_escalate": false,
    "n_sources": 6,
    "catch": true,
    "trust_class": null,
    "trust_rank": null,
    "discovery_value": 0.0,
    "known_benign": false,
    "false_flag": false,
    "false_flag_kind": null
  },
  {
    "cycle": 2,
    "assessment_id": "ca-91141e0f9efc",
    "entity_id": "ent-7855681328",
    "implant_class_ground_truth": "background",
    "relationship": "SIMILAR",
    "defense_response": "INDETERMINATE",
    "composite": 0.1,
    "concern_class": "unknown_cousin",
    "concern_raised": true,
    "concern_id": "cn-57d518c2c83f",
    "should_escalate": true,
    "n_sources": 6,
    "catch": true,
    "trust_class": null,
    "trust_rank": null,
    "discovery_value": 0.0,
    "known_benign": false,
    "false_flag": false,
    "false_flag_kind": null
  },
  {
    "cycle": 2,
    "assessment_id": "ca-c84bfe27996e",
    "entity_id": "ent-2597790770",
    "implant_class_ground_truth": "background",
    "relationship": "SAME",
    "defense_response": "INDETERMINATE",
    "composite": 0.0,
    "concern_class": "known_bad",
    "concern_raised": true,
    "concern_id": "cn-ca2cd7f15c18",
    "should_escalate": true,
    "n_sources": 6,
    "catch": true,
    "trust_class": null,
    "trust_rank": null,
    "discovery_value": 0.0,
    "known_benign": false,
    "false_flag": false,
    "false_flag_kind": null
  },
  {
    "cycle": 2,
    "assessment_id": "ca-e571dc5d824a",
    "entity_id": "ent-6797309659",
    "implant_class_ground_truth": "background",
    "relationship": "SAME",
    "defense_response": "INDETERMINATE",
    "composite": 0.0,
    "concern_class": "known_bad",
    "concern_raised": false,
    "concern_id": null,
    "should_escalate": false,
    "n_sources": 6,
    "catch": true,
    "trust_class": null,
    "trust_rank": null,
    "discovery_value": 0.0,
    "known_benign": false,
    "false_flag": false,
    "false_flag_kind": null
  },
  {
    "cycle": 2,
    "assessment_id": "ca-b637d7ccc003",
    "entity_id": "ent-3581189792",
    "implant_class_ground_truth": "background",
    "relationship": "SIMILAR",
    "defense_response": "INDETERMINATE",
    "composite": 0.1,
    "concern_class": "unknown_cousin",
    "concern_raised": true,
    "concern_id": "cn-a1aa6d4eedc9",
    "should_escalate": true,
    "n_sources": 6,
    "catch": true,
    "trust_class": null,
    "trust_rank": null,
    "discovery_value": 0.0,
    "known_benign": false,
    "false_flag": false,
    "false_flag_kind": null
  },
  {
    "cycle": 2,
    "assessment_id": "ca-76dce76b62e8",
    "entity_id": "ent-7517791242",
    "implant_class_ground_truth": "background",
    "relationship": "SAME",
    "defense_response": "INDETERMINATE",
    "composite": 0.0,
    "concern_class": "known_bad",
    "concern_raised": true,
    "concern_id": "cn-5d702df398ea",
    "should_escalate": true,
    "n_sources": 6,
    "catch": true,
    "trust_class": null,
    "trust_rank": null,
    "discovery_value": 0.0,
    "known_benign": false,
    "false_flag": false,
    "false_flag_kind": null
  },
  {
    "cycle": 2,
    "assessment_id": "ca-2fa815d989d3",
    "entity_id": "ent-8071441321",
    "implant_class_ground_truth": "background",
    "relationship": "SIMILAR",
    "defense_response": "INDETERMINATE",
    "composite": 0.1,
    "concern_class": "unknown_cousin",
    "concern_raised": true,
    "concern_id": "cn-bb17ecab0b08",
    "should_escalate": true,
    "n_sources": 6,
    "catch": true,
    "trust_class": null,
    "trust_rank": null,
    "discovery_value": 0.0,
    "known_benign": false,
    "false_flag": false,
    "false_flag_kind": null
  },
  {
    "cycle": 2,
    "assessment_id": "ca-5ff006d6f62c",
    "entity_id": "ent-8615652741",
    "implant_class_ground_truth": "background",
    "relationship": "SAME",
    "defense_response": "INDETERMINATE",
    "composite": 0.0,
    "concern_class": "known_bad",
    "concern_raised": true,
    "concern_id": "cn-8b359fa0f5e7",
    "should_escalate": true,
    "n_sources": 6,
    "catch": true,
    "trust_class": null,
    "trust_rank": null,
    "discovery_value": 0.0,
    "known_benign": false,
    "false_flag": false,
    "false_flag_kind": null
  },
  {
    "cycle": 2,
    "assessment_id": "ca-54ddb5a84f27",
    "entity_id": "ent-2645458010",
    "implant_class_ground_truth": "background",
    "relationship": "SAME",
    "defense_response": "INDETERMINATE",
    "composite": 0.0,
    "concern_class": "known_bad",
    "concern_raised": true,
    "concern_id": "cn-f453ea7f4573",
    "should_escalate": true,
    "n_sources": 6,
    "catch": true,
    "trust_class": null,
    "trust_rank": null,
    "discovery_value": 0.0,
    "known_benign": false,
    "false_flag": false,
    "false_flag_kind": null
  },
  {
    "cycle": 2,
    "assessment_id": "ca-c773eebf4cc9",
    "entity_id": "ent-8010106372",
    "implant_class_ground_truth": "background",
    "relationship": "SAME",
    "defense_response": "INDETERMINATE",
    "composite": 0.0,
    "concern_class": "known_bad",
    "concern_raised": false,
    "concern_id": null,
    "should_escalate": false,
    "n_sources": 6,
    "catch": true,
    "trust_class": null,
    "trust_rank": null,
    "discovery_value": 0.0,
    "known_benign": false,
    "false_flag": false,
    "false_flag_kind": null
  },
  {
    "cycle": 2,
    "assessment_id": "ca-d757acbe6a53",
    "entity_id": "ent-2992551527",
    "implant_class_ground_truth": "background",
    "relationship": "SAME",
    "defense_response": "INDETERMINATE",
    "composite": 0.0,
    "concern_class": "known_bad",
    "concern_raised": false,
    "concern_id": null,
    "should_escalate": false,
    "n_sources": 6,
    "catch": true,
    "trust_class": null,
    "trust_rank": null,
    "discovery_value": 0.0,
    "known_benign": false,
    "false_flag": false,
    "false_flag_kind": null
  },
  {
    "cycle": 2,
    "assessment_id": "ca-a6f5111c38e1",
    "entity_id": "ent-8512599023",
    "implant_class_ground_truth": "background",
    "relationship": "SAME",
    "defense_response": "INDETERMINATE",
    "composite": 0.0,
    "concern_class": "known_bad",
    "concern_raised": true,
    "concern_id": "cn-241f21a09dd0",
    "should_escalate": true,
    "n_sources": 6,
    "catch": true,
    "trust_class": null,
    "trust_rank": null,
    "discovery_value": 0.0,
    "known_benign": false,
    "false_flag": false,
    "false_flag_kind": null
  },
  {
    "cycle": 2,
    "assessment_id": "ca-cbd8eccfea1c",
    "entity_id": "ent-0983363439",
    "implant_class_ground_truth": "background",
    "relationship": "SAME",
    "defense_response": "INDETERMINATE",
    "composite": 0.0,
    "concern_class": "known_bad",
    "concern_raised": true,
    "concern_id": "cn-cabff0b40633",
    "should_escalate": true,
    "n_sources": 6,
    "catch": true,
    "trust_class": null,
    "trust_rank": null,
    "discovery_value": 0.0,
    "known_benign": false,
    "false_flag": false,
    "false_flag_kind": null
  },
  {
    "cycle": 2,
    "assessment_id": "ca-f633e8ca65fb",
    "entity_id": "ent-0650734559",
    "implant_class_ground_truth": "background",
    "relationship": "SAME",
    "defense_response": "INDETERMINATE",
    "composite": 0.0,
    "concern_class": "known_bad",
    "concern_raised": true,
    "concern_id": "cn-d8156392f10e",
    "should_escalate": true,
    "n_sources": 6,
    "catch": true,
    "trust_class": null,
    "trust_rank": null,
    "discovery_value": 0.0,
    "known_benign": false,
    "false_flag": false,
    "false_flag_kind": null
  },
  {
    "cycle": 2,
    "assessment_id": "ca-aeca92f457ba",
    "entity_id": "ent-7705980220",
    "implant_class_ground_truth": "background",
    "relationship": "SIMILAR",
    "defense_response": "INDETERMINATE",
    "composite": 0.1,
    "concern_class": "unknown_cousin",
    "concern_raised": true,
    "concern_id": "cn-7b3694f573e7",
    "should_escalate": true,
    "n_sources": 6,
    "catch": true,
    "trust_class": null,
    "trust_rank": null,
    "discovery_value": 0.0,
    "known_benign": false,
    "false_flag": false,
    "false_flag_kind": null
  }
]
```
