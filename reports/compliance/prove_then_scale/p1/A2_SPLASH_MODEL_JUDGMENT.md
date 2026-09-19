# A2 — the proof extended to the splash models, judged by reading

**Date:** 2026-09-19 · Task: TASK_COMPLIANCE_DELIVER_AND_SETTLE_ENGINE_V1 §A2 (Coupling 1)

Twelve cells: the same six cases, the same `reading_material.render()` material,
the same one-call / no-tools shape, the same judged-by-reading protocol as
PROVE_THEN_SCALE_V1 §P1 — on the two bases the splash packages ship:

| seat | model (Ollama tag) | mean wall | result |
|---|---|---|---|
| `qwen38` | `hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M-ctx32k` (base of `incoai/Qwen3.8-27B-Splash`) | ~301 s (251.6–413.5) | **4/6** |
| `qwen36` | `hf.co/unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q4_K_XL-ctx32k` (base of `incoai/Qwen3.6-35B-A3B-Splash`) | ~56 s (39.2–92.3) | **4/6** |

`think` off both seats (`think=False` in the transport; Qwen3.8's template opens
`<think>` by default and degenerates on hard compliance questions without it).
Raw cells: `cell_qwen38_*.json`, `cell_qwen36_*.json` in this directory.

## The verdict, per cell

**Both splash-base models read the material.** `read_check` passes on both —
each names the specific operator sections it received (qwen38 lists all seven
LSPG procedure sections with ids; qwen36 names the fixed body and the operator
side) — and every answer cites section ids from BOTH jurisdictions, verbatim
where the words matter. Nobody wrote "the material does not include our
implementation" while the sections sat labelled in the same message — the
failure that disqualified the currently-bound seat (Ling, 0/6 read_check).

Per cell:

* **parent** — PASS both. Full per-Part rollups, both sides cited; "no gaps in
  R2" matches the material (compliant + deliberate 30-day strictness).
* **choice** — FAIL both, and it is gemma4's failure to the decimal: neither
  flags the operator policy joining Part 2.3's three permitted actions with
  "and" where the Part grants one-of-three ("or"). qwen38 repeats gemma4's
  move (treats the policy's restatement as the operator "fully utilizing the
  latitude"); qwen36 avoids the restatement trap but still never notices the
  conjunction conflict.
* **interval** — PASS both. Both quote the 30-day note verbatim and conclude
  stricter-than-required; qwen38 additionally reconciles the procedure's own
  35-day sentence against the note. (Mechanical note: qwen36's cell records
  `cited_both_sides=False` because the operator-note id it cites resolves
  oddly through the parent-id splitter — the note IS cited inline with its id;
  the substance cites both sides.)
* **read_check** — PASS both (see above).
* **either_or** — PASS both. Both quote the Part's either/or and the
  procedure's "AND/OR" implementation; qwen36 adds the traceability mapping.
* **no_operator_side** — FAIL both, again gemma4's failure to the decimal:
  both answer "which of our own documents shows we do it" with the CIP Cyber
  Security Policy's verbatim *restatement* of Part 5.2 — a policy restating a
  duty is not evidence the duty is performed; the procedural WI inventory
  (§3.1.4) is.

## What this answers

1. **Do the splash models read?** Yes — 4/6 each on the proving instrument,
   identical to the proven seat (gemma4: 4/6), and with the identical two
   failures (choice, no_operator_side). The splash packages' bases are
   reading-capable seats on this material, with no navigation loop to hide in.
2. **Model choice for B6:** both bases are legitimate candidates for the
   engine-difference test — a 4/6-on-Ollama seat that drops to 2/6-on-splash
   is now measurable rather than hypothetical.

## Comparison row from §0.5

The currently-bound seat (`Ling-3.0-tiny`, 1.3B active) scored 1/6 with
read_check failing 0-of-6 and fabricated absences in the record; Nemotron also
failed read_check cells. Speed was never their problem — Ling remains the
fastest decoder measured (104.5 tok/s). Both stay installed; the seat binding
is addressed in A3 on A2's evidence.
