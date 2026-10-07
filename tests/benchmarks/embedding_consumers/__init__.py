"""Per-consumer measurement harness for the EmbeddingGemma 2 platform service.

TASK_EMBEDDINGGEMMA2_PLATFORM_V1 Phase 3. Every consumer in the collapse ledger
(``framework.CONSUMERS``) must end MEASURED or BLOCKED-with-reason; a consumer
that is merely NOT_IMPLEMENTED fails the phase gate, so no ledger item can be
dropped silently. Run: ``uv run python -m tests.benchmarks.embedding_consumers --all``.
"""
