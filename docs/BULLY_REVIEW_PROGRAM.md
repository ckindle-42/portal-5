# Bully / Crogl review program

This file defines the program. It holds no numbers and no status: those are derived
(`docs/BULLY_REVIEW_STATE.md`, rendered by `scripts/bully_review_state.py` from the defect census,
stamped reports and decision records). If this file and the derived state disagree, the state wins.

## 1. The product

A source-agnostic security-data reviewer. It finds things that are **not known but are the same as,
or similar to, something known**, raises them to an analyst with evidence the analyst can check,
and turns the analyst's verdict (something / nothing / unsure) into knowledge so the system matures
instead of being tuned. Known-bad matching is the floor, not the product.

Decision (operator, 2026-10-08, restated 2026-10-09): the reviewer is the product. The attack-emulation
loop is not. It does not survive as a generator either: **this program executes nothing.** What survives
is the *replay plane* -- telemetry already indexed in the corpus (BOTS, `portal5_lab`) and previously
recorded exercise captures, each usable only as far as its ground truth still validates. When recorded
truth is too thin to answer a question, the answer is INCONCLUSIVE and the thinness is the finding; it is
never an invitation to run something.

## 2. Why the old system failed: root causes, not symptoms

Fourteen reproducible defects and nineteen written lessons are not fourteen problems. They are
eleven failure classes, each with one root cause. Fixing instances is what the lab did for ten
months; each class below is removed by a structural change and made loud by a guard.

| # | Failure class (lesson) | Root cause | Structural remedy | Guard that makes it loud |
|---|---|---|---|---|
| 1 | Components proven, system never run (3, 7.3, 7.9, 11) | The unit of work was the module and its proof was its own fixture; no single executable path every change had to pass through | One path: the evaluation runner drives only the public service; arms are configuration; reachability is shown by execution trace | `guards.disallowed_imports` on the runner; prune ledger traces; scorer-wall closure test |
| 2 | Tuning the wrong stage (B1/F1/T1: 558 of 988 probes had no candidate) | No per-stage ceiling: nothing said *where* truth was lost | A truth ledger in every report; an experiment may only target the binding stage | `review_eval.attribution`, `decisions.problems` |
| 3 | Constants decide (1, 12, 13, 15, 17) | Thresholds were fit to an instrument and inherited its artifacts (embedder scale, bench asymmetries) | Replace "what is the threshold" with "what is the null": conformal thresholds from a benign slice, re-fit when the embedder identity changes; every remaining number is a registered budget, bound or protocol minimum | `review.constants` registry test |
| 4 | Instruments that cannot fail (2, 14, 16) | The instrument was never itself tested and lived in the engine's address space | Known-answer self-test before any report; each metric states how it fails; values recomputed from raw rows; corpora declared `real:` or `proxy:` | `review_eval.selftest`, `report`, `Stamp.problems` |
| 5 | Truth leaks (5, 9, 15) | Truth lived inside the engine's address space | The wall by construction; scorer plane unreachable from the product; independently sourced truth | `wall.scan_source`, scorer-wall closure test |
| 6 | Definition-matcher creep (7.7) | A table is always the cheapest fix and nothing ratcheted it | A table-free product; curated-literal lines counted in the census | `test_the_product_carries_no_curated_tables`, census metric |
| 7 | Judgment implemented as arithmetic (the discarded LLM verdict; endless distance tuning) | "Cold / no model calls" doctrine applied to a *reading* problem | Reading is the comparator: code proposes candidates (judged by candidate recall), a reasoning model reads (judged conditional on candidates, reasoning on), code verifies (grounding) | `review.grounding`; every reader arm is A/B'd against the deterministic arm |
| 8 | State as prose (19; the brief this program started from was itself stale) | State was recorded as snapshots, and snapshots go stale in days | State is derived: claims are probes, numbers are stamped reports, the document is rendered and checked | `bully_review_state.py --check` |
| 9 | Delegated optimization (18) | A metric and no question, no stop, no anti-goals | Every experiment is a decision record committed before its arm runs; order verified by git ancestry | `decisions.problems` |
| 10 | Proven in a proxy (never on the real thing) | Outages were worked around with proxies; fixtures were cheap and embedded their labels | Claims accept only `real:` corpora; an outage is fixed or the task BLOCKS | `Stamp.problems`, state renderer |
| 11 | No product contract | Nobody defined analyst-facing success; metrics were internal | One operating dial, analyst workload B; the headline is recall of independently sourced cousins at B | the harness headline |

