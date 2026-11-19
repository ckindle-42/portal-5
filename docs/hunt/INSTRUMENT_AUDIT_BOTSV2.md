# Hunt instrument audit — botsv2 (2026-11-19, lane `hunt-instrument-audit`)

Question: five solver rounds in four lineages all land botsv2 at 0–4 of 15 steps @50 while the build
families pass. Is that the solvers, or our instrument, keys, or design? Findings and receipts only; no
hunt code was changed and nothing was applied (a scoreboard fix is proposed at the end).

Inputs: run `~/projects/portal-5-hunt-open-neon/coding_task/scratch/neon-live.03k31Qkn/` (main `defd357bc`),
keys `/Volumes/data01/portal5_hunt/corpora/botsv2_keys/keys.jsonl`, live READ-ONLY Splunk `botsv2` only
(no other index and no other key set was opened). Scratch scripts and raw pulls are under
`coding_task/scratch/` (gitignored); queries are quoted below.

> [!IMPORTANT]
> Two facts corrected up front. (1) The index holds **226,317,740** events in **104** sourcetypes
> (`| tstats count where index=botsv2`, twice), not the "~266M" in the brief; 266,058 is the number of
> events the run *read*. (2) I reproduced the headline: re-running the scoreboard on the stored run gives
> `steps top50 4/15 top100 4/15 all 4/15, scenarios 3/4` exactly as `score.log`.

## 1. Coverage ceiling (Q1)

Counts: the stored audit counts (2026-11-18) re-verified today with the same locators
(`keys_audit_queries.spl` forms) — all equal except where noted. "Read" = key string present in a read store:
`events.raw` (behaviour sample, 266,058 rows, raw capped at **2,400 chars**), `behaviour_all`, `misfits`
(from `behaviours.duckdb`). Carrier read-fractions are `events_read/events_available` from `progress.json` receipts.

