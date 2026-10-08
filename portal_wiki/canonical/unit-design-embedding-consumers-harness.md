---
id: unit-design-embedding-consumers-harness
kind: mixed
title: "EmbeddingGemma 2 per-consumer measurement harness"
sources:
- type: code
  path: tests/benchmarks/embedding_consumers/__init__.py
- type: code
  path: tests/benchmarks/embedding_consumers/__main__.py
- type: code
  path: tests/benchmarks/embedding_consumers/cli.py
- type: code
  path: tests/benchmarks/embedding_consumers/framework.py
- type: code
  path: tests/benchmarks/embedding_consumers/gen_media.py
- type: code
  path: tests/benchmarks/embedding_consumers/probes/__init__.py
- type: code
  path: tests/benchmarks/embedding_consumers/probes/_common.py
- type: code
  path: tests/benchmarks/embedding_consumers/probes/attack_mapping.py
- type: code
  path: tests/benchmarks/embedding_consumers/probes/bully.py
- type: code
  path: tests/benchmarks/embedding_consumers/probes/compliance.py
- type: code
  path: tests/benchmarks/embedding_consumers/probes/harmful_intent.py
- type: code
  path: tests/benchmarks/embedding_consumers/probes/hygiene.py
- type: code
  path: tests/benchmarks/embedding_consumers/probes/media.py
- type: code
  path: tests/benchmarks/embedding_consumers/probes/memory.py
- type: code
  path: tests/benchmarks/embedding_consumers/probes/rag.py
- type: code
  path: tests/benchmarks/embedding_consumers/probes/refusal_classifier.py
- type: code
  path: tests/benchmarks/embedding_consumers/probes/router.py
- type: code
  path: tests/benchmarks/embedding_consumers/probes/seccode.py
- type: code
  path: tests/benchmarks/embedding_consumers/probes/security_text.py
- type: code
  path: tests/benchmarks/embedding_consumers/probes/tool_preselect.py
- type: code
  path: tests/benchmarks/embedding_consumers/probes/wiki_search.py
- type: data
  path: tests/data/embedding_consumers/csf2_to_80053r5_official.json
claims: []
confidence: high
tags:
- design
- embedding
- benchmark
created_at: 1791388900
updated_at: 1791388900
---

# EmbeddingGemma 2 per-consumer measurement harness

## What

`python -m tests.benchmarks.embedding_consumers --all --live` runs one probe per ledger consumer
(`framework.CONSUMERS`). Each probe compares the incumbent path (the real code where possible) with the
candidate (EmbeddingGemma 2 through `portal.platform.embedding`) on one fixture and returns `MEASURED` with
`incumbent.primary`/`candidate.primary`, or `BLOCKED` with a concrete reason. `hint` is advisory input to the
Phase-4 gates of `coding_task/TASK_EMBEDDINGGEMMA2_PLATFORM_V1.md`; the harness never decides adoption.
The Phase-3 gate passes when every consumer is MEASURED or BLOCKED-with-reason. Results land in
`reports/embedding_consumers/<stamp>/` (`results.json`, `SCORECARD.md`).

## Why

Fixtures live under `tests/data/embedding_consumers/` and follow the no-leakage, key-independent,
paraphrase-overlap and provenance rules from the task file; a probe with leakage is BLOCKED. The harness exists because the migration decision is per consumer and
evidence-based: each consumer is adopted, rejected or deferred only after its own measured comparison, so a
single shared yardstick keeps the incumbent and the candidate on identical inputs.

## Comparison validity

A measured number is only evidence about the embedder if the two arms differ in nothing else. Six
rules, each of which a probe in this harness got wrong once and now encodes:

* **Re-derive every calibrated threshold per space.** A cutoff fitted to the incumbent's score
  distribution measures the cutoff, not the candidate. `rag_first_stage` reusing the incumbent's
  `VL_TEXT_GATE` suppressed the visual boost for most diagram queries; the candidate gets a
  label-free quantile-matched gate (same share of queries gated) and the incumbent-gate run is kept
  as a diagnostic. `bully_projection`'s derived thresholds are reported per arm for the same reason.
* **Compare the same pipeline stage.** Dense-vs-dense or reranked-vs-reranked, never one of each —
  `owui_attachment_rag` scored EG2-with-rerank against the incumbent-without.
* **A fine-tuned incumbent needs a post-training test sample.** `vuln_severity`'s incumbent is
  retrained on public CVE data continuously, so the test window opens after the pinned local
  revision's training cutoff and the probe BLOCKS if that revision moves.
* **Call the incumbent as production calls it.** Where production sends raw text (graph memory, the
  Bully Organ), the incumbent arm sends raw text; adding a prefix the live caller does not send
  measures a hypothetical, not the thing being replaced.
* **Prefer external gold over the artifact under test.** `compliance_crosswalk` scores both arms
  against NIST's own CSF 2.0 -> SP 800-53 Rev 5 informative references, so the hand-curated seed is
  no longer its own reference at 1.0.
* **Degeneracy is a measurement, not a block.** When a corpus is smaller than the consumer's own
  result limit every query returns everything, so both arms are provably identical; `field_journal`
  reports that with the identity verified rather than declining to measure.
* **A retired incumbent arm is a frozen block, not a re-run.** After the EG2 cutover retired
  :8917, the probes that embedded a live incumbent arm there stopped working; `_common.HISTORICAL_ARMS`
  freezes each arm's committed scorecard block (per-entry provenance stamp) so the probes still run
  and still report the comparison — explicitly a same-fixture comparison against a fixed arm, not a
  fresh paired run. A paired test against a frozen arm is not recomputable (its per-probe verdicts
  died with the service), so `bully_projection`'s live hint stays INCONCLUSIVE and the vs-incumbent
  pairing lives in the cutover stamp.
