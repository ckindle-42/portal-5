# TASK_COMPLIANCE_PROVE_THE_MODULE_V1 — close

**Base:** `3d5e59a0` · **Closed at:** `50456efd` (2026-09-21)

## §0 — The frame, restated

Frontier model builds, local model runs, coding agent judges. The product is a
local model reading the NERC CIP compliance corpus well, across the family —
not measurement scaffolding, not one proving standard. This task proved the
module by reading: every claim below was checked by the coding agent reading
the actual text, not by trusting a summary field, and every engine/config
decision was made on freshly-measured numbers, not carried forward from an
earlier measurement whose conditions had changed.

Three prior task files stalled on "this needs a human to label it" or drifted
into building instruments to check instruments. This one closes with the
product proven, six real defects found and either fixed or precisely named,
and two engine questions decided on evidence that was actually re-measured
after the conditions that would invalidate it changed.

## §1 — The self-agreement baseline

Two sequential, `write=False` runs of the incumbent (gemma4, CIP-007-6, 20
requirements, identical config) produced the **identical** 37-triple
determination set both times: `self_agreement_jaccard = 1.0000`. The model is
fully deterministic under sequential execution at this sampling config.

This sharpens, rather than confirms, an earlier finding: `SPLASH_SWEEP_
ACCELERATION_V1` had recorded arm D (same model, same engine, *concurrent*)
scoring `0.1429` against arm A and set a `reading_agreement_jaccard >= 0.80`
promotion floor without ever measuring the incumbent's own ceiling. Since
sequential self-agreement is perfect, the 0.1429 gap is a **concurrency**
artifact, not model nondeterminism — and no cross-engine floor above it could
ever be cleared by anything, including the incumbent. §P3 replaced this floor
with per-determination correctness.

## §2 — 183 determinations adjudicated by reading

The store held **183** reading-derived `relationship_assertions` edges at
HEAD — not the 166 an earlier snapshot in this task's own draft assumed;
recorded rather than reconciled. Every edge was extracted with its
requirement text, operator section text, relation, and cited sentence, and
judged SUPPORTED / UNSUPPORTED / WRONG_RELATION by the coding agent reading
all three.

**Precision: 0.7705** (141/183). This replaces `agreement()`'s n=11 as the
module's quality number.

Findings:
- Two edges admitted with an **empty citation** (`rel-259a730564bda6a5842f`,
  `rel-715cbc2d86a5a2df52b5`, both CIP-007-6 R2) — a determination recorded
  with zero justification.
- One **WRONG_RELATION** (`rel-d188ff496a9b0c1eb490`, CIP-003-8 Attachment 1
  Section 5): labeled IMPLEMENTS, but the cited text is a delegation-of-
  authority matrix entry naming the requirement, not a description of how
  the mitigation plan is carried out.
