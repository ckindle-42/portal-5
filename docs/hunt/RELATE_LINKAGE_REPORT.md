# RELATE linkage report — what actually connects the attack steps

Data-first analysis of the two training corpora that relate has failed on for four live
runs. It answers one question per consecutive attack-step pair: **what concretely links
their log lines — a shared host, user, session or PID, source IP, file path, URL, or only
time — and how far apart in time, across which sources.** The same question is asked of the
benign lines in the same windows, so the distinctive links are separated from the noise.
Every number below was read from the on-disk corpus, not estimated.

## Corpus and files read

| Corpus | Keys | Labelled lines | Raw logs | Index |
|---|---|---|---|---|
| kyoushi | `corpora/hunt_bed/kyoushi_s1_ingest/keys.jsonl` | 408,038 | `kyoushi_s1/gather/` | `hb_kyoushi_s1` |
| santos | `corpora/ait_lds_v21/santos_ingest/keys.jsonl` | 47,367 | `ait_lds_v21/santos/gather/` | `hb_ait_santos` |

The stored Stage-3 receipt examined for the "what relate actually did" side is
`/Volumes/data01/portal5_hunt/snap_s3_6648dc6/results/hunt/knowledge_s3a/{kyoushi,santos}/relate.json`
and its sibling `behaviours.duckdb`.

---

## 1. Kyoushi — the attack is one actor, on two hosts, over three days

The labelled steps, in kill-chain order, with the entities their lines actually carry:

| Stage | Step labels | Host · source | Lines | Entities in the lines | Time span |
|---|---|---|---|---|---|
| 0 | `attacker_vpn`, `foothold` | vpn · `/openvpn.log` | 336 | VPN user `ffeichtner`, public IP `192.42.0.255` / `192.42.1.252` | Mar 23 20:31:00 → Mar 25 20:36 |
| 1 | `dirb`, `foothold`, `attacker_http` | intranet_server · `…-access.log.4` + `…-error.log.2` | 407,670 | source IP `172.16.100.151` (100% of lines), UA `MSIE 6.0` | Mar 23 20:32:09 → 21:13:13 |
| 2 | `webshell_upload`, `webshell_cmd` | intranet_server · `…-access.log.4` (lines 408468–408477) | 10 | `172.16.100.151`, UA `python-requests/2.25.1`, URL `special-1616533976.4603.php` | Mar 23 21:12:56 → 21:13:13 |
| 3 | `escalate`, `attacker_change_user`, `escalated_command`, `escalated_sudo_command`, `escalated_sudo_session` | intranet_server · `/audit/audit.log` + `/auth.log` | 31 | **no IP** (`hostname=? addr=?`); user chain `www-data`→`su msperl`→`sudo`; terminal `/dev/pts/1` | Mar 25 20:36:52 → 20:37:05 |
| 4 | `reverse_shell` | intranet_server · `/apache2/error.log.2` line 3 | 1 | **none** — see §4 | (no timestamp on the line) |

### What links each consecutive pair

