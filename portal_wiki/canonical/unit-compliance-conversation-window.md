---
id: unit-compliance-conversation-window
kind: what
title: "Compliance conversational window — price the material, route instead of clip"
sources:
- type: code
  path: portal/modules/compliance/core/conversation_window.py
claims: []
confidence: high
tags:
- compliance
- conversation
- window
created_at: 1789238000.0
updated_at: 1789238000.0
---

# Compliance conversational window

`conversation_window` gives the conversation what the sweep already had: a price
check BEFORE the model reads. Ollama does not refuse an oversized prompt — it
truncates silently and answers from the remainder, which is how CIP-003-8 R1
once answered "no operator sections" while 65 operator sections were sent. The
module prices a rendered material with `sweep.window_fit`, at
`CONVERSATION_BYTES_PER_TOKEN` — the measured MINIMUM bytes per token for this
seat, not the median, because under-counting tokens is the one direction a
truncation guard may never err. `seat_window` parses the `-ctxNk` suffix of the
seat tag; a tag with no suffix yields 0 and the material is refused rather than
priced blind.

When the material does not fit, nothing is clipped or summarised: the tool
returns `mode=material_routed` with the overflow arithmetic and a per-Part
`route`, each Part priced individually, so the conversation reads what fits and
says what does not.

## Why

A silent truncation masquerades as coverage: the receipt looks normal, the
answer is confident, and the missing material is invisible to every downstream
check. The sweep learned this in LOAD_AND_CONVERSE and got `window_fit` plus an
overflow seat; the conversation kept returning the whole neighbourhood
unbudgeted, and a five-turn session is precisely where accumulated material
crosses the window. Routing rather than clipping keeps the module's honesty
rule — a reader never argues with a fraction of its evidence without being told
— while keeping requirement-level questions answerable at Part granularity,
which is how the register itself numbers them.
