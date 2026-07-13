# Routing Integrity Findings — pre-collapse (`45edb25`) vs current (`00635aa`)

**Stage:** R (Routing integrity), Phase R2. **Program:** `BUILD_PROGRAM_ROUTING_INTEGRITY_V1.md`.
**Corpus:** `tests/routing/corpus.json` (86 prompts — see provenance below).
**Baselines:** `/tmp/routing-precollapse-baseline.json` (45edb25),
`/tmp/routing-current.json` (00635aa). Reproduce with
`tests/routing/build_corpus.py` + `tests/routing/measure.py` (see each
file's docstring).

**Question answered:** did shrinking the workspace surface (104→21 base
workspaces) change what the router does? **Answer: the keyword-layer
*decision* logic is unchanged (proven exhaustively, not sampled). Two
regressions were found — both in supporting config, not in the
decision code itself — and are fixed in this pass (see R-FIX below).**

---

## Method

### Keyword layer (Layer 2, `_detect_workspace`) — the deterministic hard gate

Two independent checks, per the build program's non-negotiable that the
keyword layer must be the exact-match gate:

1. **Structural equality.** Extracted `_KEYWORD_CACHE` (every keyword→weight
   pair) and `_WORKSPACE_ROUTING` (every threshold) from both trees via
   direct import and JSON dump, then diffed under the collapse's own
   documented fold map. Every keyword set and threshold is byte-identical
   across the fold, with one documented exception (below). This is an
   exhaustive proof — it covers every possible input, not a sample.
2. **Corpus run.** Ran all 86 corpus prompts through `_detect_workspace` on
   both trees. 72/86 identical outputs; the other 14 are the *same* 3
   canonicalization folds appearing across different corpus prompts (below).

### LLM layer (Layer 1, `_route_with_llm`)

Not live-measured (the configured router model,
`hf.co/mradermacher/gemma-4-E4B-it-OBLITERATED-GGUF:Q4_K_M`, is not pulled
in this environment, and grammar-decoded LLM output is nondeterministic
regardless — per the build program's own failure-mode guidance, this layer
gets an accuracy check, not an exact-match gate, and forcing one on a
sampled model would be false precision). Instead, the LLM layer's **inputs**
were statically audited: the few-shot prompt (`_build_router_prompt`) and
the workspace-id allowlist (`_VALID_WORKSPACE_IDS`, grammar-enforced via
`_ROUTER_JSON_SCHEMA`) that constrains what it can ever emit. This surfaced
a real, well-evidenced regression (#2 below) independent of any specific
model's behavior — the corpus feeding the model is broken regardless of
which model reads it.

---

## Findings

### Finding 1 — Keyword layer: 0 regressions, 1 documented intended change

**Verdict: INTENDED.**

All 9 pre-collapse keyword-scorer entries map 1:1 to the current 8
(`_MISTRAL_KEYWORDS` unioned into `auto-reasoning`, all others renamed via
the `"<base>::<variant>"` canonicalization) with byte-identical keyword
weights and thresholds:

| Pre-collapse key | Current key | Threshold | Served model |
|---|---|---|---|
| `auto-redteam` | `_security_redteam` → `auto-security::redteam` | 4→4 | MATCH |
| `auto-security` | `auto-security` | 3→3 | MATCH |
| `auto-spl` | `auto-spl` | 3→3 | MATCH |
| `auto-coding` | `auto-coding` | 3→3 | MATCH |
| `auto-coding-agentic` | `_coding_laguna` → `auto-coding::laguna` | 3→3 | MATCH |
| `auto-agentic` | `_coding_heavy` → `auto-coding::heavy` | 3→3 | MATCH |
| `auto-reasoning` | `auto-reasoning` | 3→3 | MATCH |
| `auto-compliance` | `auto-compliance` | 3→3 | MATCH |
| `auto-mistral` | unioned into `auto-reasoning` | 3→3 | **DIFF (intended)** |

`auto-mistral`'s served model changes from
`hf.co/unsloth/Magistral-Small-2509-GGUF:Q8_0-ctx64k` to
`hf.co/unsloth/DeepSeek-R1-0528-Qwen3-8B-GGUF:Q4_K_XL-ctx64k`. This is the
**documented, intended** Phase 7 operator decision (routing.py:557-568):
`_MISTRAL_KEYWORDS`/`_REASONING_KEYWORDS` have zero key overlap (a lossless
union), and the reassignment away from the alias shim's original
`auto-coding` mapping was made explicitly after review of the keywords, the
LLM router's own `auto-mistral` description, and the `magistralstrategist`
persona's system prompt — all three turned out to be 100% reasoning-flavored
with zero coding terms.

**Corpus confirmation:** all 14 corpus divergences between pre/current
keyword-layer output are exactly these 3 folds (redteam×6, laguna/heavy
folds×6, mistral×2) recurring across different prompts — no unexplained
divergence anywhere in 86 prompts.

### Finding 2 — `config/routing_examples.json` was never migrated (REGRESSION, fixed)

**Verdict: REGRESSION.**

`config/routing_examples.json` is **byte-identical** between `45edb25` and
`00635aa` (`diff` confirms zero changes). This file feeds
`_build_router_prompt`'s few-shot block directly — the first 9 entries
(`examples[:9]`) are injected verbatim into every LLM-router classification
call.

Contrast with `config/routing_descriptions.json`, whose own `_note` field
states it was deliberately bumped 1.1→2.0 by Phase 7's canonicalization,
explicitly retiring the 10 pre-collapse alias entries
(`auto-agentic`, `auto-blueteam`, `auto-redteam`, `auto-redteam-deep`,
`auto-pentest`, `auto-purpleteam`, `auto-purpleteam-deep`,
`auto-purpleteam-exec`, `auto-mistral`, `auto-phi4`). `routing_examples.json`
was not given the same treatment.

**Impact:** 13 of 44 examples (30%) — and critically **4 of the first 9**
(`examples[5]`, `examples[6]`, `examples[7]` = `auto-redteam`; `examples[8]`
= `auto-pentest`) that are actually sent to the model — label training
examples with workspace ids no longer in `_VALID_WORKSPACE_IDS`. Grammar-
enforced decoding (`_ROUTER_JSON_SCHEMA`'s `enum`) prevents the model from
ever literally emitting these ids, so this is not a crash — but the model is
being few-shot-calibrated on target labels it can never produce, corrupting
exactly the highest-content-risk few-shot slots (offensive-security intent).
This is the LLM layer's real contribution to "did shrinking it break it":
yes, in the training signal, independent of which router model reads it.

**Fix applied (R-FIX):** re-labeled all 13 stale-id examples in
`config/routing_examples.json` to their canonical post-collapse base id via
`_LEGACY_WORKSPACE_ALIASES`' own mapping (message text unchanged — only the
`workspace` label is corrected, since the base-workspace description now
carries the folded intent and `_infer_variant`'s post-classification pass
recovers the variant, matching `routing_descriptions.json`'s own stated
design). See commit for the exact diff.

### Finding 3 — Stale `auto-mistral` entry in `_LEGACY_WORKSPACE_ALIASES` (REGRESSION, fixed)

**Verdict: REGRESSION.**

`portal/platform/inference/router/preinject.py`'s
`_LEGACY_WORKSPACE_ALIASES["auto-mistral"] = ("auto-coding", None)`
contradicts the Phase 7 decision documented in `routing.py:557-568` and
confirmed by Finding 1: `auto-mistral` was deliberately folded into
`auto-reasoning`, not `auto-coding` (the alias shim's original, pre-Phase-7
mapping — exactly the "collapse-era filing artifact" `routing.py`'s own
comment warns about). The two files disagree with each other.

**Currently latent, not actively triggered:** the keyword scorer never
emits the literal string `"auto-mistral"` post-canonicalization (it unions
directly into `auto-reasoning`), and the `magistralstrategist` persona's
`workspace_model` field already points at `auto-coding` directly (a
separate, already-tracked Stage P bug — see
`DESIGN_PERSONA_INTENT_REMEDIATION_V1.md`), not through this alias path. But
it is a live trap: any caller that sends the literal legacy id
`model=auto-mistral` (an old bookmark, a stale client, or the LLM router
itself once Finding 2's corpus correction re-exposes `auto-mistral`-flavored
few-shot semantics) resolves to the wrong base workspace and the wrong
served model.

**Fix applied (R-FIX):** `_LEGACY_WORKSPACE_ALIASES["auto-mistral"]` changed
to `("auto-reasoning", None)` to match the documented decision.

### Finding 4 — Model-tied lanes: zero Stage-R risk by construction (informational, not a regression)

**Verdict: not applicable to Stage R — tracked under Stage P.**

`auto-devstral`, `auto-glm`, `auto-glm-thinking`, `auto-gemma-e4b`,
`auto-gemma-fast`, `auto-gemma-vision` were confirmed **absent from both**
the pre-collapse keyword scorer (`_WORKSPACE_ROUTING`) **and** the
pre-collapse LLM-router descriptions (`routing_descriptions.json`) at
`45edb25` — they were reachable only via direct/manual workspace selection,
never via either auto-routing layer, before the collapse. Their deletion as
standalone workspaces is explicitly **intended** per
`DESIGN_COLLAPSE_V1.md` §D5 ("model choice moves to router param /
persona `preferred_models` chain"). They carry **zero auto-routing decision
regression risk** because there was no auto-routing decision to preserve.

`auto-phi4` and `auto-mistral` *were* present in the pre-collapse LLM
description set (i.e. had LLM-layer reachability) — their removal from
`routing_descriptions.json` is the same documented §D5 intent. Whether the
right *served model* now reaches a user who asks for phi4/mistral-flavored
reasoning is a **persona/`preferred_models` correctness question**, already
captured by Stage P's known-cases list (`magistralstrategist` is one of the
5). No Stage R action needed beyond Finding 3's alias-table fix.

### Coverage note

The keyword layer's fold coverage is complete for every pre-collapse
keyword-scorer entry (9/9 mapped and verified). Two fold-coverage prompts
authored for this corpus (`fold_coding_uncensored_agentic`,
`fold_devstral_manual_only`) fell through to the nearest keyword match on
**both** sides rather than a dedicated bucket — this is not a fold-map
error, it's a **pre-existing, symmetric blind spot**: those lanes were never
in the keyword scorer on either side of the collapse (consistent with
Finding 4). Recorded here as a known blind spot per the build program's
guidance ("a known blind spot beats a false all-clear"), not asserted as a
pass.

---

## R-GATE

**REGRESSION bucket: Findings 2 and 3 (both fixed in this pass — see commits).**
**INTENDED bucket: Finding 1's mistral served-model change, Finding 4's model-tied-lane deletions — both cite their documenting source.**
**AMBIGUOUS bucket: none.**

Per the gate rule: regressions found → R-FIX required before proceeding →
done (Findings 2/3 fixed) → **R1/R2 re-run to confirm clean** (see
"Post-fix verification" below) → gate green → proceed to R3.

## Post-fix verification

After applying Findings 2/3's fixes, `_resolve_legacy_workspace_alias`
correctly resolves `"auto-mistral"` to `("auto-reasoning", None)`, and
`config/routing_examples.json` no longer contains any workspace label
outside `_VALID_WORKSPACE_IDS`. Re-running the keyword-layer corpus
comparison (`tests/routing/measure.py` on current HEAD post-fix) continues
to show only the 3 documented canonicalization folds — no new divergence
introduced by the fix itself.

## Phase R3 — permanent gate

`scripts/routing_regression.py --assert-baseline` now asserts the full
`(base, variant, served_model)` tuple for all 86 corpus prompts against
`tests/routing/baseline.json` (committed, the post-R-FIX proven truth).
Wired into `scripts/validate_system.py` as check **AU. routing regression
(served model)**. `--rebless` regenerates the baseline and prints the diff
for the commit message — re-blessing is never silent.

The **consumed-field invariant check** (flag any `PersonaSpec`/
`WorkspaceSpec` field set non-default in config with zero serving-path read
sites) is deliberately **deferred to Stage P**, not built here: the master
plan's own file-to-stage map lists Stage S as "folded into P's build," and
Stage P hasn't started yet in this pass — building it now would duplicate
work once Stage P's `model_pin` mechanism lands and the check needs to know
about it. Flagged so Stage P's build program doesn't drop it.

## Phase R4 — handoff to Stage P

No new persona-attributable REGRESSION or AMBIGUOUS case surfaced beyond
the 5 already known to `DESIGN_PERSONA_INTENT_REMEDIATION_V1.md`. Notably,
that design doc *independently* prescribes `magistralstrategist` →
`auto-reasoning` (its own line 95) — the exact same target this pass's
Finding 1/Finding 3 establish at the routing layer from a completely
different direction (keyword-scorer structural proof + alias-table
consistency, not persona analysis). The two stages agree without having
coordinated, which is itself corroborating evidence both are right.

**Stage P's fix list is therefore unchanged: the 5 known cases**
(`magistralstrategist`, `devstral_coder`, `glm_coder`, `glm_thinker`,
`phi4stemanalyst`). Stage R's routing-layer work is a prerequisite these can
now build on with confidence — `auto-reasoning` (not `auto-coding`) is the
routing-proven landing spot for Magistral-flavored intent, both by keyword
fold and by alias-table resolution.

**Gate status: GREEN.** `pytest tests/unit/ -q` — 716 passed, 0 failed.
`scripts/routing_regression.py --assert-baseline` — PASS, 86/86.
