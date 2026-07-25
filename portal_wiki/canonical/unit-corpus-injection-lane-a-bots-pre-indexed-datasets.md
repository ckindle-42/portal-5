---
id: unit-corpus-injection-lane-a-bots-pre-indexed-datasets
kind: what
title: "corpus_injection \u2014 Lane A \u2014 BOTS pre-indexed datasets"
sources:
- type: doc
  path: docs/security/corpus_injection.md
  commit: 05e42ec2
  section: "Lane A \u2014 BOTS pre-indexed datasets"
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.5822139
updated_at: 1784946220.5822139
---

BOTS ships as pre-indexed Splunk buckets, so it does **not** go through HEC. Each
tarball untars into `$SPLUNK_HOME/etc/apps` and serves its own index.

```bash
