# BOTSV2 diagnosis — why the 2026-11-18 run located 1 of 15 steps, and the fixes that followed

Status (2026-11-19): this diagnoses the 2026-11-18 pre-fix run only. Since it was written,
two solver lanes merged with live four-family receipts — behaviour-burst deviation
(`b947b840a`) and the source-path crossover fix (`080f89314`) — and the merged state of main
measures 3 of 15 steps at top-50 and 2 of 4 scenarios. The outcome and per-lane state are
recorded at the bottom of this file and in `docs/hunt/OPEN_PROBLEM_INDEX.md`.

Run diagnosed: `main 5628c8402` + scoreboard fix, receipts
`receipts_botsv2_full_20261118.log` (cards+behaviours), `..._20261118c.log`
(notables+judge), `receipts_botsv2_score_20261118.log` (scoreboard), run dir
`/Volumes/data01/portal5_hunt/snap_b2_8998b09a7/results/hunt/b2/botsv2/`.
Keys: `corpora/botsv2_keys/keys.jsonl` (24 admitted artefacts, 3 excluded, 7 assets).
All counts below are read from the run's own stores (`sources.json`,
`behaviours.duckdb`, `notables.jsonl`, `progress.json`) and read-only lab Splunk
probes (`diag/probe_clean.py`, `diag/trace_offline.py`); nothing here is a live
re-run. Probe scripts and intermediate JSON live under
`/Volumes/data01/portal5_hunt/snap_b2_8998b09a7/diag/`.

## Headline

The index holds **266,560,601 events across 104 sourcetypes**. The behaviour stage
read **306,466** of them (`per_window=392`, 12 windows/source, newest-first inside
each window). **21 of the 24 admitted artefacts have zero events in that read
slice.** Only three artefacts appear anywhere in the slice: `/member.php` (69 raw
events), `45.77.65.211` (2,523), and `GoT.S07E02...mkv.crypt` (1 misfit line). Of
those three, one is ranked below 100 (`/member.php` @598), one is dropped by its
generator (`45.77.65.211`), and one is dropped by the misfit share filter (GoT).
So the failure is overwhelmingly **upstream of ranking**: the artefact events are
never read, or their source is never behaviour-keyed.

Loss categories (brief §1): **(a)** source never sampled/carded for behaviours,
**(b)** carded but artefact events outside the sampled windows, **(c)** a behaviour
carries it but no generator scored/kept it, **(d)** scored but ranked below 100,
**(e)** present in a notable but the scoreboard surface misses it. **No artefact is
lost at (e)** — the scoreboard's entity surface is sound; every artefact that
reaches a notable's text is located (e.g. `/member.php`).

## Per-artefact trace

`audit` = live-audited keyed-event count (keys.jsonl). `slice raw/keyed` = artefact
value present in the behaviour read slice (`events.raw`) / literally in a behaviour
key. `beh` = behaviours carrying it. `misfit` = misfit shapes carrying it.
`notables` = notables whose haystack locates it (generator:count). Carrier
sourcetypes are in **indexed** names (lab Splunk renames Windows sourcetypes at
search time: `WinRegistry`→`winregistry`, `WinEventLog:Security`→`wineventlog:security`,
`xmlwineventlog`→`xmlwineventlog:microsoft-windows-sysmon/operational`,
`WinHostMon`→`winhostmon`, `Perfmon:Process`→`perfmon:process`).

