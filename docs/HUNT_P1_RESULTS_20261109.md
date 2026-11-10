<!-- HUNT_P2_RERUN_20261110 -->
# Phase 2 rerun — completed live, bars NOT met (2026-11-10)

**Not a working product.** The four enterprise environments regress on false leads and
focused case coverage. AWS modestly improves recall; BOTS gains two focused cores containing
both scenarios. None of those gains clears Phase 2 overall. Passing merge gates do not
establish product quality.

## Frozen run and receipts

Engine `dc2db868da1ce8bce0266c5d41bbf402d364cacc`: ranking `98692433f` merged via
`ea3b636e9`; core-route diversity `cbf543322` merged via `dc2db868d`. Review MCP restarted
at `2026-11-10T13:24:44Z`. Campaign `13:24:48Z`–`19:49:50Z` (6h 25m), driven by
`results/hunt/p2/run_p2.sh`. All six hunts completed through Open WebUI →
`security-reviewer` (`granite4.1:8b-ctx8k` on Ollama) → review MCP → live Splunk.
No engine changes or service restarts during the campaign; final source hashes match
`FREEZE.txt`. Keys were used only by the out-of-band scorers, with no feedback into the run.

Local receipts: `results/hunt/p2/` (`FREEZE.txt`, six transcripts and scores,
`job_summary.json`, `MANIFEST.json`). Prior P2 preserved in
`results/hunt/p2_run1_20261110T130944Z/`. Raw records and keys remain local/ignored.
All six transcripts have the exact real job id in the start answer and completed lead/case
retrieval: 18 analyst turns. This supports start-id integrity for this run; it is not a
claim that every generated sentence was independently verified.

## Results against the previous Phase 2 run

| environment / job | false leads top 10 (previous) | attack first-hit ranks | best core coverage (previous) | engine time |
|---|---|---|---|---|
| Kyoushi `hunt-cea770e4b4e1` | **8/10** (6) | 1, 20 | **3/9 stages** (3/9) | **35.3 min** |
| russellmitchell `hunt-879d81d24532` | **9/10** (7) | 8, 19, 23, 26 | **2/21** (3/21) | **33.8 min** |
| santos `hunt-960195e04fc8` | **8/10** (7) | 8, 9, 14, 20 | **1/19** (3/19) | **37.1 min** |
| wheeler `hunt-baff6b0f5beb` | **9/10** (5) | 6, 13, 16, 22, 29 | **2/17** (3/17) | **34.9 min** |
| AWS `hunt-9c418b8d82eb` | **4/10** (4) | first 4; **7/35 attacks top 25** (5/35) | not stage-keyed | **19.5 min** |
| BOTS v1 `hunt-a4cfe59b6ff6` | **4/10** (4) | Cerber 1; defacement 3 | **both scenarios in cores 2 and 3** (200 events each) | **212.2 min** |

Best full-evidence stage coverage, separately from the focused core: Kyoushi 3/9,
russellmitchell 8/21, santos 7/19, wheeler 3/17. The misses are therefore not only core
truncation. BOTS full cases 1–3 contain artefacts from both scenarios; core 1 only has Cerber,
cores 2–3 have both, and core 4 has defacement. Core hosts: 2, 3, 44, 2; core sizes:
200, 200, 200, 195. Full BOTS evidence remains large: 61,047 / 55,388 / 16,530 / 222 events.
The BOTS job records two degraded footprint lookups (`WindowFetchError`); other five record
none. These degradations are retained, not scored as successful lookups.

| Phase 2 bar | ledger | observation |
|---|---|---|
| At least one attack in every environment's top 10 | PASS | 6/6 |
| False leads ≤3/10 | FAIL | 0/6 meet the bar |
| Whole-attack core in ≥4/5 stage-keyed environments | FAIL | 1/5; BOTS only |
| Start ids exact through Open WebUI | PASS | 6/6; lead/case retrieval completed by environment |
| Each hunt ≤15 min | FAIL | 0/6 |
| Constants only as effort budgets | FAIL | existing top-decile seed filter, below |

## What changed, and what the live run disproved

Ranking now uses elapsed history hours, maximum concentration across zooms, and peers that
only discount. Core selection spends capacity across originating pivot routes within seed
priority, normalizes timeline/near wrappers, preserves colon-bearing tokens and original
route evidence, and retains kind and total effort budgets. These are implementation facts,
not claims of improvement. The live enterprise results contradict an improvement claim.
The combined run does not isolate which ranking component caused each regression.

