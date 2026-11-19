# Open problem: wide-telemetry truncation, fleet-wide burst masking, and burst-guided sampling

## Findings (from `snap_astra_ba2a615` and read-only lab Splunk probes)

Auditing the live post-astra baseline (`main 080f89314`, snapshot `snap_astra_ba2a615/results/hunt/astra`) alongside read-only `botsv2` discovery queries revealed six general structural bottlenecks that disproportionately hit large, multi-platform, wide-schema telemetry (`botsv2`: 226M–266M events across 31 days, 104 sourcetypes, 0.140% behaviour-slice coverage) while barely affecting the shorter Linux/syslog build families (`kyoushi`, `santos`, `russell`: 5.3%–7.6% behaviour-slice coverage):

1. **Template mining hardcoded sample-specific PIDs, glog dates, and clock times as literal constants.**
   In `osquery_warning` (1,035 events, read in full), `learn_templates` mined `W0815 * 264929280 virtual_table.cpp:515] ...` because all 120 sampled lines happened to share date `W0815` and PID `264929280`. As a result, 134 normal lines from other days/PIDs failed template matching, inflating `osquery_warning`'s misfit share from **3/1,035 (0.29%)** to **137/1,035 (13.2%)** — above `MISFIT_MAX_SHARE = 0.01` — dropping the entire source including its 1-event `GoT.S07E02.BOTS.BOTS.BOTS.mkv.crypt` anomaly. The same bug affected `osquery_info` (`264929280`) and build-family startup logs (`suricata-start.log`, `shorewall-init.log` clock times).

2. **Fleet-wide common-mode volume surges buried source-specific bursts.**
   In `botsv2`'s 4-hour `tstats` series, three adjacent buckets (`1503100800`–`1503129600`) spiked **48–52 of 86 sourcetypes simultaneously** (`z >= 1.5`), filling 28 of the top 40 raw `source_burst` ranks with fleet-wide surge noise and `kind=other`/`measurement` sources. Subtracting each bucket's positive fleet-wide median z-score (`shift(t) = max(0, median_z(t))` when >=3 sources are active) and restricting source deviations to behaviour-eligible sources moves source-specific attack bursts directly into the review head:
   - `botsv2`: `apache_error` moves to #3, `osquery_results` jumps #31 → #7, `csp-violation` jumps #45 → #8.
   - `santos` (which also has a fleet-wide surge, `max_bucket_med_z = 1.77`): `intranet.smith.santos.com-access.log` jumps into top 7 and `auth.log` into top 8.
   - `kyoushi`: `openvpn.log` rises #7 → #6; `russell`: top 7 preserved.

3. **400-character raw truncation (`EXAMPLE_CHARS = 400`, `EVIDENCE_CHARS = 400`) cut off structured event payloads.**
   Linux syslog lines fit inside 100–250 characters. Wide JSON/XML/KV telemetry carries headers and metadata in the first 350–600 characters, placing security fields past offset 400. Measured on real burst-sampled `botsv2` rows:
   - `osquery_results` (`Important_HR_INFO_for_mkraeusen`, `sha256`): offsets 491–618 (**5/5 and 2/2 lost at 400**).
   - `csp-violation` (`kIagerfield` in `document-uri`/`referrer`): offsets 760–778 (**32/33 lost at 400**).
   - `xmlwineventlog:sysmon` (`45.77.65.211`): offsets 1207–1210 (**22/22 lost at 400**).
   - `stream:smtp` (`mberk@berkbeer.com`, `berkbeer.com`): offset 1212 (**1/1 lost at 400**).
   - `stream:http` (`/member.php`): offsets 1264–7083 (**178/178 lost at 400**).

4. **Uniform-tail behaviour sampling missed burst-localized episodes; `identity_plan` wildcarded bursty actors and dropped `from`/`to`-only sources.**
   Reading 12 uniform slices across 31 days covered <0.5% of time on high-volume sources. Reserving 4 of the existing 12 windows per sampled source for its own top 4-hour `tstats` burst buckets (top 2 raw-z + top 2 residual-z, keeping the exact 24-request/source budget) puts 9/15 `botsv2` steps and all 4/4 scenarios into the read slice. Separately, `IDENTITY_BUCKET_SHARE = 0.5` wildcarded bursty actors like `stream:http`'s `c_ip` (`recurrence = 125.57`, `distinct = 7`, `bucket_share = 0.172`), while sources using `from`/`to` (`csp-violation`, `stream:smtp`) collapsed to empty actors or 2-valued objects (`inline`/`self`).

