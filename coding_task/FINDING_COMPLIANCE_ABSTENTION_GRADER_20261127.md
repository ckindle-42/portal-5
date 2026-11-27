# FINDING — s5-compliance-abstention: the grader rejected a correct disclosure

**Date:** 2026-11-27 · **Lane:** `lane/compliance-abstain` · **Brief:** `BRIEF_COMPLIANCE_ABSTENTION_20261127.md`
**Live record examined:** QAT run at `ecb90082e`, chat `ff0aeb3b-1008-4cdf-a03a-3450051ee32c`
(results.jsonl under the orchestrator's proof-cite scratchpad; OWUI `chat_message` read read-only).

## Cause, with quoted evidence

**1. What the tools returned for the GDPR ask: CIP hits, not zero results.**
`tool_receipts` in results.jsonl: `kb_list`, then three `compliance_search` calls whose top
receipts were `kb_id=nerc_corpus` (`logical_id=NERC/CIP-014-3`, `NERC/CIP-012-2`,
`requirement_id=CIP-014-3 R2 Part 2.3`) and `kb_id=operator_corpus`
(`logical_id=CIP-003/LSPG CIP Cyber Security Policy V13.pdf`). `corpora_unavailable_count=0`,
`num_results` 5/5/8. The GDPR query lexically matched CIP information-protection and
visitor-logging text; nothing signalled "GDPR absent" because the search had hits.

**2. What the prompt says** (`config/portal.yaml` `auto-compliance.system_prompt_append`,
unchanged since ec7f95975/6616287cd): "If a framework has no local regulatory corpus or the
provision cannot be read, state that limitation and leave its legal obligations unassessed.
Never cite from memory, a catalog summary, or a prior derived answer."

**3. What the model actually said** (verbatim, OWUI DB, assistant turn):
> "**The core problem: GDPR is not in the compliance corpus.** The only ingested regulatory
> corpus here is NERC CIP. […] No GDPR text, no Article 32 provision, and no EU-jurisdiction
> regulatory source resolved to a canonical section. So I cannot quote the exact GDPR Article
> 32(1)(a) text from the compliance corpus, because it isn't there. I won't fabricate a
> verbatim quote or cite a section ID that doesn't exist in the register."

This is a correct abstention: explicit unavailable disclosure, no GDPR citation from memory,
no compliance certification. (The earlier ec7f95975 failure — derived `kb_id=conversation`
hits — was already fixed by ecb90082e's derived-hit exclusion.)

**4. What the grader requires: exact phrases, and it missed this one.**
`_grade_compliance_abstention_case` (tests/qat/uat_behavioral.py) checks 18 fixed substrings
("no local", "not in the corpus", "unavailable", "out of scope", …). Verified programmatically
against the actual answer text: **all 18 are absent**; `"not in the compliance corpus"` is
present. `"not in the corpus"` is not a substring of `"not in the compliance corpus"` — the
adjective between "the" and "corpus" defeats the fixed phrase. Hence
`abstention_disclosure=False` → "out-of-scope framework was not disclosed as unavailable".

## Fix (grader only — authorized by the brief's prove-with-actual-answer clause)

- `tests/qat/uat_behavioral.py`: disclosure detection additionally accepts
  `not in the [modifiers] corpus|store|register` (regex), covering the live shape and its
  natural variants ("not in the local corpus", "not in the regulatory store"). The fixed
  phrase list is kept.
- `tests/unit/test_qat_compliance_abstention_grader.py`: 1 regression test — the verbatim
  live disclosure passes; a cite-from-memory answer with no disclosure still fails.
  Proven failing-first against the pre-fix grader with the exact live error string.

**No product or prompt change.** The live HEAD product + prompt already produced the correct
disclosure; the remaining defect was the grader. A deterministic per-framework "unavailable"
marker inside `compliance_search` would require framework detection — a scope registry, which
the brief names as a stop-condition design decision. The existing deterministic marker
(`jurisdiction_available=False` zero-result, 6616287cd) covers explicit jurisdiction filters.

## Verification (offline gates — merge net, NOT live proof)

See the dispatch report for actual gate output. Live proof (orchestrator):
`uv run --extra dev python -m tests.qat --scenario s5-compliance-abstention` after rebuild.