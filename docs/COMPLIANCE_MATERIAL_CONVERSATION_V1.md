# A4 — the conversation reaches the material that works

**Date:** 2026-09-19 · **Task:** TASK_COMPLIANCE_DELIVER_AND_SETTLE_ENGINE_V1 §A4 · **Base:** post-A3

## A4.1 — one tool returns the proven material

`compliance_context` gained `mode="material"`: it calls the exact
`reading_material.render()` primitive the §P1 proof used — no second renderer,
no sibling tool. `mode="index"` stays the default; `mode="packet"` at
`budget_tokens=60000` stays the explicit legacy batch path. Verified live
through the restarted compliance MCP (`:8937`): CIP-007-6 R2 Part 2.2 renders
80,249 chars (fixed body 57,906; 14 regulatory + 4 operator + 1 note).

Why `compliance_context` and not a sibling: the workspace already had nineteen
tools and the module has twice grown duplicate extractions of the same thing.
One entry point with three renderings keeps the model's choice among "ids",
"the material", and "the batch packet" a mode flag rather than a new name to
learn.

## A4.2 — the prompt says read it, don't hunt for it

Prompt `workspace-reading-v2.2` (artifact `config/compliance/workspace_reading_prompt.md`
+ the serving inline copy, edited together): compliance_context is now THE
MATERIAL TOOL — *"call the material tool ONCE with that requirement's ref and
answer from what it returns. It is the whole neighbourhood — the standard and
the operator's own documents — and nothing is missing from it. Do not search."*
The latitude requirement, the both-sides rule and cite-section-ids are kept
unchanged — gemma4 honoured them at 6/6 under §P1.

## A4.3 — the conversation gets the cache: PROVEN, two ways

**On the real path** (Open WebUI-shaped thread → pipeline :9099 → Ollama): the
five-turn conversation's turn-1 tool loop shows the append shape in the per-hop
prompt tokens — 2,798 → 10,054 → 10,152 → 10,231 → 12,906 — each hop the
previous thread plus the new tool result, exactly the shape §P4.1 measured
Ollama caching.

**On the runner, with the real material** (`reports/compliance/census/a4_append_cache_probe.json`):
the v2.3 system prompt + the real `reading_material.render` output for R2, on
Ollama 0.34.2 native `/api/chat` (which reports `prompt_eval_duration` and,
newly visible, `prompt_eval_cached_count`):

| call | prompt tokens | cached | prefill |
|---|---:|---:|---:|
| 1: system + question | 1,049 | 0 | 1.43 s |
| 2: + material appended | 26,395 | 0 | 59.21 s |
| 3: + answer + follow-up (next turn) | 26,458 | **26,395** | **0.376 s** |

Call 3's prefill is **×157 cheaper** than call 2's full price for the same
prefix: the append-only conversation shape gets the cache; independent
requests that merely share a prefix (call 2's cold arrival, and the sweep's
shape) do not. §0.2's correction, reconfirmed on the production runner with
production material: **the conversation already has the cache; the sweep does
not** — and the conversation earns it by append, not by sharing.

## A4.4 — the five turns, judged by reading

Driver: `WorkspaceThread` from `scripts/compliance_acceptance.py` — the
deployed workspace path (real router loop, real tool dispatch, per-hop usage).
Seat: gemma4 (the A3 binding). Five turns: gaps in R2 · latitude on 2.3 · the
30-day question · did you read our procedure or just the standard · what
haven't you read.

### Run 1 on v2.2 — FAIL

Receipt: `reports/compliance/census/a4_five_turn_v2_2_FAIL.json`. Turn 1 called
the material tool (5 hops, real ids, the module's own Senior-Manager
COMPLIANCE_CONFLICT surfaced with both-sides citations). **Turns 2–5 fabricated.**
With no tool calls and the material no longer in the thread (the pipeline is
stateless — only user/assistant messages replay across turns), the seat wrote
19 citations across 3 invented ids (`csection-c36c38b8842c8intac` ×9,
`isection-8822f1a2b3c4d5e6f7g8` ×5, `isection-9922a1b2c3d4e5f6` ×5 — none
resolve), attributed the 30-day cycle to a "Section 3.4" that does not exist,
and restated Part 2.2's direction wrongly ("within at least 35 days"). Root
cause: v2.2 had no rule for the follow-up-turn shape.

### Prompt v2.3 — the fix

One structural rule added (artifact + inline copy, version bumped):
*"Follow-up turns: if the question moves to a requirement or Part whose
material is not already in THIS conversation, call the material tool once for
THAT ref before answering. NEVER write a section id from memory."*

### Run 2 on v2.3 — PASS

Receipt: `reports/compliance/census/a4_five_turn_conversation.json`.

* **Turn 1 (gaps)** — material tool called first; honest posture ("cannot
  definitively state gaps; the linked operator documents are marked
  `proposed`"), then a per-Part potential-gap table with severity. Correct Part
  text throughout.
* **Turn 2 (latitude on 2.3)** — **the case the batch instrument failed on all
  three seats is now caught**: the turn re-called the material tool (1 hop of
  `compliance_context` + 2 of `compliance_read`) and answered "You are NOT
  using all the latitude — the standard's 'or' is restated as 'and' in your
  policy §3.4.2.1", citing the operator policy id (resolves, internal).
* **Turn 3 (30-day)** — correct direction (30 < 35, stricter, stated as fact),
  both sides cited (both ids resolve).
* **Turn 4 (read_check)** — names exactly which sections it read, with ids,
  from THIS conversation.
* **Turn 5 (unread)** — a faithful unread inventory consistent with turns 1–4;
  offers to go further.

Citation resolution across the transcript: **26 of 29 resolve** (16
regulatory + 7 internal; the 3 unresolved are one recurring dropped-character
typo of `csection-c0cd08b61c308b0e6403` — an id that WAS read this
conversation and appears correctly once, not an invention). Turn wall times
45.8 / 30.1 / 10.1 / 13.2 / 10.2 s — every turn well inside the product's
one-minute-class bar for turns 3–5 and inside budget for the tool-carrying
turns.

**PASS, with the caveat on record:** the seat still misspells a long id when
reproducing it from thread memory in a citation list; the v2.3 rule stopped
that from inventing ids, but id *spelling* from memory remains imperfect. A
checker-side citation-resolution warning (it exists in the module's
verification path) is the backstop; a prompt line cannot fully fix typing.

## What A4 changes about the product

* The proof's primitive is reachable in conversation, by the same name the
  proof used, and the conversation uses it (`compliance_context` calls visible
  in the router's tool counters on the turns that needed material).
* The one-message shape and the multi-turn shape have different failure modes,
  and both now have measured evidence and a rule each: turn-one hunting
  (v2.1's stop rule) and follow-up fabrication (v2.3's re-read rule).
* The append cache — ×157 prefill on the probe, ×8.6 hop growth on the live
  path — is the property the conversation already gets and the sweep still
  does not. That asymmetry is the running context for every Part B verdict.
