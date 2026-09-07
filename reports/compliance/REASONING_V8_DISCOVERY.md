# REASONING_V8_DISCOVERY — D0

`PROGRAM_COMPLIANCE_CLOSEOUT_V1` · V8 phase D0 · run
`coding_task/v9_compliance/private/runs/V8_20260907T012843Z/` · repo HEAD `d37fcc65`
· 2026-09-07

D0 verifies the ten findings in `TASK_COMPLIANCE_REASONING_V8.md` "The diagnosis" against
HEAD, censuses the corpus, and projects the P1 reading cost against a measured per-unit
seat cost. GATE 1 verdict at the end.

---

## 1. Diagnosis dispositions (D0.1 – D0.10)

| # | Finding | Verdict | Proof |
| --- | --- | --- | --- |
| D0.1 | The reading is still rules; one model call site in the whole module | **CONFIRMED** | `grep -rn "ollama\|/api/chat\|AsyncClient\|generate("` over `core/` + `tools/` → the only inference call is `core/council.py:192` inside `_ollama_seat` (`council.py:175`). `planner.py` has a `planner_fn` seam (`planner.py:112,114`) but its only implementation is `classify_question` (regex). No call site in `policy_graph.py` / `org_graph.py` / `cip_extract.py`. |
| D0.1a | `policy_graph.py` decomposes with regex | **CONFIRMED** | `_MODAL` (48), `_IMPERATIVE` (54), `_ENUMERATING_LEAD` (73), `_META` (81), `_TOPIC_LABEL` (92), `_DEF_LEAD` (97), `_ROLE` (477), `_SECTION_LEAD` (483), `_QUANTITY_SPAN` (484), `_COND_RE` (500). Typing decided by `_classify` at `policy_graph.py:188-218` — `explicit_modal` / `imperative_fragment_under_modal_parent` / `mandatory_enumerated_element` are literal branch labels on regex matches. |
| D0.1b | `org_graph.py` builds the org side with regex | **CONFIRMED** | `_HEADING`, `_NUMBERED`, `_MODAL`, `_OPERATIONAL`, `_CADENCE`, `_ROLE_RE`, `_EVIDENCE_RE`, `_SYSTEM_RE`, `_classify_document(title, header)` and a sentence splitter — all present in `org_graph.py`. No inference call. |
| D0.2 | The judgment has no field structure | **CONFIRMED** | `determination.py:61-84` defines `FIELDS` (ten) and `determination.py:91` `FieldResult`. `council.py` `SeatOpinion` / `CouncilResult` carry only `determination`, `cited_refs`, `confidence`, `rationale` (`council.py:60-90`). No `FieldResult` is ever constructed by the council. Q03 `[X]` (PARTIAL naming the removed condition) therefore not producible. |
| D0.3 | Nothing is persisted; the CHECK layer never fires | **CONFIRMED** | `Repository.record_claim` at `repository.py:340` has **zero callers** in `core/` or `tools/` (`grep -rn "record_claim"`). `compliance_analyze` accumulates into `_ANALYSIS_JOBS` module dict (`tools/compliance_mcp.py:1113`, written at `:1196`, read at `:1129`). No `analysis_runs` / `claims` / `claim_evidence` / `findings` row is written on the V6 path. Migration 6 CHECK constraints are bypassed, not triggered. `run_id` does not survive a restart. |
| D0.4 | Three determination vocabularies coexist | **CONFIRMED** | `coverage.py` / `mapping_store.py` / `models.py`: FULL/PARTIAL/NONE/NOT_APPLICABLE/NEEDS_REVIEW/UNRESOLVED (tuple constant). `determination.py:27-33`: SUPPORTED/PARTIAL/CONTRADICTED/ABSENT/UNRESOLVED (dataclass + SQLite CHECK). `council.py:36`: `_DETERMINATIONS = (...,"INSUFFICIENT")` plus ESCALATE / NOT_APPLICABLE in `operations.py`. `INSUFFICIENT` is never mapped to `UNRESOLVED`+code. `compliance_gaps` still serves the legacy coverage engine. |
| D0.5 | `ABSENT` is a seat's guess about corpus completeness | **CONFIRMED** | `council.py:54` `_SEAT_SYSTEM`: *"ABSENT = the packet is complete and no candidate addresses the unit."* The `ReadingReceipt` / `boundary.py` completeness proof (`boundary.py:74`) is not consulted in `judge()`. |
| D0.6 | Cite-or-drop is a bidirectional substring match | **CONFIRMED** | `council.py:150-152` `_ref_in_allowlist` — `r == a.lower() or r in a.lower() or a.lower() in r`. `"1.1"` matches `CIP-002-5.1a Attachment 1 Part 1.1`; `"CIP"` matches almost anything. Citations are node IDs; the per-field `char_span`s Y02 verifies are never what a determination cites. |
| D0.7 | `compliance_compare` does not interpret | **CONFIRMED** | `tools/compliance_mcp.py:1219-1220` `compliance_compare` returns `{"raw_diff": rows, "interpreted_delta": rows}` — same object, two keys. `operations.diff` change-taxonomy classifier not called. |
| D0.8 | The planner is regex with a silent `Q01` fallback | **CONFIRMED** | `planner.py:100-104` `classify_question`: `return best if scores[best] else "Q01"`. "Do our procedures line up with CIP-007-6 R2?" scores 0 on Q03 cues → silent Q01. `planner_fn` seam exists (`planner.py:112`) and is unused. |
| D0.9 | The corpus stops at the requirements tables | **CONFIRMED** | Register: 254 nodes, 99 with `source_pages`; ranges are the Table R# pages only (CIP-007-6 7–25 of 51). No Guidelines and Technical Basis / Rationale / Compliance-section / Supplemental nodes. `completeness.n_missing == 0` for all 14 because the denominator is `document:enumerated-list`, not document extent. `measure_text` reaches the packet as `cu.context` and no consumer reads it. |
| D0.10 | Y25 grades a proxy | **CONFIRMED** | `prose-cip-07`'s answer is already in the graph as ~70 typed `CIP-002-5.1a Attachment 1` nodes that `resolve()` returns. Y25 is a chunk-rank contest; the distractor beating it is applicability boilerplate the graph already types `meta_cu`, a signal the retrieval layer never uses. (Verifier currently: Y25 FAIL, prose-cip-07 rank 2.) |