| scenario/step | artefact | audit | slice raw/keyed | beh | misfit | notables | loss | where it is lost |
|---|---|--:|--:|--:|--:|--:|:--:|---|
| brewertalk_web/malicious_account | `kIagerfield` | 352 | 0/0 | 0 | 0 | 0 (-) | b | 0 of 352 in slice; carriers carded except wineventlog:security(no_roles). Burst 2017-08-16; newest-392 window tails miss it. |
| brewertalk_web/sql_injection | `/member.php` | 9978 | 69/69 | 55 | 0 | 5 (deviation:5) | d | 69 in slice -> 55 behaviours -> 5 deviation notables, best merged rank 598 (>100). Located only at 'all'. |
| brewertalk_web/sql_injection | `updatexml` | 1139 | 0/0 | 0 | 0 | 0 (-) | b | 0 of 1139 in slice; mysql SQL_TEXT + stream:http, burst 2017-08-16 08:24-08:38. |
| brewertalk_web/web_scan | `45.77.65.211` | 168004 | 2523/2523 | 1 | 0 | 0 (-) | c/d | 2523 in slice -> 1 behaviour (pan:threat card claimed pan:traffic via source routing). peer_rare measure below cut (host-share 1/1); merge weight peer_rare=0 -> never top100. |
| brewertalk_web/xss_cookie_theft | `1502408189` | 221 | 0/0 | 0 | 0 | 0 (-) | b | 0 of 221 in slice; stream:http cookie is not a role field; burst-localized. |
| fruitfly/c2_beacon | `eidk.duckdns.org` | 12 | 0/0 | 0 | 0 | 0 (-) | b | 0 of 12 in slice; only stream:dns (1.19M events); expected slice hits ~0.05. |
| fruitfly/c2_beacon | `eidk.hopto.org` | 8 | 0/0 | 0 | 0 | 0 (-) | b | 0 of 8 in slice; only stream:dns; expected ~0.03. |
| fruitfly/macbook_file_encryption | `Frothly_marketing_campaign_Q317.pptx....` | 10 | 0/0 | 0 | 0 | 0 (-) | b | 0 of 10 in slice; osquery_results/stream:smb/ps. |
| fruitfly/macbook_file_encryption | `GoT.S07E02.BOTS.BOTS.BOTS.mkv.crypt` | 11 | 0/0 | 0 | 1 | 0 (-) | c | read as 1 misfit shape in osquery_warning, but misfit share 13.2% > MISFIT_MAX_SHARE(1%) -> whole source dropped (1042/1299 shapes dropped). |
| fruitfly/usb_malware_delivery | `Important_HR_INFO_for_mkraeusen` | 5 | 0/0 | 0 | 0 | 0 (-) | b | 0 of 5 in slice; only osquery_results (47k events). |
| fruitfly/usb_malware_delivery | `befa9bfe488244c64db096522b4fad73fc01e...` | 2 | 0/0 | 0 | 0 | 0 (-) | b | 0 of 2 in slice; only osquery_results. |
| insider_leak/competitor_recon | `berkbeer.com` | 52 | 0/0 | 0 | 0 | 0 (-) | b | 0 of 52 in slice; suricata/stream:http/stream:dns/smtp; burst 2017-08-29. |
| insider_leak/competitor_recon | `ceoberk.png` | 3 | 0/0 | 0 | 0 | 0 (-) | b | 0 of 3 in slice; suricata/stream:http. |
| insider_leak/covert_channel | `torbrowser-install` | 382 | 0/0 | 0 | 0 | 0 (-) | b | 0 of 382 in slice; winregistry 228/55.5M (exp ~0.02), sysmon 128/1.1M (exp ~0.5). |
| insider_leak/executive_contact | `mberk@berkbeer.com` | 7 | 0/0 | 0 | 0 | 0 (-) | b/c | 0 of 7 in slice; smtp keyless (from/to only), wineventlog:security no_roles, sysmon. |
| insider_leak/patent_exfil | `Saccharomyces_cerevisiae_patent.docx` | 98 | 0/0 | 0 | 0 | 0 (-) | b | 0 of 98 in slice; stream:smb 74/211k (exp ~1.6, tail-biased out), sysmon/security/winregistry/winhostmon. |
| insider_leak/patent_exfil | `hbernhard@berkbeer.com` | 3 | 0/0 | 0 | 0 | 0 (-) | b/c | 0 of 3 in slice; only stream:smtp (keyless). |
| taedonggang_phish/c2_ssl | `45.77.65.211` | 168004 | 2523/2523 | 1 | 0 | 0 (-) | c/d | same artefact as web_scan; same peer_rare measure + weight-0 loss. |
| taedonggang_phish/ftp_download | `winsys32.dll` | 7 | 0/0 | 0 | 0 | 0 (-) | a/b | 0 of 7 in slice; wineventlog:security 4 (no_roles), sysmon 3 (exp ~0.013). |
| taedonggang_phish/ftp_download | `나는_데이비드를_사랑한다.hwp` | 2 | 0/0 | 0 | 0 | 0 (-) | b | 0 of 2 in slice; stream:ftp (phrase probe misses Hangul segmentation; audit locator confirms 2). |
| taedonggang_phish/scheduled_task_persistence | `Software\Microsoft\Network` | 119 | 0/0 | 0 | 0 | 0 (-) | a | 0 of 119 in slice; winhostmon 103 (kind:other), wineventlog:security 7 (no_roles), sysmon 5/winregistry 4 (sampling). |
| taedonggang_phish/spearphish_attachment | `912345678` | 4 | 0/0 | 0 | 0 | 0 (-) | b/c | 0 of 4 in slice; only stream:smtp (keyless). |
| taedonggang_phish/spearphish_attachment | `invoice.doc` | 5 | 0/0 | 0 | 0 | 0 (-) | a/b | 0 of 5 in slice; sysmon 2, security 1(no_roles), winhostmon 1(kind:other), winregistry 1. |
| taedonggang_phish/spearphish_attachment | `invoice.zip` | 9 | 0/0 | 0 | 0 | 0 (-) | a/b/c | 0 of 9 in slice; smtp 4(keyless), sysmon 2, security 1(no_roles), winhostmon 1(kind:other), winregistry 1. |

