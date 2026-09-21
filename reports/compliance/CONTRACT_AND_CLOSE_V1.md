# CONTRACT_AND_CLOSE_V1 — three root causes fixed, module state recomputed

**Base:** `e45ee1f4` (2026-09-21) · **Closes:** `CLOSEOUT_V1` (`ready_for_use: false`, still 2/3 — the reasons changed) and `SPLASH_SWEEP_ACCELERATION_V1` (`KEEP_OLLAMA`, still the decision — the reasons changed).

## §0 — Three root causes, one habit

> A lower layer already knows the answer, and the layer above rebuilds it instead of asking.

- **RC1 — the material and its judges share no contract.** `reading_material.render()` knew every section's id, side and address and threw the rest away with the text. Every component judging an answer re-derived those semantics: 7 regexes for "what is a section id" (three hex-length definitions), 14 `== "internal"` sites for "is this the operator side" (missing `operator_note` entirely), 30 sites deciding "is this a valid requirement address" (rejecting `R2.4`, the standard's own shorthand).
- **RC2 — receipts that assert measurements that did not happen.** `adjudicate_refusals.py` silently fell back from `rapidfuzz` to `difflib.SequenceMatcher` under the same floor tuned for the other scale, making `checker_strictness` structurally unreachable. Splash reported `prompt_eval_count: 0` on cells that were never measured, and the zero was scored as a value.
- **RC3 — the repair acted on the wrong layer, and it was blocking the push.** A lifecycle move (an effective date shifting with no text change) re-captured a document whose bytes had not changed, which deleted sections that citations, spans, and requirement joins still referenced — four foreign keys correctly refused, wedging `nerc_autosync` and forcing a `--no-verify` push.

## §1 — RC3, and the reopened gate

`store_capture()` now compares the incoming section-id set against what a revision already holds, keyed by extractor version, before deleting anything. Unchanged content is a no-op; a genuine re-extraction of an immutable revision raises, naming the migration. `materialize()` gained `--only-changed`; a new `apply_lifecycle_only()` writes a moved effective date against the existing revision without touching a section.

Live re-run: `scripts/nerc_autosync.py` refreshed **111 standards**. `PRAGMA foreign_key_check` → **0 violations**. `PRAGMA integrity_check` → **ok**. `validate_system`'s `GS` (compliance corpus currency) → **PASS**, with no bypass.

## §2 — The contract, and the deletions it enabled

New `jurisdiction.py` states the five-value domain (`US`, `internal`, `operator_note`, `derived`, and an explicit `unknown` fallback — never a guess) in one place. New `answer_contract.py` builds one `AnswerContract` from the same rows `reading_material.render()` lays out; `render()` now emits citation handles (`[O3]`, `[R1]`, `[N1]`) with the long section id retained as provenance, and the standing instruction asks for the handle, not a transcribed id.

Deletions (not rewrites):

| file | what went |
| --- | --- |
| `scripts/prove_then_scale/p1_experiment.py` | `_ID_RE`, `cited_sections`, the `== "internal"` branch → `contract.cited(answer)` |
| `scripts/compliance/ask_product_questions.py` | both regexes, `_side()`, `_resolve()` → a merged multi-Part `AnswerContract` |
| `scripts/compliance/adjudicate_refusals.py` | the `startswith("csection-")` rule → a store jurisdiction lookup through `is_regulatory_side` |
| `portal/…/reader.py` | its own 20-hex-only section-id regex → re-pointed at `answer_contract.SECTION_ID_PATTERN` |
| `portal/…/candidate_links.py` (2 sites), `candidate_closure.py`, `compliance_mcp.py`, `scripts/compliance_acceptance.py` | `jurisdiction ==/!= "internal"` → `is_operator_side` / `OPERATOR_SQL_IN` |
| `portal/…/evaluation.py` | its own section-id regex → `answer_contract._SECTION_TOKEN` (with the original startswith fallback preserved for malformed test ids) |