All ten confirmed. Nothing in "What V6 actually landed" is disturbed.

---

## 2. Corpus census

### 2.1 Governing side — 14 NERC CIP standards

| Standard | PDF pages | Register nodes | Nodes w/ `source_pages` | Covered range | Unread sections |
| --- | --- | --- | --- | --- | --- |
| CIP-002-5.1a | 37 | 33 | yes | ~1–20 (incl. Attachment 1) | Guidelines & Technical Basis, Rationale |
| CIP-003-8 | 59 | 39 | partial | tables + Attmts | G&TB, Supplemental Material (large) |
| CIP-003-9 | 27 | 44 | partial | tables + Attmts | G&TB |
| CIP-004-7 | 31 | 19 | yes | ~5–16 | G&TB, Rationale |
| CIP-005-7 | 17 | 12 | no | — | all non-table pages; **no source_pages** |
| CIP-006-6 | 27 | 14 | yes | ~6–12 | G&TB, Rationale |
| CIP-007-6 | 51 | 20 | yes | 7–25 | G&TB (26–48), Rationale, Compliance §, Measures column |
| CIP-008-6 | 20 | 11 | no | — | **no source_pages** |
| CIP-009-6 | 20 | 10 | no | — | **no source_pages** |
| CIP-010-4 | 29 | 12 | no | — | **no source_pages** |
| CIP-011-3 | 14 | 4 | no | — | **no source_pages** |
| CIP-012-2 | 6 | 6 | partial | — | — |
| CIP-013-2 | 10 | 11 | partial | — | Rationale |
| CIP-014-3 | 36 | 19 | partial | tables + Attmts | G&TB |

Totals: **384 PDF pages**, 254 register nodes, **99** with `source_pages`, **6 standards
record none** (CIP-005/008/009/010/011 confirmed; the finding's "six" also counts one
partial). Register verbatim fidelity 254/254. Estimated **~250 of 384 pages currently
yield no node** (guidance/rationale/compliance/supplemental).

