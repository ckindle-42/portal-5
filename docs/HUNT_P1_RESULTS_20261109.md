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
| BOTS v1 | **2 / 2** | 2 / 2 | **Cerber 1, web defacement 2** | 3 / 17 | *investigation crashed in P1; re-run pending (below)* | leads ~60 min |

**Against the bar:**
- *≥1 attack episode per environment in the top 25:* **met in 6 / 6**. Every environment
  actually has one at rank ≤ 4.
- *Best case covers ≥ half its stages:* **met in Kyoushi and russellmitchell**, missed in santos
  (7/19) and wheeler (8/17), pending for BOTS v1. Cloud has no stage structure; its cases are
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
| wheeler | **product** | the 8B model **mis-copied the hunt job id** (`…963382f` → `…9633a2f`) and later rendered it with spaces; an analyst would be stuck | **open**: ids a small model can't garble, or tools that accept "latest hunt on <env>" |
| all | ingest | earlier corpora carry labels in `source`/`host`/`p5_item`; `imported_observed` is attack data | hunt bed re-ingests everything label-free; old indexes left untouched |
| — | current review service | 86 min on one hour of one environment without finishing; Splunk time ≈ 1 min, the rest single-threaded Python over raw events | recorded; not used for hunting |

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
