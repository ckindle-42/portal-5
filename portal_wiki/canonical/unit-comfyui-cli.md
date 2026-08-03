---
id: unit-comfyui-cli
kind: mixed
title: "ComfyUI acceptance CLI \u2014 section entry point"
sources:
- type: code
  path: tests/comfyui/cli.py
  commit: 441fd2a1
last_generated_commit: 441fd2a1
claims: []
confidence: high
tags:
- authored-v1
- tests
- comfyui
created_at: 1785799020.085456
updated_at: 1785799020.085456
---

`cli.py` is the ComfyUI acceptance CLI entry: it parses the section
selection and drives the runner.

## Why

The operator-facing surface is the documented invocation, and a
section-selecting CLI is what turns that command into a run. Keeping the
argument parsing separate from the runner means a CLI change — a new flag, a
different default — never touches the sequencing logic, and an operator can
run one section of a long acceptance without re-running the whole suite.

## Interfaces

`main` parses the section spec and calls the runner.

## Gotchas

Section selection is by the C0-C11 identifiers; an unknown section must
fail loudly rather than silently running nothing.
