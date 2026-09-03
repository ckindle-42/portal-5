---
id: unit-known-limitations-vl-text-gate-tuned-against-manufactured-collision
kind: what
title: "KNOWN_LIMITATIONS — VL_TEXT_GATE τ was tuned against a collision the ingest made"
sources:
- type: code
  path: reports/retrieval/SUBSTRATE_MIGRATION_V1.md
claims: []
confidence: high
tags:
- docs
- verified-v1
---
### VL_TEXT_GATE — τ was fitted to an index the ingest doubled

- **ID**: T2-RAG-TAU-001
- **Status**: OPEN (documented). The figure-scoped visual arm
  (`RAG_VISUAL_SCOPE=figures`) removes the collision. On a docling KB the shipped
  τ = 0.72 still holds the **prose** lane; its *range* does not transfer (raising
  it to help the diagram lane collapses prose). Ship τ = 0.72 + BM25 on a docling
  KB; re-measure τ from scratch for any other corpus.
- **Description**: Before SUBSTRATE_MIGRATION_V1, `kb_ingest` VL-embedded **every**
  rendered PDF page into the visual arm (O7). On the compliance eval corpus that
  was **435 page images, of which 419 (96%) were prose pages already covered by
  the text chunks** — indexed a second time and searched with the same query
  vector. `VL_TEXT_GATE` (the τ that decides whether a page image may outrank a
  text chunk) existed to referee that collision, and its knee — 0.72 on the
  fixed chunker — was measured on the doubled index.
  - Figure-scoping the visual arm (index only pages under `FIGURE_PAGE_MAX_TEXT`)
    costs **no recall**: diagram r@1 0.952 → 0.952, prose r@1/r@5 unchanged. The
    419 removed images never produced a correct top hit the text arm lacked.
  - The docling `HybridChunker` then makes the **text arm more confident**
    (better-formed chunks score higher). Sweeping τ = 0.72 / 0.80 / 0.86 / 0.92
    on the docling index: prose r@1 collapses 0.938 → 0.50 → 0.25 as τ rises,
    diagram r@1 maxes at 1.0 from τ = 0.80 — **no τ serves both lanes**. But the
    diagram-lane loss at τ = 0.72 is a synthetic-corpus artifact (every synthetic
    figure doc's page 2 has a "See the … drawing" caption the chunker isolates
    and every fusion mode ranks above the figure image; r@5 stays 1.000). So the
    prose lane keeps τ = 0.72; the diagram lane needs a real figure corpus. See
    `reports/retrieval/SUBSTRATE_MIGRATION_V1.md`.
- **Lesson**: a threshold tuned against a distribution you also generate at
  ingest is not measuring the world — it is measuring your own pipeline. The
  retrieval eval could not see this because it scored a hit whenever the right
  file ranked ≤ k, and the doubled page images were the same file. Any future
  chunker, figure-policy, or fusion change re-opens the τ question; the
  stage-set stamp (check `HD`) now forces a re-ingest when any of them changes,
  and this unit is the reminder to re-measure τ with it.

## Why

`prose-cip-07` — the archetypal compliance question, "how does CIP-002
categorize BES Cyber Systems" — sat outside the top 5 across three builds,
hidden by an aggregate recall number, while τ was tuned and re-tuned around it.
The fix was not a better τ; it was removing the manufactured collision (O7) and
using a real chunker (O5). Recording this keeps the next person from spending
another cycle fitting τ to an artifact.
