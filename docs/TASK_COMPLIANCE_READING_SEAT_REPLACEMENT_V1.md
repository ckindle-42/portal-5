# TASK_COMPLIANCE_READING_SEAT_REPLACEMENT_V1

**Status:** SUPERSEDED AS A STANDALONE TASK — retain as diagnostic evidence.
Execute the complete sequence through
`coding_task/v9_compliance/TASK_COMPLIANCE_REASONING_PRODUCT_END_TO_END_V1.md`.
Its model-qualification phases correct the production-reader and quantization
confounds and do not require an operator preference when frozen hard gates
determine the result.

**Opened:** 2026-09-14, on the operator's instruction after
`reports/compliance/LDOC_FAMILY_LIVE_REPLAY.md`.
**Incumbent under review:** `mistral-small3.2:24b-instruct-2506-q4_K_M`
(seat id `mistral`, `config/compliance/council.yaml`).

---

## 1. Why this seat is under review

The council roster was selected by the 2026-09-06 twelve-seat judgment probe,
scored on F2 for violation detection over a **pre-analyzed packet**. That was the
old question. The product path is now a *reading* task
(`core/reading.py`): read the Part, enumerate its mandatory duties, read the
operator's material, judge each duty, and **cite the slice ids that prove it**.

The roster's qualification evidence does not transfer to that question. This
task is the re-qualification for the `mistral` seat specifically, because it is
the only seat that fails and it fails the same way every time.

## 2. The evidence

Four live reads of the L-document family, one per case, all three seats
(`reports/compliance/LDOC_FAMILY_LIVE_REPLAY.json`):

| case | `documentary_coverage` | gap kind | counterevidence cited |
|---|---|---|---|
| 10 | PARTIAL ✓ | WEAKER_COMMITMENT ✓ | **`[]` — empty** |
| 19 | PARTIAL ✓ | WEAKER_COMMITMENT ✓ | `cand-L23` ✓ |
| 20 | PARTIAL ✓ | **OMISSION ✗** | **`[]` — empty** |
| 25 | PARTIAL ✓ | WEAKER_COMMITMENT ✓ | **`[]` — empty** |

A fifth observation, from the earlier case-10 probe
(`reports/compliance/READING_JUDGMENT_V1.md` §2.2): it cited
`cand-aee961b20917773` — the real id `cand-aee961b209177773` with **one digit
dropped**.

The other two seats scored 6/6 on all four cases.

### 2.1 The defect is citation attachment, not comprehension

`documentary_coverage` is correct **4 of 4**. Gap kind is correct **3 of 4**.
What fails is attaching the slice id that grounds the gap.

Case 20's `OMISSION` is not a second defect — it follows from the first. Having
attached no counterevidence, the model described its own (uncited) gap as an
absence. One root cause: **the model finds the gap and does not carry the
identifier that proves it.**

This is the exact failure mode the product cannot tolerate. A gap with no
counterevidence id is an unciteable finding: an operator cannot follow it to the
sentence in their own procedure, and the verification layer has nothing to
verify. The verdict survives — the verification layer names the failure and does
not void it — but the finding is not actionable.

### 2.2 The most likely cause is worth testing before replacing the family

Slice ids are 20-hex-character strings (`cand-aee961b209177773`). Verbatim echo
of a long opaque identifier is precisely the capability that aggressive
quantization degrades, and the incumbent is `Q4_K_M`. The dropped-digit
observation is a literal transcription error, not a reasoning error.

**So the first experiment is not "find a different family" — it is "is this
quantization or is this the model".** `Magistral-Small-2509` at `Q8_0` is the
same lineage at higher precision and is already local. If Q8 fixes it, the
finding is about quant, generalises to every seat, and is cheaper than a swap.

## 3. Diagnostic protocol

Run in order. Each step is cheap (~50 s per read) using the existing harness:

```sh
uv run python scripts/replay_compliance_reading_family.py 10,19,20,25
```

**D1 — isolate citation fidelity from reading.** Add a probe that gives the model
a packet and asks only for the ids that ground a stated finding, with the
finding supplied. If a candidate fails here it is not a reading problem.

