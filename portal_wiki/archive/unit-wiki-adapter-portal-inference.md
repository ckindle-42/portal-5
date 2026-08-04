---
id: unit-wiki-adapter-portal-inference
kind: mixed
title: "Wiki inference adapter \u2014 Ollama binding for seeding"
sources:
- type: code
  path: portal/platform/wiki/adapters/portal_inference.py
  commit: 66aa9fda
last_generated_commit: 66aa9fda
claims: []
confidence: high
tags:
- authored-v1
- wiki
- adapter
created_at: 1785797572.9919202
updated_at: 1785797572.9919202
---

The portal inference adapter wires the stack-agnostic `InferenceBackend`
interface to Ollama at localhost:11434, using `/api/generate` for the
single-turn generation the wiki seeding needs.

## Why

The wiki engine defines an inference interface so the seeding adapters can
ask a model questions without knowing which backend answers. This adapter is
the Portal-5 binding of that interface to the single inference tier (Ollama).
It exists so the intent seeder and the fact derivation can generate text
through the same backend the platform serves with, rather than embedding a
backend-specific HTTP call in the engine.

## Interfaces

`PortalInference` implements the `InferenceBackend` contract against the
Ollama generate endpoint, with the URL and default model read from
configuration.

## Gotchas

The adapter uses `/api/generate` (single-turn), not the chat endpoint — wiki
seeding is a generation task, not a conversation, so the simpler endpoint is
the right tool.
