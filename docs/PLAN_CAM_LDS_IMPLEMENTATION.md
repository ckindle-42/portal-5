# Implementation plan — CAM-LDS as the grounding source

Source 1 of 5 (`docs/CORPUS_SCOPE_20261108.md`). Written against the real
archive contents read 2026-11-08, not from the Zenodo abstract.

## Why this source first

It supplies, pre-aligned, the three things today's live measurements showed we
do not have:

| today's measured defect | what CAM-LDS supplies |
|---|---|
| 505/505 anchors degenerate, median spine 0, one class (`enumerate`) in the library | `attackmate.json` gives an ordered step list per sequence, each step carrying `cmd` + `techniques` + `tactics` |
| 11.3% of records classify; behaviour derived from log format, not content | labels attach to the attacker's *action*, independent of which sourcetype recorded it |
| cross-source `shared_entity` edges = 0 | every sequence spans attacker/inetfw/corpdns/wazuh with shared IPs and timestamps |

## What is actually in the archive (verified)

```
manifestations_filtered/sequences/<scenario>-<run>/
  attacker/logs/attackmate.json     ordered attack steps, ATT&CK metadata per step
  attacker/logs/attackmate.log      human log of the same
  attacker/logs/output.log          what the attacker saw
  wazuh/logs/alerts/alerts.json     EDR/IDS alerts, timestamped, agent-attributed
  inetfw/logs/log/syslog            firewall host
  inetfw/logs/log/suricata/fast.log network IDS
  corpdns/logs/log/syslog           DNS host
```

Observed step record:

    {"start-datetime": "2025-12-11T14:28:03.325538", "type": "shell",
     "cmd": "hydra -C user_pass_combo.txt -s 10022 fw.attackbed.com ssh",
     "metadata": {"techniques": "T1078.002,T1110.001,T1133",
                  "tactics": "Initial Access", "technique_name": "..."}}

Observed defender record 1.2 s later, different host:

    {"timestamp":"2025-12-11T14:28:04.494+0000",
     "rule":{"description":"Suricata: Alert - ET SCAN Potential SSH Scan"},
     "agent":{"name":"inetfw","ip":"192.168.100.254"},
     "data":{"src_ip":"192.42.1.174","dest_ip":"172.17.100.122","dest_port":"22"}}

Two bundles: `manifestations_filtered` (214 MB) and `manifestations_raw`
(536 MB). Filtered is assumed the attack-relevant slice and raw the full
capture -- TO VERIFY before use, not assumed.

## The cousin grid (from completed filenames, not inferred)

    scenario_1_{racecondition,pwnkit,sudo,validaccount,autostart,cron}
              x {pam,localaccount,sshkey}              18 variants
    scenario_2_{cron,rootkit}
    scenario_3_{ssh,vnc}_{apt,healthcheck,puppet}
    scenario_4
    scenario_6_{macro,screensharing}_binary

Two orthogonal mutation axes on scenario 1: escalation technique and
persistence mechanism. `racecondition_pam -> racecondition_sshkey` is distance
1 on persistence; `racecondition_pam -> pwnkit_pam` is distance 1 on
escalation. This is what makes SIMILAR vs NEW gradeable from the data instead
of asserted, and it is supplied by the publisher rather than by our MUT stage
(which has never run).

## Build order

Each step ends in a live reading against real files. No step is satisfied by a
unit test (`FINAL_VALIDATION`: synthetic fixtures prove plumbing, never
end-to-end claims).

**C1 - step extraction.** Parse `attackmate.json` for every sequence into
(ts, cmd, techniques, tactics, technique_name, step_index). Report: sequences
parsed, steps per sequence, distinct techniques, any sequence that fails to
parse. Acceptance: a real count from all 36 archives, with failures named.

**C2 - defender event extraction.** Parse each host's logs into
(ts, host, sourcetype-ish, entities{ips,users,paths}, raw). Report per
sequence: events per host, time span, entity counts. Acceptance: real counts;
unparsed files listed, never silently dropped.