`stream:smtp` is carded `activity` but its only roles are `from`/`to` (no
actor/action/object), so `identity_plan` keys nothing — `behaviours=0` in the
receipt. It is a carrier for `912345678`, `hbernhard@berkbeer.com`, `mberk@…`,
`invoice.zip`, i.e. the quiet email-borne artefacts have **no keyable source**.

## Root causes, ranked by steps lost

1. **Sampling floor + newest-N tail bias (category b) — ~10 steps.** With 400k
   total budget over 266M events, a 2–382-event artefact in a 100k–55M-event source
   has expected slice hits ≪1 (`eidk.duckdns.org` 12/1.19M ≈ 0.05; `torbrowser-install`
   228/55.5M ≈ 0.02; the USB hash 2/47k ≈ 0.2). Reading the **newest** 392 events of
   each window further concentrates reads on window tails, so even burst-localized
   events with non-trivial expectation are missed (`45.77.65.211` in `access_combined`:
   4,854 events index-wide, **0** in slice; `Saccharomyces…docx` in `stream:smb`:
   74/211k, expected ≈1.6, **0** in slice). This is the dominant cause. More budget
   alone cannot reliably find the quietest artefacts (2–12 events); that is a
   detection floor, not a bug.

2. **Rendered Windows Security body not parsed → `no_roles` (category a) — feeds
   ~4 steps.** `wineventlog:security` (2,178,447 events) is carded `understood=True`
   but `roles={}` and skipped `no_roles`. `parse_kv` reads only the single-token KV
   header (`LogName`, `EventCode`, `ComputerName`, … 11 fields); the actor/object
   detail lives in the colon-labelled body (`Account Name:`, `New Process Name:`,
   `Process Command Line:`, `SAM Account Name:`, `Source Network Address:`), which
   the KV grammar never sees. The model correctly answered "no roles" for the 11
   fields it was shown. This source carries `kIagerfield`(1), `winsys32.dll`(4),
   `invoice.doc/zip`(1+1), `berkbeer.com`(2), `mberk@`(2), `Saccharomyces`(6),
   `torbrowser`(1), the registry key(7). **Confirmed** expected candidate.

