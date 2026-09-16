# Reading-seat research — findings, and what is still open

**Status:** pivot point. The substrate (P0–P5) is built and verified; the model
layer is measured but **not settled**. This document is the standalone record of
what was measured, what it means, what was decided provisionally, and what
research the model pieces still need.

**Scope.** Choosing the model that reads a bilateral regulatory/operator
neighbourhood and answers an analyst in prose. Not the council (three models
voting on a JSON verdict over a pre-analysed packet — a different question, a
different packet, chosen separately in TASK_COMPLIANCE_REASONING_V6 D0-M).

**Hardware.** One Apple M4 Pro, 64 GB unified memory. Ollama 0.34.0,
`llama-server` Metal backend. Everything below is measured on this machine, on
this build, with the numbers the runner itself reported.

---

## 1. The hard constraint that reframes everything

**The compliance module ships inside the running product.** It is a module in
Portal 5, not a tool you stop the product to use. A seat must therefore run
co-resident with the full Docker stack (22 containers, ~6 GB of containers plus
the Docker VM) and the host-native MLX retrieval server.

This was learned the hard way. The first live probe produced nothing for twenty
minutes. Cause, measured:

| | |
| --- | --- |
| `granite4.1:30b-ctx64k` resident at 32k context | **36.4 GB** |
| swap used, stack up, model loaded | **50.6 GB of 51.2 GB** |
| free memory | **16%** |

With the stack down, free memory went to 85% and the same call completed. The
initial instinct — "take the stack down for the model work" — was a workaround,
and the numbers it produced were numbers nobody can have in production. All
measurements in §4 onward are **stack up**.

**Consequence:** `granite4.1:30b` is excluded on footprint, before any question
of reading quality. Footprint is a first-class seat criterion, listed before
quality, because it is a gate rather than a preference.

---

## 2. Method

Same corpus, same requirement (`CIP-007-6 R2 Part 2.2`), same three questions,
transcripts retained. **No rubric and no score.** A rubric that could capture
"did it understand the material" would make the reading model unnecessary, and
selecting on a number is the prescriptive move at one remove. What the harness
produces is transcripts, citation-resolution facts and latency; the judgement is
written by hand from reading them.

The three questions, each answerable only from a different part of the
neighbourhood:

1. *What is this requirement actually for? What outcome does it exist to
   achieve, and what does it deliberately leave to us?*
2. *Our own procedure evaluates security patches every thirty calendar days, not
   thirty-five. Are we stricter than we need to be, and does that matter?*
3. *What would an auditor ask us to produce for this Part, and what in our own
   material would satisfy them? Be specific about what is missing.*

Harness: `scripts/compliance_reading_seat_probe.py`.
Transcripts: `reports/compliance/seat_probe/*.json`.

### 2.1 The discriminator

Question 2 has a checkable answer that requires actually reading the operator's
material rather than summarising it.

* The standard, `CIP-007-6 R2 Part 2.2`: *"At least once every 35 calendar
  days, evaluate security patches for applicability…"*
