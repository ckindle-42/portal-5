---
id: unit-router-auth
kind: mixed
title: "Router auth \u2014 constant-time bearer-token verification"
sources:
- type: code
  path: portal/platform/inference/router/auth.py
  commit: a234187e
last_generated_commit: a234187e
claims: []
confidence: high
tags:
- authored-v1
- platform
- inference
- router
created_at: 1785798052.362176
updated_at: 1785798052.362176
---

`auth.py` is the pipeline's bearer-token verification for the `/v1/*` and
`/admin/*` endpoints, using constant-time HMAC comparison.

## Why

The pipeline is a network service, and an unauthenticated chat endpoint is a
free model server for anyone who can reach the port. The bearer-token check
closes that, and the constant-time comparison exists because a naive `==`
comparison on a token is a timing oracle — an attacker who can measure
response time can recover the key character by character. The admin
endpoints carry a separate, stricter key so operator operations are gated
more tightly than chat.

## Interfaces

The module exports the key constants and the verification helpers
(`_verify_key`, `_verify_admin_key`) that the route dependencies call.

## Gotchas

The distinction between the pipeline key and the admin key matters — a
script that uses the pipeline key must not be able to hit admin endpoints.
