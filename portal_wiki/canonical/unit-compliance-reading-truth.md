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

## P6R measurement design

The harness starts with the Open WebUI preset's system message. The pipeline
appends the workspace persona once, using its existing append operation. The
receipt hashes that combined system text and records the preset parameters and
tool ids. Sampling continues to come from the workspace configuration.

Every compliance turn records its correlation id and authenticated pipeline
trace, the final backend and model, and the serving engine's window metadata.
For oMLX the window comes from `max_model_len` in `/v1/models`; for Ollama it
comes from `context_length` in `/api/ps`. A workspace context limit or a tag
suffix is not evidence of the applied window. Unknown measurements stay
unknown. Window pressure divides prompt tokens by the serving window;
exceedance includes equality. Declared pins are compared with the final model.

The harness requests the existing `exec_audit` stream event and saves its exact
tool arguments and outputs locally. A turn that called tools but has no audit
event records capture as unavailable, rather than fabricating an empty result.

A campaign must pin one store snapshot and restore it before every arm and rep,
verifying the logical digest. `store_snapshot.py` provides SQLite online backup
and restore; its digest excludes page layout. External retrieval indexes also
need isolation or an explicit record of unrestored writes. `run_campaign.py` pins one SQLite snapshot and a shared external-index
manifest, restores and verifies SQLite before every arm/rep, preserves changed
post-rep stores locally, and records index versions, row counts and sidecar
hashes. External-index restoration is not implemented; a changed external
state halts the campaign before another rep. A run with a mismatched final
build, unknown serving facts or unavailable tool outputs is invalid.

`near_verbatim` is a separate diagnostic class for quoted text that fails exact
containment but matches a source window within the calibrated character edit
budget. It never makes a quote grounded or repairs the answer. Matching uses
the store's own fold. Calibration must catch every retained corruption while
flagging none of the calibration's verbatim spans. A quoted list may span several captured sections. After whole-span matching
fails, the diagnostic checks its bullet clauses independently at the same edit
budget and records `match_scope: bullet_segment` and the clause that matched.
It does not claim the whole assembled quotation matched. The retained
calibration passes without changing the default edit budget. `quote_classes`
reports near-verbatim occurrences separately from unresolved spans.

The corrected substrate instrument selects coverage rows through the module's
requirement scope and compares each Part only with that Part's linked sections.
It cannot pool another Part's evidence or discard Part rows of a parent query.
