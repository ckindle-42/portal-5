---
id: D-T9-BENIGN-POPULATION
question: Does portal5_lab hold a benign population (events from sources Portal did not write, on every UTC day of a window as long as the attack span) that can serve as a cross-index comparator for at least two of the three BOTS indexes?
stage: window
why_not_binding: "No product stage has ever been measured: D-T8 resolved INCONCLUSIVE with 0 of 3 paired slices under every arm, so the window stage is still where every truth item is lost before a product arm can run."
arms: [cross_index, cross_index_benign]
metric: count of the three pre-registered indexes that yield an occupied, provenance-eligible benign window under the arm, reported beside the answer-key entry yield and the eligible-versus-denied event census of the benign index; recomputed from the committed rows by scripts/review_eval_truth.py
adopt_if: "Adopt cross_index_benign if, for at least two of the three indexes, it yields a UTC-day-aligned window of the full attack duration in portal5_lab in which every UTC day the window touches carries at least one event from an eligible source. A source is eligible unless it starts with `portal5:` or equals `http:portal5_hec`. The control (cross_index, D-T8's extent-only rule) cannot qualify, because it checks neither occupancy nor provenance; it is run only to reproduce D-T8's empty 2010-10-01 windows. An adopted arm is proxy-paired: the benign index and the eligible-source list are covariates on every row, the product reads the window restricted to eligible sources, and no claim may call the pairing real. If it does not qualify, resolve INCONCLUSIVE: portal5_lab holds no benign population, and the next task is benign telemetry acquisition, not another pairing rule."
anti_goals:
  - do not change the denied-source rule, the one-event-per-day floor, the earliest-window selection or the day alignment after seeing the census; any change is a new record
  - do not count a portal5-written source (attack corpora or Bully emulation-run evidence) as benign, and do not hand-pick a window
  - do not add, re-index, inject or synthesize telemetry
  - do not treat an adopted arm as a product result; it re-enables T1, it does not answer it
  - do not tune any threshold, weight, cutoff or prompt, and do not edit a deprecated module
status: PREREGISTERED
---

## Why this record exists

D-T8 was first resolved ADOPTED for `cross_index`, then corrected to INCONCLUSIVE (`0162220d`).
Its `cross_index` arm placed each benign window from `portal5_lab`'s `min(_time)`/`max(_time)` and
nothing else. The index's earliest timestamps are a handful of stray 2010 events, so both windows
landed on 2010-10-01, and both hold 0 events (`reports/review_eval/d_t8_correction/occupancy.json`).

Fixing occupancy alone is not enough. What `portal5_lab` holds matters, not just whether it holds
something. Most of it is written by Portal itself: the published attack corpora, sourced
`portal5:corpus:mordor:*` (APT29 and APT3 evaluations, Empire, Caldera) and
`portal5:corpus:attack_data:*` (Splunk attack_data: Cobalt Strike, TrickBot, PrintNightmare, ...).
Bully's emulation-run evidence is sourced `portal5:<origin>`, using the origins in
`portal/modules/security/core/telemetry.py` (`observed_packet`, `imported_observed`, ...), and
Bully's HEC shipper writes `http:portal5_hec`. An occupied window of that is attack telemetry, and
calling it benign would be worse than the empty window.

## The arms

* **`cross_index` (control).** D-T8's rule, unchanged. Expected to reproduce the empty 2010-10-01
  windows. It is reported, never adopted.
* **`cross_index_benign`.** It reads `portal5_lab`'s per-UTC-day, per-source event counts from tsidx
  metadata (aggregates only; no raw event is read for this). It drops every source that starts with
  `portal5:` and the source `http:portal5_hec`, and keeps every other source as unlabeled
  background. It then takes the **earliest** UTC-day-aligned window of the index's attack-hull
  duration in which every day carries at least one eligible event. Earliest-first is the only
  selection rule, so no window is chosen for its content. The window's eligible event count, its
  minimum daily count and its per-source eligible counts are covariates in the report.

The floor is one event per day on purpose. It is a pre-registered existence test ("is anything
benign there at all"), not a density claim. Density is reported, not gated, and a sparse adopted
window will show as sparse in every downstream false-raise rate.

## What the reviewer saw before writing this

That disclosure belongs here because seeing data before writing a rule is exactly what this
protocol guards against. Before writing the record, the reviewer saw `portal5_lab`'s yearly event
histogram and its top 40 (year, source) rows by count. Every one of those 40 sources is
`portal5:`-prefixed or `http:portal5_hec`. The reviewer has not seen any count for a source outside
the denied set and does not know whether one exists. The denied-source rule comes from provenance
(who writes the source, read from code), not from counts, and it fails toward INCONCLUSIVE, not
toward a pair.

## What adopting does and does not mean

Same as D-T8. Adopting re-enables T1 with a proxy-paired comparator restricted to eligible
sources, nothing more. If the arm fails, the program has established that none of its indexes
contains a benign population of the needed length. That is a corpus statement, and the next task is
acquiring benign telemetry for the lab.
