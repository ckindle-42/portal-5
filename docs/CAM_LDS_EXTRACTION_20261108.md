# CAM-LDS extraction — attack steps, manifestations and sequence granularity

Generated from the JSON report by `scripts/cam_lds_extract.py`; no number below is
hand-typed. The full row-level JSON is written with `--out` and kept out of the checkout.

- Bundle root: `/Volumes/data01/portal5_hunt/corpora/thirdparty_20261108_extract/raw/manifestations_raw`
- Campaign archives: 34
- Filtered comparison root: `/Volumes/data01/portal5_hunt/corpora/thirdparty_20261108_extract/filtered/manifestations_filtered`

## Readers

| view | files | lines/records | parse failures |
|---|---|---|---|
| steps | 879 | 1332 | 0 |
| sequences | 564 | 1332 | 0 |
| techniques | 1317 | 2127 | 0 |
| events | 811 | 477050 | 0 |

Defender event parse failures by kind: `{}`.

### Defender events

| host | events |
|---|---|
| videoserver | 211087 |
| corpdns | 199867 |
| inetfw | 66084 |
| wazuh | 12 |

| kind | events |
|---|---|
| wazuh | 245797 |
| syslog | 208299 |
| suricata_fast | 22954 |

Per-sequence and per-campaign event/host counts are in the JSON (`events_by_host_by_sequence`, `events_by_host_by_campaign`).

## Sequence granularity — what a `sequences/<name>` directory is

| view | directories | `attackmate.json` files |
|---|---|---|
| sequences | 564 | 564 |
| steps | 883 | 879 |
| techniques | 97 | 1317 |

- `steps/` directories without `attackmate.json`: 4 (`6_macro_binary-22, 6_macro_cron-22, 6_screensharing_binary-22, 6_screensharing_cron-22`)
- The `-<n>` suffix is a **step ordinal inside one campaign**, not a repeat run of the same
  variant. 564 sequence directories partition the bundle's step dirs into
  879 runs across 34 campaigns.
- A multi-run sequence directory groups a contiguous block of step ordinals for one
  technique: 130 multi-run dirs, 130 share a technique, and 127 are the maximal contiguous block (3 exceptions recorded).

| campaign | runs | max ordinal | median step gap (s) | run-index inversions |
|---|---|---|---|---|
| 1_autostart_localaccount | 28 | 28 | 16.346894 | 0 |
| 1_autostart_pam | 28 | 29 | 16.364941 | 1 |
| 1_autostart_sshkey | 28 | 30 | 16.331933 | 1 |
| 1_cron_localaccount | 30 | 34 | 16.339099 | 3 |
| 1_cron_pam | 30 | 34 | 16.361185 | 4 |
| 1_cron_sshkey | 30 | 34 | 16.364322 | 4 |
| 1_pwnkit_localaccount | 26 | 40 | 16.323529 | 1 |
| 1_pwnkit_pam | 26 | 42 | 16.321174 | 2 |
| 1_pwnkit_sshkey | 26 | 44 | 16.35829 | 2 |
| 1_racecondition_localaccount | 34 | 52 | 16.328108 | 3 |
| 1_racecondition_pam | 34 | 52 | 16.322176 | 4 |
| 1_racecondition_sshkey | 34 | 52 | 16.355846 | 4 |
| 1_sudo_localaccount | 26 | 54 | 16.356186 | 2 |
| 1_sudo_pam | 26 | 54 | 16.365813 | 3 |
| 1_sudo_sshkey | 26 | 54 | 16.325801 | 3 |
| 1_validaccount_localaccount | 26 | 56 | 16.361396 | 2 |
| 1_validaccount_pam | 26 | 56 | 16.291193 | 3 |
| 1_validaccount_sshkey | 26 | 56 | 16.315342 | 3 |
| 2_cron | 21 | 21 | 15.084725 | 0 |
| 2_rootkit | 26 | 29 | 15.078369 | 2 |
| 3_ssh_apt | 32 | 32 | 16.371926 | 0 |
| 3_ssh_healthcheck | 26 | 36 | 16.335847 | 1 |
| 3_ssh_puppet | 25 | 40 | 16.32783 | 2 |
| 3_vnc_apt | 28 | 54 | 16.33068 | 1 |
| 3_vnc_healthcheck | 25 | 57 | 16.369064 | 3 |
| 3_vnc_puppet | 22 | 60 | 16.366459 | 3 |
| 4 | 22 | 22 | 16.002598 | 0 |
| 5 | 3 | 3 | 35.05161 | 0 |
| 6_macro_binary | 22 | 23 | 16.360259 | 0 |
| 6_macro_cron | 20 | 24 | 16.358754 | 1 |
| 6_plugin | 13 | 37 | 15.003167 | 2 |
| 6_screensharing_binary | 38 | 59 | 16.004276 | 4 |
| 6_screensharing_cron | 33 | 60 | 16.233098 | 5 |
| 7 | 13 | 13 | 44.603984 | 0 |

### Publisher window check

The publisher's per-sequence slices were checked against the campaign step clock: 415 sequence dirs with events and steps, 47 contain events outside `[first_step - 1.0s, next_step)`, 43 have events before the first step (max lead 0.956s) and 4 have events after the window (max lag 616.488s). Events without any step: 0.

### Episodes: bundle vs campaign archives

The `steps/` view is a strict subset of the campaign archives: 0 bundle steps are absent from the archives, while 474 archive steps are absent from the bundle (all unlabelled: 0 labelled steps dropped). The episode unit is therefore one campaign archive (1806 steps over 34 archives), not a bundle sequence directory (1332 steps).

### The brief's 5,554-sequence / 11,388-step baseline does not reproduce

Per bundle the three views hold 2760 `attackmate.json` files and 4791 step lines. Counting both bundles and the campaign archives gives 5554 files and 11388 steps — exactly the brief's quoted 5,554 / 11,388. The baseline is therefore a file-and-line double-count across views and bundles, not a count of distinct attack episodes.

## Unlabelled steps — bundle

425 of 1332 steps (31.91%) carry no ATT&CK metadata. They are kept in every count above; none is dropped and none is relabelled.

| type | count |
|---|---|
| sleep | 256 |
| msf-session | 78 |
| vnc | 62 |
| msf-module | 9 |
| shell | 8 |
| setvar | 7 |
| debug | 3 |
| include | 1 |
| mktemp | 1 |

| command shape | count |
|---|---|
| sleep | 256 |
| editor-keystroke | 48 |
| command:move | 32 |
| command:click | 12 |
| command:exploit/multi/handler | 9 |
| command:key | 9 |
| command:ssh | 8 |
| command:shell | 8 |
| command:jj | 6 |
| command:type | 6 |
| command:getuid | 4 |
| command:revshell | 4 |
| command:curl | 3 |
| command:vim | 3 |
| command:id | 3 |
| command:cat | 3 |
| command:movement | 2 |
| command:fbbf9e022d1a6a03fbb1e859 | 2 |
| command:capture | 2 |
| command:659 | 1 |
| command:684 | 1 |
| command:include | 1 |
| command:rightclick | 1 |
| command:file | 1 |