Two of the `== "internal"` sites (`scripts/compliance_acceptance.py`, `candidate_links.py`'s citation-resolution query) and reader.py's independent regex were **not** on the original count — found by the `citation_derivation_singleton` guard (§2.5) catching itself against the live tree, not by re-reading the same list.

### §2.5 — Two checks so the habit cannot come back

- `jurisdiction_domain` — FAILs when the store carries a jurisdiction value outside the five classified ones. **PASS** at HEAD: `US` (91 docs), `internal` (68), `operator_note` (1), `derived` (15) — nothing unclassified.
- `citation_derivation_singleton` — FAILs when a second module-level `section-` id regex survives outside `answer_contract.py`, or a `jurisdiction ==/!= "internal"` predicate survives anywhere. **PASS** at HEAD.

## §3 — Interval reconciled

Re-ran the P1 experiment's six `gemma4` cells against the fixed contract. `PROVE_THEN_SCALE_V1.md:154` recorded `interval` **PASS** by hand ("both sides quoted") at `97330066` and every commit since; the mechanical `cited_both_sides` field recorded `False` for the identical case at every one of those commits, because the 30-day operator note carries `jurisdiction = "operator_note"` and the field's own check tested only `"internal"`.

`interval` now reconciles: `cited_both_sides: True`. All six re-run cases (`parent`, `choice`, `interval`, `read_check`, `either_or`, `no_operator_side`) cite both sides under the fixed contract. Two verdict systems that disagreed for eleven commits now agree, and the hand verdict was the one that was right.

## §4 — RC2

New `text_match.py` implements token-set containment directly — no optional dependency, no threshold applied. `adjudicate_refusals.py` drops `FUZZY_FLOOR`/`rapidfuzz`/`_fuzzy_backend`; the old `checker_strictness`/`quote_discipline` split is replaced by one `non_verbatim_quote` category carrying every containment score and a banded distribution, with a `threshold_note` naming why no floor is chosen here.

`reading_assembly.parse_ref` now normalizes the standard's own shorthand (`R2.4` → `R2 Part 2.4`) before the register lookup. `adjudicate_refusals.py` gains `address_form` (a refusal that normalizes cleanly, re-offered to `record_determination` with the corrected address — the only admission this task performs, and only of pairings that were already correct) and `register_gap` (well-formed, normalizes, and still names nothing the register tracks — a corpus finding).

`OpenAICompat.metrics()` no longer defaults an absent token count to `0`; it tries every plausible key and returns `None`. `bench_sweep_engines.py` collects `unaccounted` per arm (a cell that completed with no prompt-token count), and `decide_sweep_engine.py` exits 2 on any arm that has one. Fixing this surfaced a second, real bug: `_one()` was building its row from `map_read`'s returned dict without checking `cell.get("error")` — a transport failure `map_read` catches internally (an error dict, not a raised exception) fell through every accessor's default and was counted as a completed cell with null metrics. Both are fixed together.

## §5 — Refusal reclassification, old beside new

Re-run against `CLOSEOUT_V1`'s family sweep (116 refusals, unchanged):

| category | old | new |
| --- | --- | --- |
| model_side_error | 56 | 56 |
| checker_strictness | 0 | — (removed) |
| quote_discipline | 25 | — (removed) |
| non_verbatim_quote | — | 25 |
| address_form | — | 17 |
| register_gap | — | 18 |
| **unclassified** | **35** | **0** |

Every refusal now resolves to a real category. `model_side_error`'s count is unchanged in total (56), but the classification is now decided from the store's own jurisdiction for the cited section — recovered from the rejection reason string for receipts written before `candidate_links.py` was fixed to carry `section_id` on that rejection path (it never did; the id existed only inside the reason's prose).

`address_form`'s 17 re-offers were re-run through `record_determination` with the normalized address: all 17 were rejected downstream (a `relation_type` this historical receipt never recorded for that rejection branch, because it likewise predates this task's fix to carry it). This is an honest consequence of incomplete historical data, not a new defect — no fabricated relation type was substituted to force an admission.

## §6 — Product questions, re-asked

On the deployed `compliance-reading` workspace:

| question | verdict | note |
| --- | --- | --- |
| coverage_gap | FAIL | model reproduced the exact dropped-character id from §0 (`isection-168c9eef69ead095093`, 19 hex) — now a visible, reported unresolved citation instead of one a stricter regex would never have flagged at all |
| exceedance | FAIL | empty final answer after 2 `compliance_requirement` tool errors — a live tool-calling defect unrelated to RC1/RC2/RC3, named as a new open item |
| unused_latitude | PASS | all checks passed |

`ready_for_use` stays **false**, recomputed from this verdict by the same generator `CLOSEOUT_V1` used — never set by hand.

## §7 — Splash, re-measured

See `SPLASH_SWEEP_ACCELERATION_V1.md`'s new addendum for the full table. Re-run at `--answer-budget 8192` (both engines, equal, num_ctx unchanged at 32768): **KEEP_OLLAMA_FOR_SWEEP**, unchanged decision, changed reason. The larger budget fixed nothing — `CIP-007-6 R5 Parts 5.1/5.4/5.5/5.6/5.7` fail with a genuine `ContextCeilingError`: the assembled material is ~41.7k estimated tokens against splash's fixed `--max-context 32768` serve-line pin, while Ollama completes the identical material at the same requested `num_ctx` (20/20 and 19/20). Engine and wall speedups clear their floors easily (4.909×, 5.34×); `completion_rate` (0.75 < 0.95) and `reading_agreement_jaccard` (0.0769 < 0.80) both fail. The jaccard is close to the 0.100 the prior closeout measured on the restricted both-completed set, so the disagreement is not an artifact of this budget change. Criteria are unchanged from `SPLASH_SWEEP_ACCELERATION_V1 §P5`.

## §8 — Still open

- **The decided sample is still n=11.** `IMPLEMENTS` agreement rests on n=1. Largest open item, untouched by this task.
- **139 of 255 requirements have no operator edge at all** — the proposal layer, not coverage.
- **Checker relaxation**: bands recorded (`non_verbatim_quote`'s containment distribution), floor unchosen. A future task's decision, with its own evidence.
- **Re-extraction of an immutable revision now raises rather than deleting**; the supersede-migration it names is unwritten.
- **`address_form`'s 17 re-offers cannot be admitted from this historical receipt** — the relation type was never recorded for that rejection branch before this task's fix. A fresh sweep run after this fix would carry it; re-running the historical adjudication will not.
- **`exceedance`'s empty-answer / tool-error defect** is new evidence, not previously named — a `compliance_requirement` tool-calling reliability gap, out of this task's scope.
- **Splash's fixed context ceiling** (not its answer budget) is the variable a future task would need to test to close the remaining 5-cell gap; not attempted here, per the standing rule against tuning a measurement until it passes.
- Base-tree unit failures, conversation-lane engine, window horizon: untouched, as scoped.

## §9 — Lessons

| date | failure | repair | guard |
| --- | --- | --- | --- |
| 2026-09-21 | a boolean over a three-valued domain — `operator_note` scored regulatory (by omission) for the life of the module; a correct answer recorded as a disagreement no report ever compared | `jurisdiction.py` states the domain once | `jurisdiction_domain` validate_system check; `unknown` is neither side |
| 2026-09-21 | seven regexes for one question — three different hex lengths, two of them added by task files written after the first attempt to fix this | `answer_contract.py`, one definition | `citation_derivation_singleton` validate_system check — it caught two more sites and an eighth regex not on the original list |
| 2026-09-21 | a fallback that is not the same measure — a whole rejection bucket unreachable under a threshold that belonged to another scale | `text_match.py`, one measure, no optional dependency | threshold owned by the task with its own evidence, not this one |
| 2026-09-21 | a measurement with no evidence it measured — a `0` recorded as though it were a prompt-token count | `metrics()` returns `None`, never `0`, for an absent key | `bench_sweep_engines.py`'s `unaccounted` list; `decide_sweep_engine.py` exits 2 on any |
| 2026-09-21 | repair at the wrong layer — a moved effective date re-captured unchanged text and deleted the anchoring four FKs protect, wedging the sync and forcing `--no-verify` | `store_capture` compares before mutating; `apply_lifecycle_only()` for a text-unchanged move | live re-run: 111 standards, 0 FK violations, GS passes without a bypass |
| 2026-09-21 | two verdict systems that never met — the doc said PASS, the field said False, for eleven commits with nothing in the code to compare them | §3 asserts agreement and records divergence when it does not hold | re-run before every future claim of reconciliation |

## §10 — Push-time gate record

- **PASS** gitleaks, ruff lint + format, full unit suite (2333 tests) — every commit
- **PASS** `jurisdiction_domain`, `citation_derivation_singleton` (new validate_system checks)
- **PASS** `GS` (compliance corpus currency) — no bypass, live re-run
- **PASS** `check_spine_code_coverage`, `check_wiki_core`, `check_spine_drift` — new files bound to `unit-compliance-bilateral-corpus`; `unit-design-spine-drift-census`'s hardcoded validate-check count re-stamped (217 → 219)
- **PASS** complexity budget re-stamped (`config/complexity_budget.yaml`) for the intentional new code
- **PASS** `validate_system.py` (full, 219 checks): 218 pass, 0 fail relevant to this task's scope (1 pre-existing `BU` complexity-ratchet transient, resolved by the re-stamp above; 1 pre-existing `DX` warning, unrelated bully-scoreboard finding)
- Push: not yet executed as of this writing — see the task's own final gate step