3. **Generator measure + measured merge weight (category c/d) — 2 steps
   (`web_scan`, `c2_ssl`) + `sql_injection` top-100.** `45.77.65.211` IS keyed
   (2,523 events, 1 behaviour) but `peer_rare`'s relative measure
   (host-share × actor-share) ranks it below the cut: `pan:threat` has
   `hosts_possible=1`, so host-share = 1/1 = 1.0 (not peer-rare). The 300 kept
   `peer_rare` notables are all `botsv2:protocol` (largest denominator → smallest
   share). Even if kept, `DEFAULT_WEIGHTS["peer_rare"]=0` (measured LOFO,
   `GENERATOR_WEIGHTS_REPORT.md`) appends every `peer_rare` notable after the
   weighted head (rank ≥609), so it can never reach top-100. `/member.php` reaches
   only `deviation` `behaviour_first_seen` @598. A diversity cap was tried and
   **rejected**: offline it still does not keep the IP behaviour (its measure, not
   the monopoly, is the binding constraint). Fixing this needs a different rarity
   signal and/or a weight re-measurement — an operator decision, not a code hack.

4. **Misfit share filter drops whole sources (category c) — 1 step
   (`macbook_file_encryption`).** `generate_misfit` dropped **1,042 of 1,299** shapes
   as `poorly_understood_source` (misfit share > `MISFIT_MAX_SHARE=0.01`) and 242 as
   `low_coverage`; only 6 sources ranked, 15 notables kept. The GoT `.crypt` line was
   read (1 misfit shape in `osquery_warning`, card coverage 1.00) but its source's
   read misfit share is 13.2% > 1% → excluded. `MISFIT_MAX_SHARE` is a measured,
   documented threshold (`MISFIT_REPORT.md`); changing it is an operator decision.

5. **`kind:other` filter (category a) — minor independent effect.** `winhostmon`
   (kind `other`, `roles={}`) carries 103 of the 119 registry-key events and is
   skipped. But `roles={}` is the binding constraint — it would be `no_roles` even
   without the kind filter. The kind filter alone loses no artefact that roles
   would otherwise key. **Rejected** as an independent primary cause.

6. **Single-family knowledge mismatch — rejected as primary.** `similar_to_known`
   reliability AUC 0.588 on botsv2 (store families kyoushi/russell/santos, index
   unseen), kept 300, 0 covering an artefact. But the artefacts are not in the slice
   to score; this is ranking quality, not the recall bottleneck.

## Fixes implemented (general, no botsv2 keywords/fields/tuning)

- **F1 — `parse_kv` reads the colon-labelled detail body** (`parse.py`). A line-start
  `Label: value` rule adds the rendered-body fields the KV grammar misses, unlocking
  `wineventlog:security` (11 → 27–32 fields; `EventCode`, `ComputerName`,
  `Account Name`, `SAM Account Name`, `New Process Name`, `Source Network Address`
  now within the 24-field model prompt). It is a **verified no-op on the three
  regression families**: re-parsing **262,024** real KV lines (kyoushi 115,097;
  santos 80,361; russell 66,566 — `audit.log`, `mail.*`, `system.journal.txt`)
  produced **0** field-set changes, because their lines are single-line KV or start
  with a timestamp, never a line-start letter-label-colon. Unit tests use the real
  botsv2 4688/4720 shapes and real auditd/dovecot/journal lines.

- **F2 — behaviour reads spread across each window** (`sample.py`, `behaviours.py`).
  `read_windows` gains `sub_windows` (default 1 = byte-identical old behaviour); the
  behaviour stage passes `BEHAVIOUR_SUB_WINDOWS=2`, reading the newest share of each
  half-window instead of only the window tail — same total budget, twice the time
  coverage. **Cards and alerts are unchanged** (they use the default), so source
  understanding/roles do not move for any family. This attacks the proven tail bias;
  it cannot lift the absolute sampling floor (cause 1).

## Fixes recommended but NOT implemented (operator-owned decisions)

- Cause 3: a global-rarity signal for `peer_rare` (or re-measuring merge weights on a
  quiet-step corpus). `DEFAULT_WEIGHTS` is measured LOFO; re-tuning is forbidden here.
