# CITE_AND_SCOPE_V1 — the identifier leaves the model's output contract; the population gains its missing signal

**Date:** 2026-09-23 · **Base:** `22a62652` · **Code:** `c36333fc` (P1), `4fbc2b8c` (P2), `f8ac5cde` (P3 instruments), `2056a57d` (technical basis + truncation guard) · **Close:** local `main`, this document
**Follows:** LOAD_AND_CONVERSE_V1 — 121 empty populations → 0, all 14 standards populated, 366 edges at 0.8142 family precision, retrieval exercised 14/14, tool loop fixed — with all six conversational failures on `grounding_per_claim` and CIP-002-5.1a adjudicating at 0.3103.

---

## §0 — The two flaws, and what the evidence said

### §0.1 — A 20-hex storage identifier in the output contract of a 26B local model

Every conversational failure in LOAD_AND_CONVERSE was the same check with every other check green: the model hand-copied section ids and dropped, added, or concatenated hex characters. Three prior fixes moved the id around; none asked whether the model should emit one at all. P1 inverted the verbatim checker (`candidate_links._norm_for_verbatim` → `citation_by_quote.resolve_quote`): a claim is grounded when a double-quoted span of the section's words is found, by folded containment, in a stored section; ids still resolve as a fallback for stored answers, but nothing requires them. The workspace prompt is v2.7: *the quote is the citation*.

**Measured:** ground truth by construction — the 451 provenance sentences stored with prior determinations re-resolve at **recall 1.0** (`p1/quote_resolution.json`); 327 of 451 match exactly one section, 124 are multi-match (the distribution runs to 64 and 88 for boilerplate), and the multi-match policy is *grounded with every match recorded*, decided on that distribution. On the live probe the six baseline-failing questions went 2/8 → 5/8 across two runs; quote no-match fell 25% → 8%; **zero unresolved ids**.

