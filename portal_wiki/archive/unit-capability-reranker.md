---
id: unit-capability-reranker
kind: mixed
title: "Reranker MCP \u2014 two-stage RAG re-ranking"
sources:
- type: code
  path: config/portal.yaml
  section: mcp_fleet
- type: code
  path: portal/modules/research/tools/reranker_mcp.py
claims: []
confidence: high
tags:
- capability
- mcp
- research
created_at: 1788030600.446044
updated_at: 1788030600.446044
---

# Reranker MCP — two-stage RAG re-ranking

## What

The Reranker MCP (`portal/modules/research/tools/reranker_mcp.py`, port 8925)
serves a single cross-encoder reranker over the host MLX embedding/rerank lane.
It is not pipeline-exposed (`expose_to_pipeline: false`); it is called by the
RAG MCP to reorder candidates rather than directly by personas.

## How it's used

`rerank` takes a query and a set of candidate documents and returns them
re-ordered by relevance score. The underlying model is the Qwen3-Reranker-0.6B
on Metal, loaded through the host MLX server the embedding lane already runs.

## Why it exists

Two-stage retrieval — a cheap candidate search followed by a cross-encoder
rerank — is the standard way to get precision without an expensive brute-force
dense pass over the whole store. Splitting the reranker into its own MCP keeps
it independently addressable and lets the RAG pipeline call it as a service
rather than embedding the scoring logic in the vector store.

## Value

Retrieval answers get measurably better ordering for the same candidate pool,
and the dedicated server keeps the scoring model loaded once and reused. Its
host-MLX placement mirrors the speech lane: the model lives on the accelerator
that runs it, not in a container.