5. **Wide-schema card discovery truncated alphabetical JSON fields at 24, turned XML empty-text attributes into unique field names, and partitioned on non-discriminating fields.**
   - `MAX_FIELDS = 24` in serialization order showed `ack_packets_in`..`packets_in` on `stream:smtp` (75 fields) and dropped `sender_mail_from`, `receiver_email`, `subject`, `src_ip`; dropped `query` on `stream:dns`; dropped `uri_path` on `stream:http`; dropped `New Process Name` and `Process Command Line` on `wineventlog:security`.
   - `parse_xml` encoded empty-text attributes like `<TimeCreated SystemTime="..."/>` as unique empty-valued keys (`TimeCreated[SystemTime=...] = ""`), inflating Sysmon to 166 fields.
   - `choose_partition` maximized total shape union rather than between-group schema separation, partitioning Sysmon on `Computer` (dropping `wrk-aturing` as `kind=other`), `stream:http` on `accept`, and `osquery_results` on `action=added` (misclassified as `measurement`).

6. **Single-source/single-pattern monopolies crowded out `similar_to_known` and `behaviour_first_seen`, and `window_activity` only sampled window tails.**
   - In `snap_astra_ba2a615`, `vmstat` (105), `top` (67), `weblogic_stdout` (38), and `unix:useraccounts` (19) consumed 229/300 (76%) of `botsv2`'s `similar_to_known` notables; `access_combined` consumed 6/7 top-50 `behaviour_first_seen` slots with final-minute timestamps.
   - `window_activity` read only `sub_windows=1` (tail of the 4-hour window), required non-empty `actor` and `action` (skipping `csp-violation`), and retained only chronological endpoints (`first`, `last`), missing mid-window burst slices when sub-windowed.

## General code changes

All changes are general (zero dataset names, field names, keywords, or scoreboard/weight edits):

- [`portal/modules/security/core/hunt/notables/parse.py`](../../portal/modules/security/core/hunt/notables/parse.py):
  - Generalize multi-digit IDs (`\d{5,}`), glog date tags (`[IWEF]\d{4}`), and `HH:MM:SS` clock times in `_mine`.
  - Emit `tag.attr = value` in `parse_xml` when an attributed element has empty text (preserving `tag[attr=val] = text` when text is present).
  - Raise `MAX_FIELDS` to 48 and prioritize varying non-numeric fields when a record exceeds 48 fields (narrow sources <=48 fields keep exact sample order).
  - Score `choose_partition` by distinct per-group majority field-sets and mean pairwise Jaccard distance (`>= 0.25`) across all fields present in >=50% of events.
- [`portal/modules/security/core/hunt/notables/behaviours.py`](../../portal/modules/security/core/hunt/notables/behaviours.py):
  - Raise `EXAMPLE_CHARS` from 400 to 2400.
  - Add one four-hour `tstats` burst-planning read in `collect_behaviours` and split non-complete sources' 12-window budget into 8 uniform + up to 4 peak-burst windows (`sub_windows = 2` on both, preserving the 24-request/source ceiling; 1,629 total requests on `botsv2`).
  - Keep recurring fields (`recurrence >= IDENTITY_RECURRENCE` and `distinct <= IDENTITY_VALUE_BUDGET`) literal even when concentrated in one burst hour; fall back `actor` → `from` and low-variety/missing `object` → `to`.
- [`portal/modules/security/core/hunt/notables/generators.py`](../../portal/modules/security/core/hunt/notables/generators.py):
  - Raise `EVIDENCE_CHARS` to 2400.
  - Subtract common-mode positive fleet shift (`median_z(t)` when >=3 sources active in bucket `t`) in `_source_deviations`, and filter `source_burst` / `source_first_seen` to behaviour-eligible sources when cards are present.
  - Interleave `behaviour_first_seen` across sources and allocate `DEVIATION_BURST_WEIGHT = 2` burst slots per source/behaviour onset slot inside `deviation` (preserving `DEFAULT_WEIGHTS` and `MISFIT_MAX_SHARE`).
