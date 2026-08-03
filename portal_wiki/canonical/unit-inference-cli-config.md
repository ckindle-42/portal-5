---
id: unit-inference-cli-config
kind: mixed
title: "Inference CLI config \u2014 validate/show introspection"
sources:
- type: code
  path: portal/platform/inference/cli/config.py
  commit: 5fbf51f8
last_generated_commit: 5fbf51f8
claims: []
confidence: high
tags:
- authored-v1
- platform
- cli
created_at: 1785797851.0727181
updated_at: 1785797851.0727181
---

`portal config` is the config introspection surface: `config_validate`
validates `config/portal.yaml` and exits non-zero on error, and `config_show`
prints the resolved config as pretty-printed JSON.

## Why

An operator needs two config operations that the harness does not provide in
a handy form: a fast validate (does my edit break the config?) and a show
(what is the resolved config actually?). `config_show` printing the *resolved*
model output rather than the raw YAML is the point — it shows the Pydantic
view with defaults applied, which is what the rest of the system actually
uses.

## Interfaces

`config_validate` runs the validation and sets the exit code;
`config_show` prints the resolved config JSON; both register on
`config_app`.

## Gotchas

The validate here is the fast portal-config check, not the full 74-check
validate harness — the two are complementary, and neither replaces the
other.
