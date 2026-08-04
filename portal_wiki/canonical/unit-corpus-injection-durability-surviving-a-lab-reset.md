---
id: unit-corpus-injection-durability-surviving-a-lab-reset
kind: what
title: "corpus_injection \u2014 Durability \u2014 surviving a lab reset"
sources:
- type: code
  path: scripts/lab_bots_install.py
- type: code
  path: scripts/corpus_ingest.py
- type: code
  path: scripts/caldera_emulate.py
- type: code
  path: .env.example
last_generated_commit: 2f35b5ad508cd284e75ad0735ab7db02961001dd
claims: []
confidence: high
tags:
- verified-v1
created_at: 1784946220.5875359
updated_at: 1784946220.5875359
---

Everything these three lanes produce lives only in the lab, not in git. The
scripts are versioned; the indexed events they ship are not. A rollback of the
Splunk container to an older snapshot silently erases all of it, and the
bench's own reset paths roll lab guests back to named snapshots routinely
(`LAB_CLEAN_SNAPSHOT`, `LAB_MBPTL_SNAPSHOT` in `.env.example`).

Recovery is the scripts' job, which is why they are written to be idempotent
and additive-only. `scripts/lab_bots_install.py` skips any dataset whose app
dir already exists and repairs retention on re-run, so BOTS can be reinstalled
without careful bookkeeping. `scripts/corpus_ingest.py` re-ships the same
corpora from the same `--root`; `scripts/caldera_emulate.py` re-runs the same
adversary profiles. If both containers were lost, the three scripts rebuild
the whole injection unattended.

The one non-scripted piece is the sandcat agent on a target, which lives in
`/tmp` and does not survive a reboot or a target rollback; it is redeployed
with a single curl from the Lane C one-liner. For a consistent Splunk snapshot,
stop the `splunk` container first so bucket files are not crash-state.

## Why

Durability here is a bet on installers over state: because every artifact is
derived from a script plus a public dataset, losing the lab loses data but
never the ability to recreate it. The idempotence rules in the installers are
what make that bet safe — a re-run after a reset is a repair, not a
rebuild-by-hand.