## Unlabelled steps — campaign archives

899 of 1806 steps (49.78%) carry no ATT&CK metadata. They are kept in every count above; none is dropped and none is relabelled.

| type | count |
|---|---|
| sleep | 358 |
| vnc | 201 |
| msf-session | 160 |
| ssh | 53 |
| shell | 40 |
| mktemp | 20 |
| msf-module | 15 |
| setvar | 15 |
| msf-payload | 10 |
| include | 10 |
| webserv | 8 |
| debug | 5 |
| sliver | 3 |
| father | 1 |

| command shape | count |
|---|---|
| sleep | 358 |
| editor-keystroke | 77 |
| command:type | 57 |
| command:move | 56 |
| command:key | 44 |
| command:click | 36 |
| command:shell | 33 |
| command:cd | 23 |
| command:file | 19 |
| command:echo | 18 |
| command:pwd | 18 |
| command:exploit/multi/handler | 15 |
| command:jj | 14 |
| command:ssh | 13 |
| command:vim | 12 |
| command:cmd/unix/python/meterpre | 10 |
| command:include | 10 |
| command:HTTP-GET | 8 |
| command:getuid | 7 |
| command:capture | 7 |
| command:stty | 6 |
| command:id | 6 |
| command:sudo | 6 |
| command:movement | 6 |
| command:revshell | 4 |

## filtered vs raw

- `filtered` files: 17242; `raw` files: 44473; shared paths: 17242.
- Files only in `filtered`: 0; only in `raw`: 27231.
- Identical CRC on shared paths: 11973; differing content: 5269.
- Line-subset check on 3577 differing files: 0 violations. `filtered` is a strict line-subset of `raw` at identical paths; `raw` is the superset and the primary analysis root.

| path kind present only in `raw` | files |
|---|---|
| `corpdns/logs/log/collectd/collectd.log` | 1447 |
| `inetfw/logs/log/collectd/collectd.log` | 1447 |
| `inetfw/logs/log/suricata/eve.json` | 1403 |
| `corpdns/logs/log/suricata/eve.json` | 1325 |
| `videoserver/logs/log/collectd/collectd.log` | 1121 |
| `videoserver/logs/log/zm/zmc_m1.log` | 1037 |
| `videoserver/logs/log/syslog` | 849 |
| `corpdns/logs/log/audit/audit.log` | 606 |
| `inetfw/logs/log/audit/audit.log` | 578 |
| `inetfw/logs/log/syslog` | 453 |
| `videoserver/logs/log/zm/zmdc.log` | 418 |
| `videoserver/logs/log/zm/zmwatch.log` | 401 |
| `videoserver/logs/log/audit/audit.log` | 390 |
| `videoserver/logs/log/messages` | 313 |
| `linuxshare/logs/log/collectd/collectd.log` | 300 |
| `reposerver/logs/log/collectd/collectd.log` | 300 |
| `client/logs/log/collectd/collectd.log` | 184 |
| `attacker/logs/log/syslog` | 164 |
| `corpdns/logs/log/syslog` | 152 |
| `inetfw/logs/log/kern.log` | 118 |

## Step → manifestation join

Design: sort each campaign's steps by timestamp; a step's window is `[step_ts - lookback_s, next_step_ts)` (half-open), with the last step extended by `last_step_tail_s`. An event manifests a step when it falls in the window and shares at least one entity (`ip:`, `host:`, `url:`). `facts.json` maps each IP to its host; a shared entity naming a host other than the observing host is a cross-host edge.

| parameter | value |
|---|---|
| window | `[step_ts, next_step_ts) per campaign, half-open` |
| lookback_s | 2.0 |
| last_step_tail_s | 1800 |
| entity kinds | ip, host, url |
| syslog hosts | inetfw,corpdns |

| metric | value |
|---|---|
| steps | 1332 |
| steps with ≥1 manifestation | 746 |
| silent steps | 586 |
| steps with an empty publisher slice | 236 |
| raw token edges | 7445 |
| shared-entity edges | 7447 |
| steps with a cross-host edge | 22 |
| **cross-host edges** | **80** |

Shared-entity edges by kind: `{"host": 7445, "ip": 2}`. Cross-host edges by entity: `{"host:attacker": 77, "host:videoserver": 3}`.

The cross-host count is not zero, so the stopping condition (report zero with numbers) does not apply. It is small relative to the shared-entity total and rests on the `facts.json` IP→host map; DNS names are not used for identity because four external names resolve to the same gateway address in `dnsmasq`.

### filtered vs raw join

| metric | raw | filtered |
|---|---|---|
| events | 477050 | 452177 |
| silent steps | 586 | 907 |
| shared-entity edges | 7447 | 7417 |
| cross-host edges | 80 | 54 |
| steps with cross-host edge | 22 | 21 |

## Episode join — one campaign archive per episode

The bundle join above uses the publisher's per-sequence slices. Because the episode unit is a campaign archive, the same join is run over every extracted campaign archive: all archive steps, full campaign telemetry, same window and entity rules.

| metric | bundle join | episode join |
|---|---|---|
| steps | 1332 | 1806 |
| events | 477050 | 713963 |
| silent steps | 586 | 706 |
| shared-entity edges | 7447 | 7548 |
| steps with a cross-host edge | 22 | 27 |
| **cross-host edges** | **80** | **112** |

Episode events by host: `{"corpdns": 244041, "inetfw": 251006, "videoserver": 218296, "wazuh": 620}`. Cross-host by entity: `{"host:attacker": 77, "host:client": 5, "host:docker": 1, "host:videoserver": 29}`. Event parse failures: 0.

## Variant grid

