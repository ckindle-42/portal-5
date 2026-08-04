---
id: unit-router-council
kind: mixed
title: "Router council \u2014 multi-model quorum cross-check"
sources:
- type: code
  path: portal/platform/inference/router/council.py
  commit: a234187e
last_generated_commit: a234187e
claims: []
confidence: high
tags:
- authored-v1
- platform
- inference
- router
created_at: 1785798076.012774
updated_at: 1785798076.012774
---

`council.py` is the council-of-agreement engine: it renders review material,
calls the council members, parses their opinions, aggregates them with a
quorum, and produces a completion verdict for the multi-model cross-checking
loop.

## Why

The council exists to make the blue orchestration's verdicts robust — one
model's confident-but-wrong conclusion is caught by a quorum of disagreeing
members. The aggregation is the design's core: opinions are parsed from free
text, aggregated with a quorum floor (a non-voter counts against quorum, so
a member that fails to produce a parseable opinion cannot silently inflate
the vote), and the completion carries the verdict plus the individual
opinions for audit. The structured `CouncilOpinion`/`CouncilAggregate`/
`CouncilCompletion` shapes are what let the caller distinguish a genuine
majority from a no-quorum shrug.

## Interfaces

`parse_opinion` turns a member's text into a structured opinion;
`aggregate_opinions` applies the quorum and returns the aggregate;
`_render_review_material` builds the material the members review;
`_json_object` recovers a JSON object from a model's free text.

## Gotchas

The quorum rule (non-voters count against it) is a deliberate sharp edge —
the gates that test it exist because a council that lets abstentions pass
would rubber-stamp anything.
