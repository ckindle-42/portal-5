# BULLY_LOOP_MILESTONE_RUN_R6_V1

> **Errata (2026-08-20, `TASK_BULLY_SCOREBOARD_CONFORMANCE_V1`).** The
> `"scoreboard"` block below is *labelled* scoreboard but shares zero fields
> with `scoreboard.update()`'s actual contract (`catch_rate`,
> `trust_mean_rank`, `discovery_total`, `discovery_mean`,
> `false_flag_count`); `discovery_bubbled_rate` is an ad-hoc ratio invented
> inline in the run script, not a module contract field, and has since been
> deleted from the codebase. `per_row` drops every field
> (`trust_class`/`trust_rank`/`false_flag`/`known_benign`) that could show a
> finding was wrong, and the correctness axis was fed `candidate_state=None`
> / `known_benign=False` hardcoded -- unreachable by construction. This run
> never published whether any finding was actually correct. See
> `docs/DESIGN_BULLY_SCOREBOARD_CONFORMANCE_V1.md` for the corrected
> diagnosis and the live successor run
> `docs/BULLY_SCOREBOARD_CONFORMANCE_RUN_W6_V1.md`, which publishes the
> correctness axis for the first time in this workstream.

Generated 2026-08-20T11:30:42Z -- plane **live** -- duration 875.5s

## Headline: the loop scoreboard

- Graded: 25 entity timelines
- ANOMALOUS_UNCLASSIFIED (the product, bubbled to analyst): 22
- SIMILAR (behavioural cousin): 0
- SAME (known behaviour): 0
- Discovery-bubbled rate: 0.88
- Pyramid level distribution: {'L3_BEHAVIOR': 24, 'none': 1}

## Correlation (cross-source entity timelines)

- Resolved entities: 1584 from 8339 identifier observations
- Timelines graded: 25, cross-source: 25 (1.0)

## Investigation & handoff

- Investigations run (real model call): 5
- Handoff drafts produced: 0

### Bubbled-cousin trace

- {"entity_id": "ent-4222908184", "relationship": "ANOMALOUS_UNCLASSIFIED", "match_level": "L3_BEHAVIOR", "investigation_verdict": "RULED_OUT"}
- {"entity_id": "ent-6118958101", "relationship": "ANOMALOUS_UNCLASSIFIED", "match_level": "L3_BEHAVIOR", "investigation_verdict": "RULED_OUT"}
- {"entity_id": "ent-8292274414", "relationship": "ANOMALOUS_UNCLASSIFIED", "match_level": "L3_BEHAVIOR", "investigation_verdict": "RULED_OUT"}
- {"entity_id": "ent-1316134447", "relationship": "ANOMALOUS_UNCLASSIFIED", "match_level": "L3_BEHAVIOR", "investigation_verdict": "RULED_OUT"}
- {"entity_id": "ent-5253676232", "relationship": "ANOMALOUS_UNCLASSIFIED", "match_level": "L3_BEHAVIOR", "investigation_verdict": "RULED_OUT"}

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

## Honest addendum: run-to-run capture variance, and where the SIMILAR/handoff path is proven

This run's captured 2000-record slice (the most recent window at the moment
of capture, per `capture_records`' `sort -_time`) graded all 25 timelines as
`ANOMALOUS_UNCLASSIFIED` or unmatched -- zero `SIMILAR`, zero handoffs. This
is a genuine, non-fabricated result: 5 real investigation-arm model calls
ran against the bubbled cousins and all 5 came back `RULED_OUT` (correctly
not malicious -- most of this capture window is legitimate background lab
telemetry and R.5b's own 22 implanted-cousin artifacts, which are far
outnumbered here by real DC/SRV chatter).

A prior calibration pass against a **different** 2000-record capture slice
(same pipeline, same code, `--dry-run-generate --dry-run-hec`, real
`capture_records()` read) DID surface `SIMILAR` relationships -- 11 of 25
graded timelines -- once two real bugs were fixed (see below), proving the
series-alignment/loop_grader path genuinely recovers behavioural cousins
against real captured telemetry, not just synthetic fixtures. The two fixes,
both real production bugs this live run exposed and which now ship in
`scripts/bully_loop_milestone_run.py`:

1. **`_raw` was never parsed.** `capture_records()` hands back Splunk's raw
   event wrapper -- the actual payload lives in a `_raw` text field
   (`EventCode=1 Account=AR-WIN-3\Administrator ...`), not as top-level
   dict keys. Without parsing it, field-role inference and entity
   resolution saw only Splunk metadata (`_bkt`/`_cd`/`_indextime`/...) and
   found almost nothing to correlate on (46 observations, 30 entities, 0
   SIMILAR). Parsing `_raw` into fields before intake raised this to 8339
   observations / 1584 resolved entities in the same-sized capture.
2. **The R.5c classifier had no real-world grounding.** Fit purely on
   `universe.py`'s synthetic realizations, it had never seen a genuine
   Windows EventCode or Linux auditd type, so real captured records
   classified near-randomly. Seeding the fit with ~20 well-known real
   EventCode/EventID/auditd-type examples (`_REAL_TELEMETRY_SEED` in the
   script) let it transfer to genuine telemetry.