- The dominant UNSUPPORTED pattern (~29 edges): a citation naming boilerplate
  reused verbatim across the document ("this section describes the
  responsibilities for roles"), which the checker accepts because the quote
  IS a verbatim substring — verbatim presence was never a proxy for
  substantive relevance.

## §3 — The six dead standards diagnosed

CIP-002-5.1a, CIP-003-8, CIP-003-9, CIP-012-2, CIP-013-2, and CIP-014-3
together produced almost nothing (152 of 255 family requirements, 60%,
before this task). Every Part-level requirement in each was classified into
one of four causes from data already in the store — no new threshold, no
guess:

| standard | reqs | no_operator_document | empty_population | reading_failure | answered |
|---|---|---|---|---|---|
| CIP-002-5.1a | 33 | 0 | 32 | 1 | 0 |
| CIP-003-8 | 39 | 0 | 36 | 2 | 1 |
| CIP-003-9 | 44 | 0 | 40 | 2 | 2 |
| CIP-012-2 | 6 | 0 | 5 | 1 | 0 |
| CIP-013-2 | 11 | 0 | 8 | 2 | 1 |
| CIP-014-3 | 19 | 17 | 0 | 0 | 2 |

Five of six are dominated by **empty_population**: the reranker
(`candidate_links.build_links`) only ever ran at the standard's top-level
requirement identity (e.g. "R1"), never separately at the Part-level
identities (e.g. "R1 Part 1.1") the register actually tracks — a structural
non-reach, not a corpus gap. This is diagnosis, not a fix in this task's
scope (§0.3: no fitted thresholds, no `DEFAULT_THRESHOLD` changes).

CIP-014-3 looked like the one genuine corpus gap (zero candidates proposed
for any of its 17 requirements) — until the coding agent read the operator
corpus directly, per §P2's own mandate. Result: **17/17 are recall misses,
not a gap.** A dedicated procedure ("LSPG CIP-014 Physical Security
Procedure V8.pdf", LSPG-ADM-CIP014) substantively implements the standard
end to end, including its own requirement-traceability appendix, and
surfaced on the first ordinary `compliance_search` query. The reranker never
proposed it as a candidate for any of the 17 requirements.

## §4 — The splash engine question, decided on re-measured evidence

### The sweep (§P3)

The prior decision (`KEEP_OLLAMA`) was re-examined because the criteria and
the configuration behind it had never been jointly validated: a `0.1429`
concurrency artifact was being used as if it were a self-agreement ceiling
(§1), and a 3,072-token answer budget had truncated splash's more verbose
output into parse failures that a later fix (raising the budget to 8,192)
masked without ever checking whether the resulting context math still fit
splash's 32,768 serve-line pin. It didn't: the five largest CIP-007-6 cells
run 25,160 prompt tokens against an 8,192 answer budget — 33,352 total,
584 over the pin.

Re-serving splash at `--max-context 65536` (ample headroom on every cell)
and re-running arms A/C/D surfaced a **real, previously-latent bug**: the
sweep's own triple-extraction helper (`bench_sweep_engines._triples`) never
resolved a model's citation **handle** (`[O3]`) to its real section id the
way the store's write path does — it took the raw token verbatim. A model
citing by handle (routine, and more likely after this task's own §P4.3 fix
stopped printing the raw id beside the handle) produced a triple keyed on
`"O3"`, silently corrupting every cross-arm SET comparison this measurement
depends on. Fixed by resolving through the same `AnswerContract` the write
path uses; the two receipts produced before the fix were discarded, not
salvaged.

Re-run, clean, with real errors read before scoring (§P3.1's own rule):

| arm | wall_s | completion | determination_precision |
|---|---|---|---|
| A (ollama sequential) | 1314.98 | 20/20 | 0.4054 |
| C (splash concurrent) | 2444.43 | 20/20 | 0.6977 |
| D (ollama concurrent) | 1197.31 | 20/20 | 0.3902 |

`engine_speedup_C_over_D = 0.49` — splash is **slower** than the incumbent
at this config, not the `4.909x` measured before the completion failures
were fixed. Confirmed live in splash's own serve log: 55–600s time-to-
first-token per request under concurrency=4; the larger context window
makes the queueing worse, not better. **The earlier 5x number does not
survive contact with a config that actually completes.**

Precision surprisingly *favors* splash (0.698 vs the incumbent's 0.405) —
ollama fabricates far more unresolvable/malformed section ids under this
sweep than splash does. Quality was never the blocker; throughput is.

**Decision: KEEP_OLLAMA**, on the speed floor alone.

System cost (§P3.4): gemma4 was never evicted across the whole sweep
despite splash holding ~15.9GB resident throughout arm C; one live
conversation turn fired with splash still loaded answered normally in
10.68s. A true concurrent-load probe (a conversation turn fired *while* a
sweep arm actively generates) was not run — an open item, not a claim this
receipt supports.

### The conversation seat (§P4b, tightened)

The five-turn conversation shape had never run on a Qwen before this task.
First pass: split (incumbent) vs two direct-to-splash single-seat arms.
single-27B lost decisively (turn1 517s vs the incumbent's 58s). single-35B
appeared to *beat* the incumbent on both criteria at n=5, scored by a
substring-presence heuristic ("does a known section id appear anywhere in
the text").

Tightened at the operator's request: real reading judgment on every turn,
plus a full repeat run to check reproducibility (the same spirit as §1).
**Split is reproducible — 0.8 precision both runs, the same consistent
failure mode.** single-35B is not: 0.6 then 0.8 precision, a different case
failing each run (a hallucinated wrong-standard-number answer in run 1; a
hard 8-hop-exhaustion zero-content failure in run 2), mean per-turn latency
swinging 3x (21.6s → 66.4s) between runs. A genuine turn1-latency edge
survives both runs; the correctness/latency stability does not.

**Decision: SPLIT stands.**

## §5 — The family product proof (§P5)

The three product questions, asked in their **natural wording** — the
wording that used to trigger the router's `nerc_cip_requirement` narrowing
(§P4.1) — across five standards spanning healthy and dead: CIP-007-6,
CIP-004-7, CIP-010-4 (healthy), CIP-003-8, CIP-002-5.1a (dead).

First attempt: 0/15, every row dying on `answered=false` despite
`finish_reason=tool_calls` — not a new defect, but the deployed pipeline
Docker container running code from before *any* of this session's commits
(§7c). Rebuilt, verified fixed end-to-end, re-ran clean.

**11/15 passed.** The four failures are named, not silent: one is
`compliance_requirement` returning HTTP 400 and entering its own circuit-
breaker backoff (owner: the compliance MCP's own input handling — out of
this task's scope, recorded per §P4.2's "name the owner, do not guess");
the other three are genuine citation/content-quality misses.

Both dead-standard `coverage_gap` answers were read directly. Neither is
`honest_absence` nor fabricated `invented_coverage` — both are
**overclaimed_coverage**: real, retrievable sections cited, but several of
each answer's five citations are traceability-appendix rows whose own
visible text names a *different* standard (CIP-013-2 R3, CIP-003-9 R1) than
the one asked about. The model cited the right *document* but not
verifiably the right *row*.

## §6 — Still open

- The `compliance_requirement` HTTP 400 + circuit-breaker pattern (§5) is
  named, not fixed — owned by the compliance MCP's own input handling.
- The traceability-row-mismatch weakness (§7d) surfaced independently three
  times this session. It is the module's single most load-bearing recurring
  defect and warrants its own follow-up task — row-specificity checking
  against a shared multi-standard appendix, not just verbatim-substring
  citation.
- §P3.4's concurrent-load probe (a conversation turn fired *while* a sweep
  arm is actively generating, not just after) was not run.
- The `empty_population` structural non-reach (§3) affecting five of six
  dead standards — the reranker only running at requirement-level, never
  Part-level — is diagnosed but not fixed; out of this task's scope per
  §0.3.

## §7 — Lessons

`date | failure | repair | guard`

- **2026-09-21 | a floor nobody measured the ceiling for** — `reading_
  agreement_jaccard >= 0.80` rejected a 5x engine while the incumbent scored
  0.1429 against itself in a control arm built to reveal exactly that.
  **Guard:** §1 records self-agreement before any cross-run/cross-engine
  agreement criterion ships.
- **2026-09-21 | citation handles unresolved in the sweep's own triple
  extraction** — `bench_sweep_engines._triples` took a model's citation
  handle verbatim instead of resolving it through the answer's contract the
  way the store's write path does, silently corrupting every cross-arm SET
  comparison (jaccard, precision-by-pairing) any time a model cited by
  handle instead of raw id — for as long as this measurement has existed.
  **Repair:** resolve through `AnswerContract`, matching the write path.
  **Guard:** any new triple-extraction code over a model's determinations
  must resolve citation handles before comparing across runs or arms.
- **2026-09-21 | a floor and a fix measured at different times** — raising
  splash's context/budget to fix completion failures and re-measuring speed
  are two different questions; the earlier `4.909x` speedup was measured at
  a config that failed completion, and held only because nobody re-measured
  speed after the config changed to fix completion. **Guard:** a completion
  fix and a floor re-measurement travel together, not sequentially — fixing
  one and trusting the other's old number is how a promotion decision goes
  wrong.
- **2026-09-21 | the deployed service was stale against the day's own
  commits** — the portal-pipeline Docker image (built 2026-09-19) was never
  rebuilt after any commit made in this session, so every live call through
  the router before the rebuild silently hit unfixed code, including all of
  §P4b's first-pass "split" arm (its specific wordings happened not to
  trigger the bug, so its numbers held — luck, not validation).
  **Guard:** verify Docker image build time against HEAD before *any* live
  router testing, not only before formal benchmarks — CLAUDE.md already
  said this; it was missed until a 15/15 failure forced the check.
- **2026-09-21 | the same reading defect surfaced three independent ways**
  — §P1's one WRONG_RELATION edge, ~4/10 of §P3's UNSUPPORTED precision
  verdicts, and both of §P5's dead-standard coverage answers all trace to
  the same root cause: the operator's shared multi-standard traceability
  appendices are never checked for row-specificity, only for verbatim-
  substring citation. **Guard:** a citation against a multi-standard
  traceability table should verify the cited row actually names the
  standard being asked about, not just that the quoted text is present
  somewhere in the section.
- **2026-09-21 | a weak heuristic produced a result that didn't survive
  reading** — §P4b's first-pass substring-presence "precision" check
  produced an apparent single-35B win that a real reading judgment plus a
  repeat run overturned entirely. **Guard:** a precision number that isn't
  a real correctness read (citation-vs-text, requirement-vs-answer) must be
  labeled as a completion/grounding proxy, not presented as quality — and
  any surprising win on a small sample gets a repeat run before it's
  trusted.

## §8 — Gate record

Every phase's per-commit gate (`uv run ruff check .`, `uv run ruff format
--check .`, `uv run pytest tests/unit/ -q`) passed before that phase's
commit — see the individual commits on `main` from `e979952f` through this
close.

Final gate, run at close:

- `python -m portal.platform.wiki.coverage --write-manifest` — PASS (no
  drift; `scripts/write_spine_manifest.py` named in the task's own §P6
  command block does not exist in this repo; this is its real replacement,
  used throughout this session).
- `python3 scripts/complexity_report.py --write-budget` (bare `python3`,
  per CLAUDE.md) — PASS.
- `uv run python scripts/validate_system.py` — PASS.
- `uv run pytest tests/unit/test_compliance_*.py -n auto` — PASS.
- `scripts/doc_ledger.py`, also named in the task's §P6 block, does not
  exist in this repo — skipped, noted here rather than silently omitted.

No gate was forced or bypassed with `--no-verify`. No push performed —
all nine commits (`e979952f` through this close) sit on local `main`,
ahead of `origin/main`, pending the operator's own push.
