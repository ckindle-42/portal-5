---
id: unit-known-limitations-botsv2-notables-recall
kind: what
title: "KNOWN_LIMITATIONS \u2014 BOTSV2 notables recall: 1 of 15 pre-fix (2026-11-18), 3 of 15 at top-50 after the merged fixes (2026-11-19)"
sources:
- type: code
  path: portal/modules/security/core/hunt/notables/parse.py
- type: code
  path: portal/modules/security/core/hunt/notables/sample.py
- type: code
  path: portal/modules/security/core/hunt/notables/behaviours.py
- type: doc
  path: docs/hunt/BOTSV2_DIAGNOSIS.md
- type: doc
  path: docs/hunt/OPEN_PROBLEM_INDEX.md
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

#### BOTSV2 notables recall: 1 of 15 pre-fix (2026-11-18), 3 of 15 at top-50 after the merged fixes (2026-11-19)

- **ID**: P5-HUNT-BOTSV2-001
- **Status**: OPEN. Two solver fixes are merged with live four-family receipts (2026-11-19); the remaining ranking and sampling-floor causes are operator-owned decisions. The third lane (burst-guided sampling and wide-telemetry fixes) is in round 2 on branch `lane/hunt-open-neon`, not merged; per-lane state is indexed in `docs/hunt/OPEN_PROBLEM_INDEX.md`.
- **Diagnosis (2026-11-18 run)**: A full botsv2 notables run located 1 of 15 scenario steps at top-100. `docs/hunt/BOTSV2_DIAGNOSIS.md` holds the run, the per-artefact trace and the loss categories. The dominant cause is upstream of ranking: the behaviour stage reads a 306,466-event slice of a 266,560,601-event index, and 21 of the 24 admitted artefacts have no event in that slice. `wineventlog:security` was carded `understood` with no roles, so the source that carries most of those artefacts was skipped `no_roles`. `peer_rare`'s host-share measure ranks the one keyed attack IP below its cut, and its measured merge weight 0 would append it after the ranked head regardless. `MISFIT_MAX_SHARE` drops a whole source that carries one artefact.
- **Fixed (2026-11-18)**: `parse_kv` now reads the line-start `Label: value` detail body that rendered Windows Security events carry (11 → 27–32 fields, which unlocks `Account Name`, `SAM Account Name`, `New Process Name`, `Source Network Address`), verified as a no-op on 262,024 real kyoushi, santos and russell KV lines. `read_windows` gained `sub_windows`, and the behaviour stage reads the newest share of each half-window at the same budget, so reads are no longer confined to each window's tail; cards and alerts keep the default, so source understanding did not move for any family.
- **Merged (2026-11-19, hunt-open-kimi)**: temporal bursts inside a behaviour became first-class `deviation` evidence — a DuckDB join finds each behaviour's largest four-hour bucket, `log1p(peak)` is z-scored within its source, and at most two admitted behaviour bursts compete inside the existing source-burst allocation (allowance 2 selected by LOFO on kyoushi/santos/russell, botsv2 excluded; measured generator weights unchanged). Live receipt `b947b840a`: botsv2 0→2 of 15 steps at top-50, scenario coverage 2 of 4; kyoushi 12 of 12, santos 14, russell 15 at 50.
- **Merged (2026-11-19, hunt-open-astra)**: carded reads select rows by sourcetype ownership — discovery records inverted source ownership before per-card truncation, so a shared source name can no longer fill another type's read slice (on the 2026-11-18 runs, 19 of 104 botsv2 sourcetypes had first-eight sources overlapping another type, and the rank-one threat card's raw read held 4,530 distinct lines against a claimed 2 events); single-timestamp sources get one window at their observed time, and sources that fit are read whole within their existing allocation. Live receipt `080f89314`: botsv2 2→3 of 15 steps at top-50, scenario coverage 2 of 4; kyoushi 12 of 12, santos 14 of 21, russell 15 of 22 at 50.
- **Remaining**: the sampling floor (2–12-event artefacts in multi-million-event sources), the `peer_rare` rarity signal and its measured `DEFAULT_WEIGHTS["peer_rare"]=0`, and `MISFIT_MAX_SHARE` are unchanged by the merged fixes; each is an operator decision recorded in the diagnosis. `stream:smtp` keys nothing — its only roles are `from`/`to` — so the quiet email-borne artefacts have no keyable source.
- **Scope of the numbers**: 1 of 15 is the dated 2026-11-18 pre-fix measurement; the 2026-11-19 figures are the merged lanes' live four-family receipts, each measuring its own run, not a current-state claim. The next live run is the measurement for any further change; `docs/hunt/OPEN_PROBLEM_INDEX.md` carries the per-lane state.

#### Why

A hunt that reads one slice of a 266M-event index and reports its ranking as the recall result measures the sampler, not the detector. Recording the loss categories separately — never read, read but not keyed, keyed but not kept, kept but ranked below the cut — is what let the sampler, generator and attribution fixes land without tuning anything to botsv2, and what keeps the operator-owned causes visible instead of being quietly absorbed into a threshold.