**C3 - the join (this is the product's missing primitive).** For each step,
collect defender events within a bounded window after `start-datetime` that
share an entity with the step. Report, per step: manifestation count, hosts
touched, and the step's "silent" status when nothing manifests. Acceptance:
a non-zero cross-host edge count -- this is the direct answer to
`shared_entity edges = 0`.

**C4 - anchor from content.** Build an anchor whose spine is the C1 step
sequence (technique/tactic per step) and whose evidence is the C3
manifestation set. Acceptance: anchors with median spine length > 0 and more
than one distinct class -- stated against today's baseline of 0 and 1.

**C5 - cousin distance on the grid.** Compute distance between variants using
the C4 spines. Acceptance: distance(racecondition_pam, racecondition_sshkey)
and distance(racecondition_pam, pwnkit_pam) are both small and non-zero, and
both are smaller than distance(scenario_1_*, scenario_4). If the ordering
does not come out, that is the finding -- do not tune the metric to produce it.

**C6 - held-out grading.** Anchor on a subset of the grid, grade held-out
variants SAME/SIMILAR/NEW. Thresholds frozen before this run and not tuned on
its results (`FINAL_VALIDATION`). Report raw counts and intervals.

## Out of scope here

- Ingesting into Splunk. C1-C5 read files on disk; indexing is a later step and
  goes to its own new index, never an existing one.
- Changing `classify_record`, alphas, the funnel or thresholds.
- The other four datasets (own plans, one at a time).
- BOTS (archived, `docs/CORPUS_SCOPE_20261108.md`).

## Standing constraints

- Untrusted archives: each extracted into its own new empty directory, scripts
  kept elsewhere, paths passed as arguments, readers run with `python -I`.
- Run only via `./.venv/bin/python` -- `python3` resolves to Homebrew 3.14 on
  this host (it manufactured `module_absent` census rows today) and `uv run`
  fails on a network dependency resolve.
- Live, never synthetic: every count above comes from the real files.

## Orchestrator review of the four lanes (2026-11-08)

All four merged into `main` at `56351041f` with no conflicts. Full gate set on
the merged tree: `ruff check` all passed, `ruff format` 1878 files already
formatted, `complexity_report.py --gate` exit 0, `tests/unit` 5219 passed /
116 skipped, `tests/security` 1048 passed, `tests/wfe` 1414 passed / 1 skipped,
`mypy portal/` success over 677 files.

### C1 granularity is settled, and the brief's baseline was wrong

`cam-lds-extract` refuted the 5,554-sequence / 11,388-step figure this plan was
written against: it is a file-and-line double-count across the three views and
both bundles, not a count of episodes. The episode unit is **one campaign
archive** -- 1,806 steps over 34 archives. The `steps/` bundle view is a strict
subset: 0 bundle steps absent from the archives, 474 archive steps absent from
the bundle, all of them unlabelled, 0 labelled steps dropped.

C3's `shared_entity edges = 0` is answered: **7,548 shared-entity edges, 112 of
them cross-host** over 713,963 defender events, 0 parse failures.

### The 36% unlabelled steps are mechanics, not missing labels

899 of 1,806 archive steps (49.78%) carry no ATT&CK metadata, and the type
breakdown says why: `sleep` 358, `vnc` 201, `msf-session` 160, `ssh` 53. These
are waits, GUI automation keystrokes and session plumbing. Nothing to relabel;
they are kept in every count and none is dropped. No per-event ground truth
ships with CAM-LDS, so C6 cannot be graded against it -- the grid, not the
dataset, carries the truth.

### Two findings the lane produced that were not asked for

- The publisher's own per-sequence window slices leak: 47 of 415 sequence dirs
  hold events outside `[first_step - 1.0s, next_step)`, 43 leading (max 0.956s)
  and 4 trailing (max lag 616.488s). Our join must not inherit those windows.
- `filtered` is a strict line-subset of `raw` at identical paths (0 violations
  over 3,577 differing files). `raw` is the primary analysis root.

### SOC-MLD: the port is faithful and the protocol is the wrong instrument

`soc-mld-protocol` ported the instance id, session id, whole-instance split,
layer co-presence check and session-overlap check additively; `split_datasets`
and `assert_no_contamination` are untouched. Then it measured our 73.5%
sibling leak under the new rule and the answer is **100%, not lower**:

| split | eval episodes | with anchored sibling technique | leak |
|---|---|---|---|
| our seed-0 half-split (baseline) | 505 | 371 | 73.5% |
| ported, test_ratio 0.5 seed 0 | 419 | 419 | 100% |
| ported, publisher ratio 0.2 seed 42 | 164 | 164 | 100% |

This is not a porting defect. `_cover_labels_in_train` moves an eval unit back
into train for any class not already represented there, so every held-out class
is guaranteed a train sibling **by construction**. That is correct for SOC-MLD's
question -- a closed-set 32-class classifier benchmark, where an unrepresented
class is unpredictable and the leak they care about is near-duplicate *sessions*
of one attack instance. It is exactly wrong for ours: cousin discovery needs
techniques that appear **only** in eval, and our baseline already has 97 of them.

**Verdict: adopt the instance/session ids and the co-presence and
session-overlap checks; do not adopt `split_attack_instances` as our evaluation
split.** The honest conclusion is that the 73.5% leak fix is not in SOC-MLD, and
the brief was wrong to expect it there. The remaining lead is our own
`technique_parent_dirs` measurement: 175 of 313 technique directories hold more
than one episode, which is where the near-duplicate retrieval actually lives.

### SOC-MLD's own dataset card does not reconcile

Measured from the real files against `documentation/dataset_card.md`:

| claim | card | measured |
|---|---|---|
| curated samples | 6,006 | 6,600 label rows (6,120 attack + 480 NORMAL) |
| classes | 32 (31 + NORMAL) | 44 (43 attack + NORMAL) |
| collection period | 2026-06-01 / 2026-09-30 | a single 2.88h run on 2026-09-27 |
| component sum | 345,465 | 377,063 raw events |

All 198,122 HTTP rows carry one source IP (`192.168.70.132`), and layer
co-presence is 9.5% over all 801 instances but 81.7% over the 93 attacker
instances. The "live SOC cyber range" is a ~3-hour single-attacker scripted run.
Useful as protocol source material; not a corpus to anchor on.

### Brief-compliance misses to carry forward

- `soc-mld-protocol` cited their files by name in every ported docstring but
  **not by line number**, which the brief named as the deliverable that mattered
  most, and it wrote no protocol summary doc. The measurement above is
  reconstructed by the orchestrator from the lane's run output, not handed up.
- `cam-lds-extract` exited with three modified paths uncommitted despite
  DONE MEANS COMMITTED at the top of its brief; recovered by the orchestrator at
  `c7cd3315d` after re-running its gates. Second lane in two days to do this.
- Zenodo now shows a **newer version** of the SOC-MLD record than the v1.0.0 we
  hold. Re-check before any further use.
