---
id: unit-ci-pyproject-no-dup
kind: mixed
title: "CI guard \u2014 no duplicate dependency pins"
sources:
- type: code
  path: scripts/ci/check_pyproject_no_dup.py
  commit: '96146826'
last_generated_commit: '96146826'
claims: []
confidence: high
tags:
- authored-v1
- ci
- pyproject
created_at: 1785795649.117898
updated_at: 1785795649.117898
---

The pyproject guard fails if any dependency list in `pyproject.toml` — the
core `[project.dependencies]` or any `[project.optional-dependencies]` extra —
contains the same package twice, case-insensitively and ignoring version
specifiers. It runs as a pre-commit hook.

## Why

Duplicate dependency pins are a silent correctness hazard: two pins of the
same package with different version ranges are ambiguous (which wins?),
and even identical duplicates signal a merge accident. The normalization —
lowercased and `-`/`_` folded, version specifier stripped — exists so that
`Requests>=2.0` and `requests==2.28` are caught as the same package rather
than squeaking past on spelling or version differences. The check is scoped
per context (core vs. each extra), because the same package legitimately
appears in two different contexts.

## Interfaces

`_pkg_name` normalizes a dependency string to a canonical package key, and
`main()` parses the TOML, collects every dependency into its context, detects
duplicates within each context, and returns non-zero naming the offending
contexts. It falls back to the `tomli` backport when `tomllib` is unavailable
on older Pythons.

## Gotchas

The normalization replaces `-` with `_`, so `pillow` and `PIL` still differ —
the guard catches duplicated pins of the *same* normalized name, not two
distinct packages that happen to look similar.
