---
id: unit-scripts-lab_bots_install
kind: mixed
title: "Script \u2014 lab_bots_install"
sources:
- type: code
  path: scripts/lab_bots_install.py
  commit: af437ebd
last_generated_commit: af437ebd
claims: []
confidence: high
tags:
- authored-v1
- scripts
created_at: 1785799517.8129559
updated_at: 1785799517.8129559
---

Installs the pre-indexed BOTS Splunk buckets into the lab, untarring each tarball into the Splunk apps directory where it serves its own index queried directly — no HEC ingestion.

## Why

BOTS ships as pre-indexed buckets, so routing it through HEC would re-index already-indexed data. Installing the tarballs into the apps directory is what preserves the pre-indexed structure and the direct-query behaviour the BOTS hunts expect.

## Interfaces

The script is an operator or agent tool run from the repo root; it prints its findings and exits with the appropriate status.

## Gotchas

As a standalone script it reads live state — run it with the stack or environment it expects, and treat its output as current reality, not a stale record.
