---
id: unit-acceptance-cli
kind: mixed
title: "Acceptance CLI \u2014 section entry point"
sources:
- type: code
  path: tests/acceptance/cli.py
  commit: a88ad75b
last_generated_commit: a88ad75b
claims: []
confidence: high
tags:
- authored-v1
- tests
- acceptance
created_at: 1785799700.235086
updated_at: 1785799700.235086
---

`cli.py` is the acceptance CLI entry: it parses the section selection and
drives the runner.

## Why

The operator surface is `python3 tests/portal5_acceptance_v6.py --section
S3`, and the CLI is what turns that into a run — selecting sections and
running them through the runner. Keeping argument parsing separate from the
orchestration means a CLI change never touches the sequencing logic.

## Interfaces

`main` parses the section spec and calls the runner.

## Gotchas

Section selection is by the S-identifiers; unknown sections must fail loudly
rather than silently running nothing.