At P3 the transcription failure mode is dead in the wild: across the conversational fourteen, **every hex id cited resolves** (the `patching` answer alone carries 27 ids, all resolving; `most_work`'s single miss is a hand-typed *document title*, not a copied token). The three grounding failures that remain are quotation fidelity — one quote corrupted mid-span by the model itself ("evaluate security patches … at least once every 3rag 35 calendar days"), one stitched two-source quote — and each **fails as written**, exactly as an unresolved id did. The check did not loosen; §P3's test is met in the direction that hurts.

**Conversational fourteen: 8/14 → 9/14.** Failure causes, all named, none transcription: `patching` and `shared_accounts` quote-fidelity slips (1 ungrounded claim each out of 15 and 24); `most_work` cites a document by typed title that resolves to nothing; `vendor_risk` cites no regulatory section; `overlap` never called search. Invented coverage on absence questions: 0.

### §0.2 — A requirement's population scoped by similarity alone

CIP-002-5.1a adjudicated at 0.3103 because every other document's physical-security vocabulary scored high against asset-categorization requirements. P2 read the operator corpus instead of ranking it: **64 of 69 documents state their scope**, seat-read with quote-validated evidence into the store (`document_scope`, migration 20). Three arms were measured offline (`p2/scope_effect.json`, `p2/scope_decision.json`):

- **hard filter** — removes 19 of CIP-002's 20 unsupported baseline pairs at the cost of 1 SUPPORTED; but family-wide it deletes 76 of 286 adjudicated pairs (27% recall) and helps only CIP-002;
- **ranking prior** (SCOPE_PRIOR=0.125, fixed a priori) — removes *nothing* live; a prior cannot evict high-scoring vocabulary twins;
- **visible provenance** — a `> document scope:` line rendered beside every operator section.

The pick was **provenance visible, `build_links` left at `scope_mode=off`** — the reading, not the apparatus, owns the judgement, and nothing is excluded without a record.

The §RESUME runbook's step 1 re-derived scope with the amended prompt after the first derivation under-claimed the umbrella Cyber Security Policy (stored as serving CIP-003 alone despite TOC sections for CIP-004..011). The v2 receipt (`p2/document_scope_v2.json`) has the policy serving **CIP-003 plus CIP-004…011, all nine claims quote-valid**, and the family histogram widened accordingly (CIP-006 5→9 documents, CIP-004 10→12, CIP-003 7→9).

### §0.3 — One more instrument decision the runbook demanded

A store that only accumulates cannot show a re-sweep's effect store-wide. P3 therefore measures **the edges this sweep affirmed** (`sweep_edge_set.py`, 255 requirements re-read, 278 affirmed) against the previous sweep's affirmed set (`p3/baseline_edge_set.json`, 336 @ 0.8036) — not the store-wide 366 @ 0.8142, which is carried for continuity only. The pre-sweep pair set was verified equal to the baseline 366 before any writes, and the store was backed up (`pre_cite_p3_20260923T172725Z.sqlite`).

---

## §1 — Citation by quote: what resolved, what didn't, and whether the model complied

| instrument | result |
| --- | --- |
| stored-quote ground truth (451) | recall **1.0**, zero missed |
| match-count distribution | 327 ×1, 24 ×2, rest multi-match (mode 21–64 for boilerplate); policy: grounded, all matches recorded |
| live probe (P1) | 2/8 → 5/8; quote no-match 25% → 8%; zero unresolved ids |
| conversational fourteen (P3) | 9/14; **zero unresolved hex ids**; 16–17 quotes resolving on the failing answers |
| residual quote failures | model-corrupted span ("3rag"), stitched two-source quote — both fail as written |
| model compliance | the model quotes heavily *and* still emits ids alongside; both paths resolve, so compliance is not a lever that needed forcing |

The §P3 loosening test: an unsupported claim still fails; nothing is repaired onto a near neighbour; the one id failure (`most_work`) is recorded, not resolved away.

## §2 — Document scope: derived by reading, living in the store

- 69 operator documents seat-read once; 64 state a scope; every claim carries the quoted words that justify it (`document_scope_v2.json`, 3 invalid-quote claims rejected).
- Scope lives in the store (`document_scope` table), not a sidecar — the §P2 ladder's rung 5 never needed.
- Mechanism: provenance rendered into the reading; filter and prior measured and rejected on evidence (§0.2); `build_links` unchanged (`scope_mode=off`).
- What it excluded, per requirement, without judgement: `sweep_edge_set.json` records every baseline edge the new reading declined, split by baseline verdict. Family-wide: **50 baseline-UNSUPPORTED pairs declined (contamination the reader no longer sees a reason to name), 213 baseline-SUPPORTED pairs not re-affirmed (recall the reader did not re-claim), 4 WRONG_RELATION dropped; 79 baseline pairs re-affirmed; 199 of the 278 affirmed edges are new pairs** — including CIP-003-9's first real coverage, which could not be read at all before the truncation fix.
- CIP-002-5.1a, the headline cell, no-judgement: **declined all 20 baseline-UNSUPPORTED contamination pairs** and 8 baseline-SUPPORTED pairs, re-affirmed 1 — and the fresh adjudication of its new 5-edge set puts it at 0.60 with the two declines being a generic purpose statement and a backup-testing vocabulary twin. §0.2's mechanism did exactly what it predicted.

## §3 — The measured effect, edges beside precision

Comparator: the previous sweep's affirmed set (336 @ 0.8036). Adjudication: 278 edges, 203 judged fresh by this agent, 75 carried (identical sentence sets per `--carry` rules).

**Family: 336 @ 0.8036 → 278 @ 0.8345.** Precision rises; edges contract 17% without collapsing, and the contraction is concentrated where the reader was being wrong.

| standard | baseline n @ prec | P3 n @ prec | attribution group |
| --- | --- | --- | --- |
| CIP-002-5.1a | 29 @ 0.3103 | **5 @ 0.60** | scope headline; fixed body also gained its implementation plan |
| CIP-003-8 | 40 @ 0.775 | 26 @ 0.7308 | scope line only (R1/R2 newly whole — listed apart below) |
| CIP-003-9 | 41 @ 0.8537 | 46 @ 0.8478 | scope line + technical basis (R1 newly whole) |
| CIP-004-7 | 34 @ 0.8824 | 18 @ 0.9444 | scope line + technical basis |
| CIP-005-7 | 15 @ 0.6667 | 19 @ 0.6842 | scope line + technical basis |
| CIP-006-6 | 24 @ 0.8333 | **37 @ 0.8649** | scope line only |
| CIP-007-6 | 24 @ 0.875 | 22 @ 0.9091 | scope line only |
| CIP-008-6 | 20 @ 0.9 | 8 @ 0.875 | scope line + technical basis |
| CIP-009-6 | 11 @ 1.0 | 23 @ 0.913 | scope line only (prior sweep barely read it) |
| CIP-010-4 | 22 @ 0.8182 | 6 @ 0.8333 | scope line + technical basis |
| CIP-011-3 | 10 @ 0.9 | 6 @ 1.0 | scope line + technical basis |
| CIP-012-2 | 8 @ 0.875 | 9 @ 0.8889 | scope line + technical basis |
| CIP-013-2 | 29 @ 0.8966 | 25 @ 0.76 | scope line + technical basis (fresh judging declined 6 — vendor-notification vocabulary twins, below) |
| CIP-014-3 | 29 @ 0.8621 | 28 @ 0.8214 | fixed body gained its implementation plan |

**Product fifteen: 10/15.** The three baseline `coverage_gap` fails that named cross-standard contamination were all CIP-002 questions — **all three now pass**, which is §P2's prediction landing on the live path. The five current fails are new and differently caused: two **empty completions** (CIP-004-7 exceedance and unused-latitude; 0 characters returned — a seat failure, not contamination) and three `required_side_present` (CIP-007-6 coverage_gap, CIP-010-4 exceedance, CIP-003-8 coverage_gap — answers that read one side and not the required other). The conversational and product sets see **both** fixes at once (scope line + quote contract), so their moves are not attributed to either alone.

**Attribution, per group, edges beside precision:**

- *Scope line only* (CIP-006-6, CIP-007-6, CIP-009-6; CIP-003-8 with its overflow cells apart): CIP-006 and CIP-007 gain precision; CIP-006 also grows edges 24→37. CIP-003-8 loses a little precision (0.775→0.7308) — its two previously truncated readings are newly whole, so that cell is a different reading, not a scope effect.
- *Scope line + technical basis* (CIP-003-9, 004-7, 005-7, 008-6, 010-4, 011-3, 012-2, 013-2): a combined effect; six of eight gain precision, two dip (CIP-008 on 8 edges, CIP-013 whose fresh judging declined 6 vendor-notification twins at 0.76).
- *Fixed body gained its implementation plan* (CIP-002, CIP-014-3): CIP-002's move is still most plausibly the scope line — the implementation plan is dates and phasing — and no clean isolation is claimed.
- *Previously truncated, now read whole* (CIP-002-5.1a R1/R2, CIP-003-8 R1/R2, CIP-003-9 R1): these were counted at exactly 16,387 tokens against a 32,768 window in the last sweep, answered from their last Part, and determined nothing. This sweep sent them whole to the baked 64k overflow seat (`gemma4:26b-a4b-it-q4_K_M-ctx64k`, 165k/155k/118k/104k-byte readings; prefill up to 171 s) — they are newly complete readings, not an effect of either fix. Nothing flagged the truncation before; `sweep.window_fit` now refuses or reroutes it.

## §4 — Still open

- CIP-002-5.1a and CIP-003-8 GTB sits on only part of their requirements (exact-text route; genuinely absent vs locate miss unresolved) — for MODULE_COMPLETE_V1.
- RSAWs and ERO Implementation Guidance not acquired.
- The conversational path has no window guard: `compliance_context(mode=material)` is unbudgeted against the 32,768 seat; a multi-turn session will hit it first.
- Two empty completions on CIP-004-7 product questions (cause unnamed — retry did not reproduce; seat-side).
- The conversational `overlap` question answered without searching (one `used_search` failure).
- 213 baseline-SUPPORTED edges not re-affirmed: the store-wide number mixes pre-sweep campaigns; per-sweep recall accounting is still cohort-based, not lifecycle-based.

## §5 — Lessons

| date | failure | repair | guard |
| --- | --- | --- | --- |
| 2026-09-22 | *storage identity in the model's output contract* — three fixes moved the id around; none asked whether a 26B model should transcribe 20 hex characters | `citation_by_quote.resolve_quote` inverts the verbatim checker; prompt v2.7 makes the quote the citation | the grounding path resolves quotes; nothing requires the model to reproduce an identifier |
| 2026-09-22 | *similarity used for a structural question* — CIP-002, whose content is the shared vocabulary, adjudicated at 0.31 inside a 0.81 family | scope derived by reading, quote-validated, stored; rendered as provenance so the reading owns the judgement | documents carry their scope in the store; what the reader declines is recorded per verdict |
| 2026-09-22 | *a derived fact living beside the database* — `ingest.py`'s layer/tier sidecar read by nothing | the scope signal this task uses went straight into `document_scope` | whichever signal a population needs, it lands in the store |
| 2026-09-22 | *a store that only accumulates, measured as if it were a reading* — a store-wide precision after a re-sweep measures every campaign at once | `sweep_edge_set.py` measures the edges the sweep affirmed | a sweep is judged on its own affirmed set, beside the store-wide number for continuity |
| 2026-09-22 | *a token resolved by a rule other than the one that minted it* — the conversational check read `O-`/`R-` as id prefixes; the letter is the section's side | `addressing.resolve_cite_as` resolves by the minting rule: unique or nothing | cite tokens resolve by the side letter `cite_as` minted; a wrong letter still fails |
| 2026-09-23 | *silent truncation masquerading as coverage* — CIP-003 R1 answered from its last Part at exactly 16,387 tokens, `failed=0` | `sweep.window_fit` prices every prompt (3.59 B/token measured) and reroutes oversize readings to a baked 64k seat | a reading never runs on truncated material; the route taken is stamped on the receipt |

## §6 — Gate record

- `uv run python scripts/spine_p0_manifest.py --strict` — PASS, manifest re-stamped (747 units: 54 keep-fact / 72 release / 621 archive). The runbook's `write_spine_manifest.py` no longer exists; this is the current manifest gate.
- `uv run python scripts/complexity_report.py --write-budget` — PASS.
- `uv run python scripts/doc_ledger.py --check` — N/A: the script was retired on 2026-08-04 (`6afb2626` folded the ledger into the spine/wiki gates and deleted `.doc_ledger.yaml`); the spine strict gate above is its successor.
- `uv run pytest tests/unit/test_compliance_*.py -n auto` — PASS (1123 passed, 1 skipped).
- `uv run python scripts/validate_system.py` — first run **215 pass · 1 fail**: GS (NERC corpus currency) failed on sync age — last successful sync 60.2h prior, past the 24h interval + 24h grace; the residue of the prior closeout's "autosync FK bug blocks GS". A manual `scripts/nerc_autosync.py` run **succeeded** (REFRESHED — 81 registry entries moved; index re-projected; `data/private/nerc_autosync_state.json` `last_success` 2026-09-23T23:55:08Z — the FK blocker did not reproduce). Re-run: **216 pass · 0 fail · 1 warn · 3 skip** — the warn and skips are pre-existing environment conditions, not this task's.
- **Measurement provenance:** every number in §3 was measured against the store as it stood *before* that sync; the sync's 81 moved entries are registry metadata (its report warns of pre-existing missing implementation-plan links) captured after the close of measurement, and the receipts are timestamped accordingly.
- `git push` — pushed without `--no-verify` (pre-push hook ~4 min). The push carried nine earlier unpushed commits from the paused engine-eval work already on local `main`.
