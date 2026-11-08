# 9 anchors record a log file that does not exist (2026-11-08)

Found by the orchestrator while closing the `UNPROVEN` item handed up by lane
`item-id-namespace-join` (`2eaf9abbc`): after the namespace fix, 461 of 470 live
episode anchors resolve to indexed events. These are the 9 that do not.

## Measured

| | |
|---|---|
| live episode anchors | 470 |
| resolving to an indexed `p5_item` | 461 (98.1%) |
| not in the index | **9** |

All 9 are small, and they cluster in two techniques:

```
03ff5740da2c23e6   1 rec  T1021.001  bmc_creation
861f39f560cb712c  10 rec  T1021.001  mstsc_admini
529fd99fa0a6e4b9   1 rec  T1021.001  rdp_creation
4a33e9bbfb6cdacf   7 rec  T1021.001  terminal_server_reg_created
ba1973d0f66866d5  12 rec  T1021.001  unhide_file
6b539f0fea36532f   2 rec  T1070.004  automatic_file_deleted
67ada14a24e2d434   1 rec  T1070.004  bmc_file_deleted
3313a9c99506d7a4   2 rec  T1070.004  rdp_deletion
c4ff703a48a50f62   3 rec  T1070.004  terminal_server_reg_deleted
```

Every one records `sourcetype=XmlWinEventLog` and a `file` ending `windows-sysmon.log`.

## Cause: the upstream manifest names a file that is not there

`.../T1021.001/unhide_file/unhide_file.yml` declares:

```yaml
datasets:
- name: windows-sysmon
  path: /datasets/attack_techniques/T1021.001/unhide_file/windows-sysmon.log
  sourcetype: XmlWinEventLog
```

The directory contains `unhide_file.log` and `unhide_file.yml`. There is no
`windows-sysmon.log`. The content of `unhide_file.log` is the expected Sysmon XML.
This is an upstream `attack_data` naming inconsistency, not ours.

The two consumers then diverge:

- **Ingest** (`scripts/corpus_reingest.read_attack_data` via `load_manifest_catalog`)
  resolves the declared path, finds nothing, and skips the episode. Hence these 9 are
  absent from `labelled_corpus` — they are 9 of the 1,682 indexed items' complement.
- **The anchor loader** (`scripts/load_attack_data_anchors.py`) is more permissive: it
  stored an anchor with 1-12 records while recording `file` as the **declared,
  non-existent** path.

## Why it matters

The anchor's provenance exists so a stored anchor can later be traced or retracted
(`TASK_KNOWLEDGE_PLANE_AT_SCALE`, label-provenance requirement). A `file` naming a path
that is not on disk cannot satisfy that. The anchor is not fabricated -- real records
were read -- but the record of *where they came from* is wrong.

Impact is bounded: 9 of 470 anchors, 1-12 records each. Per the orchestrator's
measurement earlier today, episodes of that size cannot carry a multi-class spine
anyway (single-class anchors have median 3 records), so their detection value was
already near zero. **This is a provenance-integrity defect, not a detection defect.**

## Not fixed here

Queued for a lane, not done inline. The fix is for the loader to record the file it
actually read, and to disagree loudly with a manifest whose declared path is absent
rather than silently substituting -- the ingest/loader divergence is the thing to close,
because two consumers of one manifest resolving it differently is how this stayed
invisible. Whether such an episode should anchor at all is an operator call.

Do not "fix" this by renaming files in the upstream corpus checkout.
