---
id: unit-corpus-injection-always-dry-run-first-it-prints-exact-per-sourcetype-volume-without-injecting
kind: what
title: "corpus_injection \u2014 Always dry-run first: it prints exact per-sourcetype\
  \ volume without injecting."
sources:
- type: code
  path: scripts/corpus_ingest.py
- type: code
  path: portal/modules/security/core/siem/hec_ship.py
last_generated_commit: 2f35b5ad508cd284e75ad0735ab7db02961001dd
claims: []
confidence: high
tags:
- verified-v1
created_at: 1784946220.583261
updated_at: 1784946220.583261
---

The loader is deliberately two-phase: `--dry-run` and `--ship` are mutually
exclusive in the argument parser, and the dry-run prints the exact
per-sourcetype volume a ship pass would inject without posting anything to HEC.
In a dry-run, `run()` walks the same files, resolves the same sourcetypes, and
fills the same per-(sourcetype, second) buckets, but `Shipper._flush` skips the
`ship_batch` call unless `--ship` was given; the tally printed at the end comes
from the same `shipper.manifest` counter either way, so a dry-run and a ship
pass count events identically.

```bash
python3 scripts/corpus_ingest.py --src attack_data --root /path/attack_data/datasets --dry-run
python3 scripts/corpus_ingest.py --src attack_data --root /path/attack_data/datasets --ship
```

Corpora the loader was written for: splunk/attack_data (git-lfs, so pointer
files are detected by `is_lfs_pointer` and skipped with a reported count),
OTRF Security-Datasets (JSON inside per-dataset archives), and the two raw
`.evtx` sets decoded inline by `iter_evtx_records` when the `evtx` package is
installed.

## Why

A dry-run is not a nicety, it is the only safe first step: a mis-sourced root
can be hundreds of files and millions of lines, and a bad sourcetype mapping
would inject an entire corpus that indexes fine but matches every canned
detection zero times. Printing the volume before shipping makes the damage
predictable and reversible before any HEC write happens.