In-text structural features on `verbatim_text`: permission/alternative language 19,
prohibition/exception 22, explicit cross-reference ~45 distinct-target (63 with loose
regex incl. self-refs). Zero `REFERS_TO` edges resolved into the register today (edges are
`HAS_REQUIREMENT` only).

### 2.2 Internal side — LSPG-CIP corpus

- **68 PDF documents, 864 pages**, mean 12.7 pp/doc, organised in 13 folders
  `CIP-002 … CIP-014` (per-folder: 002×1, 003×3, 004×11, 005×15, 006×5, 007×10, 008×2,
  009×7, 010×7, 011×2, 012×1, 013×3, 014×1). Matches `closeout_manifest.json`
  `expected {standards: 13, documents: 68}`.
- Largest: `OT Security Incident Response V14` 46 pp, `LSPG CIP Cyber Security Policy V13`
  28, `LSPG Security Patch Management Work Instruction v7` 26.
- Document classes in filenames: Policy / Procedure / Work Instruction / Plan / Program —
  the hierarchy `org_graph` must type from the control block, not the filename.

### 2.3 Supporting documents held separately by the operator

Not in the tree; the operator holds these and they are **out of scope for P1's read**
unless supplied: RSAWs (Reliability Standard Audit Worksheets), Implementation Plans,
ERO-endorsed Implementation Guidance, FERC orders. `tiers.py` Tier 1 slot
`implementation_plan_rsaw_guidance_ferc_order` exists and is empty; P1c populates it only
from material actually present (the standards' own Guidelines and Technical Basis and
Supplemental Material sections).

---

## 3. Reading-cost projection for P1

**Measured unit cost.** Seat `hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M-ctx32k` (current
`auto-compliance`), `think:false`, `temp 0`, warm:

| call | prompt tok | gen tok | gen tps | wall (warm) |
| --- | --- | --- | --- | --- |
| CIP-007-6 Part 2.3 CU decomposition | 203 | 207 | 12.5 | **18.2 s** |

Cold first call 31 s (load 0). Steady-state **~18 s / Part-level extraction call** on this
seat; the 27B Qwen runs 12–13 tps on this box.

**Projection (single-seat sequential):**

| Phase | Units | s/unit | Subtotal |
| --- | --- | --- | --- |
| P1a — register CU decomposition | 254 nodes | 18 | 76 min |
| P1a — 2-seat disagreement sample (~25%) | +64 | 18 | +19 min |
| P1b — org extraction | ~580 docling sections (864 pp ÷ ~1.5) | ~30 (longer sections) | ~4.8 h |
| P1c — whole-document standard read | ~380 calls (~250 unread pp + per-Part measures/rationale) | ~25 | ~2.6 h |
| **P1 total** | | | **≈ 9 h** |

On a faster seat (`mistral-small3.2:24b-q4_K_M`, ~2–2.5× tps on this box) P1 ≈ **3.5–4.5
h**. Two-seat cross-check on the full set, not just the sample, roughly doubles the
relevant sub-phase.

**Budget fit.** P1 is a multi-hour unattended inference sweep, not interactive. It fits as
a background sweep (checkpointed, resumable) on either seat. The full read is **feasible**
— no scoped alternative is invoked. Sequencing: run P1a first (cheapest, unblocks P3/P5
field verdicts and the Y21 re-attribution), P1b and P1c can share wall-clock with P2/P3
per the program's "P4 can run in parallel" note but P1b/P1c must land before P5.

---

## 4. GATE 1 verdict

**PASS — the projection is real and the full read fits the budget.**

- Per-unit cost measured on the live seat (18 s warm), not assumed.
- Corpus census complete: 384 governing pages / 254 nodes / 6 standards missing
  `source_pages`; 68 internal docs / 864 pages.
- P1 projected at ~9 h single-seat (Qwen 27B) or ~4 h (mistral 24B), as a resumable
  background sweep.
- No scoped alternative required. Operator is notified that P1 is a long sweep; the three
  genuine operator decisions (scoped-read acceptance, phi4 seating, SME sign-off) are
  untouched — only the first is settled here (not needed).

Proceed to P1.
