# LOAD_AND_CONVERSE_V1 — the corpora were never the problem; the proposals were

**Date:** 2026-09-22 · **Base:** `e776b3a9` (PROVE_THE_MODULE_V1 close) · **Close:** local `main`, this document
**Follows:** PROVE_THE_MODULE_V1 — 183 edges at 0.7705, six standards diagnosed, engine and seat settled

---

## §0 — The frame

This task named one architecture-level gap (the retrieval projection) and three defects, and stated every causal claim as a hypothesis. The projections were traced first, and the headline hypothesis died cleanly: **all four corpora were already in the store, already in the index, and answered live probes** (`p1/projection_census.json`, `n_gaps = 0`). The 121 empty populations were never a projection gap. They were a **proposal gap**: `requirement_queries` — the function that turns register identities into search queries — stopped at requirement level for every standard whose capture has no duty table, so `build_links` proposed against `R1` while the register's `R1 Part 1.1 … R1 Part 1.9` got no query, no proposal, and therefore an empty population *by construction*, whatever the index held. CIP-007-6 was healthy precisely because its duty table yields Part-level queries. That was the 121.

The rest of the file's predictions mostly held; where evidence contradicted them, the divergence is recorded in the phase it occurred in.

## §1 — The projection census, and the gate hole

The census measured, per corpus: sections in the store, sections in the manifest, manifest status, and a **live probe** (a real search), because a manifest is not proof the index answers.

| corpus | store | manifest | status | live probe |
| --- | --- | ---: | --- | ---: |
| operator_corpus | 2636 | 2568 | FRESH | 3 |
| nerc_corpus | 7195 | 6833 | FRESH | 3 |
| operator_notes | 1 | 1 | FRESH | 1 |
| conversation | 8 | 8 | FRESH | 3 |

`n_gaps = 0`. After the §P3 re-projection the census was re-run: every corpus FRESH with non-zero live hits, and the store's projectable section counts (2568 / 6833 / 1 / 8) now match the index exactly.

**The gate hole was real anyway.** `retrieval_projection_status` excluded an ABSENT corpus with no recorded section count from the overall verdict, and a manifest-only check cannot distinguish *genuinely empty* from *unprojected*. P1.2 closed it: the status now carries the store's projectable section count per jurisdiction and reports **UNPROJECTED** — computed against the store, never only the manifest — and GS's failure message names the corpus and both counts. Unit tests pin the verdict (`test_compliance_temporal_projections.py::TestRetrievalProjectionStatus`). GS passed before this change and passes after it; the hole is closed for the day the store and index actually diverge.

Divergence recorded: the census's GAP test counts raw `source_sections` rows; the gate counts *projectable* rows (`char_start >= 0`). Pre-capture rows are a second extraction of bytes the capture already covers — `build_plan` classifies them superseded, never eligible — so counting them would make the gate fire on corpora with nothing to project.

## §2 — One projection path

`rebuild_compliance_projections.py` called `ingest_folder` — the path BILATERAL_CORPUS_V1 P4.4 marks DEPRECATED for building sha1 chunk ids — while GS's own remediation line pointed at `project_compliance_sections.py`. Fixed:

- the rebuild script's retrieval stage now runs `project_sections` for every jurisdiction in `CORPUS_FOR_JURISDICTION` (acquisition via `ingest_folder` is an explicit, optional `--corpus` step that always precedes re-projection);
- `ingest_folder` **raises** when called from a projection context (`_PROJECTION_IN_FLIGHT`), so the deprecated path can never write beside or after a section projection;
- the script records ONE retrieval manifest (the projection's own), plus the graph manifest as before, and proves materialization with a live search per corpus.

The identity assertion ran **before** the re-projection: every sampled `chunk_id` in all four corpora resolves to a canonical section (`p2/one_projection_path.json`, verdict PASS) — the deprecated path had not contaminated the live tables. The §P3 re-projection re-asserted it after.

## §3 — What the 121 actually were

`requirement_queries` now fills every register node it missed from the **Register's own verbatim text** (table rows still win where they exist), and strips the trailing space the prose fallback used to leave inside refs. `record_links` **persists absence where it is computed** — a `requirement_absence` row (migration 19) per ref whose latest run proposes nothing, deleted when a later run proposes — so *searched and found nothing* is finally distinguishable from *never searched*. `scripts/compliance/family_links.py` then ran `build_links` across all 14 register standard revisions against the whole projected operator corpus:

**317 requirements queried, 1288 edges proposed, 1 absence** (`p3/family_links.json`) — and the re-diagnosis (`p3/population_recovery.json`):

| standard | empty_population | below_threshold | no_operator_document |
| --- | --- | --- | --- |
| CIP-002-5.1a | 32 → **0** | 0 → 1 | 0 |
| CIP-003-8 | 36 → **0** | 0 | 0 |
| CIP-003-9 | 40 → **0** | 0 | 0 |
| CIP-012-2 | 5 → **0** | 0 | 0 |
| CIP-013-2 | 8 → **0** | 0 | 0 |
| CIP-014-3 | 0 → **0** | 0 | 17 → **0** |

**empty_population 121 → 0.** The one remaining `below_threshold` is a real, persisted absence (a CIP-002-5.1a Part whose best candidate scored under the calibrated 0.5 threshold). The remainder of the six standards flipped to `reading_failure` — material now in front of the seat that had never been read — which §P6's re-sweep then read. The threshold was not touched.

## §4 — The conversational proof

Fourteen questions naming no requirement address, through `compliance-reading` on the deployed stack (`scripts/compliance/ask_conversational.py`): the twelve drawn in the task file plus two added and argued in the receipt — a vocabulary bridge (*records* vs *evidence*) and a cross-revision CIP-003 ask (the store keeps history answerable by design).

The retrieval path took three runs to land honestly, and each run changed the product:

- **Run 1 (5/14, search used 11/14)** — the instrument's own first version failed two real answers: the harness judged *invented coverage* by the store's link graph, and the graph is sparse by construction — the operator's CIP Cyber Security Policy genuinely covers physical security perimeters (verified: `isection-5a5ab9d236fe29d84230`, "Physical Security Plan (R1)" with the exact duties the answer quoted) with **no recorded edge anywhere**. Verdict instrument rebuilt; the task file's own absence premise was partially wrong for that topic and the receipt says so.
- **Run 2 (8/14, search 13/14)** — prefix resolution added to the answer contract: run 1's dominant unresolved tokens were *truncated* ids (`csection-440a5c`), the seat keeping the id's prefix and dropping the tail; a prefix resolves when it names exactly one section, never when ambiguous. The search-first prompt rule (v2.5 rule 3b) landed after run 1 caught three cross-cutting questions answered without `compliance_search`.
- **Run 3 (8/14, search 14/14, invented coverage 0)** — final state. The product gap (retrieval not exercised) is closed; **every remaining failure is seat citation copy-fidelity**: the seat deterministically corrupts 20-hex ids mid-hash across independent runs (`isection-4a7915037c2d923d58e` typed three runs running for the real `…503c7c2…`), even with the short `[cite O-xxxxxx]` header riding the text (prompt v2.6) — it mimicked the header's *form* while still typing corrupted long ids. Per §0.4's non-negotiable, no unresolved id was ever mapped to a near neighbour to make it resolve: store-wide fuzzy matching is exactly the forbidden repair, so the claims stay ungrounded and the failures stay failures.

**§Done 4 verdict:** retrieval is exercised by every conversational question (14/14 `compliance_search` calls, 30–90 s turns, retrieval itself in milliseconds), both sides are cited on the relational questions, and honest absence holds (0 invented coverage — both absence answers found real operator coverage or named the gap with resolving citations). The pass criterion of *every citation resolving* is met on 8/14; the residual is a measured seat defect, not a retrieval or honesty defect — and it prices into `ready_for_use`.

## §5 — The three defects

**The tool loop returns empty on two questions — resolved, with two named causes.** The harness counter fix (`pipeline_errors`) had already landed in PROVE_THE_MODULE_V1; this task added the error body to the router's empty-completion log (backend, model, last SSE frame) at both sites, then reproduced. The two turns behave differently:

- *CIP-002-5.1a exceedance*: the old transcript shows 18 blind `compliance_read` calls and a 63-char non-answer — the seat hunting for operator material that **did not exist because the population was empty**. §P3's family-wide projection removed the cause; the re-run passes.
- *CIP-007-6 exceedance*: the old transcript died at hop 7 with `finish_reason=tool_calls` and zero content — the malformed-tool-call bail. It did not recur in the re-run (50 s, normal tool loop, PASS), and **zero `empty_completion` was recorded across all 15 re-run turns**. Recorded honestly: cause named from the old evidence, fix (logging) in place, non-reproduction measured rather than assumed.

**The grounding check is stricter than the product — fixed, per-claim.** `AnswerContract.cited_claims` judges claim units (answer lines): a claim is grounded when it cites a resolving token — full id, `cite_as` token, or a unique prefix — or when its only unresolved tokens are mistyped restatements of ids that resolved elsewhere in the same answer. The strict half is unchanged: a claim standing only on a citation that resolves to nothing fails, and no unresolved id is ever mapped onto a near neighbour (absorption only applies against support that *already resolves in the answer*; the measured CIP-007-6 typo is 3 dropped characters). Wired into both harnesses; unit-tested including the measured case.

**The handle contract holds on one surface — widened, then measured twice more.** `addressing.provenance` (every tool payload that yields a section: search, read, coverage) now carries `cite_as` (side letter + 6-hex, deterministic per section), and `with_cite_header` prepends `[cite O-xxxxxx]` to the text the seat actually copies from; the prompt (v2.4→v2.6, both artifacts) teaches the token. Measured: run 2 (token in a JSON field) — the seat ignored it; run 3 (token on the text) — the seat copied the header's form but still corrupted the long id. The test the task set — *count how many citations are handles* — therefore reads: the long-id habit survives both mitigations on this seat, and the residual failure mass in §P4/§6 is exactly that defect.

## §6 — Family precision, before and after

Every reading-derived edge — the 183 plus whatever is new — re-adjudicated by reading (requirement text, section text, cited sentence, against the relation):

**183 @ 0.7705 → 366 @ 0.8142**

| standard | n | precision |
| --- | --- | --- |
| CIP-002-5.1a | 0 → 29 | — → 0.3103 |
| CIP-003-8 | 3 → 42 | 0.667 → 0.786 |
| CIP-003-9 | 3 → 41 | 1.000 → 0.854 |
| CIP-004-7 | 42 → 45 | 0.833 → 0.911 |
| CIP-005-7 | 10 → 15 | 0.600 → 0.667 |
| CIP-006-6 | 23 → 24 | 0.783 → 0.833 |
| CIP-007-6 | 38 → 41 | 0.737 → 0.878 |
| CIP-008-6 | 18 → 20 | 0.722 → 0.900 |
| CIP-009-6 | 11 → 11 | 0.455 → 1.000 |
| CIP-010-4 | 19 → 22 | 0.947 → 0.818 |
| CIP-011-3 | 10 → 10 | 0.700 → 0.900 |
| CIP-012-2 | 0 → 8 | — → 0.875 |
| CIP-013-2 | 2 → 29 | 1.000 → 0.897 |
| CIP-014-3 | 4 → 29 | 1.000 → 0.862 |

The predicted "precision falls as the family fills" happened only in the aggregate denominator sense: thirteen of fourteen standards are ≥ 0.67 and eleven are ≥ 0.83. The outlier is **CIP-002-5.1a (0.31)**, and the cause is readable in the verdicts: its Attachment-1 nodes are *criteria definitions* ("Control Centers and backup Control Centers", "Low Impact Rating (L)"), and the reranker matched operator sections on asset-class vocabulary — key management at control centers, redundant data exchange between control centers — where the operator section performs an unrelated duty on the named asset class. Sixteen of its twenty unsupported edges are that shape. This is a proposal-quality finding for the criterion-node shape, not a reading failure, and it is the highest-value target for the next calibration (per-standard thresholds or criterion-node query shaping) without touching the global 0.5.

**Product proof re-runs:** the fifteen named-requirement questions (`p6/product_questions/`): **12/15**, with **both formerly-empty exceedance turns passing** and zero `empty_completion` recorded. The three failures are `coverage_gap` on CIP-004-7, CIP-010-4, CIP-003-8 — the first two share a newly named defect: the seat quoted **CIP-007-6 patch-management material inside other standards' coverage answers** (cross-standard contamination, deterministic in this run), plus the one deterministic garbled citations-list id on CIP-010-4.

**`ready_for_use: false`** — computed from both product proofs as required. The register path is strong (12/15, precision 0.81 family-wide over double the evidence), the conversational path now demonstrably works (retrieval exercised 14/14, honest absence, zero invented coverage), and neither proof is green end-to-end. The two named blocks are seat citation copy-fidelity (§4/§5) and coverage_gap cross-standard contamination (§6); both are seat/model-surface defects with receipts, not substrate or corpus defects.

## §7 — Still open

1. **Seat citation copy-fidelity** — 20-hex ids are corrupted mid-hash deterministically; survives both cite-token mitigations. Next lever if pushed: make the short token the *only* citable string in tool text (id resolvable from the token downstream), or a seat that copies better.
2. **Coverage_gap cross-standard contamination** — CIP-004-7/CIP-003-8 coverage answers quoted CIP-007-6 patch material. Material-tool scoping question, seat-side; one run's evidence, needs its own diagnosis.
3. **Criterion-node proposal quality (CIP-002-5.1a 0.31)** — Attachment-1 criterion definitions attract asset-class-vocabulary edges; per-standard or per-node-shape calibration, priced by the next adjudication.
4. **A live probe inside the gate** — GS now computes against the store, but a corpus whose *Lance table* is empty under a FRESH manifest is still only caught by the census's probe. Not observed; recorded as the remaining manifest-trust surface.

## §8 — Lessons

- **2026-09-22 | a gate that excludes the failure it should catch** — "nothing to project is a state, not a drift" is right for an empty corpus and wrong for an unprojected one, and the two are indistinguishable to a manifest-only check; GS passed throughout. **Guard:** status computed against the store's projectable section count, with unit tests pinning UNPROJECTED.
- **2026-09-22 | the query builder, not the index, was the bottleneck** — three campaigns diagnosed the 121 downward (corpus, projection, embedding) while `requirement_queries` silently stopped at requirement level for any standard without a duty table; the register carried the Part identities all along. **Guard:** `requirement_queries` fills from the Register, and `requirement_absence` makes *never searched* a persisted, queryable fact.
- **2026-09-22 | proving the register path and calling it the product** — every product question ever asked named a requirement; the retrieval surface the module exists for was wired and never exercised. **Guard:** §P4 requires `compliance_search` to have been called, read from the router's own counters.
- **2026-09-22 | a grounding check stricter than grounding** — a redundant mistyped duplicate failed an answer in which every claim was supported. **Guard:** per-claim, mistyped restatements of in-answer resolving citations absorbed, and an unresolved id with no resolving counterpart still fails — never mapped to a near neighbour.
- **2026-09-22 | the instrument failed before the product did** — the first conversational run called honest coverage "invented" because the link graph was the arbiter; the graph is sparse by construction and the operator's policy genuinely covered the topic with no edge recorded. **Guard:** mechanical rules judge *identity* (does the section resolve), readings judge *support* — and the reading is recorded.
- **2026-09-22 | a copied token is a product surface** — the seat corrupts 20-hex ids mid-hash deterministically; putting the short token in a JSON field changed nothing, putting it on the text changed the form but not the habit. **Guard:** citation-fidelity counts in every re-run receipt, so a seat change is priced against a measured baseline.

## §9 — Gate record

Every phase commit passed its pre-commit gate (gitleaks, ruff lint/format, portal.yaml validation, unit suite) before landing — commits `7ee069f4` through this close, no `--no-verify`, no forced push. Final gates at close:

- `python3 -m portal.platform.wiki.coverage --write-manifest` — PASS (the task's `scripts/write_spine_manifest.py` does not exist in this repo; this is its real replacement, as recorded in PROVE_THE_MODULE_V1 §8).
- `python3 scripts/complexity_report.py --write-budget` — PASS (ratchet re-stamped for the new instruments).
- `scripts/doc_ledger.py --check` — does not exist in this repo; skipped, recorded rather than silently omitted.
- `uv run python scripts/validate_system.py` — run at P1.2 close: 214 pass / 1 fail (complexity ratchet, cleared by the re-stamp above) / 1 warn (pre-existing BIN hunt record) / 3 skips (pre-existing).
- `uv run pytest tests/unit/test_compliance_*.py -n auto` — PASS.
- `git push` — performed per the task's explicit gate, NOT forced.

Divergences from the task file, all recorded: `.zcodeignore` (harness-local, untracked) gitignored so the preflight clean-tree check could pass; `project_compliance_sections.py` has no `--all --rebuild` flags because it already projects every jurisdiction with rebuild by default; the census's GAP test and the gate's UNPROJECTED test use different store counts (§1); two questions added to the §P4 floor with reasons in the receipt; the absence-judgment instrument changed after run 1 (§4).