* The operator's **procedure**, `LSPG Security Patch Management Procedure
  §3.3.1`: *"At least once every **thirty-five (35)** calendar days, SMEs in
  conjunction with Foxguard, shall review all approved sources…"*
* The operator's **note**, recorded separately: *"We evaluate patches every 30
  days, not the 35 the Part allows…"*

So the operator's own written procedure **does not say thirty**. A seat that
reads the packet notices the conflict between the procedure and the note. A seat
that paraphrases the note asserts something false about the operator's own
posture — with a correct-looking citation attached. That is precisely the
failure mode this module exists to stop, and it is why Q2 decides.

---

## 3. Throughput: this is a prefill problem, and prefill is a sparse-mixture problem

12,000-token prompt, 32k window, stack down (throughput only — not a
co-residency test):

| seat | architecture | prefill tok/s | generation tok/s | wall |
| --- | --- | --- | --- | --- |
| `glm-4.7-flash:Q4_K_M-ctx64k` | **MoE** | **244** | 34.2 | 58.1 s |
| `mistral-small3.2:24b` | dense | 126 | 28.5 | 110.5 s |
| `hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M` | dense | 112 | 22.6 | 120.3 s |
| `granite4.1:30b` | hybrid Mamba | 95 | 21.8 | 135.1 s |

What this workload costs is **prefill over a long neighbourhood**, and prefill
compute scales with *active* parameters, not total. The two slowest seats are
the two non-MoE ones. A sparse mixture with ~3B active reads a long document for
a fraction of what a dense 24–27B pays.

Generation slows as the KV cache deepens: Qwen3.8 generated at 22.6 tok/s on a
12k prompt and **10.8 tok/s** at 29k. Both halves of the cost grow with the
packet.

---

## 4. The two findings that changed the design more than any seat choice

### 4.1 Prompt order — 268× less prefill per follow-up

The prompt originally put the analyst's question *before* the material, so the
first differing token of every turn sat at position ~20 and the runner
re-prefilled all 27k tokens. Reordered to **material first, question last**:

| turn | wall | prompt evaluation |
| --- | --- | --- |
| 1 — cold | 263.9 s | 27,176 tok in **214.7 s** |
| 2 — same question | 40.5 s | 27,176 tok in **0.1 s** |
| 3 — new question, same material | 30.4 s | 27,181 tok in **0.8 s** |

Confirmed across the four-seat probe: Qwen 407 s → 123 s → 153 s; granite 459 s
→ 39 s; mistral 324 s → 18 s; glm 276 s → 30 s. A session's first exchange costs
minutes; every one after costs seconds, because the slot cache holds the
byte-identical prefix. Free, and larger than any model swap buys. A unit test
now asserts the ordering and that two different questions share a >90%
byte-identical prefix.

### 4.2 The packet, not the parameter count

55% of the full `CIP-007-6 R2 Part 2.2` packet is ballast for most questions:

| component | sections | est. tokens | share |
| --- | --- | --- | --- |
| implementation_plan | 116 | 9,822 | **32.8%** |
| compliance_and_evidence_retention | 49 | 6,735 | **22.5%** |
| linked_internal | 4 | 3,849 | 12.9% |
| technical_basis | 11 | 3,570 | 11.9% |
| background | 10 | 1,565 | 5.2% |
| vsl | 13 | 1,250 | 4.2% |
| applicability | 6 | 972 | 3.3% |
| version_history | 14 | 781 | 2.6% |
| **requirement** | 6 | 600 | **2.0%** |
| glossary | 5 | 454 | 1.5% |
| rationale, measures, effective_dates | 5 | 306 | 1.0% |
| **total** | **239** | **29,904** | |

Question-scoped profiles (`compliance_context(profile=…)`):

| profile | sections | est. tokens | real tokens (measured) |
| --- | --- | --- | --- |
| `full` | 239 | 29,904 | 26,633–30,670 |
| `intent` | 35 | 6,467 | 4,365–4,729 |
| `conformance` | 22 | 6,013 | 4,591–4,858 |
| `audit` | 79 | 13,544 | — |
| `timeline` | 138 | 11,231 | — |

**Nothing infers a profile from the question.** The caller names it, `full` is
the default, and everything a profile leaves out is listed in `omitted` and
rendered to the reader.

---

## 5. Results

### 5.1 Full packet (~27k–31k real tokens), stack down

| seat | prompt tok | Q1 | Q2 | Q3 | Q2 correct? |
| --- | --- | --- | --- | --- | --- |
| Qwen3.8-27B | 29,544 | 407 s / 9 cites | 123 s / 7 | 153 s / 7 | **yes** |
| granite4.1:30b | 26,633 | 459 s / 6 | 39 s / 3 | 168 s / 3 | no |
| mistral-small3.2:24b | 30,670 | 324 s / **0** | 18 s / 3 | 55 s / 3 | no |
| glm-4.7-flash | 27,176 | 276 s / 7 | 30 s / 4 | 52 s / 2 | no |

**Zero unresolvable citations in twelve answers.** No seat fabricated an id, so
citation fidelity did not separate them — the reading had to.

**Only Qwen3.8-27B passed the discriminator.** It quoted §3.3.1 verbatim and
surfaced the procedure-versus-note conflict. The other three asserted the
procedure says thirty. granite additionally called "at least once every 35 days"
a *minimum interval* (it is a maximum interval / minimum frequency) and reasoned
to the right conclusion anyway.

Best single observation of the whole probe came from glm on Q3: the corpus holds
the patch-evaluation **process** but not the **record** an auditor would ask for.

### 5.2 Focused packets (~4.4k–4.9k real tokens), stack up

| seat | size | profile | Q1 | Q2 | Q3 | Q2 correct? |
| --- | --- | --- | --- | --- | --- | --- |
| Qwen3.8-27B | 18.8 GB | conformance | 113 s / 4 | **55 s** / 3 | 113 s / 5 | **yes** |
| glm-4.7-flash | ~19 GB | conformance | 28 s / 2 | **14 s** / 3 | 15 s / 4 | **yes** |
| qwen3.5-abliterated 9B | **6.6 GB** | conformance | 49 s / 2 | **23 s** / 3 | 48 s / 4 | **yes** |
| granite4.1:8b | 5.3 GB | conformance | 44 s / 0 | 12 s / 2 | 36 s / 4 | no |
| qwen3-vl:8b | 6.1 GB | conformance | 36 s / 1 | 11 s / 2 | 43 s / 2 | no |
| Foundation-Sec-8B-Reasoning Q8 | 8.5 GB | conformance | 67 s / 2 | 7 s / 0 | 72 s / 6 | no — backwards |

**glm-4.7-flash got Q2 wrong on the 30k packet and right on the 6k packet.** The
sentence that decides the question is one of 239 sections in the first case and
one of 22 in the second. Nothing about the model changed.

**A 6.6 GB 9B model passes the discriminator**, quoting §3.3.1 verbatim, in 23 s,
co-resident with the whole stack.

`Foundation-Sec-8B-Reasoning` is the only model in the catalog trained for this
domain and was the **worst** seat tested: it fabricated a citation (the only
unresolvable id in the entire study), hit the 1,600-token answer cap twice, and
stated the operator's procedure says thirty when it says thirty-five. Domain
pre-training did not substitute for reading the packet.

### 5.3 End to end, in the product

`compliance_ask(..., profile="conformance")` through the MCP tool with all 22
containers running: **35.4 s, 5 citations, 0 unresolvable, answer stored and
projected, 56% memory free.**

---

## 6. Provisional decisions

Recorded in `config/compliance/council.yaml`. `_reading_seat(profile)` picks the
full-packet seat when no profile is named, the fast seat otherwise.

| role | seat | footprint | basis |
| --- | --- | --- | --- |
| `reading_seat` (focused profiles) | `glm-4.7-flash:Q4_K_M-ctx64k` | ~19 GB | fastest measured (244 tok/s prefill), correct on focused packets, 14–28 s/exchange |
| `reading_seat_full_packet` | `hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M-ctx32k` | 18.8 GB | the only seat measured correct at 30k |
| `reading_seat_minimal` | `huihui_ai/qwen3.5-abliterated:9b-ctx64k` | 6.6 GB | correct on the discriminator at 1/3 the memory |

**These are provisional.** §8 says why.

---

## 7. Settled facts (re-usable, measured here)

1. **Request-time `options.num_ctx` is honoured** on a direct Ollama
   `/api/chat`. A request *lowered* `granite4.1:30b-ctx64k` to 32,768, confirmed
   in `/api/ps`. No context tag needs baking for this call site. (The
   "request-time num_ctx is ignored" rule belongs to the pipeline/router path.)
2. **Characters per token on this corpus: 2.16–2.60**, not the usual ~4. Dense
   regulatory prose plus a 29-character `section_id` per passage that costs ~12
   tokens. The naive 4.0 under-counts by up to 1.9×, and under-counting sizes
   the context window **too small** — silent truncation, which is the top-k
   keyhole returning. The constant is 2.1 (errs high, the safe direction) and
   every call now checks its estimate against the runner's real
   `prompt_eval_count`.
3. **Reasoning must be OFF for this call site.** Measured on Qwen3.8-27B, same
   packet, one variable:

   | effort | wall | thinking | answer | citations |
   | --- | --- | --- | --- | --- |
   | `false` | 432.0 s | 0 chars | **4,756 chars** | 7 |
   | `low` | 449.8 s | 6,382 chars | **empty** | 0 |
   | `medium` | 148.5 s | 6,258 chars | **empty** | 0 |

   Not "slower for the same answer" — **no answer**. The trace consumed the
   whole `num_predict` budget. An empty answer is now reported as a failed
   reading rather than a terse one.
4. **Window sizing rounds to the next 4k, not the next power of two.** 33.5k
   rounding to 65,536 is tens of gigabytes of needless KV on a 27B.

---

## 8. What is still open — the research agenda

The seat choices in §6 rest on **three questions, one requirement, one
standard**. That is enough to exclude the clearly-worse seats and to establish
the design facts in §7. It is not enough to pick a production reader.

### 8.1 The sample is too small to generalise

One requirement (`CIP-007-6 R2 Part 2.2`), one discriminator. Q2 is a *quantity*
discrimination; a seat that is good at quantities may be poor at scope,
applicability or cross-reference. **Needed:** the same protocol across several
requirement shapes — a prose requirement (CIP-003 R1's policy-topic list), an
applicability question (CIP-002 categorisation), an attachment-shaped one
(CIP-003 Attachment 1), and a cross-reference chain (CIP-010 R1 → CIP-007 R2).
P10's family scale-up produces the corpus for this.

### 8.2 One run per cell, temperature 0, no repeats

Every number in §5 is a single sample. Temperature is 0, so the *model* is
deterministic, but slot-cache state and packet assembly order are not
necessarily identical between runs. **Needed:** three runs per cell to
distinguish a seat that reads from a seat that got lucky — particularly for
qwen3.5-9B, whose single pass is the entire basis for the minimal-footprint
recommendation.

### 8.3 The MoE hypothesis is supported but under-tested

§3 shows the two slowest seats are the two non-MoE ones, and the fastest by 2×
is the only MoE in that group. But only **one** MoE was measured. The catalog
holds several A3B-class candidates that were never run:
`hf.co/unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q4_K_XL-ctx32k`,
`qwen3-coder:30b-a3b-q4_K_M-ctx256k`, `gemma4:26b-a4b-it-q4_K_M`,
`huihui_ai/tongyi-deepresearch-abliterated:latest-ctx64k` (long-document tuned).
They are listed as `MOE_SEATS` in the probe script and are a cheap next pass.

### 8.4 The out-of-catalog candidate worth a real evaluation

**Qwen3-Next-80B-A3B-class**: ~80B total / ~3B active, hybrid linear attention,
native long context. At Q4 that is ~45 GB — which fits this machine *with the
stack down*, and the footprint is proven here (`portal5/qwen3-coder-next` is
51.7 GB and runs). It is the one model that would plausibly beat everything
local on this task: far more knowledge than a 30B at 30B-class prefill cost.

**Open question, and it is the important one:** ~45 GB does **not** obviously
co-exist with 22 containers on 64 GB, so it may fail §1's hard constraint.
Whether it fits depends on whether the focused-packet result holds — a 6k packet
needs a far smaller KV cache than 32k. **Needed:** a footprint measurement at
8k–16k context with the stack up, before any quality evaluation. If it does not
fit, it is out regardless of how well it reads.

Ruled out without testing: **GLM-4.7-Air** (~106B-A12B, won't fit at Q4 beside
anything), **gpt-oss-120b** (117B-A5.1B MXFP4 ~63 GB, same), **Llama-4-Scout**
(already recorded as a hardware-ceiling OOM on this machine).

### 8.5 Profile selection is unsolved, and it is a correctness problem

On the `intent` profile — which deliberately excludes the operator's own
sections — **all four small seats answered Q2 confidently from an operator note
alone, and none said it lacked the procedure.** The note misstates the
procedure, so all four were confidently wrong about the operator's own posture.

The omission block was made the loudest thing in the packet in response, naming
what each missing component would have answered. **That mitigation is unverified
— the small seats were not re-run against it.** Needed: re-run the `intent`
probe and count how many now say "I would need your procedure".

The deeper question is unresolved on purpose. *Something* must choose the
profile. Today the caller does. Inferring it from the question would be a
classifier deciding in advance what material may matter, which is the exact
prescriptive move §0 of the task identifies — but leaving it to the caller means
a badly-chosen profile silently narrows the evidence. The honest middle may be
for the reader to *ask* for a component by name and for the assembly to be
re-run, making profile choice part of the conversation rather than a
pre-commitment. Not built, not designed, flagged.

### 8.6 Latency has a floor we have not tested against real use

Cold exchange on a focused packet: 28–113 s. Warm: 14–55 s. Only the *first*
exchange of a session pays prefill, so a warmed seat is interactive — but
nothing warms it today, and `keep_alive` is 30 minutes, so the second question
of the morning pays full price. **Needed:** a warm-on-session-start path, and a
decision about whether the seat stays resident (19 GB held permanently against
the stack) or is loaded per session.

### 8.7 The abliterated variant is unexamined

`huihui_ai/qwen3.5-abliterated:9b` is the minimal-footprint recommendation and is
an uncensored variant. It read correctly here. Whether an abliterated model is
the right thing in a compliance-evidence path — where the failure mode of
interest is confident assertion rather than refusal — has not been thought
through. A non-abliterated Qwen3.5-9B is not in the catalog.

### 8.8 Quantity checking cannot be mechanised the way it was attempted

An earlier pass built a per-citation quantity check that reproduced a hand
finding and looked convincing. Across the wider transcript set it proved
unreliable **in both directions on exactly the prose that matters** — an answer
that correctly contrasts two numbers:

* *false positive*: *"you are compressing the evaluation window by five days
  compared to the standard's 35-day maximum"* — correct arithmetic (35 − 30),
  flagged because "five days" is absent from the cited note;
* *false negative*: granite4.1:8b wrote *"the operator's procedure evaluates
  every 30 calendar days"* — it says thirty-five — and cited nothing within
  range, so nothing was flagged.

Attribution is positional and prose is not. The field was narrowed to
`quantity_review_pointers`, carries the sentence it points at, and is documented
as a pointer for a human. **Open:** whether a semantic check is possible at all
without becoming the adjudicator the task forbids. Current position: it is not,
and citation *resolution* (which is reliable, and which caught the one
fabricated id) is the only mechanical check that should exist.

---

## 9. Bugs this research found in our own code

Every one of these was found by reading live output, not by a test, and each is
now covered by one.

| bug | consequence | status |
| --- | --- | --- |
| `int(x or -1)` read `char_start` **0** as −1 | the **first section of every document** was silently excluded from the projection — 68 internal, 6 regulatory | fixed |
| `CHARS_PER_TOKEN = 4` | under-counted by 1.9×, sizing the context window too small — silent truncation | fixed, checked per call against the runner |
| question before material in the prompt | full re-prefill every turn; 214.7 s instead of 0.8 s | fixed |
| Unicode dashes in citations | granite cited six sections and scored **zero**; a well-grounded answer reported as ungrounded | fixed, six dash characters covered |
| `"thirty-five calendar days"` matched as **"five calendar days"** | a checker reading 35 as 5 | fixed, compound vocabulary |
| `"thirty"` absent from the number vocabulary | the discriminator's own quantity was invisible to the checker | fixed |
| quantity checked against the union of all cited text | a number borrowed from one document and pinned to another passed | narrowed to a review pointer (§8.8) |
| `store_capture` deleted by module `EXTRACTOR`, inserted by `captured.extractor` | a Glossary re-capture would leave stale units beside fresh | fixed |
| a unit test wrote to the **operator's live compliance store** | `Repository()` defaults to production; a pytest tmp_path glossary page landed as a real revision | fixed at root; conftest redirects the bound default |
| empty answer returned as an answer | a reasoning-exhausted call looked like a terse model | reported as `failed` with the budget numbers |

---

## 10. Recommendation at the pivot

1. **Keep the substrate.** P0–P5 are measured, verified and independent of the
   seat question. Nothing in this document argues for changing them.
2. **Treat §6 as provisional wiring, not a decision.** It is good enough to
   continue P7–P10 against, and every phase after this one exercises the reader
   on more material, which is exactly the evidence §8.1 asks for.
3. **Run the cheap research first** — §8.2 (repeats), §8.3 (the other local
   MoEs), §8.5 (re-run `intent` against the louder omission block). All three
   are hours, not days, and use the harness that exists.
4. **Decide §8.4 deliberately.** A ~45 GB model is a real commitment on a 64 GB
   machine that must also run the product. Measure the footprint at 8k–16k
   context with the stack up *before* evaluating its reading.
5. **Do not fold the seat choice into the product's defaults until §8.1 and
   §8.2 are done.** One requirement and one run per cell is not a basis for a
   production reader, and saying otherwise would be the kind of green board this
   module exists to stop producing.