- [`portal/modules/security/core/hunt/notables/window_activity.py`](../../portal/modules/security/core/hunt/notables/window_activity.py):
  - Read anomalous windows with `WINDOW_SUB_WINDOWS = 4`, support `from`/`to` fallbacks, retain the densest 5-minute burst-slice and most-frequent object alongside earliest/latest evidence (<=4 lines), and decode percent-encoded URLs in the human-readable `what` summary while keeping `evidence[].line` and `evidence[].query` strictly literal.
- [`portal/modules/security/core/hunt/notables/similar.py`](../../portal/modules/security/core/hunt/notables/similar.py):
  - Round-robin repeating normalized `(source_id, actor, action, object)` patterns via `_diversify_ranked` before cutting at `SIMILAR_NOTABLE_BUDGET`.

## Measured 4-family verification (production code + read-only Splunk + unmodified scoreboard)

Running the committed production modules (`collect_behaviours` fresh on `botsv2` with template re-mining, `generate`, `generate_misfit`, `_diversify_ranked`, `merge_notables`, `resolve_source_windows` with real read-only Splunk queries, and unmodified `scoreboard.score`) on copies of `snap_astra_ba2a615` gave:

| family | main (`080f89314`) @50/@100/all | neon replay @50/@100/all | scenarios @50/all |
|---|---|---|---|
| `botsv2` | 3 / 3 / 3 of 15 (2/2 scen, 2 notables) | **5 / 5 / 5 of 15** | **3 / 3 of 4 (4 distinct notables)** |
| `kyoushi` | 12 / 12 / 12 of 12 | **12 / 12 / 12 of 12** | — |
| `santos` | 14 / 16 / 17 of 21 | **15 / 15 / 18 of 21** | — |
| `russell` | 15 / 15 / 16 of 22 | **15 / 15 / 16 of 22** | — |

The four distinct carrying `botsv2` notables at top 50 (two generators):
1. Rank **13** (`deviation` / `source_first_seen_activity`, `botsv2:stream:ftp`): `나는_데이비드를_사랑한다.hwp` (`taedonggang_phish/ftp_download`)
2. Rank **20** (`deviation` / `source_burst_activity`, `botsv2:apache_error`): `45.77.65.211` (`brewertalk_web/web_scan` & `taedonggang_phish/c2_ssl`)
3. Rank **43** (`misfit` / `out_of_structure`, `botsv2:osquery_warning`): `GoT.S07E02.BOTS.BOTS.BOTS.mkv.crypt` (`fruitfly/macbook_file_encryption` — **3rd scenario**)
4. Rank **45** (`deviation` / `source_burst_activity`, `botsv2:csp-violation`): `kIagerfield` (`brewertalk_web/malicious_account`, readable decoded URL in `what`, literal raw JSON + query in `evidence`)

Note on transparency: on `santos`, `@50` rose `14 → 15` and `@all` rose `17 → 18`, while `@100` moved `16 → 15` in the frozen-embedding replay. On `botsv2`, `kIagerfield` in `csp-violation` is percent-encoded in raw JSON (`%3DkIagerfield%26`) and matched via the readable decoded summary in `what` (without modifying `scoreboard.py`).

## Live verification handoff

Run all four families end-to-end (fresh `cards`, `behaviours`, `notables`, `judge`, and `scoreboard`) with the orchestrator credentials exported:

```bash
bash coding_task/RUN_HUNT_OPEN_NEON.sh
```

Predicted live `@50` range: `botsv2` **5–7/15 steps, 3–4/4 scenarios** (fresh `cards` stage additionally unlocks `stream:smtp`, `stream:dns`, `stream:http`, `osquery_results`, `xmlwineventlog:sysmon`, and `wineventlog:security`, plus fresh `similar_to_known` embeddings over diversified behaviours); `kyoushi` **12/12**, `santos` **14–16/21**, `russell` **15/22**. Check `score.log`, `stages.behaviours.events_read` / request counts (<2,000), `stages.notables.misfit.sources_ranked` (should include `osquery_warning`), and `stages.notables.source_windows` in each `progress.json`.