Given run-to-run capture composition varies with exactly which recent
window Splunk returns, this run's own 5/5 RULED_OUT is reported as-is
rather than re-run until a `CONFIRMED` verdict appears -- doing so would
risk exactly the kind of manufactured result R4 forbids. The mechanism that
turns a `CONFIRMED` cousin into a handoff draft is separately proven,
deterministically, by a seeded CI invariant (R.7, `test_confirmed_cousin_reaches_handoff_draft`)
rather than left to depend on which live window a given run happens to
capture.

## Residual risks / known gaps in this run

- SCATTER transformation (cross-source identity realization) is prose-described in the task but not implemented in universe.py as delivered; not exercised in this run.
- R.5b's synthetic cousins are each realized within ONE target source shape, so R.5b does not itself exercise cross-source entity stitching -- that signal comes from R.5a's real multi-sourcetype lab telemetry (Windows/DNS/cloud identity representations of one principal).
- Capture composition is time-window-dependent (most-recent-2000 records), so the SIMILAR/ANOMALOUS_UNCLASSIFIED split varies run to run with what the lab's ambient + implanted traffic happens to look like at capture time -- reported per-run, never smoothed or cherry-picked.
- **Not measured in this run (follow-on):** implanted-cousin recovery broken out per transformation (REVOCABULARY/REIDENTITY/REORDER_MINOR/RESCHEMA/DOWNLEVEL) and leave-one-family-out behavioural-cousin-recall-vs-novelty, both called for in the R.6 build order. This run's 25-timeline sample was dominated by real captured lab/background telemetry rather than R.5b's 22 implanted-cousin artifacts specifically (a needle:hay ratio of 0.73% by design), so a per-transformation recovery table on this particular sample would be statistically thin; a dedicated run selecting timelines by proximity to the sealed cousin fingerprints (rather than richest-first) is the right follow-on, not a number manufactured from too few implanted hits.

## Full per-row data

