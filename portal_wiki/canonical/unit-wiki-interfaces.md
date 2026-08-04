---
id: unit-wiki-interfaces
kind: mixed
title: "Wiki interfaces \u2014 stack-agnostic adapter contracts"
sources:
- type: code
  path: portal/platform/wiki/interfaces.py
  commit: 649301d0f61c5bfcf00996b57c976122dd4f8e02
last_generated_commit: 649301d0f61c5bfcf00996b57c976122dd4f8e02
claims: []
confidence: high
tags:
- authored-v1
- wiki
created_at: 1785797323.054877
updated_at: 1785797323.054877
---

The interfaces module defines the stack-agnostic contracts the wiki engine
exposes to its adapters: the functions an adapter must provide for the spine
to treat a subsystem as a knowledge source. It is the extraction-guarantee
boundary that CI enforces.

## Why

The wiki engine must stay portable — it cannot import Portal runtime code and
still be testable in isolation. The interfaces module is how that boundary is
drawn: adapters implement the declared contracts, the engine depends on the
interfaces, and nothing crosses the line. This is the same discipline as the
audit module's zero-import rule, applied to the adapter surface.

## Interfaces

The module declares the callable contracts (seeding, deriving, writing back)
that the adapters under `adapters/` implement and the engine consumes.

## Gotchas

Adding a new adapter capability means extending the interface first — an
adapter that reaches around the interface breaks the portability guarantee.
