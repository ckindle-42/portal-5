---
id: unit-known-limitations-botsv2-notables-recall
kind: what
title: "KNOWN_LIMITATIONS \u2014 BOTSV2 notables locate one of fifteen labelled steps"
sources:
- type: code
  path: portal/modules/security/core/hunt/notables/parse.py
- type: code
  path: portal/modules/security/core/hunt/notables/sample.py
- type: code
  path: portal/modules/security/core/hunt/notables/behaviours.py
- type: doc
  path: docs/hunt/BOTSV2_DIAGNOSIS.md
claims:
- probe: repo.path.exists
  path: docs/hunt/BOTSV2_DIAGNOSIS.md
  equals: true
- probe: repo.path.exists
  path: portal/modules/security/core/hunt/notables/sample.py
  equals: true
confidence: high
tags:
- known-limitations
- hunt
- security
- botsv2
---

#### BOTSV2 hunt notables locate one of fifteen labelled steps (2026-11-19)

- **ID**: P5-HUNT-BOTSV2-001
- **Status**: OPEN. Two general fixes are in; the ranking causes are operator-owned decisions.
- **Description**: A full botsv2 notables run located 1 of 15 scenario steps at top-100. `docs/hunt/BOTSV2_DIAGNOSIS.md` holds the run, the per-artefact trace and the loss categories. The dominant cause is upstream of ranking: the behaviour stage reads a 306,466-event slice of a 266,560,601-event index, and 21 of the 24 admitted artefacts have no event in that slice. `wineventlog:security` was carded `understood` with no roles, so the source that carries most of those artefacts was skipped `no_roles`. `peer_rare`'s host-share measure ranks the one keyed attack IP below its cut, and its measured merge weight 0 would append it after the ranked head regardless. `MISFIT_MAX_SHARE` drops a whole source that carries one artefact.
- **Fixed (2026-11-18)**: `parse_kv` now reads the line-start `Label: value` detail body that rendered Windows Security events carry (11 → 27–32 fields, which unlocks `Account Name`, `SAM Account Name`, `New Process Name`, `Source Network Address`), verified as a no-op on 262,024 real kyoushi, santos and russell KV lines. `read_windows` gained `sub_windows`, and the behaviour stage reads the newest share of each half-window at the same budget, so reads are no longer confined to each window's tail; cards and alerts keep the default, so source understanding did not move for any family.
- **Remaining**: the sampling floor (2–12-event artefacts in multi-million-event sources), the `peer_rare` rarity signal and its measured `DEFAULT_WEIGHTS["peer_rare"]=0`, and `MISFIT_MAX_SHARE` are unchanged; each is an operator decision recorded in the diagnosis. `stream:smtp` keys nothing — its only roles are `from`/`to` — so the quiet email-borne artefacts have no keyable source.
- **Scope of the number**: 1 of 15 is the pre-fix run. The sub-window read changes which behaviour events are read, which cannot be re-scored offline; the next live run is the measurement, and `docs/hunt/BOTSV2_DIAGNOSIS.md` states what improvement is and is not predicted.

#### Why

A hunt that reads one slice of a 266M-event index and reports its ranking as the recall result measures the sampler, not the detector. Recording the loss categories separately — never read, read but not keyed, keyed but not kept, kept but ranked below the cut — is what let two general fixes land without tuning anything to botsv2, and what keeps the three operator-owned causes visible instead of being quietly absorbed into a threshold.