## Protocol and retrieval defects found

The existing investigator uses `_TOP_DECILE = 0.1` in `_top_decile_cut()` to filter which
leads are investigated. The old comment calls it a relative band, but it is a hand-chosen
decision threshold, not an effort budget. It violates the current rule. No claim of full
protocol conformance is made. Remove it without replacing it with another hand-set cutoff,
then run a separately frozen comparison.

Live BOTS active-job metadata exposed a whole-index pivot footprint search for `/1.1`
with `head 49282`. It advanced from 4,650,986 scanned events / 12,062 matches at 176 seconds
to 5,363,452 / 13,841 at 205 seconds, then 10,675,808 / 30,132 at 442 seconds. It was not
frozen: it was scanning for a generic fragment. The returned-match cap does not bound scanned
events or total wall time. Later active raw queries included structural text, encoded
fragments and date tokens. No token-specific exclusions were added mid-run.

A live indexed probe returned zero `tstats TERM()` cells for `/1.1` in **0.434 s**, despite
many raw matches. For the top lead's actual burst token `:40464`, `tstats` returned **9,346
matches across 106 hourly host/source cells in 1.512 s** (2 hosts, 5 sources). No key was
used to select these probe tokens. This demonstrates useful indexed localization and an
indexed/raw coverage mismatch, not that TERM is a complete replacement for raw verification.