| variant | sequences | runs | steps | archive steps | distinct techniques | unlabelled |
|---|---|---|---|---|---|---|
| 1_autostart_localaccount | 18 | 28 | 45 | 53 | 29 | 17 |
| 1_autostart_pam | 18 | 28 | 45 | 53 | 29 | 17 |
| 1_autostart_sshkey | 18 | 28 | 45 | 53 | 29 | 17 |
| 1_cron_localaccount | 20 | 30 | 41 | 49 | 30 | 11 |
| 1_cron_pam | 20 | 30 | 41 | 49 | 30 | 11 |
| 1_cron_sshkey | 20 | 30 | 41 | 49 | 30 | 11 |
| 1_pwnkit_localaccount | 19 | 26 | 34 | 39 | 31 | 6 |
| 1_pwnkit_pam | 19 | 26 | 34 | 39 | 31 | 6 |
| 1_pwnkit_sshkey | 19 | 26 | 34 | 39 | 31 | 6 |
| 1_racecondition_localaccount | 18 | 34 | 48 | 53 | 29 | 13 |
| 1_racecondition_pam | 18 | 34 | 48 | 53 | 29 | 13 |
| 1_racecondition_sshkey | 18 | 34 | 49 | 54 | 29 | 14 |
| 1_sudo_localaccount | 18 | 26 | 33 | 38 | 31 | 6 |
| 1_sudo_pam | 18 | 26 | 33 | 38 | 31 | 6 |
| 1_sudo_sshkey | 18 | 26 | 33 | 38 | 31 | 6 |
| 1_validaccount_localaccount | 18 | 26 | 34 | 38 | 31 | 7 |
| 1_validaccount_pam | 18 | 26 | 34 | 38 | 31 | 7 |
| 1_validaccount_sshkey | 18 | 26 | 34 | 38 | 31 | 7 |
| 2_cron | 19 | 21 | 23 | 29 | 21 | 2 |
| 2_rootkit | 22 | 26 | 28 | 43 | 23 | 2 |
| 3_ssh_apt | 22 | 32 | 37 | 55 | 26 | 5 |
| 3_ssh_healthcheck | 19 | 26 | 28 | 41 | 21 | 2 |
| 3_ssh_puppet | 17 | 25 | 30 | 39 | 20 | 5 |
| 3_vnc_apt | 19 | 28 | 40 | 77 | 23 | 11 |
| 3_vnc_healthcheck | 17 | 25 | 41 | 64 | 20 | 16 |
| 3_vnc_puppet | 15 | 22 | 41 | 67 | 18 | 18 |
| 4 | 11 | 22 | 34 | 46 | 10 | 12 |
| 5 | 3 | 3 | 5 | 7 | 4 | 2 |
| 6_macro_binary | 14 | 23 | 29 | 51 | 12 | 6 |
| 6_macro_cron | 11 | 21 | 29 | 51 | 10 | 8 |
| 6_plugin | 4 | 13 | 39 | 56 | 4 | 24 |
| 6_screensharing_binary | 12 | 39 | 105 | 178 | 13 | 63 |
| 6_screensharing_cron | 13 | 34 | 94 | 165 | 12 | 58 |
| 7 | 13 | 13 | 23 | 26 | 22 | 10 |

| scenario | variants |
|---|---|
| 1 | 18 |
| 2 | 2 |
| 3 | 6 |
| 4 | 1 |
| 5 | 1 |
| 6 | 5 |
| 7 | 1 |

Archive variants: 34; grid variants: 34; only in archives: []; only in the grid: [].

### Step chains (comparable form)

Each chain is `type:techniques` per step in timestamp order; `?` marks a step with no
technique and labels the unlabelled command shape. Full chains are also in the JSON.

