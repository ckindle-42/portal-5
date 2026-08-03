---
id: unit-acceptance-common
kind: mixed
title: "Acceptance common \u2014 shared section infrastructure"
sources:
- type: code
  path: tests/acceptance/_common.py
  commit: a88ad75b
last_generated_commit: a88ad75b
claims: []
confidence: high
tags:
- authored-v1
- tests
- acceptance
created_at: 1785799696.542645
updated_at: 1785799696.542645
---

`_common.py` is the shared infrastructure for the acceptance section modules:
it re-exports the result surface, provides the HTTP/chat/generation helpers,
the refusal and assertion utilities, and the section-specific setup the S
modules all use.

## Why

Twenty-eight sections need the same plumbing — call the pipeline, call a
service, record a result — and duplicating it per section is the drift this
project pays to avoid. The module is the one shared import point, so a
helper change applies everywhere it is used, and a section that needs a new
service helper gets it here rather than embedding a private copy.

## Interfaces

The result-recording re-exports, the pipeline chat helper, the service
health checks, and the assertion/refusal utilities the S-modules consume.

## Gotchas

The module is large because the acceptance surface is broad — but it is the
single home for the shared helpers, and new section-specific logic belongs
in the section, not here.
