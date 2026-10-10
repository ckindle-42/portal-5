---
id: D-T8-PAIRING
question: Can any benign-comparator rule yield a same-index paired slice from the pre-registered BOTS indexes, and if so which is the simplest that does?
stage: window
why_not_binding: "The ledger reports no measured binding stage, and it cannot report one: T1 excluded all three paired product slices before any arm ran, so no product stage has ever been measured. The window stage is where that exclusion happens, which makes it the only stage this program can bind on right now."
arms: [hull, per_entry, matched_set, cross_index]
metric: count of the three pre-registered indexes that yield at least one benign comparator under the arm, reported beside the answer-key entry yield; both recomputed from the committed rows by scripts/review_eval_truth.py
adopt_if: "Adopt the SIMPLEST arm (order hull < per_entry < matched_set < cross_index) that yields at least one benign comparator for at least two of the three indexes, whose comparator windows are UTC-day aligned, disjoint by event id from every derived answer-key interval, and, for hull, per_entry and matched_set, drawn from the same index as the attack side. cross_index is exempt from the same-index condition by construction (its comparator is --benign-index); it qualifies only if no same-index arm does, and an adopted cross_index arm is marked proxy-paired: the benign index is recorded as a covariate on every row and no claim may call the pairing real. Ties keep the control. If no arm qualifies, resolve INCONCLUSIVE: the finding is that the corpus cannot furnish a benign comparator, which needs telemetry, not a rule change."
anti_goals:
  - do not widen the margin, shorten the required duration or relax day alignment to manufacture a pair; margin_seconds stays 86400 as T1 applied it, and any change to it is a new record
  - do not add, re-index, inject or synthesize telemetry to make an index long enough
  - do not treat an adopted pairing arm as a product result; it re-enables T1, it does not answer it
  - do not tune any threshold, weight, cutoff or prompt, and do not edit a deprecated module
status: ADOPTED
report: reports/review_eval/15a35aa1fcbcbfb7/truth_derivation.json
result: "cross_index is the only qualifying arm and is adopted proxy-paired (benign index portal5_lab): hull, per_entry and matched_set each paired 0 of 3 indexes because the complements outside the answer-key spans plus the 86,400 s margin are empty in botsv1 and botsv2 and botsv3 derives no interval, while cross_index yields a UTC-day-aligned benign comparator of the full attack duration for 2 of 3 indexes (botsv1 and botsv2), event-id disjoint by namespace, at an unchanged answer-key yield of 7 of 27 in every arm."
---

## Why this record exists

T1 reported `0 of 3` indexes with a usable benign interval and every record from T2 to T6 inherited
that: `0/3 eligible paired slices`, `0/20 valid same-index pairs`, "no workload B". Nine records
resolved INCONCLUSIVE or REJECTED without a single product arm running. The reason is arithmetic,
not data: T1's rule asks for a benign window **as long as the whole span of an index's answer-key
entries**, UTC-day aligned, outside that span plus a day of margin, in the same index.

| index | derived entries | answer-key hull | margin | benign window needed | indexed time available |
|---|---|---|---|---|---|
| botsv1 | 5 | 2,414,156 s (27.9 d) | 86,400 s | 27.9 d outside the hull | ~the hull |
| botsv2 | 2 | 2,674,615 s (31.0 d) | 86,400 s | 31.0 d outside the hull | ~the hull |
| botsv3 | 0 | — | — | — | no derived interval |

An index would have to hold about twice its own attack span for that to be satisfiable. BOTS
datasets are curated incident captures; they hold the incident. So the rule cannot pass for any
arm, reader, threshold or model, and no amount of re-running T3 to T6 changes it. T4 said the same
thing in its own words: "botsv1 and botsv2 have 0 seconds outside their answer-key intervals plus
margin". That is the instrument reporting on itself, and I-8 says an experiment targets the stage
that loses the most truth. Every earlier record wrote `why_not_binding` and moved on. This one
does not.

## The arms

Each is a value of `--pairing` on `scripts/review_eval_truth.py`. The product path is untouched;
only the slice-selection rule differs, and all four are computed from the same derivation in the
same run.

* **`hull` (control).** T1's rule, reproduced exactly, including its verbatim exclusion reason. One
  attack span per index (first to last derived answer-key event), one same-length benign window.
* **`per_entry`.** The attack spans are the individual derived entry intervals, not their hull, and
  each entry asks only for a benign window of **its own** duration. Two one-day scenarios twenty
  days apart stop implying a twenty-two-day attack. This is what T2 was reaching for; T2 rejected it
  because the parent-ID gate failed, and that gate failed on an unstable identity function, not on
  the data (`fix(review): event_id is the event's identity, not the search job's` — 804 of 22,397
  ids reconciled at identical row counts because the id was hashing `_serial` and friends). This
  record must be run after that fix or it will inherit the same artifact.
* **`matched_set`.** A set of day-aligned slices from the complement whose total reaches the attack
  duration, instead of one contiguous window of that length. The product reads a set of windows
  either way, so contiguity was never a requirement of the comparison. Returns nothing when the
  complement cannot reach the target, so a short corpus still fails loudly.
* **`cross_index`.** Benign windows of the attack duration drawn from `portal5_lab`, where T1 found
  12 of 12 benign cells live and event-id reconciled but could not use them because the pair rule
  demands one index. Honest only as a declared covariate: different index, different collection,
  different population. It is last in the adoption order for that reason, and an adopted
  `cross_index` is proxy-paired, never `real:`.

## What adopting one does and does not mean

It unblocks T1, nothing more. The adopted arm becomes the slice rule the single runner uses, T1 is
re-run as code for the first time, and only if T1 then produces a workload budget B do T3's and T4's
questions become answerable at all. If every arm fails, the result is a corpus statement — this
program cannot measure a false-raise rate against a benign population that its corpus does not
contain — and the next task is telemetry acquisition, not another rule.