- **1_autostart_localaccount** — `shell:T1590.002+T1591>shell:T1595+T1592.002>shell:T1595.002>sleep:?sleep>shell:T1595.003>sleep:?sleep>msf-module:T1190+T1059.006>msf-session:T1105>msf-session:T1059>msf-session:T1059>msf-session:T1059>msf-session:T1059>msf-session:T1059>msf-session:T1059>msf-session:T1087+T1083+T1201+T1069+T1057+T1518+T1082+T1614+T1016+T1049+T1033+T1007+T1615>sleep:?sleep>msf-session:T1033>msf-session:?command:curl>msf-session:?command:vim>msf-session:?editor-keystroke>msf-session:?editor-keystroke>msf-session:?editor-keystroke>msf-session:T1547>msf-session:T1547>msf-session:?editor-keystroke>shell:?command:ssh>sleep:?sleep>msf-module:?command:exploit/multi/handler>msf-session:T1059>msf-session:T1059>msf-session:T1059>msf-session:T1033>msf-session:T1105+T1136.001>sleep:?sleep>msf-session:T1033>msf-session:?editor-keystroke>msf-session:?editor-keystroke>sleep:?sleep>ssh:T1033>ssh:T1003.008>ssh:T1120>ssh:T1120>ssh:T1124>ssh:T1497.001>sleep:?sleep`
- **1_autostart_pam** — `shell:T1590.002+T1591>shell:T1595+T1592.002>shell:T1595.002>sleep:?sleep>shell:T1595.003>sleep:?sleep>msf-module:T1190+T1059.006>msf-session:T1105>msf-session:T1059>msf-session:T1059>msf-session:T1059>msf-session:T1059>msf-session:T1059>msf-session:T1059>msf-session:T1087+T1083+T1201+T1069+T1057+T1518+T1082+T1614+T1016+T1049+T1033+T1007+T1615>sleep:?sleep>msf-session:T1033>msf-session:?command:curl>msf-session:?command:vim>msf-session:?editor-keystroke>msf-session:?editor-keystroke>msf-session:?editor-keystroke>msf-session:T1547>msf-session:T1547>msf-session:?editor-keystroke>shell:?command:ssh>sleep:?sleep>msf-module:?command:exploit/multi/handler>msf-session:T1059>msf-session:T1059>msf-session:T1059>msf-session:T1033>msf-session:T1033>msf-session:?editor-keystroke>msf-session:?editor-keystroke>sleep:?sleep>ssh:T1033>ssh:T1003.008>ssh:T1120>ssh:T1120>ssh:T1124>ssh:T1497.001>sleep:?sleep>msf-session:T1105+T1556.003>sleep:?sleep`
- **1_autostart_sshkey** — `shell:T1590.002+T1591>shell:T1595+T1592.002>shell:T1595.002>sleep:?sleep>shell:T1595.003>sleep:?sleep>msf-module:T1190+T1059.006>msf-session:T1105>msf-session:T1059>msf-session:T1059>msf-session:T1059>msf-session:T1059>msf-session:T1059>msf-session:T1059>msf-session:T1087+T1083+T1201+T1069+T1057+T1518+T1082+T1614+T1016+T1049+T1033+T1007+T1615>sleep:?sleep>msf-session:T1033>msf-session:?command:curl>msf-session:?command:vim>msf-session:?editor-keystroke>msf-session:?editor-keystroke>msf-session:?editor-keystroke>msf-session:T1547>msf-session:T1547>msf-session:?editor-keystroke>shell:?command:ssh>sleep:?sleep>msf-module:?command:exploit/multi/handler>msf-session:T1059>msf-session:T1059>msf-session:T1059>msf-session:T1033>msf-session:T1033>msf-session:?editor-keystroke>msf-session:?editor-keystroke>sleep:?sleep>ssh:T1033>ssh:T1003.008>ssh:T1120>ssh:T1120>ssh:T1124>ssh:T1497.001>sleep:?sleep>msf-session:T1105+T1098.004>sleep:?sleep`
- **1_cron_localaccount** — `shell:T1590.002+T1591>shell:T1595+T1592.002>shell:T1595.002>sleep:?sleep>shell:T1595.003>sleep:?sleep>msf-module:T1190+T1059.006>msf-session:T1105>msf-session:T1059>msf-session:T1059>msf-session:T1059>msf-session:T1059>msf-session:T1059>msf-session:T1059>msf-session:T1087+T1083+T1201+T1069+T1057+T1518+T1082+T1614+T1016+T1049+T1033+T1007+T1615>sleep:?sleep>msf-session:T1033>msf-session:T1059>msf-session:T1059>msf-session:T1059>msf-session:T1033>msf-session:T1105+T1136.001>sleep:?sleep>msf-session:T1033>ssh:T1033>ssh:T1003.008>ssh:T1120>ssh:T1120>ssh:T1124>ssh:T1497.001>sleep:?sleep>msf-session:T1053>msf-session:T1053>msf-module:?command:exploit/multi/handler>msf-session:?command:getuid>msf-session:?command:shell>msf-session:T1059>msf-session:T1070.004>msf-session:?editor-keystroke>msf-session:?editor-keystroke>sleep:?sleep`
- **1_cron_pam** — `shell:T1590.002+T1591>shell:T1595+T1592.002>shell:T1595.002>sleep:?sleep>shell:T1595.003>sleep:?sleep>msf-module:T1190+T1059.006>msf-session:T1105>msf-session:T1059>msf-session:T1059>msf-session:T1059>msf-session:T1059>msf-session:T1059>msf-session:T1059>msf-session:T1087+T1083+T1201+T1069+T1057+T1518+T1082+T1614+T1016+T1049+T1033+T1007+T1615>sleep:?sleep>msf-session:T1033>msf-session:T1059>msf-session:T1059>msf-session:T1059>msf-session:T1033>msf-session:T1033>ssh:T1033>ssh:T1003.008>ssh:T1120>ssh:T1120>ssh:T1124>ssh:T1497.001>sleep:?sleep>msf-session:T1105+T1556.003>sleep:?sleep>msf-session:T1053>msf-session:T1053>msf-module:?command:exploit/multi/handler>msf-session:?command:getuid>msf-session:?command:shell>msf-session:T1059>msf-session:T1070.004>msf-session:?editor-keystroke>msf-session:?editor-keystroke>sleep:?sleep`
- **1_cron_sshkey** — `shell:T1590.002+T1591>shell:T1595+T1592.002>shell:T1595.002>sleep:?sleep>shell:T1595.003>sleep:?sleep>msf-module:T1190+T1059.006>msf-session:T1105>msf-session:T1059>msf-session:T1059>msf-session:T1059>msf-session:T1059>msf-session:T1059>msf-session:T1059>msf-session:T1087+T1083+T1201+T1069+T1057+T1518+T1082+T1614+T1016+T1049+T1033+T1007+T1615>sleep:?sleep>msf-session:T1033>msf-session:T1059>msf-session:T1059>msf-session:T1059>msf-session:T1033>msf-session:T1033>ssh:T1033>ssh:T1003.008>ssh:T1120>ssh:T1120>ssh:T1124>ssh:T1497.001>sleep:?sleep>msf-session:T1105+T1098.004>sleep:?sleep>msf-session:T1053>msf-session:T1053>msf-module:?command:exploit/multi/handler>msf-session:?command:getuid>msf-session:?command:shell>msf-session:T1059>msf-session:T1070.004>msf-session:?editor-keystroke>msf-session:?editor-keystroke>sleep:?sleep`
- **1_pwnkit_localaccount** — `shell:T1590.002+T1591>shell:T1595+T1592.002>shell:T1595.002>sleep:?sleep>shell:T1595.003>sleep:?sleep>msf-module:T1190+T1059.006>msf-session:T1105>msf-session:T1059>msf-session:T1059>msf-session:T1059>msf-session:T1059>msf-session:T1059>msf-session:T1059>msf-session:T1087+T1083+T1201+T1069+T1057+T1518+T1082+T1614+T1016+T1049+T1033+T1007+T1615>sleep:?sleep>msf-session:T1033>ssh:T1033>ssh:T1003.008>ssh:T1120>ssh:T1120>ssh:T1124>ssh:T1497.001>sleep:?sleep>msf-session:T1105>msf-session:T1068>msf-session:T1033>msf-session:T1105+T1136.001>msf-session:T1218+T1136.001>msf-session:T1070.004>msf-session:T1070.004>msf-session:T1070.004>msf-session:?editor-keystroke>sleep:?sleep`
- **1_pwnkit_pam** — `shell:T1590.002+T1591>shell:T1595+T1592.002>shell:T1595.002>sleep:?sleep>shell:T1595.003>sleep:?sleep>msf-module:T1190+T1059.006>msf-session:T1105>msf-session:T1059>msf-session:T1059>msf-session:T1059>msf-session:T1059>msf-session:T1059>msf-session:T1059>msf-session:T1087+T1083+T1201+T1069+T1057+T1518+T1082+T1614+T1016+T1049+T1033+T1007+T1615>sleep:?sleep>msf-session:T1033>ssh:T1033>ssh:T1003.008>ssh:T1120>ssh:T1120>ssh:T1124>ssh:T1497.001>sleep:?sleep>msf-session:T1105>msf-session:T1068>msf-session:T1033>msf-session:T1070.004>msf-session:T1070.004>msf-session:T1070.004>msf-session:?editor-keystroke>sleep:?sleep>msf-session:T1105+T1556.003>msf-session:T1218+T1556.003`
- **1_pwnkit_sshkey** — `shell:T1590.002+T1591>shell:T1595+T1592.002>shell:T1595.002>sleep:?sleep>shell:T1595.003>sleep:?sleep>msf-module:T1190+T1059.006>msf-session:T1105>msf-session:T1059>msf-session:T1059>msf-session:T1059>msf-session:T1059>msf-session:T1059>msf-session:T1059>msf-session:T1087+T1083+T1201+T1069+T1057+T1518+T1082+T1614+T1016+T1049+T1033+T1007+T1615>sleep:?sleep>msf-session:T1033>ssh:T1033>ssh:T1003.008>ssh:T1120>ssh:T1120>ssh:T1124>ssh:T1497.001>sleep:?sleep>msf-session:T1105>msf-session:T1068>msf-session:T1033>msf-session:T1070.004>msf-session:T1070.004>msf-session:T1070.004>msf-session:?editor-keystroke>sleep:?sleep>msf-session:T1105+T1098.004>msf-session:T1218+T1098.004`
- **1_racecondition_localaccount** — `shell:T1590.002+T1591>shell:T1595+T1592.002>shell:T1595.002>sleep:?sleep>shell:T1595.003>sleep:?sleep>msf-module:T1190+T1059.006>msf-session:T1105>msf-session:T1059>msf-session:T1059>msf-session:T1059>msf-session:T1059>msf-session:T1059>msf-session:T1059>msf-session:T1087+T1083+T1201+T1069+T1057+T1518+T1082+T1614+T1016+T1049+T1033+T1007+T1615>sleep:?sleep>msf-session:T1033>msf-session:T1059>msf-session:T1059>msf-session:T1059>msf-session:T1033>msf-session:T1105+T1136.001>sleep:?sleep>msf-session:T1033>msf-session:?editor-keystroke>msf-session:?editor-keystroke>sleep:?sleep>ssh:T1033>ssh:T1003.008>ssh:T1120>ssh:T1120>ssh:T1124>ssh:T1497.001>sleep:?sleep>msf-session:T1105>msf-session:T1059>msf-session:T1546>msf-session:T1546>msf-session:T1546>msf-session:T1546>msf-session:T1546>msf-session:T1546>sleep:T1546>msf-session:?command:id>msf-session:?command:cat>shell:?command:ssh>msf-module:?command:exploit/multi/handler>msf-session:?command:shell`
- **1_racecondition_pam** — `shell:T1590.002+T1591>shell:T1595+T1592.002>shell:T1595.002>sleep:?sleep>shell:T1595.003>sleep:?sleep>msf-module:T1190+T1059.006>msf-session:T1105>msf-session:T1059>msf-session:T1059>msf-session:T1059>msf-session:T1059>msf-session:T1059>msf-session:T1059>msf-session:T1087+T1083+T1201+T1069+T1057+T1518+T1082+T1614+T1016+T1049+T1033+T1007+T1615>sleep:?sleep>msf-session:T1033>msf-session:T1059>msf-session:T1059>msf-session:T1059>msf-session:T1033>msf-session:T1033>msf-session:?editor-keystroke>msf-session:?editor-keystroke>sleep:?sleep>ssh:T1033>ssh:T1003.008>ssh:T1120>ssh:T1120>ssh:T1124>ssh:T1497.001>sleep:?sleep>msf-session:T1105+T1556.003>sleep:?sleep>msf-session:T1105>msf-session:T1059>msf-session:T1546>msf-session:T1546>msf-session:T1546>msf-session:T1546>msf-session:T1546>msf-session:T1546>sleep:T1546>msf-session:?command:id>msf-session:?command:cat>shell:?command:ssh>msf-module:?command:exploit/multi/handler>msf-session:?command:shell`
- **1_racecondition_sshkey** — `shell:T1590.002+T1591>shell:T1595+T1592.002>shell:T1595.002>sleep:?sleep>shell:T1595.003>sleep:?sleep>msf-module:T1190+T1059.006>msf-session:T1105>msf-session:T1059>msf-session:T1059>msf-session:T1059>msf-session:T1059>msf-session:T1059>msf-session:T1059>msf-session:T1087+T1083+T1201+T1069+T1057+T1518+T1082+T1614+T1016+T1049+T1033+T1007+T1615>sleep:?sleep>msf-session:T1033>msf-session:T1059>msf-session:T1059>msf-session:T1059>msf-session:T1033>msf-session:T1033>msf-session:?editor-keystroke>msf-session:?editor-keystroke>sleep:?sleep>ssh:T1033>ssh:T1003.008>ssh:T1120>ssh:T1120>ssh:T1124>ssh:T1497.001>sleep:?sleep>msf-session:T1105+T1098.004>sleep:?sleep>msf-session:T1105>msf-session:T1059>msf-session:T1546>msf-session:T1546>msf-session:T1546>msf-session:T1546>msf-session:T1546>msf-session:T1546>sleep:T1546>msf-session:?command:id>msf-session:?command:cat>shell:?command:ssh>msf-module:?command:exploit/multi/handler>msf-session:?command:getuid>msf-session:?command:shell`
- **1_sudo_localaccount** — `shell:T1590.002+T1591>shell:T1595+T1592.002>shell:T1595.002>sleep:?sleep>shell:T1595.003>sleep:?sleep>msf-module:T1190+T1059.006>msf-session:T1105>msf-session:T1059>msf-session:T1059>msf-session:T1059>msf-session:T1059>msf-session:T1059>msf-session:T1059>msf-session:T1087+T1083+T1201+T1069+T1057+T1518+T1082+T1614+T1016+T1049+T1033+T1007+T1615>sleep:?sleep>msf-session:T1033>ssh:T1033>ssh:T1003.008>ssh:T1120>ssh:T1120>ssh:T1124>ssh:T1497.001>sleep:?sleep>msf-session:T1033>msf-session:T1105+T1136.001>msf-session:T1218+T1136.001>msf-session:T1070.004>msf-session:T1070.004>msf-session:?editor-keystroke>sleep:?sleep>msf-session:T1548.003>msf-session:T1548.003`
- **1_sudo_pam** — `shell:T1590.002+T1591>shell:T1595+T1592.002>shell:T1595.002>sleep:?sleep>shell:T1595.003>sleep:?sleep>msf-module:T1190+T1059.006>msf-session:T1105>msf-session:T1059>msf-session:T1059>msf-session:T1059>msf-session:T1059>msf-session:T1059>msf-session:T1059>msf-session:T1087+T1083+T1201+T1069+T1057+T1518+T1082+T1614+T1016+T1049+T1033+T1007+T1615>sleep:?sleep>msf-session:T1033>ssh:T1033>ssh:T1003.008>ssh:T1120>ssh:T1120>ssh:T1124>ssh:T1497.001>sleep:?sleep>msf-session:T1033>msf-session:T1070.004>msf-session:T1070.004>msf-session:?editor-keystroke>sleep:?sleep>msf-session:T1105+T1556.003>msf-session:T1218+T1556.003>msf-session:T1548.003>msf-session:T1548.003`
- **1_sudo_sshkey** — `shell:T1590.002+T1591>shell:T1595+T1592.002>shell:T1595.002>sleep:?sleep>shell:T1595.003>sleep:?sleep>msf-module:T1190+T1059.006>msf-session:T1105>msf-session:T1059>msf-session:T1059>msf-session:T1059>msf-session:T1059>msf-session:T1059>msf-session:T1059>msf-session:T1087+T1083+T1201+T1069+T1057+T1518+T1082+T1614+T1016+T1049+T1033+T1007+T1615>sleep:?sleep>msf-session:T1033>ssh:T1033>ssh:T1003.008>ssh:T1120>ssh:T1120>ssh:T1124>ssh:T1497.001>sleep:?sleep>msf-session:T1033>msf-session:T1070.004>msf-session:T1070.004>msf-session:?editor-keystroke>sleep:?sleep>msf-session:T1105+T1098.004>msf-session:T1218+T1098.004>msf-session:T1548.003>msf-session:T1548.003`
- **1_validaccount_localaccount** — `shell:T1590.002+T1591>shell:T1595+T1592.002>shell:T1595.002>sleep:?sleep>shell:T1595.003>sleep:?sleep>msf-module:T1190+T1059.006>msf-session:T1105>msf-session:T1059>msf-session:T1059>msf-session:T1059>msf-session:T1059>msf-session:T1059>msf-session:T1059>msf-session:T1087+T1083+T1201+T1069+T1057+T1518+T1082+T1614+T1016+T1049+T1033+T1007+T1615>sleep:?sleep>msf-session:T1033>ssh:T1033>ssh:T1003.008>ssh:T1120>ssh:T1120>ssh:T1124>ssh:T1497.001>sleep:?sleep>msf-session:T1033>msf-session:T1105+T1136.001>msf-session:T1218+T1136.001>msf-session:T1070.004>msf-session:T1070.004>msf-session:?editor-keystroke>msf-session:?editor-keystroke>sleep:?sleep>msf-session:T1078.003>msf-session:T1078.003`
- **1_validaccount_pam** — `shell:T1590.002+T1591>shell:T1595+T1592.002>shell:T1595.002>sleep:?sleep>shell:T1595.003>sleep:?sleep>msf-module:T1190+T1059.006>msf-session:T1105>msf-session:T1059>msf-session:T1059>msf-session:T1059>msf-session:T1059>msf-session:T1059>msf-session:T1059>msf-session:T1087+T1083+T1201+T1069+T1057+T1518+T1082+T1614+T1016+T1049+T1033+T1007+T1615>sleep:?sleep>msf-session:T1033>ssh:T1033>ssh:T1003.008>ssh:T1120>ssh:T1120>ssh:T1124>ssh:T1497.001>sleep:?sleep>msf-session:T1033>msf-session:T1070.004>msf-session:T1070.004>msf-session:?editor-keystroke>msf-session:?editor-keystroke>sleep:?sleep>msf-session:T1105+T1556.003>msf-session:T1218+T1556.003>msf-session:T1078.003>msf-session:T1078.003`
- **1_validaccount_sshkey** — `shell:T1590.002+T1591>shell:T1595+T1592.002>shell:T1595.002>sleep:?sleep>shell:T1595.003>sleep:?sleep>msf-module:T1190+T1059.006>msf-session:T1105>msf-session:T1059>msf-session:T1059>msf-session:T1059>msf-session:T1059>msf-session:T1059>msf-session:T1059>msf-session:T1087+T1083+T1201+T1069+T1057+T1518+T1082+T1614+T1016+T1049+T1033+T1007+T1615>sleep:?sleep>msf-session:T1033>ssh:T1033>ssh:T1003.008>ssh:T1120>ssh:T1120>ssh:T1124>ssh:T1497.001>sleep:?sleep>msf-session:T1033>msf-session:T1070.004>msf-session:T1070.004>msf-session:?editor-keystroke>msf-session:?editor-keystroke>sleep:?sleep>msf-session:T1105+T1098.004>msf-session:T1218+T1098.004>msf-session:T1078.003>msf-session:T1078.003`
- **2_cron** — `ssh:T1021.004>sliver:T1071.001+T1573.001>sftp:T1105>ssh:T1547+T1569>sliver-session:T1083>sliver-session:T1057>regex:T1007>debug:?command:659>sliver-session:T1003>sliver-session:T1049>sliver-session:T1016>sliver-session:T1003.008+T1041>sliver-session:T1560.001+T1074.001>sliver-session:T1041>sliver-session:T1070.004>sliver-session:T1005>sliver-session:T1201>sliver-session:T1003.008>sliver-session:T1201>sliver-session:T1105+T1046+T1018>sliver-session:T1046+T1018>sliver-session:T1046+T1018>sleep:?sleep`
- **2_rootkit** — `sftp:T1105>sliver-session:T1083>sliver-session:T1057>regex:T1007>debug:?command:684>sliver-session:T1003>sliver-session:T1049>sliver-session:T1016>sliver-session:T1003.008+T1041>sliver-session:T1560.001+T1074.001>sliver-session:T1041>sliver-session:T1070.004>sliver-session:T1005>sliver-session:T1201>sliver-session:T1003.008>sliver-session:T1201>sliver-session:T1105+T1046+T1018>sliver-session:T1046+T1018>sliver-session:T1046+T1018>sleep:?sleep>ssh:T1021>sftp:T1105>sliver:T1071.001+T1573>ssh:T1543.002>ssh:T1543.002>ssh:T1014+T1564+T1574>ssh:T1543.002>ssh:T1543.002`
- **3_ssh_apt** — `shell:T1078.002+T1110.001+T1133>ssh:T1078.002>ssh:T1040>sleep:?sleep>ssh:T1078.003>ssh:T1078.003>ssh:T1003.008>ssh:T1213>ssh:T1039>ssh:T1083>ssh:T1059.004>sleep:?sleep>ssh:T1036.005+T1564.001>ssh:T1574>ssh:T1059+T1574>ssh:T1059+T1574>ssh:T1053.003+T1105+T1071.001>ssh:T1053.003+T1105+T1071.001>ssh:T1072>ssh:T1072>shell:?command:ssh>sleep:?sleep>msf-session:T1059>msf-session:T1059>msf-session:T1059>msf-session:T1059>msf-session:T1059>msf-session:T1059>msf-session:T1486+T1105>msf-session:T1486+T1565.001>msf-session:T1018>msf-session:T1087.001>msf-session:T1531>msf-session:T1485>msf-session:T1490>msf-session:T1489>sleep:?sleep`
- **3_ssh_healthcheck** — `shell:T1078.002+T1110.001+T1133>ssh:T1078.002>ssh:T1040>sleep:?sleep>ssh:T1078.003>ssh:T1078.003>ssh:T1003.008>ssh:T1213>ssh:T1039>msf-session:T1059>msf-session:T1059>msf-session:T1059>msf-session:T1059>msf-session:T1059>msf-session:T1059>msf-session:T1486+T1105>msf-session:T1486+T1565.001>msf-session:T1018>msf-session:T1087.001>msf-session:T1531>msf-session:T1485>msf-session:T1490>msf-session:T1489>sleep:?sleep>ssh:T1080>ssh:T1080>msf-session:T1082>msf-session:T1033`
- **3_ssh_puppet** — `shell:T1078.002+T1110.001+T1133>ssh:T1040>sleep:?sleep>ssh:T1078.003>ssh:T1078.003>ssh:T1003.008>ssh:T1213>ssh:T1039>msf-session:T1059>msf-session:T1059>msf-session:T1059>msf-session:T1059>msf-session:T1059>msf-session:T1059>msf-session:T1486+T1105>msf-session:T1486+T1565.001>msf-session:T1018>msf-session:T1087.001>msf-session:T1531>msf-session:T1485>msf-session:T1490>msf-session:T1489>sleep:?sleep>ssh:T1078.003>ssh:T1072+T1105+T1059.004>ssh:T1072+T1105+T1059.004>ssh:T1072+T1105+T1059.004>msf-session:?command:shell>setvar:?command:movement>include:?command:include`
- **3_vnc_apt** — `msf-session:T1059>msf-session:T1059>msf-session:T1059>msf-session:T1059>msf-session:T1059>msf-session:T1059>msf-session:T1486+T1105>msf-session:T1486+T1565.001>msf-session:T1018>msf-session:T1087.001>msf-session:T1531>msf-session:T1485>msf-session:T1490>msf-session:T1489>sleep:?sleep>loop:T1110.001+T1021.005>vnc:?command:move>vnc:T1021.005>sleep:?sleep>vnc:T1021.005>sleep:?sleep>vnc:T1021.005>sleep:?sleep>vnc:T1003.008>sleep:?sleep>vnc:T1213>sleep:?sleep>vnc:T1039>sleep:?sleep>vnc:T1083>vnc:T1059.004>sleep:?sleep>vnc:T1036.005+T1564.001>vnc:T1574>vnc:T1059+T1574>vnc:T1053.003+T1105+T1071.001>vnc:T1072>vnc:T1072>shell:?command:ssh>sleep:?sleep`
- **3_vnc_healthcheck** — `msf-session:T1059>msf-session:T1059>msf-session:T1059>msf-session:T1059>msf-session:T1059>msf-session:T1059>msf-session:T1486+T1105>msf-session:T1486+T1565.001>msf-session:T1018>msf-session:T1087.001>msf-session:T1531>msf-session:T1485>msf-session:T1490>msf-session:T1489>sleep:?sleep>msf-session:T1082>msf-session:T1033>vnc:T1021.005>sleep:?sleep>vnc:T1021.005>sleep:?sleep>vnc:T1021.005>sleep:?sleep>vnc:T1003.008>sleep:?sleep>vnc:T1213>sleep:?sleep>vnc:T1039>sleep:?sleep>loop:T1110.001+T1021.005>vnc:?command:move>vnc:?command:move>vnc:?command:move>vnc:?command:move>vnc:?command:move>vnc:?command:move>vnc:?command:move>vnc:?command:move>vnc:T1105+T1059.004+T1053.003+T1021.005+T1071.001>sleep:?sleep>vnc:T1021.005`
- **3_vnc_puppet** — `msf-session:T1059>msf-session:T1059>msf-session:T1059>msf-session:T1059>msf-session:T1059>msf-session:T1059>msf-session:T1486+T1105>msf-session:T1486+T1565.001>msf-session:T1018>msf-session:T1087.001>msf-session:T1531>msf-session:T1485>msf-session:T1490>msf-session:T1489>sleep:?sleep>vnc:T1021.005>sleep:?sleep>vnc:T1021.005>sleep:?sleep>vnc:T1003.008>sleep:?sleep>vnc:T1213>sleep:?sleep>vnc:T1039>sleep:?sleep>loop:T1110.001+T1021.005>vnc:?command:move>vnc:?command:move>vnc:?command:move>vnc:?command:move>vnc:?command:move>vnc:?command:move>vnc:?command:move>vnc:?command:move>vnc:T1078.003>sleep:?sleep>vnc:T1078.003>sleep:?sleep>vnc:T1072+T1105+T1059.004>msf-session:?command:shell>setvar:?command:movement`
- **4** — `sliver:T1071.001>sliver:T1071.001>shell:T1078.003+T1105+T1205.001>sleep:?sleep>ssh:T1078.003>sleep:?sleep>ssh:T1078.003>sleep:?sleep>ssh:T1078.003>ssh:T1548.003>sleep:?sleep>ssh:T1548.003>ssh:T1036.005+T1205.001>ssh:T1070.004>ssh:T1543.002>ssh:T1543.002>sleep:?sleep>ssh:T1543.002>sleep:?sleep>ssh:T1543.002>sleep:?sleep>ssh:T1543.002>sleep:?sleep>shell:T1205.001+T1071.001+T1036.005>sleep:?sleep>sliver-session:T1599>sliver-session:T1599>ssh:T1078.003>ssh:T1078.003>sleep:?sleep>ssh:T1078.003>sleep:?sleep>ssh:T1082>sleep:?sleep`
- **5** — `shell:T1040+T1557.002>shell:T1040+T1528>setvar:?command:fbbf9e022d1a6a03fbb1e859>debug:?command:fbbf9e022d1a6a03fbb1e859>http-client:T1550.001`
- **6_macro_binary** — `vnc:T1105+T1204.002>sleep:?sleep>vnc:T1204.002>sleep:?sleep>msf-session:T1082>msf-session:T1105>setvar:?command:revshell>msf-session:T1059.004>msf-session:T1059.004>msf-session:T1059.004>msf-session:T1059.004>msf-session:T1059.004>msf-session:T1059.004>msf-session:T1105>msf-session:T1574.008+T1546>msf-session:T1222.002>msf-session:T1105>msf-session:T1115>msf-session:T1564.001>msf-session:T1222.002>msf-session:T1222.002>msf-session:T1010>msf-session:T1053.003>msf-session:T1053.003>msf-session:?command:jj>msf-session:T1053.003>msf-session:T1070.003>msf-session:?editor-keystroke>sleep:?sleep`
- **6_macro_cron** — `vnc:T1105+T1204.002>sleep:?sleep>vnc:T1204.002>sleep:?sleep>msf-session:T1082>msf-session:T1105>setvar:?command:revshell>msf-session:T1059.004>msf-session:T1059.004>msf-session:T1059.004>msf-session:T1059.004>msf-session:T1059.004>msf-session:T1059.004>msf-session:T1105>msf-session:T1115>msf-session:T1564.001>msf-session:T1222.002>msf-session:T1222.002>msf-session:T1010>msf-session:T1053.003>msf-session:T1053.003>msf-session:?command:jj>msf-session:?editor-keystroke>msf-session:T1070.003>msf-session:?editor-keystroke>sleep:?sleep>msf-session:T1053.003>msf-session:?command:jj>msf-session:T1053.003`
- **6_plugin** — `vnc:T1176+T1056.001+T1056.004+T1115>sleep:?sleep>vnc:T1176+T1056.001+T1056.004+T1115>sleep:?sleep>vnc:T1176+T1056.001+T1056.004+T1115>sleep:?sleep>vnc:T1176+T1056.001+T1056.004+T1115>sleep:?sleep>vnc:T1176+T1056.001+T1056.004+T1115>sleep:?sleep>vnc:T1176+T1056.001+T1056.004+T1115>sleep:?sleep>vnc:T1176+T1056.001+T1056.004+T1115>sleep:?sleep>vnc:T1176+T1056.001+T1056.004+T1115>sleep:?sleep>vnc:T1056.001>sleep:?sleep>vnc:T1056.001>sleep:?sleep>vnc:?command:key>sleep:?sleep>vnc:T1056.004+T1056.001>sleep:?sleep>vnc:?command:key>vnc:T1056.004+T1056.001>sleep:?sleep>vnc:?command:key>sleep:?sleep>vnc:T1056.004>sleep:?sleep>vnc:?command:move>sleep:?sleep>vnc:?command:rightclick>sleep:?sleep>vnc:T1115>sleep:?sleep>vnc:T1115>sleep:?sleep`
- **6_screensharing_binary** — `msf-session:T1082>msf-session:T1105>setvar:?command:revshell>msf-session:T1059.004>msf-session:T1059.004>msf-session:T1059.004>msf-session:T1059.004>msf-session:T1059.004>msf-session:T1059.004>msf-session:T1105>msf-session:T1115>msf-session:T1222.002>msf-session:T1222.002>msf-session:T1010>msf-session:T1053.003>msf-session:T1053.003>msf-session:?command:jj>msf-session:T1053.003>msf-session:T1070.003>msf-session:?editor-keystroke>sleep:?sleep>vnc:T1204.001+T1105+T1566.004>sleep:?sleep>vnc:T1204.001+T1105+T1566.004>sleep:?sleep>vnc:T1204.001+T1219>sleep:?sleep>vnc:T1204.001+T1219>sleep:?sleep>vnc:T1566.004+T1219>sleep:?sleep>vnc:T1566.004+T1219>sleep:?sleep>vnc:T1566.004+T1219>sleep:?sleep>vnc:?command:move>sleep:?sleep>vnc:T1566.004+T1219>sleep:?sleep>vnc:?command:click>sleep:?sleep>vnc:?command:move>vnc:?command:click>sleep:?sleep>vnc:?command:move>vnc:?command:click>sleep:?sleep>vnc:?command:type>sleep:?sleep>vnc:?command:key>sleep:?sleep>vnc:?command:move>vnc:?command:click>sleep:?sleep>vnc:T1219>sleep:?sleep>vnc:T1219>sleep:?sleep>vnc:?command:move>vnc:?command:click>sleep:?sleep>vnc:?command:type>sleep:?sleep>vnc:?command:key>sleep:?sleep>vnc:?command:capture>vnc:?command:move>vnc:?command:click>sleep:?sleep>vnc:T1219>sleep:?sleep>vnc:?command:move>sleep:?sleep>vnc:?command:type>sleep:?sleep>vnc:?command:key>sleep:?sleep>vnc:T1219>sleep:?sleep>vnc:T1105+T1219+T1564.001>sleep:?sleep>vnc:T1105+T1219+T1564.001>sleep:?sleep>vnc:T1222.002+T1219>sleep:?sleep>vnc:T1222.002+T1219>sleep:?sleep>vnc:T1222.002+T1219>sleep:?sleep>vnc:T1105+T1219>sleep:?sleep>vnc:T1105+T1219>sleep:?sleep>vnc:T1222.002+T1219>sleep:?sleep>vnc:T1574.008+T1219>sleep:?sleep>vnc:T1574.008+T1219>sleep:?sleep>vnc:T1574.008+T1219>sleep:?sleep>vnc:T1059.004+T1219>sleep:?sleep>vnc:T1059.004+T1219>sleep:?sleep`
- **6_screensharing_cron** — `msf-session:T1082>msf-session:T1105>setvar:?command:revshell>msf-session:T1059.004>msf-session:T1059.004>msf-session:T1059.004>msf-session:T1059.004>msf-session:T1059.004>msf-session:T1059.004>msf-session:T1105>msf-session:T1115>msf-session:T1222.002>msf-session:T1222.002>msf-session:T1010>msf-session:T1053.003>msf-session:T1053.003>msf-session:?command:jj>msf-session:?editor-keystroke>msf-session:T1070.003>msf-session:?editor-keystroke>sleep:?sleep>msf-session:T1053.003>msf-session:?command:jj>msf-session:T1053.003>vnc:T1204.001+T1105+T1566.004>sleep:?sleep>vnc:T1204.001+T1105+T1566.004>sleep:?sleep>vnc:T1204.001+T1219>sleep:?sleep>vnc:T1204.001+T1219>sleep:?sleep>vnc:T1566.004+T1219>sleep:?sleep>vnc:T1566.004+T1219>sleep:?sleep>vnc:T1566.004+T1219>sleep:?sleep>vnc:?command:move>sleep:?sleep>vnc:T1566.004+T1219>sleep:?sleep>vnc:?command:click>sleep:?sleep>vnc:?command:move>vnc:?command:click>sleep:?sleep>vnc:?command:move>vnc:?command:click>sleep:?sleep>vnc:?command:type>sleep:?sleep>vnc:?command:key>sleep:?sleep>vnc:?command:move>vnc:?command:click>sleep:?sleep>vnc:T1219>sleep:?sleep>vnc:T1219>sleep:?sleep>vnc:?command:move>vnc:?command:click>sleep:?sleep>vnc:?command:type>sleep:?sleep>vnc:?command:key>sleep:?sleep>vnc:?command:capture>vnc:?command:move>vnc:?command:click>sleep:?sleep>vnc:T1219>sleep:?sleep>vnc:?command:move>sleep:?sleep>vnc:?command:type>sleep:?sleep>vnc:?command:key>sleep:?sleep>vnc:T1219>sleep:?sleep>vnc:T1105+T1219+T1564.001>sleep:?sleep>vnc:T1105+T1219+T1564.001>sleep:?sleep>vnc:T1222.002+T1219>sleep:?sleep>vnc:T1222.002+T1219>sleep:?sleep>vnc:T1219+T1059.004>sleep:?sleep>vnc:T1219+T1059.004>sleep:?sleep`
- **7** — `shell:T1590.002+T1591>shell:T1589.002>sleep:?sleep>shell:T1078.002+T1110.001+T1133>sleep:?sleep>http-client:T1592.002>sliver:T1071.001+T1573.001>msf-module:T1190+T1059.004+T1095>msf-session:T1033>sleep:?sleep>shell:T1057>sleep:?sleep>shell:T1016>sleep:?sleep>shell:T1610+T1525+T1053.003+T1210>sleep:?sleep>sliver-session:T1083>sleep:?sleep>sliver-session:T1057>mktemp:?command:file>sleep:?sleep>sliver-session:T1003.008+T1041>sleep:?sleep`

## What this cannot evidence

- CAM-LDS has no per-event ground truth. The join is a reproducible attribution, not a
  scored accuracy result; nothing here validates it against published truth.
- Cross-host identity depends on `facts.json`; entities that never appear in an IP-to-host
  mapping cannot become a cross-host edge.
- 706 steps produce no manifestation in the window. These are reported,
  not repaired.