- Cause 4: relax/replace `MISFIT_MAX_SHARE` with a per-source cap (measured threshold
  in `MISFIT_REPORT.md`). A trial removal was reverted to keep the measured decision.
- Cause 1 floor: a larger behaviour budget, or a rarity-directed read, is an effort
  budget decision. A Splunk `rare <field>` probe was tested and **rejected**: it
  depends on per-sourcetype field extraction (`rare query` on `stream:dns` returns
  nothing) and the rarest values are benign noise (winregistry `rare key_path` →
  count-1 keyboard-class keys, not the 4-event persistence key).
- `stream:smtp` keyless: needs core-role understanding of SMTP DATA, not a botsv2 hack.

## Offline regression check (how "unchanged" was verified)

- F1: 262,024 real family KV lines re-parsed old-vs-new → 0 diffs (above).
- F2: `sub_windows=1` path proven identical (one slice/window, `per_window` unchanged);
  cards/alerts call sites untouched. The three families' **card stage** is therefore
  unchanged. Their behaviour **event selection** does change (midpoint+tail vs tail),
  which can move `deviation`/`similar` rankings — this is **not** verifiable offline
  and needs the live regression run below.

## Predicted effect (hypotheses as of 2026-11-18 — superseded by the receipts below)

- F1 makes `wineventlog:security` understood with roles → it enters behaviours.
  Whether its rare artefact events are then read depends on F2/budget; expect the
  source to move from `skipped:no_roles` to keyed, not an immediate step jump.
- F2 should recover some burst-localized artefacts in medium-volume sources
  (e.g. `access_combined`/`stream:smb` carriers); quiet-step recovery is not promised.
- Net botsv2 top-50 step count is **not predicted to jump to family levels**: causes 3
  and 4 (operator-owned) still bind `web_scan`/`c2_ssl`/`macbook`. The honest
  expectation is a modest improvement plus a now-understood Security source.

## Outcome (2026-11-19 live receipts)

The step jump came from two solver lanes merged after this diagnosis, not from F1/F2 alone:

- **hunt-open-kimi** — merged `b947b840a` (2026-11-19); problem and replay:
  `OPEN_PROBLEM_hunt-open-kimi.md`. Temporal bursts inside a behaviour became
  first-class `deviation` evidence; the two-slot allowance was chosen by LOFO on the
  build families and the measured generator weights are unchanged. Live four-family
  run: botsv2 0→2 of 15 steps at top-50, 2 of 4 scenarios; kyoushi 12 of 12,
  santos 14, russell 15 at 50.
- **hunt-open-astra** — merged `080f89314` (2026-11-19); problem and replay:
  `OPEN_PROBLEM_hunt-open-astra.md`. Carded reads select by sourcetype ownership, so
  the shared-source crossover this diagnosis hit at `pan:threat`/`pan:traffic`
  (cause 3's traffic/threat mix-up) is closed at the sampler; single-timestamp
  sources read their observed time and small sources read whole within their
  allocation. Live four-family run: botsv2 2→3 of 15 steps at top-50, 2 of 4
  scenarios; kyoushi 12 of 12, santos 14 of 21, russell 15 of 22 at 50.
- **hunt-open-neon** — branch `lane/hunt-open-neon`, round 2, **not merged**;
  its `OPEN_PROBLEM_hunt-open-neon.md` rides the lane. Burst-guided sampling,
  wide-schema cards, common-mode surge subtraction and 2,400-char evidence; a
  frozen-embedding replay over the 2026-11-19 astra snapshot measured botsv2 5 of 15
  at top-50 and 3 of 4 scenarios with no build-family regression. No live run yet.

The headline above is therefore a dated measurement, not the current state: 1 of 15
was the 2026-11-18 pre-fix run; main as of 2026-11-19 measures 3 of 15 at top-50 and
2 of 4 scenarios. Causes 1 (sampling floor), 3's rarity signal and measured weights,
and 4 (`MISFIT_MAX_SHARE`) remain operator-owned decisions; per-lane state:
`docs/hunt/OPEN_PROBLEM_INDEX.md`.
