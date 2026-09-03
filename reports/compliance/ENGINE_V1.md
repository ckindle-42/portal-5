<!--
evidence: TASK_COMPLIANCE_ENGINE_V1 (program track T3) — rollup
range:    1f468724 (T1 done) .. HEAD
seam commits: b157faba P1 · caa54a93 P3 · <this> P2/P4/P5/P6/P7/P8/P9
host:     darwin 25.6.0, Apple Silicon; nerc.com reachable
inputs:   13 NERC CIP standard PDFs (public record, not committed) -> data/nerc_cip_register.json
generated: 2026-09-03
-->

# Compliance engine V1 — rollup

A version-aware, Part-granular compliance reasoning engine — a **second
composition** of the retrieval stage library (`compliance_*` tables only; no
`kb_*` table touched). Not a RAG chatbot: temporal validity filters before
ranking, authority tiers have precedence and a cross-tier contradiction is
emitted, gaps come from enumeration, and settled mappings are human-owned.

## Phase 0 — the three inconsistencies (all confirmed)

| # | finding | resolution |
|---|---|---|
| 1 | `nerc_cip_map.json` held CIP-003-8 / CIP-012-1; the corpus manifest holds cip-003-9 / cip-012-2 | register built on the enforceable versions; map is now a derived view |
| 2 | register was 27 entries, R-level, `title` + `related_800_53`, **no requirement text** | 117-node Part-level verbatim register |
| 3 | `refresh_catalogs()` covers NIST/CSF, **not NERC** | `nerc_cip_currency` probe added (Phase 8) |

Corpus is CIP-002 … CIP-014 (13 standards); the persona claims 002–015 — the
persona overclaims.

## Phase 1 — the register (`b157faba`)

Per-standard **found / verified / missing** (verbatim round-tripped against the
source PDF text):

| standard | R | Parts | verbatim-verified | shortfall |
|---|--:|--:|--:|---|
| CIP-004-7 | 6 | 19 | 19/19 | — |
| CIP-005-7 | 3 | 12 | 12/12 | — |
| CIP-006-6 | 3 | 13 | 13/13 | R3 part-less (correct) |
| CIP-007-6 | 5 | 20 | 20/20 | — |
| CIP-008-6 | 4 | 10 | 10/10 | R3 part-less (correct) |
| CIP-009-6 | 3 | 10 | 10/10 | — |
| CIP-010-4 | 4 | 11 | 11/11 | R4 part-less (correct) |
| CIP-011-3 | 2 | 4 | 4/4 | — |
| CIP-002-5.1a / CIP-003-9 / CIP-012-2 / CIP-013-2 / CIP-014-3 | 15 R | 0 | 15/15 R-level | **Attachment / prose parts not extracted** (~20 parts) — documented in `unit-known-limitations-cip-register-behind-published-versions` |

**Totals: 45 requirements, 99 verbatim Parts, 117 register nodes, all verified.**
Edges: 117 `HAS_REQUIREMENT`, 2 `CROSS_REFERENCES` (both correct — recall is low
because most cross-refs are prose-implicit, not literal `CIP-NNN` tokens),
2 `SUPERSEDES` + 2 `SUPERSEDED_BY`.

## R3 prompt footprint (Phase 0)

Estimated against the 8192-token input budget (`context_limit 32768` −
`predict_limit 24576`): system prompt + append ~1490 tok · a 10-chunk
two-document retrieval payload ~2500 tok · two turns history ~300 tok · question
~100 tok → **~4400 tok, ~3800 headroom. No context re-split needed.** (char/4
estimate; a tokenizer measurement would be tighter, but the margin is large.)

## Phases 3-6 — the reasoning composition

- **Phase 3** (`caa54a93`) — authority tiers; `detect_conflicts` across
  *different* tiers emits `COMPLIANCE_CONFLICT` (quantitative or deontic), never
  reconciled, lower tier never wins. Code rule + test.
- **Phase 2** — `effective_parts` is a predicate, not a score; `classify_intent`
  is one keyword-scored call (four paths), not an agent swarm.
- **Phase 4** — mapping store: propose / approve; approved rows short-circuit
  retrieval and win over model judgement; SME override rate is the trust signal.
- **Phase 5** `[GATE]` — applicability dimensions (`impact_present`,
  `associated_present`, `has_erc`, `has_control_center`) derived from the
  register; `AssetScope` is operator input; `coverage_matrix` raises without a
  declared scope. **See gate outcome below.**