| step | artefact (Splunk count) | main carriers (read / available) | keyed events read (events table) | string anywhere read | reachable |
|---|---|---|---|---|---|
| brewertalk/malicious_account | kIagerfield (352) | stream:http 5,248/1.42M; mysql:*stats 5,248/26.9M; suricata 4,810/2.16M; csp-violation 2,260/2,290 | 33 (all csp-violation) | yes | yes |
| brewertalk/sql_injection | /member.php (9,978); updatexml (1,139) | stream:http (5,248/1.42M); mysql:* (5,248/26.9M) | 18 of 9,978; updatexml **0** | /member.php 462 events | yes (weak key) |
| brewertalk/web_scan | 45.77.65.211 (168,004) | pan:traffic 4,372/1.88M; suricata 4,810/2.16M; stream:tcp/ip ~5K/2.1–2.5M; stream:http 5,248/1.42M | 388 of 168,004 (0.23 %) | yes (400) | yes |
| brewertalk/xss_cookie_theft | 1502408189 (221; 219 via search) | stream:http, mysql:* | **0** | no | **no** |
| fruitfly/c2_beacon | eidk.duckdns.org (12), eidk.hopto.org (8) | stream:dns 5,248/1.19M | **0** | no | **no** |
| fruitfly/macbook_file_encryption | …pptx.crypt (10), …mkv.crypt (11) | osquery_results 4,965/47,178; osquery_warning 1,035/1,036 | 0 in events; 5 shapes in `misfits` | yes (misfit) | yes |
| fruitfly/usb_malware_delivery | Important_HR_INFO… (5), sha256 (2) | osquery_results 4,965/47,178 | 0 in events; 1 misfit shape | yes (misfit) | yes |
| insider_leak/competitor_recon | berkbeer.com (52), ceoberk.png (3) | suricata, stream:http/smtp/dns (~5K each of 0.67–2.2M) | 1 | yes | yes (1 event) |
| insider_leak/covert_channel | torbrowser-install (382) | winregistry 5,248/**55.5M**; sysmon 4,810/1.11M | **0** | no | **no** |
| insider_leak/executive_contact | mberk@berkbeer.com (7) | stream:smtp 5,248/670,760 | 1 | yes | yes (1 event) |
| insider_leak/patent_exfil | …patent.docx (98), hbernhard@ (3) | stream:smb 5,197/211,155 | 0 in events; 1 misfit shape | yes (misfit) | yes |
| taedonggang/c2_ssl | 45.77.65.211 (168,004) | same as web_scan | 388 | yes | yes |
| taedonggang/ftp_download | winsys32.dll (7), 나는…hwp (2) | stream:ftp 1,489/1,490 | 2 (.hwp) | yes | yes |
| taedonggang/scheduled_task_persistence | Software\Microsoft\Network (119) | winregistry 5,248/55.5M | **0** | no | **no** |
| taedonggang/spearphish_attachment | invoice.zip (9), invoice.doc (5), 912345678 (4) | stream:smtp 5,248/670,760 | invoice.zip 4; 912345678 4 events read **but value is at char ~12.7K of a 40 KB event, past the 2,400 cap** | invoice.zip yes; password no | yes |

(`empire_execution` hash and `process.php` / `ambersthebest@…` are `admitted=false`, 0 events, excluded by the
scorer: 15 scored steps.)

**Ceiling @50 vs 4/15.**

| definition | steps | of 15 |
|---|---|---|
| achieved (entity scorer) | web_scan, c2_ssl, ftp_download, macbook | 4 |
| key string in the behaviour `events` table | malicious_account, sql_injection, web_scan, c2_ssl, competitor, executive, ftp, spearphish | 8 |
| key string in any read store (events, behaviours, misfits) | + macbook, usb_malware, patent_exfil | **11** |
| nothing read at all | xss_cookie_theft, c2_beacon, covert_channel, scheduled_task | 4 |

The 11 is generous: for 4 of those steps the string is a single event among ~5,200 reads of the carrier
(berkbeer 1, mberk 1, one misfit shape each for HR/patent). Sampling alone does **not** explain 4/15; it explains the
last four steps, and it makes the other seven needles in a haystack of 17,928 behaviours of which 10,134 are
singletons.

**Contrast family (santos, same method on its stored run; kyoushi alongside).** Labelled lines read verbatim
(`events.raw` equals the labelled line text, from `…/santos_ingest/keys.jsonl` + `…/santos/gather`):

| family | labelled lines | read verbatim | steps with ≥1 labelled line read | scored @50 | scored all |
|---|---|---|---|---|---|
| santos | 47,367 | 867 (1.8 %) | 12/21 | 15/21 | 17/21 |
| kyoushi | 408,038 | 1,963 (0.5 %) | 11/12 | 12/12 | 12/12 |
| botsv2 | (see above) | — | 8/15 events, 11/15 any store | 4/15 | 4/15 |

So the families' read ceiling is comparable to botsv2's (santos 57 %, botsv2 53–73 %); their @50 *exceeds* it
(santos 15 > 12) because credit does not require the labelled line to have been read (§2). Steps with 0
labelled lines read yet credited @50: santos `webshell_upload`, `webshell_cmd`, `network_scan`, `service_scan`.

## 2. Scoreboard parity (Q2)

Entity mode (botsv2) credits a step when a key string appears whole-word in a notable's `what/basis/why`,
entities, or evidence **queries and lines**. Line mode (families) credits a step when a notable's evidence
query selects a labelled line (source from `source="…"`, every quoted TERM present in the line, else the
evidence time window).

I applied the **scoreboard's own** line-mode functions (`_claim`, `_on_source`, `_covers`) to the botsv2
keyed events pulled live (every event the locator matches: 168,004 for the IP, 9,978 for /member.php, …;
fields `_time source sourcetype host _raw[:1500]`), against the run's 876 notables in rank order.

| step | entity rank (@50?) | line-mode first rank, as written | line-mode, `source=` matched case-insensitively |
|---|---|---|---|
| web_scan / c2_ssl | 30 | 30 | 30 |
| ftp_download | 18 | 18 | 18 |
| macbook_file_encryption | 33 | none | 33 |
| malicious_account | none | 34 | 34 |
| sql_injection | none | 34 | 34 |
| xss_cookie_theft | none | 68 (top100) | 68 (top100) |
| other 8 steps | none | none | none |
| **steps @50 / @100 / all** | **4 / 4 / 4** | **5 / 6 / 6** | **6 / 7 / 7** |

- Line mode is a superset of entity mode once source case is folded (Splunk `source=` matching is
  case-insensitive; the scoreboard compares exact strings, so notable #33, whose own evidence line *is* the
  `.crypt` file, misses on `osqueryd.WARNING` vs `osqueryd.warning`). That is a minor scoreboard defect.
- Entity mode misses `malicious_account` / `sql_injection`, which line mode credits through notable #34
  (`SELECT * FROM mybb_users WHERE uid='31'` on `mysql:transaction:details`, terms `mybb_users`, `SELECT`,
  `mysql` occur in the keyed mysql events). Plausibly on-target (SQLi/account probing), but it never names
  `kIagerfield`, `updatexml` or `/member.php`: the two instruments measure different things.
- Even the more lenient scoring leaves 8 steps unfound, so parity explains at most 2–3 of the 11 misses.
- Whole-word / NFC / basename: I searched all 876 notable texts (the scorer's haystack) for 23 hand-listed looser
  variants (basename, extension-less stem, `ip:` prefix, `.crypt`, `.hwp`, `torbrowser|tor browser`, …;
  not tuned — listed before looking). Result: **no new match** except those already scored; the only near-miss
  is `lagerfield` in notable #338, a legitimate user `klagerfield@froth.ly` — the key is the *homograph*
  `kIagerfield` (capital I), so casefolding correctly refuses it. Matching strictness is not a cause.
- Inflation, the other direction: the IP credit (2 of the 4 passes) comes from one evidence line
  (`[client 45.77.65.211] File does not exist: /var/www/html/1101`) in notable #30 (also #263).
  `grep` over all notables: the IP occurs only there. A scorer that required the artefact to be in what/basis/
  why/entities would give botsv2 **2/15**.

## 3. Keys validity (Q3)

Classification is my judgement (reasoned, not measured). B = an anomaly/behaviour hunt should surface it;
P = partly (behaviour exists, key is a name/hash); T = trivia (CTF answer not an anomaly).

| step | class | note |
|---|---|---|
| web_scan | B | scanner IP, 168K events |
| c2_ssl | B, **duplicate** | same key value as web_scan (counts twice) |
| sql_injection | B (payload) | `/member.php` is the forum's main page (9,978 events incl. benign): weak key; `updatexml` is the real behaviour |
| macbook_file_encryption | B | mass `.crypt` files; 21 events |
| scheduled_task_persistence | B | registry key; 119 audit events in 55.5M winregistry; backslash escaping unverified by me |
| c2_beacon | B | DDNS beacon, 20 events in 1.19M DNS |
| malicious_account | P | homograph username only visible as a string |
| usb_malware_delivery | P | HR file name / sha256 |
| covert_channel | P | Tor installer name |
| patent_exfil | P | docx name + e-mail address |
| ftp_download | P | file names on FTP to an external host |
| spearphish_attachment | P | `invoice.zip` yes; `912345678` (zip password) is T, and sits at char ~12.7K |
| xss_cookie_theft | T | cookie value is a Unix epoch; collides with raw epochs (key note says so) |
| competitor_recon | T | visiting a competitor domain; `ceoberk.png` an image name |
| executive_contact | T | one e-mail address, 7 events |

6 B, 6 P, 3 T; 14 distinct (c2_ssl duplicates web_scan). **Fair bar for a blind behaviour hunt (proposal):**
dedupe shared keys (14), report T steps separately instead of in the denominator (11 B+P), and grade against the
reachable set from the receipts (here 8 of those 11 are string-reachable) — e.g. surfacing ≥50 % of the
reachable B+P steps @50 — rather than an absolute "N of 15". Today's run on that basis: web_scan (by an incidental
line), ftp_download, macbook = 3 of 8 reachable (37 %), 2 of 8 if the incidental IP credit is removed.

## 4. Design assumption (Q4)

"Sample the index, then score behaviours" at botsv2 scale:

| run | events available (receipt sum) | events read | fraction | sources read | events in sources read <0.5 % | median read per source |
|---|---|---|---|---|---|---|
| botsv2 | 227.07M (true 226.32M) | 266,058 | **0.117 %** | 102 | **94.7 %** | 5,152 |
| kyoushi | 5.53M | 153,845 | 2.78 % | 33 | 0 % | 9,000 |
| santos | 5.40M | 175,775 | 3.26 % | 48 | 0 % | 5,670 |
| russell | 6.44M | 159,126 | 2.47 % | 64 | 52 % | 3,838 |

The read budget is roughly constant per source (~5K), so fraction collapses with source size: botsv2 carriers
read at 0.02 % (mysql 26.9M), 0.0095 % (winregistry 55.5M), 0.44 % (dns). Under uniform reads the chance of seeing
at least one of n needle events is 1-(1-f)^n: a 20-event step at botsv2's overall 0.117 % → 2.3 %; a 14-event santos step
at 3.26 % → 37 % (reasoned; the real sample also adds burst windows, and small sources are read almost in full — which is
why 11/15 are reachable). The families' sources are also two orders of magnitude smaller than botsv2's largest.

Verdict on the assumption: viable for the build families (≤6.4M events, 0 % in <0.5 % sources for two of
three), a **design limit** at botsv2 scale for needle steps in the large sources, and independent of that,
reached events are not separable at the rank cut (peer_rare weight 0, 876 notables, 10,134 singleton behaviours).

Probes of full-index aggregation (live, `botsv2`, `| stats count by <field>` over the whole sourcetype, all-time):

| probe | result |
|---|---|
| stream:dns `query{}` | 34,194 distinct, 582 singletons; `eidk.hopto.org` (8) / `eidk.duckdns.org` (12): **94.8 % / 96.6 % of values are as rare or rarer** — count-rarity alone does not isolate the beacon |
| stream:ftp `filename` | 505 distinct; the whole list is reviewable; `.hwp` is count 2 |
| stream:smtp `attach_filename{}` | 6 distinct values; `invoice.zip` (4) listed trivially |
| stream:http `src_ip` | 1,087 distinct; 45.77.65.211 (8,966) is in the top 2 % by **volume** |
| stream:http `uri_query` | 16,960 distinct, 15,885 singletons; `updatexml` not found under that field (the SQLi payload is not in `uri_query`; unresolved) |

(Earlier `BOTSV2_DIAGNOSIS.md` also rejected `rare <field>` probes; this confirms rarity-by-count is a weak signal.)
Properties of a design that would fit: (1) enumerate **low-cardinality fields in full** (filenames,
attachments, recipient domains, processes) instead of sampling them; (2) rank **volume outliers** per entity
over the full index (scanners, top talkers) with Splunk aggregation; (3) use **second-order features** rather
than raw rarity (first-seen per host, dynamic-DNS/suffix classes, beacon periodicity, new-process/-registry-key per
host); (4) **drill down** by sampling inside the flagged entity/time slice; (5) keep fat events whole where the
signal is deep (2,400-char cap hid the zip password).

## Receipts (queries and commands)

```
| tstats count where index=botsv2                          -> 226317740
| tstats count where index=botsv2 TERM("45.77.65.211")     -> 168004
search index=botsv2 sourcetype="stream:http" uri_path="/member.php" | stats count   -> 9978
| tstats count where index=botsv2 by sourcetype            -> 104 rows
per artefact: key locator (keys.jsonl) | eval r=substr(_raw,1,1500) | table _time source sourcetype host r
search index=botsv2 sourcetype="stream:smtp" ("912345678" OR "invoice.zip") | eval len=len(_raw), p1=len(mvindex(split(_raw,"912345678"),0)) | table _time len p1
   -> len 40207..40244, password at char 12735..12753; invoice.zip at ~178
index=botsv2 sourcetype="stream:ftp" hwp | table ...      -> 2 events, filename 나는_데이비드를_사랑한다.hwp
uv run python -m portal.modules.security.core.hunt.notables.scoreboard --out <dir with botsv2 symlink> --keys botsv2=…/keys.jsonl
   -> steps top50 4/15 top100 4/15 all 4/15; scenarios 3/4
```

## RESULT

- **The 4/15 is not a clean measurement of hunt skill.** Of the 4 steps passed, 2 (`web_scan`, `c2_ssl`) are the
  *same* attacker IP, matched in one evidence line of an unrelated "File does not exist" burst notable (#30);
  the IP is in no notable's `what`/`basis`/`why`/`entities`. Real, about-the-artefact passes: `ftp_download`
  (notable #18, the `.hwp` RETR) and `macbook_file_encryption` (#33, the `.crypt` osquery warning).
- **Coverage is not the cap at 4.** 11/15 steps have ≥1 key string in what the run read (events, behaviours or
  misfit store); 8/15 in the behaviour `events` table alone. 4 steps (xss, c2_beacon, covert_channel,
  scheduled_task) have **zero** keyed events read. So the loss is mostly *reached but not surfaced* (7 steps),
  plus 4 not reached.
- **The run read 0.117 % of the index** (families 2.5–3.3 %); 94.7 % of botsv2 events sit in sources read at
  <0.5 % (families: 0 % kyoushi/santos, 52 % russell). Per-source read is capped at about 5,2xx lines whatever
  the source size.
- **Scoreboard parity:** scored the way the build families are scored (labelled-event coverage via each notable's
  evidence query), botsv2 is **6/15 @50, 7/15 @100** (5/15 / 6/15 with the scorer as written), not 4/15 — a
  modest, not decisive, difference. The families' rule also credits steps whose labelled lines were never
  read (santos: 4 steps at top-50 with 0 lines read).
- **Keys:** 3 of the 15 steps are trivia (epoch cookie, exec e-mail, competitor domain); 1 step is a duplicate key
  (`c2_ssl` = `web_scan`'s IP); 6 are partly trivia (filenames, password, hash).

## VERDICT

Of the 11 missed steps (each assigned one primary cause; secondary causes in brackets; assignment is judgement):

| cause | steps | share |
|---|---|---|
| instrument defect | malicious_account, sql_injection (line mode credits both @34; entity mode demands a string) | 2/11 (18 %) |
| keys defect | xss_cookie_theft, competitor_recon, executive_contact (trivia; 0–1 events read) | 3/11 (27 %) |
| design limit | c2_beacon, covert_channel, scheduled_task_persistence (0 events read; 20/382/4–119 events in 1.2M–55M sources) | 3/11 (27 %) |
| genuine hunt failure (reached, not surfaced) | usb_malware_delivery, patent_exfil (both in a misfit shape, not kept), spearphish_attachment (`invoice.zip` read ×4) | 3/11 (27 %) |

Plus a measurement defect on the 4 passes (2 are one incidental IP match) and a 0.117 % sample. The
identical cross-solver result is consistent with all solvers working inside the same read budget, keys and
scorer, but I cannot show that from this run alone (it needs the other rounds' stores).

## RECOMMENDATION (order)

1. **Scoreboard (cheap, first).** Report botsv2 in line mode beside entity mode; fold `source=` case; dedupe the
   shared IP key; add a strict variant that matches only `what/basis/why/entities`. Proposed patch below
   (not applied).
2. **Keys.** Tag B/P/T per step; report B+P separately; drop `912345678`, the cookie epoch and `ceoberk.png`
   as step-credit keys; make `/member.php` require the payload; verify the registry-key locator escaping and the
   CJK locator (my phrase search for the `.hwp` returned 0 while a `hwp` term search returned both events).
3. **Raw cap** (2,400 chars) for fat sources (stream:smtp): keep value-bearing windows or raise the cap; the zip
   password is unreachable otherwise.
4. **Design.** Add a hypothesis-driven full-index aggregation stage (properties in §4) before sampling, then
   re-run botsv2 with the keys from step 2; do not tune generator weights until then.
5. **Only then** re-open solver rounds on botsv2; against the unchanged instrument, the missing steps are
   mostly outside what a solver can change.

```diff
--- a/portal/modules/security/core/hunt/notables/scoreboard.py
+++ b/portal/modules/security/core/hunt/notables/scoreboard.py
@@ def _on_source(claim: Claim, source: str) -> bool:
     if claim.sources:
-        return source in claim.sources
+        return source.casefold() in {item.casefold() for item in claim.sources}
     return _stem(source) in claim.names
```

(Whether this changes any family's score has not been checked; families' file paths are case-stable but I did
not re-score them.)

## UNPROVEN

- Per-step cause assignment and the B/P/T classes are my judgement.
- Read-presence uses string matching against the run's stores, not a replay of the pipeline; a single read
  string does not mean a scorer could have used it (§1).
- The line-mode botsv2 score is my application of the scoreboard's functions to Splunk-pulled events
  (raw truncated to 1,500 chars for term checks), not an operator-sanctioned scorer; `time` parsing is UTC.
- Splunk counts: audit counts matched on re-run except cookie (219 via search vs 221 TERM), and the registry key
  (119 audit; 4 pulled by my phrase search — escaping not resolved) and `.hwp` (needs the plain `hwp` term).
- Family contrast reads only `events.raw` equality (a lower bound; `behaviour_all`/`misfits` not included).
- Rarity probes: 5 aggregations on fields I guessed (`attach_filename{}`, `uri_query`); not a design validation.
- `peer_rare`, `similar_to_known` and the judge were not examined beyond counts; no LLM output was re-judged.
- Early in the work one export pulled preview rows and inflated counts (331M); fixed (`preview` rows dropped) and
  every number above is from the fixed client.

