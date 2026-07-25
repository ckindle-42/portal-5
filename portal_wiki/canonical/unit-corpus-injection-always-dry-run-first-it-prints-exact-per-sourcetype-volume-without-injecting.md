---
id: unit-corpus-injection-always-dry-run-first-it-prints-exact-per-sourcetype-volume-without-injecting
kind: what
title: "corpus_injection \u2014 Always dry-run first: it prints exact per-sourcetype\
  \ volume without injecting."
sources:
- type: doc
  path: docs/security/corpus_injection.md
  commit: 05e42ec2
  section: 'Always dry-run first: it prints exact per-sourcetype volume without injecting.'
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.583261
updated_at: 1784946220.583261
---

python3 scripts/corpus_ingest.py --src attack_data --root /path/attack_data/datasets --dry-run
python3 scripts/corpus_ingest.py --src attack_data --root /path/attack_data/datasets --ship
```

Corpora used, and what each needs:

- **`splunk/attack_data`** — highest fit; purpose-built for detection dev. Stores
  data in **git-lfs**, so a plain clone yields pointer files. Run
  `git lfs install --local && git lfs pull && git lfs checkout` — a `git lfs pull`
  alone will fetch the objects but leave the working tree as pointers if LFS
  filters were never installed for the repo. The loader detects and skips
  pointer files rather than shipping them, and reports the count.
- **`OTRF/Security-Datasets`** (Mordor) — JSON datasets inside per-dataset `.zip`.
- **`sbousseaden/EVTX-ATTACK-SAMPLES`** and **`mdecrevoisier/EVTX-to-MITRE-Attack`**
  — raw `.evtx`. The loader decodes these inline (`pip install evtx`); no manual
  EVTX→JSON pre-step is needed.
