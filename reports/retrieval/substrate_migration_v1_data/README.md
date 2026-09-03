# SUBSTRATE_MIGRATION_V1 — raw eval outputs

Per-query `scripts/rag_retrieval_eval.py` results for
`../SUBSTRATE_MIGRATION_V1.md`. Run 2026-09-03 on the compliance/OT corpus
(13 NERC CIP PDFs + NIST SP 800-82r3 slice + 9 synthetic figure docs), VL server
`mlx-community/Qwen3-VL-Embedding-2B-mxfp8` (dim 2048) + `…-Reranker-2B-mxfp8`,
docling 2.99.0, `queries.yaml` (42) + `queries_lexical.yaml` (8).

| file | config |
|---|---|
| `baseline` | fixed chunker, visual=all, no BM25, text_gate τ0.72 — reproduces the committed `retrieval_eval_baseline.json` |
| `s1_figscope` | + `RAG_VISUAL_SCOPE=figures` (P3.1) |
| `s2_docling` | + `RAG_CHUNK_STRATEGY=docling` (P3.2) |
| `s3_bm25` | + `RAG_FTS=1 RAG_BM25_WEIGHT=0.3` (P3.3) |
| `tauf_0.72/0.80/0.86/0.92` | τ sweep on the s2 (docling) index |
| `unified_docling` | `VL_FUSION=unified` on the s2 index |
| `*_lexical` | the same config against `queries_lexical.yaml` |
