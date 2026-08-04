---
id: unit-tests-init
kind: mixed
title: "Tests package root \u2014 versioned test tree namespace"
sources:
- type: code
  path: tests/__init__.py
  commit: 4900007a
last_generated_commit: 4900007a
claims: []
confidence: high
tags:
- authored-v1
- tests
created_at: 1785798770.9236748
updated_at: 1785798770.9236748
---

The tests package is the root of the test tree, carrying the version string
for the test suite.

## Why

The namespace exists so the test tree has a stable import root and a single
place its version is recorded. The version lets a UAT report state which test
generation produced it.

## Interfaces

Exposes the version string only; the real content is the sibling packages
(`tests/acceptance`, `tests/uat`, `tests/benchmarks`, `tests/lib`) and the
top-level drivers and helpers.
