---
id: unit-security-cli-pass-through
kind: mixed
title: "Security module CLI \u2014 argv pass-through to core"
sources:
- type: code
  path: portal/modules/security/cli/__init__.py
  commit: b0aa6770
last_generated_commit: b0aa6770
claims: []
confidence: high
tags:
- authored-v1
- module
- security
- cli
created_at: 1785795006.4514072
updated_at: 1785795006.4514072
---

The security module CLI is a thin argv pass-through to the existing
`portal.modules.security.core` dispatcher rather than a reimplementation.
`portal security ...` rewrites `sys.argv` and hands control to the core
package's `__main__`, so the same surface (self-index, stage2-propose,
candidate-eval, compliance-report, and the bench argparse CLI) serves both
invocations.

## Why

The RBP engine already owns real argument parsing for each of its entry
points. Building Typer subcommands here would be new integration code with
zero behavior change, and the modularization spec's "bench, eval, coverage,
report, grow" naming does not map one-to-one onto the existing entry points —
`run_growth_loop`, for one, has no standalone CLI wrapper today. The pass-through
keeps `portal security ...` and `python3 -m portal.modules.security.core ...`
behaving identically: one surface, no drift between two parsers that could
accept different flags for the same operation.

## Interfaces

`register(app)` mounts the `security` command on a Typer app, and
`cmd_security(ctx)` forwards `ctx.args` into the core dispatcher via
`runpy.run_module`. The `allow_extra_args`/`ignore_unknown_options` context
settings are what let the raw core argv flow through untouched instead of
Typer trying to interpret it first.
