# DESIGN_BULLY_CORPUS_BED_V1

Design note for `TASK_BULLY_CORPUS_BED_V1`, which stands the product on the
real corpus instead of the data it generated for itself.

## The product, as one system

Four pieces built and measured separately are one product:

- **Crogl** -- the universal data reviewer: ingests any source, infers field
  roles, stitches entities across schemas nobody enumerated.
- **Bully** -- the hunt loop: discovery-first, cousins among observations,
  analyst verdicts, maturation.
- **The corpus** -- millions of real, verifiable, answer-keyed events. The
  ground truth the whole thing is supposed to stand on.
- **The generator** -- makes COUSINS of what the answer key confirms is in
  the corpus, and injects them into it.

This task links them. It adds almost no new capability; it connects what
exists and makes the resulting numbers interpretable for the first time.

## The three-lane bed (already implemented, never wired up)

`portal_wiki/canonical/unit-corpus-injection-corpus-injection-getting-hunt-ready-telemetry-into-lab-splunk.md`
documents:

| Lane | Source | Index | Labelled | Scale |
|---|---|---|---|---|
| **A -- BOTS** | Splunk Boss of the SOC v1/v2/v3 | `botsv1`/`botsv2`/`botsv3` | published answer keys | millions of real events |
| **B -- ATT&CK corpora** | splunk/attack_data, OTRF, EVTX sets | `portal5_lab` | technique-tagged | large |
| **C -- Live emulation** | Caldera + Atomic Red Team | `portal5_lab` | unlabelled | on demand |

`scripts/lab_bots_install.py` installs Lane A as pre-indexed Splunk buckets
serving their own `botsvN` indexes -- untarred directly into
`$SPLUNK_HOME/etc/apps`, no HEC involved.

## The single-index binding that hid millions of events

Every bully run to date -- R.6, W.6, X.6, Y.6, D.4 -- read `index=portal5_lab`
with `--capture-limit 2000` (`bully.inject_plane.capture_records`,
`os.environ.get("LAB_SPLUNK_INDEX", "portal5_lab")`) and got back only the
`gen:*` synthetic universe it had just written itself. BOTS lives under a
different index name (`botsv1`/`botsv2`/`botsv3`), so the capture path could
not see it -- the comment in `capture_records` even names the pre-loaded
corpus while the code hardcodes one index.

The generator was therefore manufacturing both the haystack and the needles,
and the system was measured against data it authored.

## The 1.1-entities-per-record signature

D.4 resolved 2,212 entities from 2,000 captured records -- ~1.1 entities per
record. Each procedurally-invented `gen:*` source invents its own identifier
space, so there is almost nothing to resolve *across* sources. Cross-source
entity correlation was being validated on data engineered to have no
cross-source entities to correlate.

The wiki states the design intent this task implements:

> "Lanes A and B are finite and pre-labeled: every event already carries its
> answer, which makes them ideal for detection coverage and hunt training but
> **useless for discovery work**. Lane C is the only lane that generates
> genuinely novel, unlabeled activity, which is what
> `ANOMALOUS_UNCLASSIFIED` / discovery evaluation needs."

## The bed this task builds

BOTS is the haystack -- real, messy, multi-source, at scale, with an answer
key telling us what is genuinely present. The generator builds cousins of
techniques the answer key confirms, and injects them via Lane B. Lane C
supplies genuine unlabelled novelty. Three numbers, never averaged:

    floor    known-bad recall against the published answer key
    product  injected-cousin recall inside millions of real records
    cost     false-positive rate against real benign traffic

A floor-only result (perfect recall on the answer key, zero cousin recall) is
a FAIL, not a success -- it means the system found what it was handed and
nothing it had to actually look for.

## Errata

Every prior bully run doc (R.6, W.6, X.6, Y.6, D.4) carries this note as of
2026-08-21: each run was live in transport (real Splunk HEC/search calls) and
synthetic in content -- its distributions, false-positive rates and recall
figures describe `gen:*` data the system generated and injected itself, not
the real BOTS/ATT&CK corpus. The mechanics validated (discovery pipeline,
scoreboard conformance, truth acceptance, degeneracy checks) remain real; the
*numbers* describe a closed loop, not the product standing on outside data.
See `TASK_BULLY_CORPUS_BED_V1` and `docs/BULLY_CORPUS_BED_RUN_C6_V1.md` for
the first run against the real bed.