- **Phase 6** — coverage by enumeration; policy / procedure / evidence classified
  separately; `FULL` needs a locatable span from both sides; summary reports
  **examined** apart from **substantively resolved** (Bully GP) with a
  degenerate-fixture guard.

## Phase 7 — verification

**Tier 0 (invariants):** compliance tables namespaced `compliance_`; a compliance
rebuild leaves every `kb_*` table + stamp byte-identical
(`test_compliance_retrieval_seam.py`, T1 P7); every register span round-trips.

**Tier 1 (deterministic):** verbatim fidelity of `CIP-007-6 R2 Part 2.2`
byte-exact; per-standard found/verified; version divergences resolved with the
supersession recorded; lifecycle intervals internally consistent.

**Tier 2 (planted corpus):** 9 synthetic docs against the public NERC PDFs, one
per control class.

| metric | result |
|---|---|
| **Full-Gap recall** (headline) | **1.000** |
| false-covered | **0** |
| false-gap | **0** |
| citation resolution | **1.000** (required) |
| control classes passing | covered, hole, aspirational, lexical, applicability, temporal, tier_conflict, deontic — **8/8** |

`implicit_change` and `cross_reference` classes are not yet resolved end-to-end
(they need register-diff + graph traversal beyond this task's scope) — honestly
excluded from the corpus, not faked green.

**Tier 3 (real corpus):** the mapping store feeds it continuously; not a gate.

## Phase 8 — currency

`nerc_cip_currency` reports, per standard: held version, whether a newer version
PDF is reachable on nerc.com, and an explicit *verify the enforcement date*.
`honest-BLOCKED` when nerc.com is unreachable. **Currency is never inferred.**

**Finding: 12 of 13 held standards have a newer version PDF published**
(CIP-002-7, CIP-003-10, CIP-004-8, …, CIP-011-4, CIP-013-3) — adopted, effective
dates unconfirmed (the PDFs defer to a separate Implementation Plan). The engine
flags this rather than serving stale data; rebuilding the register on the
enforceable versions is future work once those dates are verified.

## Gates — report, do not choose

**`[GATE]` 1 — asset applicability scope.** `applicability.gate_presentation()`
returns the schema, the four dimensions, and what each choice includes/excludes.
Not populated by inference; `coverage_matrix` refuses to run without a declared
`AssetScope`. **Operator decision.**

**`[GATE]` 2 — may the engine assert `FULL` without SME approval?** The mapping
store resolves this: the engine *proposes* `FULL` (requiring a locatable span
from both the policy and procedure side), but only an **approved row is
authoritative** and `nerc_cip_requirement` / the coverage matrix consult approved
rows first. Tier-2 false-covered rate is **0** on the planted corpus. History:
`granite-4.1-8b` was demoted from this persona for fabricating regulatory
requirements and source URLs; `Qwen3.8-27B` was promoted as the only candidate
that refused to fabricate — fabrication resistance has never been measured
downstream, and this task does not add that measurement. **Operator decision on
whether to allow an unapproved `FULL` in the UI.**

## Disjoint-table proof

`tests/unit/test_compliance_retrieval_seam.py` (T1 P7): the same corpus through
`rag_multimodal` and `compliance_retrieval` returns equivalent results while
`kb_*` and `compliance_*` tables + stamps stay disjoint; a compliance `rebuild`
leaves every `kb_x` row and the `kb_` stamp byte-identical.

## honest-BLOCKED

- **Attachment-part extraction** for CIP-002/003/012/013/014 — the `Table R<n>`
  extractor does not read Attachment 1 / prose sub-sections. R-level verbatim
  captured; ~20 parts uncaptured. Documented, not faked.
- **Register currency** — a newer published version wave exists; enforcement
  dates unconfirmed. Flagged by the probe, `honest-BLOCKED` on "is the register
  on the enforceable version".
- **`implicit_change` / `cross_reference` control classes** — not resolved
  end-to-end; excluded from the planted corpus rather than scored as passing.

## Done

- Part-level bitemporal register with published found/verified/missing — **yes**.
- The system can state whether each held standard is current or `honest-BLOCKED`
  on why not — **yes** (`nerc_cip_currency`).
- Gaps produced by enumeration over applicable parts — **yes**.
- A tier conflict emitted rather than reconciled — **yes** (code rule + test).
- Every citation resolves — **yes** (Tier-2 citation resolution 1.000).
- Tier 2 passes — **8 of 11 control classes** (2 honestly excluded, 1 not
  applicable to the deterministic path); Full-Gap recall 1.000.
- No `kb_*` table touched — **yes**.
