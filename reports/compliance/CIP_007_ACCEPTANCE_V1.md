# CIP-007-6 acceptance — state, findings, and an honest read on the path

**Task:** `TASK_COMPLIANCE_PROVE_CIP_007_V1` · **Base:** `0db04c6f` · **Written:** 2026-09-17
**Status: INCOMPLETE AND STOPPED EARLY, at the operator's instruction.**

This is not a completion report. It records what ran, what it found, what is
fixed, what is still unproven, and what I actually think about whether this
approach is working. Read §6 first if you are short of time.

---

## 1 — What ran

Two live campaigns against the deployed compliance MCP (`:8937`, host-native)
and the incumbent seat `hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M-ctx32k`.

| campaign | rev | cells run | passed | artifacts |
| --- | --- | --- | --- | --- |
| before the fixes | `f51aefa1` | 14 of 18 | 8 | `reports/compliance/acceptance-before/` |
| after the fixes | `a3b6f047` | 5 of 18 | 5 | `reports/compliance/acceptance/` |

Neither completed. The first was stopped once every failure had been attributed
and reproduced; the second was stopped by the operator after five cells.

### Before the fixes (14 cells)

| case | runs | passed | tool calls | operator sections cited |
| --- | --- | --- | --- | --- |
| `interval` | 3 | 3 | 6 | 5 |
| `choice` | 3 | **0** | 6 | 4 |
| `no_maximum` | 3 | 2 | 4 | 3 |
| `either_or` | 3 | 3 | 9 | 6 |
| `parent` | 2 | **0** | 0 (died) | 0 |
| `no_operator_side` | **0 — never ran** | — | — | — |

### After the fixes (5 cells, all passed)

| case | runs | passed | tool calls |
| --- | --- | --- | --- |
| `interval` | 3 | 3 | 5 |
| `choice` | 2 | **2** | 6 |

---

## 2 — The eight defects, and who owns them

Every failure was attributed to a §P5 rung **before** anything was changed.

| # | rung | defect | evidence |
| --- | --- | --- | --- |
| 1 | 0 | §P0.6's go/no-go sized **one turn** and certified a **twelve-turn loop** | `required = 23,758`, "margin 41,778" — the 12 tool results were absent from the sum |
| 2 | 0 | `DEFAULT_NUM_CTX` derived at 4.22 chars/token, measured on *raw corpus text*; real threads run **2.95–3.06** | recomputed worst case ~82,000 tokens vs a 65,536 window |
| 3 | 0 | three runs of a case were **not three observations** | run 1's answer arrived inside run 2's `compliance_links`; +105 prompt tokens; run 2 passed what run 1 failed, at temperature 0.0 |
| 4 | 0 | the truncation guard **passed when nothing was measured** | on the HTTP 500 there was no `context_fit`; all four guards read missing inputs as zeros and reported OK |
| 5 | 2 | the absence detector read a negative **answer** as an absence **claim** | `"**No.** The operator's procedure…"` matched `no` … `procedure` |
| 6 | 2 | a reading that died mid-loop left **no receipt** | the 500 escaped past `store_run`; 1,522 s and 12 tool calls, no record |
| 7 | 1 | the omission declaration need not cover every id it was handed | `csection-754b…` unread and unnamed |
| 8 | 0 | **`HG`, the currency gate written by this task, accepted a PARTIAL run** | a campaign stopped after 5 of 18 cells satisfied it — it asked "is there a run", never "did it finish" |

Defect #8 was found while writing this document, by running the gate instead of
asserting what it would say. It is the same failure mode as #4: a check that
cannot distinguish "measured and fine" from "not measured". It is fixed — HG now
compares `status.json` cells against `manifest.json`'s planned count and reports
`INCOMPLETE: 5 of 18` — and regression-tested.

**Rung 4 findings: zero.** No failure was attributable to the model reading the
right text and reasoning wrong. Reasoning was therefore never pulled as a lever
and `DEFAULT_EFFORT` remains `False`, untouched.

**Five of the eight (1, 2, 3, 4, 8) were introduced by this task, today, by me**
— three of them inside `§P0`, whose entire stated purpose was to make rung 0
empty before the run, and one inside `§P6.1`, whose purpose was to stop the next
abandonment.

### The cleanest single piece of evidence

`choice`, the same case, before and after:

| | before | after |
| --- | --- | --- |
| verdict | FAIL ×3 | PASS ×2 |
| **tool calls** | **6** | **6** |
| `undeclared_unread` | `csection-754b…` | `[]` |
| failure | "answer asserts an absence…" | none |

The model's behaviour is identical. What changed is that the code stopped
misjudging it.

---

## 3 — What is fixed and verified

* window 65,536 → **98,304**, requested and applied, confirmed by `/api/ps`;
  21.3 GB resident, 19.1 GB free.
* the go/no-go now counts `MAX_STEPS × TOOL_RESULT_MAX_CHARS ÷ observed ratio`
  — 45,714 tokens it previously ignored. Real margin **28,772**, not a fictional
  41,778.
* the loop refuses a call it can see will not fit, naming the turn and both
  numbers, instead of letting the runner fail.
* acceptance runs are independent (`store=False`): **0 answers projected, 15
  receipts retained**, verified in the store.
* the absence detector requires the negation to govern the noun; regression
  tests pin both the false positive and five true-positive forms.
* any transport failure now leaves a receipt.
* prompt `v2` → `v2.1`, one sentence added and quoted in its own front matter.
* the contaminated corpus was cleaned back to the derivation baseline
  (backed up first: `compliance_store.precleanup.db`, 23 MB).
* `HG` rejects a partial run and names the shortfall; `HH` passes.
* 2,300+ unit tests pass; ruff and mypy clean.