**D2 — the quantization control.** Same four cases against
`hf.co/unsloth/Magistral-Small-2509-GGUF:Q8_0-ctx64k` (24.2 GB, already pulled).
Same family, higher precision. Record whether counterevidence attachment
recovers.

**D3 — candidate sweep.** The four cases against each shortlisted candidate.

**D4 — family-diversity check.** The roster deliberately spans three model
families so that a shared blind spot cannot reach quorum. Any replacement must
preserve that: it must not be a Qwen or a Granite.

## 4. Candidate shortlist

Local, already pulled, non-Qwen and non-Granite so roster diversity survives:

| candidate | size | family | why |
|---|---|---|---|
| `hf.co/unsloth/Magistral-Small-2509-GGUF:Q8_0-ctx64k` | 24.2 GB | Mistral | **the control, run first.** Same lineage at Q8 — separates a quantization artifact from a model limitation |
| `gpt-oss:20b` | 12.8 GB | OpenAI | smallest of the shortlist, different family, native reasoning-effort levels, MXFP4 |
| `gemma4:26b-a4b-it-q4_K_M` | 16.8 GB | Gemma | MoE (A4B active) so materially faster than a dense 24B; different family |
| `glm-4.7-flash:Q4_K_M-ctx64k` | 17.7 GB | GLM | different family, thinking-capable, 64k baked context |

Not shortlisted, with reasons: any Qwen (breaks D4 — `qwen38` holds that seat);
any Granite (same); `devstral-small-2` and the coder models (code-specialised);
`deepseek-r1:32b` and `GLM-Z1-Rumination` (reasoning-first models, and §5 records
that reasoning buys nothing on this task).

**Reasoning capability is not a criterion.** Measured on the real case-10 packet:
`think` false / low / medium / xhigh returned the identical correct reading at
52 s / 180 s / 224 s / 683 s (`reports/compliance/THINKING_CONFOUND_V1.md`).
`DEFAULT_EFFORT` is `False`. Do not prefer a candidate for being a reasoner.

## 5. Acceptance criteria

A candidate replaces the seat only if, across cases 10, 19, 20 and 25:

1. `documentary_coverage` matches the expectation on **4 of 4** (the incumbent
   already achieves this — it is a floor, not a discriminator).
2. Gap kind matches on **4 of 4**.
3. Counterevidence slice ids are attached and resolve on **4 of 4** — the
   discriminator; the incumbent scores 1 of 4.
4. No unresolvable citation in any run.
5. Wall time per read within ~2× the incumbent's ~46 s, so the suite stays
   affordable.
6. It is not a Qwen or a Granite (D4).

Run each candidate **three times per case** before deciding. Case 02/04's history
in the original qualification is the precedent: single observations confounded
stable failure with sampling variance.

## 6. What this task must not conclude

- **Not that mistral "cannot read".** Its `documentary_coverage` is correct on
  every case measured, and it read the isolated case-10 packet correctly when
  the old architecture's seats did not. The defect is narrow and named.
- **Not that the quorum is broken.** At 2-of-3 all four cases carry today. This
  is a quality improvement, not an outage.
- **Not that the other two seats are qualified.** They score 6/6 on four cases of
  one family in one standard. The roster as a whole is still qualified against
  the *old* question; a full re-qualification against the reading task remains
  outstanding and is larger than this task.
- **No gold label moves and no case expectation is edited**, here or anywhere
  downstream of it.

## 7. Related

- `reports/compliance/LDOC_FAMILY_LIVE_REPLAY.md` — the evidence
- `reports/compliance/READING_JUDGMENT_V1.md` — the architecture and the
  hallucinated-id observation
- `reports/compliance/THINKING_CONFOUND_V1.md` — why reasoning is not a criterion
- `scripts/replay_compliance_reading_family.py` — the harness
- `config/compliance/council.yaml` — the roster, and the rejected-candidate log
  from the 2026-09-06 sweep (do not re-add a rejected model without a fresh
  sweep *against the reading task*)
