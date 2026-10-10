---
id: D-T10-TRUTH-SPAN
question: When each answer-key entry's attack span is limited to the UTC days on which every one of its declared entities is present, does a same-index pairing arm yield a benign comparator for at least two of the three BOTS indexes?
stage: window
why_not_binding: "No product stage has ever been measured: D-T8 and D-T9 both resolved INCONCLUSIVE with 0 of 3 paired slices, so the window stage is still where every truth item is lost before a product arm can run."
arms: [index, entity_days]
metric: count of the three pre-registered indexes that yield a same-index benign comparator, under D-T8's same-index pairing arms evaluated in order (hull, then per_entry, then matched_set), reported beside the answer-key entry yield and each derived entry's span; recomputed from the committed rows by scripts/review_eval_truth.py
adopt_if: "Adopt entity_days with the SIMPLEST same-index pairing arm that yields a benign comparator for at least two of the three indexes. Run the arms in the order hull, per_entry, matched_set, and stop at the first that qualifies. D-T8's conditions apply unchanged: UTC-day aligned windows, a margin of 86,400 s, disjoint from every derived answer-key span, drawn from the same index. The control (index, the span rule every report since T1 used) cannot qualify. It runs once, with hull, to reproduce D-T8's hull result: 0 of 3 paired, 7 of 27 entries, corpus_snapshot 82bae32d. An adopted arm is same-index and same-collection, so it is not proxy-paired. Its truth is the narrowed truth: the result names every entry the control derives and entity_days drops. If no pairing arm qualifies, resolve INCONCLUSIVE, and the next task is benign telemetry acquisition."
anti_goals:
  - do not add, remove or edit any answer-key entity, sourcetype or entry; the answer key stays exactly as committed, and no attacker indicator from a write-up is added to it
  - do not change the day granularity, the margin, the day alignment, the pairing order or the same-index condition after seeing a number; any change is a new record
  - do not choose days by event count, spike or threshold; a day is in an entry's span only because every declared entity is present on it
  - do not add, re-index, inject or synthesize telemetry
  - do not treat an adopted arm as a product result; it re-enables T1, it does not answer it
  - do not tune any threshold, weight, cutoff or prompt, and do not edit a deprecated module
status: ADOPTED
report: reports/review_eval/931f78ea19fa21c0/truth_derivation.json
result: "entity_days with per_entry pairing qualified (hull paired 1 of 3, botsv1 only; per_entry paired 2 of 3): botsv1 paired with candidate windows 2016-08-01 and 2016-08-12 (one UTC day each), botsv2 with candidate windows 2017-08-01, 2017-08-05, 2017-08-18 and 2017-08-18 to 08-24, botsv3 unpaired; entry yield stays 7 of 27 under both spans, but the index span dated the 7 derived entries over whole months (botsv1 T1071.001 and T1190 from 2016-08-01 to 08-28, 23438 events; botsv2 T1190 from 2017-08-01 to 08-31, 616196 events), and entity_days narrows them to their attack days (2016-08-10, 22491 events; 2017-08-11 to 08-17, 127114 events), dropping no derived entry and changing only the reasons of three dropped entries (botsv1 T1592, botsv3 T1071.001 and T1190)."
---

## Why this record exists

D-T8 said BOTS indexes "hold the incident" and nothing else, so a benign window as long as the
attack cannot exist in them. D-T9 then looked for benign data in `portal5_lab` and found 1 eligible
event in 15.1M. Both records took the derived attack spans as given. The spans are the problem.

`scripts/review_eval_truth.py` dates each answer-key entry from the first to the last event that
contains **any** of its declared entities, anywhere in the index. Some entities are victim assets,
not attack indicators. They appear in ordinary traffic every day. botsv1's T1190 entry declares
`imreallynotbatman.com` and `192.168.250.70`, the attacked web server's name and address. The address
appears in `stream:http` on every day from 2016-08-01 to 2016-08-28 (18 to 36 times a day, apart from
22,490 on 08-10 and 235 on 08-24), so the entry spans
the whole index (D-T8 per_entry report: 08-01 00:30 to 08-28 23:06). The name appears on one day
only, 2016-08-10. That is the day the published write-up gives for the attack.

botsv1 holds 29 days at about 1M events a day, and botsv2 holds 31 days at about 5M a day. The benign
population is in the same index, collected by the same sensors, and the derivation hides it.

The same flaw touches truth quality, not just pairing. Under the index span, botsv1 T1190's truth
item includes the web server's everyday background traffic as "known" attack events.

## The arms

* **`index` (control).** The current rule. An entry spans the first to the last event that matches
  any declared entity.
* **`entity_days`.** For each declared entity, read the UTC days on which it appears in the entry's
  declared sourcetypes (aggregate counts only). The entry's span runs from the first day on which
  **every** declared entity appears to the end of the last such day. Raw rows are fetched only
  inside that span, and the expected-versus-fetched reconciliation is recomputed over the same
  days. This is the derivation's existing "all entities located" condition, applied per day instead
  of per index. If the entities never share a day, the entry is dropped with reason
  `answer_key_entities_share_no_utc_day`.

The pairing rule does not change. The same-index arms from D-T8 (hull, per_entry, matched_set) run
on the narrowed spans, simplest first.

## What the reviewer saw before writing this

The reviewer saw:

* the per-UTC-day event totals of botsv1, botsv2 and botsv3;
* the per-day `stream:http` counts in botsv1 for the two T1190 entities;
* the per-day botsv1 counts for two attacker addresses from the public write-up (40.80.148.42 and
  23.22.63.114, both 2016-08-10 only). These are **not** in the answer key and the rule does not
  use them;
* the D-T8 reports' derived spans.

No per-day count for any other entry has been seen. botsv3 holds a single day of data (2018-08-20,
1,944,421 events) and derives no entry today, so at most two indexes can pair. That is why the bar is
two of three, the same as D-T8 and D-T9.

## What adopting does and does not mean

It re-enables T1 with a same-index, real comparator and narrower truth, nothing more. T1 is then
re-run under the adopted span and pairing rule. botsv3 stays without a comparator either way, so if
botsv3 is needed later, benign telemetry for it is a separate question.
