---
id: D-T11-ANSWER-KEY
question: Can a rebuilt BOTS answer key, with every entry cited to a public write-up and admitted only by the audit rule, admit entries in at least two indexes and pair them under D-T10's adopted rule (entity_days + per_entry)?
stage: window
why_not_binding: "No product stage has ever been measured: D-T8, D-T9 and D-T10 resolved with 0 of 3 or 2 of 3 paired slices and no product arm run, so the window stage is still where every truth item is lost before a product arm can run."
arms: [BOTS_ANSWER_KEY, rebuilt_key]
metric: count of entries the audit admits under the rebuilt key, per index, beside the audit problem count of every admitted entry; then the count of the three pre-registered indexes that pair under entity_days + per_entry on the admitted key; power reported beside both, never gated
adopt_if: "Adopt the rebuilt key if the audit admits at least 1 entry in each of at least 2 indexes, every admitted entry has no problem in review_truth_audit.py, and under D-T10's adopted rule (entity_days + per_entry) at least 2 of the 3 indexes pair on the admitted key. Otherwise resolve INCONCLUSIVE. The power statement (admitted count against N = 233) is reported, not gated: if the admitted count is below 233, the result says plainly that BOTS alone cannot power T1's comparison, and that T1's headline needs a second labelled corpus, with coding_task/BULLY_TRUTH_REDESIGN_V1.md as the candidate, awaiting operator review. BOTS_ANSWER_KEY is the control and is never edited; it cannot qualify."
anti_goals:
  - do not add, remove or edit any entity or sourcetype of BOTS_ANSWER_KEY; the control stays exactly as committed and is not deleted
  - do not take an entity, sourcetype, IP, domain or host from looking at the data; each one must cite a public write-up (URL plus the question or section) for the entity and for the sourcetype it names
  - do not AND-match across events, OR-match within an entry, or count a portal5-written source (source="portal5:*") as truth; an entry whose indicator does not co-occur in one event is two entries
  - do not admit an entry the audit flags with any problem, and do not edit the audit rule after seeing a number
  - do not change the admission rule, the power inputs (d = 0.10, discordance 0.3, two-sided alpha 0.05, 80% power), the pairing order or the arm ordering after seeing a number; any change is a new record
  - do not re-run T1 under this record; re-running T1 is the next task
  - do not tune any threshold, weight, cutoff or prompt, and do not edit a deprecated module; BOTS_ANSWER_KEY is imported by deprecated Bully modules and stays in place
status: PREREGISTERED
---

## Corrections and disclosures carried into this record

**Correction to D-T10.** D-T10's "what the reviewer saw" section says the attacker addresses
40.80.148.42 and 23.22.63.114 are "not in the answer key". That is false. They are entities of
botsv1 T1595.002, T1583, T1110 and T1592 in `BOTS_ANSWER_KEY`. The rule in D-T10 is unaffected by
this, but the disclosure was wrong. Records are never edited, so the correction is stated here. The
audit (`reports/review_eval/truth_audit/answer_key_audit/answer_key_audit.md`) confirms that botsv1
T1583 declares 40.80.148.42.

**Injected cousins were deleted.** On 2026-10-10, with operator approval, all 745
`portal5:corpus:cousin:*` events were deleted from botsv1 (60), botsv2 (100) and botsv3 (585). Before
the deletion, `can_delete` was temporarily granted to the admin account and revoked straight after.
`portal5_lab` still holds 225 cousin events and is out of scope here.

**Every earlier truth manifest is from the contaminated corpus.** Reports T1 to T10 were produced
before the deletion. Nobody checked whether any of their truth events were cousins, and the deleted
events can no longer be inspected. Those manifests are not evidence about the current corpus.

**Victim assets as attack markers.** The audit shows 192.168.250.70 on every sensor day of botsv1 and
www.brewertalk.com matching every stream:http event of that site in botsv2. Any entry that
depends on these alone is rejected by the audit rule, which is why no entry may rely on them.

## Power, before transcription

The record fixes the effect, discordance and power before any entry is transcribed.

* Effect: d = 0.10 absolute recall at workload B. This is the smallest loss a SOC would treat as
  material. T1's adopt_if is a non-inferiority question, so a 10-point recall deficit is the
  smallest difference T1 should care about.
* Discordance: 0.3. No discordance has ever been measured. Two pipelines plausibly disagree often,
  so the conservative value is used.
* Two-sided alpha 0.05, 80% power, normal approximation to the paired exact McNemar test.

N = ((z(0.975) * sqrt(p) + z(0.80) * sqrt(p - d^2)) / d)^2, with p = 0.30 and d = 0.10:

    z(0.975) = 1.96,  z(0.80) = 0.8416
    sqrt(0.30) = 0.5477,  sqrt(0.29) = 0.5385
    numerator = 1.96 * 0.5477 + 0.8416 * 0.5385 = 1.0735 + 0.4532 = 1.5267
    N = (1.5267 / 0.10)^2 = 15.267^2 = 233.1, so N = 233 truth items

## Why the rule changed from N to two indexes

An earlier draft tied adoption to reaching N. That was the wrong gate. A valid, audited key is worth
having even if it cannot power T1 on its own. Adoption therefore depends on the two rules in
`adopt_if`, and the admitted count against N = 233 is reported as the power statement.

## The arms

* **BOTS_ANSWER_KEY (control).** The 27 committed entries. Its audit shows 2 of 27 with no problem.
  It is not edited, and it cannot qualify.
* **rebuilt_key.** Entries transcribed from public BOTS write-ups under the admission rule above,
  then run through `review_truth_audit.py`. Only entries the audit reports with no problem are
  admitted. Every rejected entry is listed with its audit reason.

## Citations and sources

Each entry cites a public BOTS write-up for each entity and each sourcetype it names. Accepted
sources: Splunk's botsv3 GitHub pages, the official BOTS v1, v2 and v3 question sets, and community
write-ups. The URL and the question or section are recorded beside each entry. No entity or sourcetype
may come from looking at the data.