The code already uses tstats for templates, value series and candidate footprints. But
`_footprint_rows(exact=True)` unconditionally repeats an index-wide raw search, and indexed
misses also fall back there. `kinds()` and `timeline()` repeat broad retrieval without
carrying indexed host/source/time localization into the deeper read. `investigate()` also
fetches kinds even after a pivot's exact weight becomes zero. Structural/date/fragment
candidates continue entering the frontier. These are retrieval and candidate-quality defects,
not a lab-health success. Splunk's indexed-search and token-coverage constraints are described
in its [tstats reference](https://help.splunk.com/en/splunk-enterprise/search/spl-search-reference/10.0/search-commands/tstats).

## Next repair and validation

Prioritize indexed discovery and trends → explicit candidate envelopes → bounded raw evidence
verification. Preserve the compound-value recall that motivated the old exact-search fallback;
a TERM miss is unknown coverage, not absence. Discover index representation from the environment,
retain localized host/source/time evidence, and make expansion and exhausted work budgets explicit.
Do not introduce token/field/format exclusion lists or hand suspicion cutoffs. Independently
remove the top-decile filter and diagnose the ranking regression with frozen live comparisons.
Do not advance to Phase 3 on this result.

Merge gates passed for the source changes, and `bash scripts/ci_local.sh` passed with
9,857 tests / 21 skips plus lint, formatting, type and complexity gates. They permitted review
and publication; they did not prove the product worked. The live scoreboard above is the verdict.
<!-- END_HUNT_P2_RERUN_20261110 -->

# Milestone P1 — blind threat hunting, proven live (2026-11-09)

**Claim tested:** one unchanged, blind engine, started by an analyst through Open WebUI, surfaces
the known attacks across independent third-party environments of different kinds, and the
false leads it raises on their benign activity are counted. No labels, rules or per-dataset
tuning are in the decision path.

**Verdict:** the claim holds for **lead finding** in all six environments: every environment
has known attack activity in its top 10 leads. **Case assembly** (pulling the whole attack into
one case) clears the half-the-stages bar in 2 of 5 scored environments. False-lead rates are
high (4–6 of the top 10) and are reported, not tuned away.

## Setup (all live)

- **Engine:** `portal/modules/security/core/hunt/` frozen at `eda16d9ab` for the proof run.
  BOTS v1 is re-run at `dd56e36a4` (one investigator crash fix, below). Lead ranking is
  identical code in both.
- **Path:** Open WebUI → Pipeline → `security-reviewer` (`granite4.1:8b`, 8K context) →
  `portal-review` MCP (`hunt_sources` / `hunt_start` / `hunt_leads` / `hunt_case`) → the engine
  → the lab Splunk.
  - Driver: `scripts/hunt_bed/owui_proof.py`.
  - Transcripts: `results/hunt/p1/<index>.json`.
- **Data:** third-party, one index per environment, native records, **no labels in the events**.
- **Keys:** kept out of band and read only by the scorers (`scripts/hunt_bed/score_*.py`)
  after each hunt. Every key joins 100% to the ingested records.
- **Lab:** Splunk LXC 301 scaled from 4 cores / 4 GB to 12 cores / 16 GB, `base_max_searches`
  raised from 6 to 20. The original sizing failed live with `503` under concurrent searches.

| environment | kind | events | hosts | sourcetypes | truth |
|---|---|---|---|---|---|
| `hb_kyoushi_s1` (AIT Kyoushi test set) | enterprise host + network logs | 24.5M | 17 | 36 | per-line labels, 408k lines, 9 stages, 2 attack days |
| `hb_ait_russellmitchell` (AIT-LDS v2.1) | enterprise host + network logs | 25.5M | 16 | 127 | per-line labels, 61.9k lines, 21 stages |
| `hb_ait_santos` (AIT-LDS v2.1) | enterprise host + network logs | 25.1M | 16 | 126 | per-line labels, 47.4k lines, 19 stages |
| `hb_ait_wheeler` (AIT-LDS v2.1) | enterprise host + network logs | 32.3M | 20 | 144 | per-line labels, 491k lines, 17 stages |
| `hb_cloudobs_aws` (DSN'26 cloud_obs) | AWS CloudTrail API | 0.16M | 1 | 2 | 35 attacks, signature from 845 paired payload/no-payload runs |
| `botsv1` (Splunk BOTS v1) | mixed enterprise Splunk (web, Windows, Sysmon, network, IDS, …) | 33.4M | 1,764 | 26 | 2 scenarios, cited entity key (3 public write-ups), live-audited |

## Results

"Episodes": attack days for AIT/Kyoushi, attacks for cloud, scenarios for BOTS. "False" = a
lead whose host and time bucket hold no keyed attack record.

| environment | episodes in top 10 | episodes in top 25 | first-hit ranks | false leads top 10 / top 25 | best case: stages covered | hunt time |
|---|---|---|---|---|---|---|
| Kyoushi s1 | 1 / 2 | **2 / 2** | 1, 14 | 6 / 20 | **8 / 9** (VPN, dirb, webshell upload + cmd, su, sudo cmd + session; reverse shell missed) | 20.4 min |
| AIT russellmitchell | **4 / 4** | 4 / 4 | 1, 6, 7, 9 | 4 / 15 | **11 / 21** (wpscan, dirb, webshell, service scan, su, sudo); a 2nd case has DNSteal exfil | 29.5 min |
| AIT santos | 3 / 4 | **4 / 4** | 1, 3, 4, 14 | 5 / 17 | 7 / 19 (**miss**: wpscan, dirb, webshell, service scan; exfil in separate cases) | 21.3 min |
| AIT wheeler | 4 / 5 | 4 / 5 (5/5 by top 50) | 1, 2, 4, 6, 33 | 4 / 16 | 8 / 17 (**miss**, just under half: wpscan, dirb, webshell, scans, DNSteal) | 27.1 min |
| AWS cloud_obs | 4 / 35 | 5 / 35 (11 by top 50) | 4, 5, 7, 9, 12, … | 5 / 15 | case 2 holds 9 attacks' records (account creation, credentials from password stores, data encrypted for impact, exfiltration, …) | 9.9 min |
| BOTS v1 | **2 / 2** | 2 / 2 | **Cerber 1, web defacement 2** (re-run 4: 1, 3) | 3 / 17 (re-run 4: 4 / 17) | re-run 4 (`eca1af2c8`): all 4 cases hold artefacts; case 1 holds **both** scenarios (`121214.tmp`, `MIRANDA_PRI`, `40.80.148.42`, `23.22.63.114`, `3791.exe`) but is bloated (17.5k events, 1,762 hosts) | leads ~60 min; dig 108 min (1 lookup degraded) |

**Against the bar:**
- *≥1 attack episode per environment in the top 25:* **met in 6 / 6**. Every environment
  actually has one at rank ≤ 4.
- *Best case covers ≥ half its stages:* **met in Kyoushi and russellmitchell**, missed in santos
  (7/19) and wheeler (8/17), BOTS v1 cases contain both scenarios' artefacts but are not focused (17.5k–21k events). Cloud has no stage structure; its cases are
  reported by attacks contained.
- *False leads:* 3–6 of the top 10 and 15–20 of the top 25 in every environment. **Reported,
  not tuned.**

## What the engine does (and does not)

- **Generic signals only, computed in Splunk where possible.**
  - *Template novelty:* Splunk's indexed `punct`, scored against prior history only.
  - *Concentration:* novelty on every host at once is environment-wide, not an intrusion.
  - *Value burst:* a value's count against its own active prior buckets.
  - *Coherence:* the product of signal percentiles, i.e. "this *and* that".
- **Zoom ladder.** 1 min / 10 min / 1 h / 1 day, each used only when the data spans enough
  history; one incident seen at several levels is folded into one lead.
- **Investigation.** Digs from leads on values that are rare in the environment *and* recur in
  ≥2 places, looks at every kind of event a value appears in, looks around the most specific
  events on their host, and merges cases that share a specific pivot.
- **Nothing in the decision path names a technique, field, sourcetype or format.** The constants
  left are effort budgets: candidates per zoom level, dig depth/breadth, look-around minutes.

## Defects found by running it live (fixed or recorded)

| found | where | what | status |
|---|---|---|---|
| Kyoushi | search layer | `TERM()` misses a value inside a compound token: it found 179 of the attacker address's 455 events | fixed: exact plain-search footprints for pivots |
| Kyoushi | pivot | a fixed 50,000-count cap discarded the attacker's address | removed: burst against the value's own history |
| Kyoushi | merge | cases merged through benign words and the victim's ordinary activity | relative-specificity merge; still noisy (case 1 = 19,973 events) |
| cloud_obs | engine | a fixed 1-hour bucket cannot see 3-minute attack runs | zoom ladder |
| cloud_obs | data | publisher's CloudWatch exports are invalid JSON (redaction) and duplicate CloudTrail; `-jq-` files are duplicates | excluded; recorded |
| P1 | lab | Splunk 4 cores / 4 GB → `503` under concurrent hunts | scaled to 12 cores / 16 GB, `base_max_searches` 20 |
| BOTS v1 | investigator | multivalue Splunk fields arrive as lists → crash after ~1 h | fixed `dd56e36a4`; re-run |
| BOTS v1 re-runs | investigator | a punctuation run (`........`) became a pivot whose exact lookup scanned all 33M events (>20 min); then a common fragment (`10.10`) exceeded the 600 s read timeout and failed the whole dig | fixed `6bfe43615` (a value needs a letter/digit) and `eca1af2c8` (exact counting bounded at an average hour of the environment; a failed lookup degrades one pivot) |
| wheeler | **product** | the 8B model **mis-copied the hunt job id** (`…963382f` → `…9633a2f`) and later rendered it with spaces; an analyst would be stuck | **open**: ids a small model can't garble, or tools that accept "latest hunt on <env>" |
| all | ingest | earlier corpora carry labels in `source`/`host`/`p5_item`; `imported_observed` is attack data | hunt bed re-ingests everything label-free; old indexes left untouched |
| — | current review service | 86 min on one hour of one environment without finishing; Splunk time ≈ 1 min, the rest single-threaded Python over raw events | recorded; not used for hunting |

## Job-id corruption: probe through the real path (not yet root-caused)

8 analyst questions through Open WebUI that require copying a hunt id. The streamed path is served
by oMLX `granite-4.1-8b-mxfp8`.
- **Tool calls carried the correct id in 8/8.** Every lookup returned real data; no "unknown
  hunt" errors.
- **The answer text corrupted the id in 6/8,** every time the same way: a space after `hunt-`,
  stray `**`, typographic characters (U+202F narrow no-break space, U+2011 non-breaking hyphen),
  and once a digit split (`e606e96 3382f`).
- A consistent `hunt- ` space points first at **our path** (stream assembly / detokenisation /
  sampling penalties on oMLX), not model choice. The Ollama variant of this seat runs with
  Ollama's default `repeat_penalty 1.1` over 64 tokens (its Modelfile sets only `num_ctx`).
- Next: A/B the same request stream vs non-stream and oMLX vs Ollama, with penalties neutralised,
  before considering a different model.
- Harness-side fix either way: tools that accept "latest hunt on <environment>" so no id is
  retyped.

## Open, for the next decision

1. **Case assembly:** whole-attack cases in 2/5. The misses keep exfiltration or escalation in a
   separate case. The time/place pivot and the merge rule are the levers.
2. **False leads:** half the top 10 everywhere.
3. **Cloud recall:** 5/35 in the top 25. The job keeps only its top 50 leads, so "never
   surfaced" means "not in the top 50".
4. **The id-copy product bug.**
5. **The remaining sources** (`coding_task/HUNT_BED_SOURCES.md`): 5 more AIT-LDS environments
   downloaded, cloud_obs Azure/GCP, WitFoo (real SOC benign), AInception, Loghub, UWF, and the
   attack-only Windows sets.
