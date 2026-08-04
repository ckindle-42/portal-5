---
id: unit-router-thinking
kind: mixed
title: "Router thinking \u2014 reasoning-block strip/extract/normalise"
sources:
- type: code
  path: portal/platform/inference/router/thinking.py
  commit: a234187e
last_generated_commit: a234187e
claims: []
confidence: high
tags:
- authored-v1
- platform
- inference
- router
created_at: 1785798123.5369432
updated_at: 1785798123.5369432
---

`thinking.py` handles reasoning-model thinking blocks: it strips the
thinking/scratch content from responses when configured, extracts the inner
thinking, and normalises thinking messages on the request path.

## Why

Reasoning models emit a thinking block before their answer, and whether that
block should reach the user is a policy choice — a workspace that wants the
final answer only (for speed or for tool-loop cleanliness) needs the strip;
a workspace that wants to see the reasoning needs the extract. The
normalisation on the request path exists because thinking content arriving
in the wrong message shape would corrupt the conversation history sent to the
backend.

## Interfaces

`strip_think` removes the thinking block; `extract_think_inner` recovers its
content; `normalize_think_message` rewrites a message's thinking into the
canonical shape.

## Gotchas

The strip and extract are inverse operations on the same marker format — a
change to one without the other breaks both the clean-answer and the
show-reasoning paths.