| Pair | Link | Time gap |
|---|---|---|
| vpn → dirb | **subnet + time only.** The VPN hands the attacker the internal address that the dirb requests then come from (`192.42.0.255` → `172.16.100.151`); no single line names both. | **69 s** |
| dirb → webshell | **same source IP `172.16.100.151`**, same host, same source file. | **~40 min** |
| webshell → escalate | **same host + the user `www-data`** (the webshell runs as Apache; the `su` is `…su for msperl by www-data`, working dir is the webshell's uploads dir). No shared IP — the `su`/`sudo` lines carry `addr=?`. | **47.4 h (~2 days)** |
| escalate → reverse_shell | **host only** (`intranet_server`), plus inferred time. The `reverse_shell` line shares no IP, no user, no session, no PID with the `sudo`/`su` lines. | **~0** (the shell line is untimestamped; see §4) |

### Distinctiveness of those links (vs benign in the same windows)

The intranet_server access log holds **9 distinct client IPs** over the whole attack window.
The attacker is `172.16.100.151`, which accounts for **406,469 of 408,395 requests (99.5%)**
and is the *only* client using the dirb user-agent `Mozilla/4.0 (compatible; MSIE 6.0; …)`.
The other eight are `172.16.0.x` office users at ~0.5% combined. So the web link is
distinctive **by volume and user-agent, not by being a rare address** — in fact the same
address is mirrored across five hosts' Suricata `eve.json` flows, so a *host-count rarity*
metric (what relate currently uses) scores it as common, not distinctive.

The escalation link (`www-data` → `su msperl` → `sudo`) is distinctive by **user**: `msperl`
is one employee account, and `su`/`sudo` from the Apache user is unusual. Benign lines in
the same `auth.log`/`audit.log` window are `cron` runs as `root` every ~20 minutes — no
`su`, no `sudo`.

---

## 2. Santos — the web phase is fast; the exfiltration is a different host and a different day

| Stage | Step labels | Host · source | Entities in the lines | Time span |
|---|---|---|---|---|
| 0 | `attacker_vpn`, `foothold` | vpn · `/openvpn.log` | VPN IP `10.229.2.216` | Jan 17 11:15:00 |
| 1 | `network_scan`, `service_scan`, `dns_scan`, `traceroute` | inet-firewall · `/dnsmasq.log` (PTR queries) | source `172.21.128.119` | Jan 17 11:15:09 → 11:21:46 |
| 2 | `dirb`, `wpscan`, `foothold`, `attacker_http` | intranet_server · `…-access.log` + `…-error.log` | `172.21.128.119` (UA `WPScan` then `python-requests`) | Jan 17 11:22:02 → 11:24:14 |
| 3 | `webshell_upload`, `webshell_cmd`, `escalate` | intranet_server · `…-access.log` + inet-firewall · `/dnsmasq.log` | `172.21.128.119`; the webshell `wget`s `wphashcrack` + `rockyou.txt` | Jan 17 11:24:16 → 11:24:45 |
| 4 | `escalate`, `attacker_change_user`, `escalated_*`, `crack_passwords` | intranet_server · `/audit.log`+`/auth.log`; monitoring · `…-system.cpu.log` | **no IP**; `www-data`→`su gmorgan`→`sudo`; `/dev/pts/1`; CPU "nice"≈0.96 | Jan 17 11:24:58 → 12:12:14 |
| 5 | `dnsteal`, `dnsteal-received`, `attacker`, `exfiltration-service` | inet-firewall · `/dnsmasq.log` (38,561 lines) + internal_share · `/audit/audit.log` | source `192.168.104.218`, exfil domain `kiirjekuimkpcrcioastvkeodpnimx.biz` | **Jan 14 00:00 → Jan 16 07:16** |

### What links each consecutive pair

| Pair | Link | Time gap |
|---|---|---|
| vpn → recon | **subnet + time** (`10.229.2.216` → `172.21.128.119`) | **9 s** |
| recon → wpscan | **same source IP `172.21.128.119`** | **16 s** |
| wpscan → webshell | **same source IP `172.21.128.119`** | **~2 min** |
| webshell → escalate | **same host + user `www-data`** (identical pattern to kyoushi) | **~0** |
| escalate → crack | **same host** (`intranet_server`), the crack is detected only by the monitoring CPU stream | **13 s** |
| crack → dnsteal | **nothing temporal.** The DNS exfiltration is from a *different* host (`192.168.104.218`) and ends **~28 h before** the crack begins. The only shared link is the scenario label. | **−28 h** |

Santos is the sharper demonstration of the point: the **web phase is linked by the attacker
IP and runs in seconds-to-minutes, but the exfiltration step is on a different host and a
different day, and shares no entity with the crack that "feeds" it in the label narrative.**

---

## 3. What the current relate actually pivots on (from the stored receipt)

The stored kyoushi `relate.json` holds 578 related events. Their (host, source) spread:

- `inet-dns`/`dnsmasq.log` + `inet-firewall`/`dnsmasq.log`: **300** (52%)
- `*/suricata/eve.json` (across 7 hosts): **160**
- `intranet_server`/`…-error.log.2` (the dirb 404 error log): 32
- `intranet_server`/`…-access.log.4` (the actual attack): **14**
- `intranet_server`/`audit.log`: **0** · `intranet_server`/`auth.log`: 7 · `error.log.2` (reverse_shell): **0**

So the pivot pulls DNS and network-flow noise, and pulls almost nothing from the attack's
own sources. The seed entities it pivots on are, in rank order: `AH01630`, `script`,
`systemd-logind`, `dnsmasq`, timestamps like `[23/Mar/2021:21:12:56 +0000]`, and a few
addresses. The attacker address `172.16.100.151` *does* get 9 of the 84 queries — but each
is bounded to `| head 20` inside a **±1 h window** around a seed whose evidence is Mar 23,
so the Mar 25 escalation and the reverse_shell line are 2 days outside the window and are
never read.

---

## 4. reverse_shell: the single line carries no link beyond its host and its file

The entire kyoushi reverse_shell evidence is one line, `intranet_server` `/apache2/error.log.2`
line 3, in a four-line file:

```
1  [Thu Mar 25 06:25:06…] [mpm_prefork:notice] [pid 21629] AH00163: Apache/2.4.29 … resuming normal operations
2  [Thu Mar 25 06:25:06…] [core:notice] [pid 21629] AH00094: Command line: '/usr/sbin/apache2'
3  bash: 196: Bad file descriptor
4  [Fri Mar 26 06:25:04…] [mpm_prefork:notice] [pid 21629] AH00171: Graceful restart requested, doing restart
```

Measured properties of that line:

- **no timestamp** (its neighbours bracket it: Mar 25 06:25 … Mar 26 06:25, a 24 h window);
- **no source IP, no user, no session, no PID, no URL** — it is a bare `bash` error;
- **absent from the behaviour store** — `behaviours.duckdb` `events` has **0 rows** matching
  `Bad file descriptor`, so the card stage never extracted it and no entity pivot can reach it.

Its only concrete links to the `escalate` step are the **host** (`intranet_server`) and the
**source file's position in time**. The host is the *least* distinctive link available
(shared with all benign intranet_server traffic); the source file is four lines, one of
which is the attack. The line is itself anomalous — a `bash:` error in an Apache error log —
but that anomaly is a **content signal for a generator**, not an entity that relate can
pivot on.

---

## 5. Conclusion — what relate must pivot on, and what it cannot do

**The data shows these logs carry links beyond time, but not the links relate is built
around.**

1. **The web phase is linked by the attacker's source IP** — `172.16.100.151` (kyoushi),
   `172.21.128.119` (santos). This is distinctive **by volume and user-agent**, *not* by
   host-count rarity: the address is mirrored into Suricata flows on five hosts, so the
   rarity weighting added in `6648dc61f` scores the one truly distinctive address as common.

2. **The escalation is linked by the user chain, not the IP** — `www-data → su <user> →
   sudo` on `/dev/pts/1`, with the working directory being the webshell's uploads folder.
   The `su`/`sudo` lines carry `addr=?`, so an IP pivot can never reach them.

3. **The steps are not time-adjacent.** Kyoushi's webshell→escalate gap is **47.4 h**;
   santos's crack→dnsteal gap is **−28 h** (different day, different host). relate's
   `TIME_MARGIN_SECONDS = 3600` (1 h) is contradicted by every long pair, and a time window
   is *not* a link in this data.

4. **reverse_shell has no entity, no timestamp, and is not in the behaviour store.** No
   entity pivot — IP, user, session, PID, file, URL — can reach it. It is reachable only as
   "the one non-Apache line in a four-line Apache error log on the victim host", which is a
   **content anomaly for a generator**, not a relation between found notables.

**Net:** relate, as "entity pivot + ±1 h time adjacency", is the wrong mechanism on this
data for both of its jobs. It cannot make cases pure (it scatters the pull across DNS and
Suricata on unrelated hosts), and it cannot make reverse_shell reachable (the line carries
no entity). The honest, data-backed statement is: **relate should not exist in its current
form.** What the data supports instead is:

- pivoting the *web* steps on the attacker source IP and the *escalation* on the user
  identity, with an **episode-sized (multi-day) window**, and
- surfacing the entity-less quiet step (reverse_shell) through a **generator** that flags
  the content anomaly (`bash:` error in an Apache error log), not through relate.

---

## Appendix — how the numbers were produced (all offline)

Every figure above was read directly from disk; no Splunk, no model, no synthetic data.

- Attack-step per-line labels and host/source/line: `*/_ingest/keys.jsonl` (kyoushi 408,038,
  santos 47,367 lines). The `labels` field is the step name; `digest`/`line` locate the raw line.
- Raw log text: `<family>/gather/<host>/logs/<source>` — the `line` field is 1-based into that
  file. Step timing and per-line entities (source IP, user, UA) were parsed from these files.
- The reverse_shell line is `kyoushi_s1/gather/intranet_server/logs/apache2/error.log.2` line 3
  (`bash: 196: Bad file descriptor`); its absence from the behaviour store was checked with
  `SELECT … FROM events WHERE raw LIKE '%Bad file descriptor%'` over
  `snap_s3_6648dc6/results/hunt/knowledge_s3a/kyoushi/behaviours.duckdb` (0 rows).
- What relate actually pulled (the 578 related events and 4 cases, and their host/source
  spread) was read from
  `snap_s3_6648dc6/results/hunt/knowledge_s3a/kyoushi/relate.json`.
- The 99.5% attacker-IP volume and the nine client IPs were counted from
  `kyoushi_s1/gather/intranet_server/logs/apache2/intranet.company.cyberrange.at-access.log.4`
  by regex on the common-log-format client field.
