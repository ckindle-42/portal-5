---
id: unit-p5-roadmap-p5-fut-embed-001-embeddinggemma-migration-seed
kind: what
title: "P5_ROADMAP \u2014 P5-FUT-EMBED-001: EmbeddingGemma Migration Seed"
sources:
- type: doc
  path: P5_ROADMAP.md
  commit: 05e42ec2
  section: 'P5-FUT-EMBED-001: EmbeddingGemma Migration Seed'
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.593046
updated_at: 1784946220.593046
---

Current production: scripts/embedding-server.py with
microsoft/harrier-oss-v1-0.6b on :8917 (ARM64). Candidate:
google/embeddinggemma-300M (outperforms Qwen3-Embedding-0.6B on multiple
MTEB v2 categories at half the size).

Migration blockers (out of scope for V7):

1. LanceDB index at /Volumes/data01/portal5_lance/ is bound to current
   embedding dimensionality. Switching requires full re-ingestion of
   every RAG source under /Volumes/data01/portal5_kb_sources/.
2. Need shadow-index A/B test to validate retrieval quality before flip.
3. Need rollback procedure (keep Harrier index on disk 14 days post-cutover
   with a feature flag in RAG MCP to flip back).

Note: mlx-community/Qwen3-Embedding-0.6B-4bit-DWQ is already in the
default pull list (pre-positioned by an earlier task). Whether the
migration target is EmbeddingGemma or Qwen3-Embedding is itself part of
the P5-FUT-EMBED-001 scope.

---
