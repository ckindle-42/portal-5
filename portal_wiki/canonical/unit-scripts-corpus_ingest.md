---
id: unit-scripts-corpus_ingest
kind: mixed
title: "Script \u2014 corpus_ingest"
sources:
- type: code
  path: scripts/corpus_ingest.py
  commit: af437ebd
last_generated_commit: af437ebd
claims: []
confidence: high
tags:
- authored-v1
- scripts
created_at: 1785799472.692678
updated_at: 1785799472.692678
---

Ingests the labeled detection corpora into the lab Splunk index, mapping events onto the detection sourcetypes so corpus data coexists cleanly with live bench traffic.

## Why

Corpus events and live bench traffic share one index, and the sourcetype mapping is what keeps them separable — a detection query must be able to target corpus-only or live-only events. The properties the module documents (sourcetype mapping, coexistence rules) are the contract that prevents corpus data from polluting live measurements.

## Interfaces

The script is an operator or agent tool run from the repo root; it prints its findings and exits with the appropriate status.

## Gotchas

As a standalone script it reads live state — run it with the stack or environment it expects, and treat its output as current reality, not a stale record.
