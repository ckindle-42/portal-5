---
id: unit-uat-freshness
historical: true
kind: mixed
title: "UAT freshness \u2014 image-vs-HEAD check"
sources:
- type: code
  path: tests/uat/freshness.py
  commit: d7dcc96a
claims: []
confidence: high
tags:
- authored-v1
- tests
- uat

---

The running-image vs git-HEAD freshness check that warns before a UAT run if the containers are stale.

## Why

A UAT run against a stale image produces results for the wrong code, and the freshness check is the guard that surfaces that before hours of execution. It is the same discipline as the bench's image-freshness check, applied to the acceptance run.

## Interfaces

The freshness comparison and its warning path.

## Gotchas

The check warns and blocks — a UAT result against a stale image is worthless, and the run must not proceed silently.
