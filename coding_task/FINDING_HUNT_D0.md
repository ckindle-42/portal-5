# FINDING — hunt replan slice D0 (measurement truth: keys ∩ index, step-level diffs)

Lane `lane/hunt-d0`, brief `coding_task/BRIEF_HUNT_D0.md`, spec
`docs/hunt/ORCACYBER_DEEP_DIVE_2.md` §5 D0. Offline only: the hunt pipeline was not run
(operator hold). Lab Splunk was touched read-only, credentials read from the live checkout's
`.env` by key name, never sourced. Held-out indexes (`hb_ait_wheeler`, `hb_cloudobs_aws`,
`botsv1`) were never opened.

## What the slice changed

`portal/modules/security/core/hunt/notables/scoreboard.py`

1. **`keys_present` / `evidence_absent`.** For each line-mode family the scoreboard now resolves
   every labelled line's source path against the run's own record of what its index holds, and
   reports per step `evidence_absent: n/N`. A step whose labelled lines are *all* absent leaves
   the step denominator: it is printed as
   `C0 evidence absent (excluded from the step denominator)  <step> n/N labelled lines`, never as
   an unreachable step, because no ranking can reach a line the index does not hold.
2. **Step-set diff against a named baseline (`--baseline <run>`).** Prints
   `lost` / `gained` (covered @50) and `reachable_lost` / `reachable_gained` as **step names**.
   No ratio is introduced or moved.

`tests/unit/test_hunt_scoreboard.py` — one test
(`test_a_step_whose_file_the_index_lacks_is_evidence_absent_not_unreachable`), which also covers
the diff.

## How index membership is resolved, and why that is sound

The brief allows `| tstats count … source=…` or a first/last window check. The scoreboard is
offline, so it reads the **run's own estate map**: the `cards`-stage ledger row
`| tstats count where index="…" by sourcetype source`. That row is complete and uncapped
(`capped: false`) and its `values_extracted` holds the source paths. A row is used only when the
number of distinct paths equals the row count, so a deduplicated or ragged row cannot masquerade
as a complete map; otherwise `index_map` says so and no step is excluded.

Verified against the lab index independently for all six stored runs (read-only `tstats`, §9):
the ledger's path set is **identical** to the live `by sourcetype source` path set in every case.

| run | index | live paths | ledger paths | equal |
|---|---|---:|---:|:--:|
| v2/santos | `hb_ait_santos_v2` | 132 | 132 | yes |
| control/santos | `hb_ait_santos` | 256 | 256 | yes |
| v2/kyoushi | `hb_kyoushi_s1_v2` | 87 | 87 | yes |
| control/kyoushi | `hb_kyoushi_s1` | 88 | 88 | yes |
| v2/russell | `hb_ait_russellmitchell_v2` | 134 | 134 | yes |
| control/russell | `hb_ait_russellmitchell` | 258 | 258 | yes |

## The acceptance property, proved on the stored runs

`santos _v2` against `control/santos`:

```
C0 ceiling  steps 11/20 reachable  labelled lines read verbatim 3002/47367
C0 evidence absent (excluded from the step denominator)  crack_passwords 44/44 labelled lines
C0 recall-of-reachable  line @50 8/11  @100 9/11  all 10/11
C0 modes  line 16/21 @50  17/21 @100  18/21 all   strict n/a for per-line keys
C0 step diff vs …/control/santos
  covered@50  lost webshell_upload  gained dns_scan, traceroute
  reachable   lost attacker_http, dirb, wpscan  gained attacker_change_user, exfiltration-service
```

That is §5 D0's live proof, line for line: `crack_passwords` 44/44 absent, step denominator
21 → **20**, and the four step lists of §2.2.

`russell _v2` is the second family the instrument now reports honestly:

```
C0 ceiling  steps 11/21 reachable  labelled lines read verbatim 2502/61862
C0 evidence absent (excluded from the step denominator)  crack_passwords 49/49 labelled lines
C0 step diff vs …/control/russell
  covered@50  lost webshell_cmd, webshell_upload  gained -
  reachable   lost attacker_http, dirb, webshell_cmd, webshell_upload, wpscan  gained exfiltration-service
```

`kyoushi _v2` has no evidence-absent step (7/12 reachable, unchanged) and prints none, so the
mechanism is not firing spuriously. Both control runs print none either. Live confirmation that
the file is really gone from `_v2` and really present on the control (exact `source=` paths, not
a wildcard — `tstats` did not honour `source="*…"` here, it returned 0 on the control too):

```
| tstats count where index=hb_ait_santos           source="/logstash/intranet-server/2022-01-17-system.cpu.log" -> 1,920  (scan 1,920, 0.36 s)
| tstats count where index=hb_ait_santos_v2        source="/logstash/intranet-server/2022-01-17-system.cpu.log" -> 0      (scan 0)
| tstats count where index=hb_ait_russellmitchell  source="/logstash/intranet-server/2022-01-24-system.cpu.log" -> 1,920  (0.35 s)
| tstats count where index=hb_ait_russellmitchell_v2 source="/logstash/intranet-server/2022-01-24-system.cpu.log" -> 0   (0.37 s)
```

The deep dive's `3,840` is the wildcard sum of both shipper copies of that day; each exact path
holds 1,920. The 44 labelled lines live in the `intranet-server` copy.

## Cost

None at run time. `_index_paths` reads the ledger the run already wrote; the diff re-scores the
baseline run directory offline. No new search is issued by the scoreboard.

## Not done / unproven

- **The full live hunt proof is not run here** (operator hold). See the orchestrator command.
- **Line-mode families only.** `keys_present` is defined over per-line keys, exactly as §5 D0
  writes it. Entity-level families keep the existing ceiling untouched; `--baseline` does work
  for them (the diff reads `per_step[].reachable`, which both modes produce).
- The index map is per *source path*; the brief's "`(host, source, line)` resolves" is answered at
  the `(host, source)` level, because a Splunk index exposes no line numbers. A file that is
  present but truncated would not be flagged — that is D1's job (per-file read receipts), not D0's.
- `_index_paths` relies on the `cards` stage having issued `by sourcetype source` over the whole
  index. It did for all six stored runs. A run that skips it prints
  `C0 evidence absent  n/a (the run recorded no complete per-source index map)` rather than
  guessing.

## Orchestrator's live proof

```bash
run=/Users/chris/projects/portal-5-hunt-proof-run/coding_task/scratch/hunt_proof_20261121
keys_s=/Volumes/data01/portal5_hunt/corpora/ait_lds_v21/santos_ingest/keys.jsonl
keys_k=/Volumes/data01/portal5_hunt/corpora/hunt_bed/kyoushi_s1_ingest/keys.jsonl
keys_r=/Volumes/data01/portal5_hunt/corpora/ait_lds_v21/russellmitchell_ingest/keys.jsonl
control=/Users/chris/projects/portal-5-hunt-proof-run/coding_task/scratch/hunt_proof_20261120T232700/control

# D0 offline, on the tuned index (no Splunk, no judge)
uv run python -m portal.modules.security.core.hunt.notables.scoreboard \
  --out "$run/v2/santos" --keys santos=$keys_s --baseline "$control/santos"
```

Pass: the `C0 ceiling` line reads `steps 11/20 reachable`; one
`C0 evidence absent (excluded from the step denominator)  crack_passwords 44/44` line; and the
diff block reads `reachable lost attacker_http, dirb, wpscan  gained attacker_change_user,
exfiltration-service`. Fail: `44/21`, `crack_passwords` listed as merely unreachable, an
`n/a (…)` index-map note, or a diff that prints a ratio.
