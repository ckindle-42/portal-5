# A6.3 / A6.4 — the refusals, separated; CIP-007-6 re-read; the CIP-002 re-run

**Date:** 2026-09-20 · **Task:** TASK_COMPLIANCE_DELIVER_AND_SETTLE_ENGINE_V1 §A6.3/§A6.4 + the §A5 owed re-run

## The writer defect A6.3 exposed first

"Re-run with reasons retained" was impossible on arrival: `sweep.py`'s closure
receipt **strips** `outcomes` from `determinations` before `store_run`
persists it — the comment above the line says the outcomes ride inside the
receipt, the code excluded them, so every rejection reason died at write time.
The re-run reproduced the loss live (first v1 receipts had tallies only), the
one-line fix retains `outcomes` inside `closure_receipt.determinations`, and
the v2 re-runs persist every reason. That defect is why §P7's rejection
reasons were lost in the first place — the comment recorded the intent, the
code never carried it.

## A6.3 — CIP-003-8 and CIP-004-7 re-run, reasons retained (v2)

Seat gemma4, `sweep_standard`, write=True (determinations land at their own
status with provenance). Receipts: `a63_cip003_8_v2.json`, `a63_cip004_7_v2.json`;
per-row reasons in the store's `closure_json`.

| standard | rows | determined | corroborated | rejected | wall |
|---|---:|---:|---:|---:|---:|
| CIP-003-8 | 39 (0 errors) | 0 | 3 | 20 | 880 s |
| CIP-004-7 | 19 (0 errors) | 10 | 22 | 15 | 937 s |

### The separation — §8.1's dichotomy doesn't survive contact with reasons

**CIP-003-8: the refusals are neither quote discipline nor checker
strictness — they are model side-error.** 18 of 20 rejections are
*"section … is US jurisdiction — determinations pair a requirement with an
OPERATOR section only"*: the reading reached for the standard's OWN sections
as if they were operator documents. The remaining two are one invented
requirement id and one non-verbatim quote. The corpus-level cause is the
census's: CIP-003-8's operator side is thin (15 operator sections across 3
requirements' populations), and a map pass over operator-thin populations
reaches for the wrong side.

**CIP-004-7: genuinely mixed.** 8 of 15 are *"the quoted sentence is not in
the section's text"* — **checker strictness** (paraphrase or near-miss
quotation refused by the verbatim guard); 7 are model discipline failures
(invented/misaddressed requirement ids: 3 "not in the register", 3
"section id unresolved", 1 wrong standard). And the run's headline: **10
determinations and 22 corroborations where the recorded family sweep refused
11 and determined 0** — same seat, same store, so the old all-refuse outcome
was substantially run variance and prompt-era, not a wall.

Quote discipline vs checker strictness, answered: on CIP-004-7 the checker
refuses real pairings for paraphrase in ~half the rejections — a quote-repair
retry (ask the model to re-quote the exact sentence) is the indicated fix; on
CIP-003-8 no checker relaxation is warranted — the fix is side-labeling in the
map prompt (the same class the census found at family scale: a passage about a
duty vs the section that states it).

## A6.4 — CIP-007-6 re-read

Receipt: `a64_cip007_6.json` (20 rows, 0 errors, 1,389 s). Outcome: **0
determined, 19 corroborated, 15 rejected.** The second pass corroborated
19 of the first pass's pairings — two independent passes over the same corpus
now agree, which is what the contradiction queue needed to see: its zero was
structural (one pass cannot disagree with itself), and the second pass
disagrees about nothing so far. The 15 rejections predate the outcomes fix, so
their reasons are tally-only — noted honestly; the v2 writer makes every
future pass fully reason-addressable.

## The §A5 owed re-run — CIP-002-5.1a

Receipt: `a5_cip002_rerun.json` (33 rows, **0 errors**, 642 s). All 26
previously-skipped Attachment nodes read at ~13-14 s each — the grammar growth
works end to end. Determinations: 1 (via R1), 0 elsewhere — matching the
census's inverse-orphan finding: the operator's BES Cyber System Categorisation
Process (47 sections in store) has no recorded edges to the Attachment parts,
so the readings correctly found nothing to map. The follow-up is link
creation, not addressability; CIP-002-5.1a is now fully readable by the sweep
whenever that work lands.