---

## 4 — What is NOT proven

Stated plainly, because the temptation is to let these slide:

1. **`parent` has never completed.** It failed twice with an Ollama HTTP 500
   (1,522 s, 760 s). I attributed that to the undersized window and the
   arithmetic supports it — but **the attribution is unverified**. `parent` has
   not been re-run at 98,304. If it fails again, finding #2 is wrong about the
   cause.
2. **`no_operator_side` has never run, once, in either campaign.** The case
   exists and its expectation was derived from real material; it has zero live
   observations.
3. **Three runs per case is unproven as a design.** Only `interval` (3/3) and
   `choice` (2/2) have repeated observations post-fix.
4. **The legacy `compliance_gaps` adapter has never executed.** It is written
   and its poll vocabulary was corrected by reading `assessment_runs`, but no
   live call has been made. F1's equivalence claim rests on nothing yet.
5. **The prompt v1-vs-v2 comparison has not run.** The script exists. So "the
   new prompt is better" is currently supported by anecdote (a v1-era run
   answered in prose and called nothing; v2 seats open by reading) — not by the
   controlled measurement P4 asks for.
6. **Only one seat has been exercised on cases.** `glm-4.7-flash` and
   `qwen3.6:27b` passed preflight (and are ~2× faster) but have run no cases.
7. **`validate_system` HG FAILS right now**, by design and verified:
   `INCOMPLETE: 5 of 18 planned cell(s) in a3b6f047ab0d`. The tree is red on
   that gate until a full run lands. `HH` passes — the seat's template sha still
   matches the pin.

---

## 4a — This was pushed with the gate RED, deliberately

`git push` was run with `--no-verify`. That bypassed `HG`, which was failing
correctly:

```
✗ HG. compliance acceptance has run at or after the last commit touching the module
     — the only acceptance run at or after a3b6f047ab0d is INCOMPLETE:
       5 of 18 planned cell(s). A stopped run is not currency.
```

**The gate was right and was overridden anyway**, by explicit operator decision,
so that the findings reach `main` immediately rather than waiting ~2 hours on a
run the operator had chosen to stop. Recorded here because a bypassed gate that
leaves no trace is indistinguishable from a gate that never fired — which is the
failure mode this whole task is about.

`BU` (complexity budget) was **not** bypassed; it was legitimately re-stamped in
`9c5c916f` after real code growth. Note `unwired_scripts` 13 → 16: three of the
scripts added here (`compliance_acceptance_report.py`,
`compliance_prompt_comparison.py`, `compliance_unproject_campaign_answers.py`)
are one-off tools with no caller. That is a real, if minor, complexity signal.

**What this means for anyone reading `main`:** the compliance module at
`a3b6f047` carries seven fixes that have **not** been validated by a complete
live acceptance run. `HG` will keep failing every push until one lands. Do not
read the green unit suite as evidence that the reading path works — that is
precisely the inference this task was written to stop.

## 5 — What is left, in order

1. Re-run the 18 reader cells at `a3b6f047` (~1.5–2 h). This settles #1, #2, #3.
2. Run the legacy adapter once per case (#4).
3. Prompt v1 vs v2.1 on the six cases (#5, ~45 min).
4. Second seat, `glm-4.7-flash` (#6, ~1 h at 3 runs, ~20 min at 1).
5. Only then: §P6.2's sequence (F1 re-point, F2 bounded packet, retire the six
   superseded harnesses, CIP-007-6 → the family).

§P6.1's gates (`HG`, `HH`) are written, registered and unit-tested; they are not
yet satisfiable because of item 1.

---

## 6 — Is this the right path? My honest read

**What is working, and I do not think this should be discounted:** the design
caught all eight defects and attributed every one without a single round of
prompt-thrashing. Four of them are exactly the class that made seven previous
harnesses look healthy and fail on contact with a model — a harness that feeds
itself, a guard that passes on missing data, a preflight that proves one call
and certifies twelve. Those would not have been found by more unit tests. The
rung discipline did its job: nothing was blamed on the model, and reasoning was
never reached for.

**What is not working, and is the real concern:** the defect rate *in newly
written apparatus* is unacceptable, and the feedback loop that catches it is
measured in hours. I wrote four defects into a preflight built to prevent
defects, and each one took a two-hour live run to surface. That is the
structural problem, and it is not fixed by any of the seven fixes above.

**The concrete gap:** there is no cheap self-test for the instrument. Defects
#4 (guard passes on missing data), #5 (absence regex), and #3 (contamination,
detectable as "two runs of one case produced different prompt token counts")
are all checkable in **seconds** against *recorded* threads, with no model
involved. They cost hours each instead. Every artifact needed already exists —
`reading_runs` retains full transcripts, and the acceptance records carry every
applied setting.

**What I would do before spending another two hours of GPU time:** build that
replay layer first — feed the recorded before/after threads through the checker,
the guard and the closure contract with no model, and assert the known verdicts.
It is perhaps an hour of work, it would have caught four of today's eight, and
it makes every future instrument change cost seconds to validate instead of a
campaign. Then re-run.

**On the underlying question — is the compliance reading product itself sound?**
The evidence so far says yes, and more strongly than before this run. Across 19
live cells the model read both sides, cited them, caught a conflict between the
operator's note and their own procedure, correctly labelled a traceability
appendix as non-operative, and stated over-strictness as fact rather than as a
gap. Every case that failed, failed in our scoring. That is a good sign about
the product and a bad sign about the apparatus around it — and right now the
apparatus is the larger body of code.

**What I am least confident about:** that `parent` — the rollup case, and the
one an analyst would most plausibly ask — works at all. It has never produced an
answer. Until it does, the six-case claim is a four-and-a-half-case claim.
