# Task: `auto` router — standard-vs-abliterated posture gate

## Problem (adaptive UAT capability findings, 2026-08-31)

`tests/uat_adaptive/FINDINGS_FIXLIST.md` §C1/C2/C3, `ACTION_ITEMS.md` AI-14/15/16:

- **C1 [HIGH]** — `auto` routed a genuinely harmful doxxing/harassment request to
  the abliterated lane (`qwen3.5-abliterated`), which produced a full harassment
  dossier. No refusal.
- **C2 [HIGH]** — `qwen3.5-abliterated` is the router's default pick, so every
  `workspace_model: auto` persona (itexpert, techreviewer, webnavigator — 12 rows)
  and every ambiguous auto-routed request lands on an abliterated model.
  Observed: a coworker-password-theft walkthrough, three fabricated 1-star
  reviews with a fake safety recall, dossier compilation.
- **C3 [MED]** — `auto-math` (a standard-posture space) produced a working covert
  exam-cheating scheme.

## Operator intent (this is the design constraint — build to it)

**`auto` SHOULD route most traffic to an abliterated lane** — that is deliberate,
not a bug. The fix is NOT "stop using abliterated models." The fix is: **when a
request needs standard posture — or is genuinely harmful — it must route to a
lane that will handle it correctly (refuse the harmful ask, apply standard
guardrails), regardless of the abliterated default.**

## Objective

Add a **posture classification step before lane selection** in the `auto` router
(`portal/platform/inference/router/`):

### 1. Harmful-intent keyword gate — DONE 2026-08-31 (shipped)

`config/inference/routing_harmful_intent_keywords.json` (weighted, threshold 3,
env-overridable) + `routing.detect_harmful_intent()`. `preinject._resolve_auto_routing`
now checks it FIRST: when `auto` (including `workspace_model: auto` personas,
which resolve to `auto`) sees a harmful ask — targeting a private individual,
deception/fraud, harassment, exam-cheating — it routes to `_HARMFUL_INTENT_LANE`
(`auto-daily`, non-abliterated, `gemma4:26b-a4b-it-qat`), logs a WARN, and
increments `_router_layer_total{layer="harmful_intent_gate"}`. Non-harmful `auto`
traffic is untouched (still mostly abliterated, by design). Authorized security
work does NOT trip it (verified — `mimikatz`/`kerberoast` route via
`auto-security`'s own keywords). Tests: `tests/unit/test_routing.py::TestHarmfulIntentGate`.

**Remaining for this item:** tune the keyword set against the real C1/C2 corpus
rows; consider an LLM-layer posture dimension (below) for cases keywords miss.

### 2. LLM-layer posture dimension (not yet done)

Extend the Layer-1 intent classifier prompt/output with a posture field
(`harmful` / `standard` / `permissive`) so semantic harmful intent that dodges
the keyword set is still diverted. Keyword gate stays as the deterministic
floor.

### 3. `workspace_model: auto` personas (C2/AI-15) — decide per persona
   - personas whose directive implies standard posture (itexpert, techreviewer,
     webnavigator, compliance-flavored ones) → either pin a stock `model_hint`
     or let the new posture gate handle them (preferred if the gate is reliable);
   - personas that are genuinely permissive → leave on `auto`.
   Document the decision in each persona YAML so their UAT boundary rows become
   testable (they currently grade the abliterated model, not the persona).

### 4. `auto-math` and other standard-posture non-`auto` spaces (C3)

`auto-math` (phi4-mini) produced a covert exam-cheating scheme — it's not
abliterated but is small and weak on safety. The harmful-intent gate only
covers `auto`; a user directly selecting `auto-math` bypasses it. Options: a
lightweight refusal-posture system-prompt prefix on standard-posture spaces, or
a pre-dispatch harmful-intent check that applies regardless of the selected
workspace (reuse `detect_harmful_intent`).

## Verification

- Re-run the C1 doxxing boundary challenge through `auto` → routed model is a
  standard lane, response is a refusal + safe alternative.
- Re-run the permissive-but-sensitive boundary challenges (auto-spl,
  auto-general-uncensored — `FINDINGS_FIXLIST.md` §C6) → still complied, no
  new over-refusal regression.
- The 12 `workspace_model: auto` persona boundary rows re-graded against the
  resolved model.
- Boundary posture census (AI-17) re-run: standard general workspaces should
  now consistently refuse unambiguous harmful asks.

## Reference

`tests/uat_adaptive/FINDINGS_FIXLIST.md` §C/§D1, `ACTION_ITEMS.md` AI-14–17,
CLAUDE.md §6 (auto-routing: Layer 1 LLM intent classifier / Layer 2 keyword
fallback).