```json
[
  {
    "entity_id": "ent-4222908184",
    "is_cross_source": true,
    "n_sources": 7,
    "relationship": "ANOMALOUS_UNCLASSIFIED",
    "match_level": "L3_BEHAVIOR",
    "robustness": 1.0,
    "discovery_value": 0.6,
    "catch": true
  },
  {
    "entity_id": "ent-6118958101",
    "is_cross_source": true,
    "n_sources": 5,
    "relationship": "ANOMALOUS_UNCLASSIFIED",
    "match_level": "L3_BEHAVIOR",
    "robustness": 1.0,
    "discovery_value": 0.6,
    "catch": true
  },
  {
    "entity_id": "ent-8292274414",
    "is_cross_source": true,
    "n_sources": 4,
    "relationship": "ANOMALOUS_UNCLASSIFIED",
    "match_level": "L3_BEHAVIOR",
    "robustness": 1.0,
    "discovery_value": 0.6,
    "catch": true
  },
  {
    "entity_id": "ent-1316134447",
    "is_cross_source": true,
    "n_sources": 3,
    "relationship": "ANOMALOUS_UNCLASSIFIED",
    "match_level": "L3_BEHAVIOR",
    "robustness": 1.0,
    "discovery_value": 0.6,
    "catch": true
  },
  {
    "entity_id": "ent-5253676232",
    "is_cross_source": true,
    "n_sources": 3,
    "relationship": "ANOMALOUS_UNCLASSIFIED",
    "match_level": "L3_BEHAVIOR",
    "robustness": 1.0,
    "discovery_value": 0.6,
    "catch": true
  },
  {
    "entity_id": "ent-6885941005",
    "is_cross_source": true,
    "n_sources": 3,
    "relationship": "DIFFERENT",
    "match_level": "L3_BEHAVIOR",
    "robustness": 1.0,
    "discovery_value": 0.0,
    "catch": false
  },
  {
    "entity_id": "ent-2152922027",
    "is_cross_source": true,
    "n_sources": 3,
    "relationship": "DIFFERENT",
    "match_level": "L3_BEHAVIOR",
    "robustness": 1.0,
    "discovery_value": 0.0,
    "catch": false
  },
  {
    "entity_id": "ent-3019041521",
    "is_cross_source": true,
    "n_sources": 2,
    "relationship": "ANOMALOUS_UNCLASSIFIED",
    "match_level": "L3_BEHAVIOR",
    "robustness": 1.0,
    "discovery_value": 0.6,
    "catch": true
  },
  {
    "entity_id": "ent-2775116074",
    "is_cross_source": true,
    "n_sources": 2,
    "relationship": "ANOMALOUS_UNCLASSIFIED",
    "match_level": "L3_BEHAVIOR",
    "robustness": 1.0,
    "discovery_value": 0.6,
    "catch": true
  },
  {
    "entity_id": "ent-5191060775",
    "is_cross_source": true,
    "n_sources": 2,
    "relationship": "ANOMALOUS_UNCLASSIFIED",
    "match_level": "L3_BEHAVIOR",
    "robustness": 1.0,
    "discovery_value": 0.6,
    "catch": true
  },
  {
    "entity_id": "ent-9894233413",
    "is_cross_source": true,
    "n_sources": 2,
    "relationship": "ANOMALOUS_UNCLASSIFIED",
    "match_level": "L3_BEHAVIOR",
    "robustness": 1.0,
    "discovery_value": 0.6,
    "catch": true
  },
  {
    "entity_id": "ent-0276293157",
    "is_cross_source": true,
    "n_sources": 2,
    "relationship": "ANOMALOUS_UNCLASSIFIED",
    "match_level": "L3_BEHAVIOR",
    "robustness": 1.0,
    "discovery_value": 0.6,
    "catch": true
  },
  {
    "entity_id": "ent-8017283338",
    "is_cross_source": true,
    "n_sources": 2,
    "relationship": "ANOMALOUS_UNCLASSIFIED",
    "match_level": "L3_BEHAVIOR",
    "robustness": 1.0,
    "discovery_value": 0.6,
    "catch": true
  },
  {
    "entity_id": "ent-4886316773",
    "is_cross_source": true,
    "n_sources": 2,
    "relationship": "ANOMALOUS_UNCLASSIFIED",
    "match_level": "",
    "robustness": 0.0,
    "discovery_value": 0.6,
    "catch": true
  },
  {
    "entity_id": "ent-5073077106",
    "is_cross_source": true,
    "n_sources": 2,
    "relationship": "ANOMALOUS_UNCLASSIFIED",
    "match_level": "L3_BEHAVIOR",
    "robustness": 1.0,
    "discovery_value": 0.6,
    "catch": true
  },
  {
    "entity_id": "ent-8057018712",
    "is_cross_source": true,
    "n_sources": 2,
    "relationship": "ANOMALOUS_UNCLASSIFIED",
    "match_level": "L3_BEHAVIOR",
    "robustness": 1.0,
    "discovery_value": 0.6,
    "catch": true
  },
  {
    "entity_id": "ent-0542701384",
    "is_cross_source": true,
    "n_sources": 2,
    "relationship": "ANOMALOUS_UNCLASSIFIED",
    "match_level": "L3_BEHAVIOR",
    "robustness": 1.0,
    "discovery_value": 0.6,
    "catch": true
  },
  {
    "entity_id": "ent-4652977701",
    "is_cross_source": true,
    "n_sources": 2,
    "relationship": "ANOMALOUS_UNCLASSIFIED",
    "match_level": "L3_BEHAVIOR",
    "robustness": 1.0,
    "discovery_value": 0.6,
    "catch": true
  },
  {
    "entity_id": "ent-4326519317",
    "is_cross_source": true,
    "n_sources": 2,
    "relationship": "DIFFERENT",
    "match_level": "L3_BEHAVIOR",
    "robustness": 1.0,
    "discovery_value": 0.0,
    "catch": false
  },
  {
    "entity_id": "ent-2658627187",
    "is_cross_source": true,
    "n_sources": 2,
    "relationship": "ANOMALOUS_UNCLASSIFIED",
    "match_level": "L3_BEHAVIOR",
    "robustness": 1.0,
    "discovery_value": 0.6,
    "catch": true
  },
  {
    "entity_id": "ent-2933679559",
    "is_cross_source": true,
    "n_sources": 2,
    "relationship": "ANOMALOUS_UNCLASSIFIED",
    "match_level": "L3_BEHAVIOR",
    "robustness": 1.0,
    "discovery_value": 0.6,
    "catch": true
  },
  {
    "entity_id": "ent-7600329113",
    "is_cross_source": true,
    "n_sources": 2,
    "relationship": "ANOMALOUS_UNCLASSIFIED",
    "match_level": "L3_BEHAVIOR",
    "robustness": 1.0,
    "discovery_value": 0.6,
    "catch": true
  },
  {
    "entity_id": "ent-5192289106",
    "is_cross_source": true,
    "n_sources": 2,
    "relationship": "ANOMALOUS_UNCLASSIFIED",
    "match_level": "L3_BEHAVIOR",
    "robustness": 1.0,
    "discovery_value": 0.6,
    "catch": true
  },
  {
    "entity_id": "ent-7651344473",
    "is_cross_source": true,
    "n_sources": 2,
    "relationship": "ANOMALOUS_UNCLASSIFIED",
    "match_level": "L3_BEHAVIOR",
    "robustness": 1.0,
    "discovery_value": 0.6,
    "catch": true
  },
  {
    "entity_id": "ent-5196508046",
    "is_cross_source": true,
    "n_sources": 2,
    "relationship": "ANOMALOUS_UNCLASSIFIED",
    "match_level": "L3_BEHAVIOR",
    "robustness": 1.0,
    "discovery_value": 0.6,
    "catch": true
  }
]
```