## 3. The architecture that follows

Three duties, three owners. Deterministic code never decides what is "similar" for a verdict.

1. **Propose** (code). Per-source intake builds units; a calibrated funnel and knowledge retrieval
   propose candidates. Judged by *candidate recall* at the reader's budget, nothing else.
2. **Read** (a reasoning model, reasoning always on). It reads one candidate with pull-based
   pivots, states whether it is something / nothing / unsure, and cites evidence. A real Challenger
   always runs. Silencing needs independent agreement; raising yields only to a grounded refutation.
3. **Verify** (code). Every claim cites event ids a deterministic checker can locate; absence is
   recorded with a receipt of what was searched; examined and resolved are separate counts.

Authority order: analyst verdict > reader (once adopted by data) > deterministic arm (always
available as the measured baseline and the fallback when no model is reachable).

Planes, enforced by tests: observation (what the data shows; may not name a label), knowledge
(anchors: the only place a label may live), judgment, scorer (offline; unreachable from the product),
replay (telemetry already recorded, plus whatever manifest was recorded alongside it; read-only, never
product, and never re-executed to produce more).

## 4. Invariants

- **I-1 One path.** The runner calls only the public service API; arms are configuration.
- **I-2 Truth outside the engine.** Observation modules cannot spell a label; the product cannot reach the scorer.
- **I-3 No fitted constants.** Thresholds are null quantiles; other numbers are registered budget / bound / protocol.
- **I-4 Table-free.** No curated tables in the product; on a tie between curated and table-free, table-free wins.
- **I-5 Instruments can fail.** Self-test first; stamp; recomputation; `real:` corpora only for claims.
- **I-6 Never cap silently.** Every stage reports examined and resolved; a cap is a receipt, not a default.
- **I-7 Reading is the comparator.** Reasoning on, grounded claims only, `unsure` first-class, a real Challenger.
- **I-8 Fix the binding stage.** An experiment targets the stage that loses the most truth, or says why not.
- **I-9 State is derived.** No hand-written status documents; claims are probes.
- **I-10 Questions, not metrics.** Each task answers one question and carries its anti-goals and stop rule.
- **I-11 Replay only.** Nothing executes: no attack, chain, tool against a target or emulation
  operation. Truth is telemetry already indexed; the product's only traffic is read-only search.

## 5. How decisions are made without operator gates

`docs/review_decisions/README.md` is the protocol: write the record (question, stage, arms, metric,
adopt-if, anti-goals), commit it alone, run the arms, resolve it with a stamped report, never edit it
again. Ties keep the control. `scripts/bully_review_state.py --check` verifies all of it.

## 6. Sequence

| task | question it answers |
|---|---|
| T0 ground | What is true of the system and the lab right now? |
| T1 skeleton | Does one end-to-end path run on real data with a stamped, self-tested, stage-attributed measurement, and where is truth lost? |
| T2 candidate loop | Which stage loses the most truth, and what is the smallest change that recovers it? |
| T3 reading | Does a reasoning reader let the analyst see more truth at the same workload? |
| T4 knowledge | Does a verdict make the next cycle quieter without making it blind, and does the system know what existing detections would have caught? |
| T5 surface | Can an analyst use it through the interfaces Portal already has, and does it stay honest across restarts and embedder changes? |
| T6 proof | At a stated fraction of the real corpus, which standing claims are proven, and by what margin over control? |
| T7 consolidate | What of the old system is still reachable, and can everything else be deleted safely? |

## 7. Non-goals

No fine-tuning or training. No new platform extraction (build against existing primitives; record
extraction candidates). **No execution of anything**: no attack, chain, tool against a target or
emulation operation, and no work on the emulation loop beyond reading what it already recorded. No UI
beyond the MCP tools and one workspace. No tuning of anything against a headline metric.
