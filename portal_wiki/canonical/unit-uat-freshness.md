---
id: unit-uat-freshness
kind: mixed
title: "UAT freshness \u2014 image-vs-HEAD check"
sources:
- type: code
  path: tests/uat/freshness.py
  commit: 85bb65bd
last_generated_commit: 85bb65bd
claims: []
confidence: high
tags:
- authored-v1
- tests
- uat
created_at: 1785799270.594826
updated_at: 1785799270.594826
---

The running-image vs git-HEAD freshness check that warns before a UAT run if the containers are stale.

## Why

A UAT run against a stale image produces results for the wrong code, and the freshness check is the guard that surfaces that before hours of execution. It is the same discipline as the bench's image-freshness check, applied to the acceptance run.

## Interfaces

The freshness comparison and its warning path.

## Gotchas

The check warns and blocks — a UAT result against a stale image is worthless, and the run must not proceed silently.
