---
id: unit-surface-compliance-reading-truth
kind: what
title: "Compliance reading-truth instruments — evaluation infrastructure and the local-data boundary"
sources:
- type: code
  path: scripts/compliance/truth/*.py
- type: code
  path: portal/modules/compliance/core/operator_profile.py
claims: []
confidence: high
tags:
- authored-v1
- module
- compliance
- evaluation
created_at: 1785672000.000000
updated_at: 1785672000.000000
---

The `scripts/compliance/truth/` package is evaluation infrastructure: it
measures whether a compliance answer is RIGHT. It never enters a prompt, a
persona, a tool result or a store write — the local model is measured by it and
never sees it. Its outputs are local-only by construction.

## Why

A review that keeps finding defects one at a time is measuring what a machine
can check, not whether the module is right. This package exists so the module
can be measured against a written correct answer, and so that measuring it
never itself leaks the material being measured — the instruments are correct
only if their own outputs are bound as tightly as the data they read.

## The local-data boundary

`_local.py` is the write policy for the whole package: `is_local(path)` is true
only for paths under the gitignored private dir
(`portal/modules/compliance/data/private/`) or outside the repo entirely, and
every instrument refuses any other destination. Nothing an instrument produces
can be carried by a commit; the only public artifact of an evaluation is the
hand-written outcome summary.

## The operator-content detector

`operator_text_audit.py` finds operator-derived content in text, files and
history, so the public tree can be kept to outcome summaries:

- **text spans** — 8-token shingles of the operator documents and notes in the
  store, folded with the module's own verbatim fold
  (`candidate_links._norm_for_verbatim`), minus every shingle that also occurs
  in a regulatory document, because the regulator's text is public. Hits report
  the exact original substring through a char-offset map built while folding.
- **identity terms** — the local, agent-reviewed list under the private
  profile; matched on word boundaries, longest first.
- **operator ids** — `isection-` + 20 hex and the operator-side short cite
  token (`O-` + 6 hex, `addressing.cite_as`'s side letter). The all-zero ids
  are this module's own synthetic replacements and never flag.

Its three surfaces: `scan_text` (one text), `head_findings` (every git-tracked
file, PDF and DOCX extracted — the content scan `HK` calls), and `history_scan`
(every blob reachable from every ref plus every commit message, emitting the
LOCAL-class paths and the `git filter-repo` replacement-line files).

## The operator profile

`portal/modules/compliance/core/operator_profile.py` reads the gitignored
profile JSON that holds the operator-specific constants code used to carry
inline — the entity name, corpus locations, document targets and pinned store
sections. `require("dotted.path")` raises a clear error naming the missing file
when a machine without the profile calls for it (CI, a fresh clone), so the
public tree stays free of the constants and live runs still work where the
profile exists.

## Measurement hygiene

Three guards keep a measured run honest about what it measured:

- **One split per queue** — `truth_corpus.py queue --key … --split dev` queues
  only the questions of one key split, and refuses any transcript whose
  question the key does not hold (an unkeyed item can never be judged).
  Holdout questions are never judged while the system is being changed.
- **Store guard** — `provenance.store_counts` records, at the start and end
  of every harness run, the row counts of each store table a reading turn can
  write (the workspace's note, correction, review and standing-question
  tools). The receipt's `store_guard.changed` names any table that moved, so
  a run whose answers could feed the next run's material is visible.
- **Served config** — `config/portal.yaml` is baked into the pipeline image,
  so `provenance.served_config` hashes the copy inside the running container
  and records whether it matches the host file. A persona edit without a
  rebuild and restart shows as `matches_host: false`.

`citation_integrity.py` also runs as a CLI that recomputes the diagnostic over
finished run dirs at a given `--min-quote-words`, so a calibrated threshold
applies to every earlier run without re-asking the model.
