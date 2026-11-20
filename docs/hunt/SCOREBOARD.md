# Hunt scoreboard — modes and pass bar

Proposed 2026-11-19 (lane `hunt-scoreboard-keys`), implementing RECOMMENDATION 1 of
`INSTRUMENT_AUDIT_BOTSV2.md`. The mode definitions are in the scoreboard
(`portal/modules/security/core/hunt/notables/scoreboard.py`, `MODES_RULE`); this page says
what each one measures and which one should be the pass bar. **The pass bar is a proposal —
the operator decides.**

## What each mode measures

| mode | a step counts when | what it measures | blind to |
|---|---|---|---|
| entity loose | a key value appears whole-word anywhere the notable speaks: what/basis/why, entity values, evidence queries and lines | the run surfaced the artefact anywhere in its output | nothing — the most permissive |
| entity strict | a key value appears only in what/basis/why or entity values — an artefact seen only inside an evidence line does not count | the notable is *about* the artefact, not merely containing it | incidental evidence-line matches |
| deduped (always on) | a key value shared by several steps credits its first step only | honest denominators — one notable cannot count twice | double-counting |
| class B/P/T | keys tagged B (behavioural) / P (partly) / T (trivia); B+P reported beside T | keeps CTF-answer keys out of the pass bar's denominator | trivia inflation |
| line mode (build families; entity families given `--keyed-events`) | a notable's evidence query selects a keyed event: `source=` matched case-insensitively, every literal TERM in the event's raw text, else the evidence window | the run's evidence retrieval touched a labelled event | whether the notable says anything about it |

## Pass bar (proposal)

- **Blind behaviour hunts (botsv2-style entity keys): entity strict over scored B+P steps.**
  Today that is **1/11** for botsv2 (the `.hwp` RETR notable). Strict is the only variant that
  cannot be passed by an incidental match — 2 of the 4 old entity passes were one scanner IP
  sitting inside an unrelated "File does not exist" burst line. B+P excludes the trivia keys
  (a cookie epoch, a zip password, an image name) that a hunt should not be graded on.
- **Build families keep line mode** (their keys are per-line, no entity keys): kyoushi 12/12,
  santos 15/21, russell 15/22 @50 on the stored 2026-11-19 runs — unchanged by every patch
  in this lane.
- Every report prints all modes; the operator picks the bar per family kind. A reachable-step
  refinement (steps with ≥1 keyed event read, from the run receipts) is worth adding later;
  the audit measured botsv2 at 8 of 11 reachable B+P steps, which would make today's bar 1/8.

## Rescore, all modes (2026-11-19)

Stored run `neon-live.03k31Qkn` (botsv2/kyoushi/santos/russell at `defd357bc`); botsv2 keyed
events re-exported live from `botsv2` (180,431 events, raw capped at 1500 chars, per-artefact
counts equal to the stored audit counts).

| family | mode | steps | top50 | top100 | all |
|---|---|---|---|---|---|
| botsv2 | entity loose (deduped) | 14 | 3 | 3 | 3 |
| botsv2 | entity strict | 14 | 1 | 1 | 1 |
| botsv2 | entity loose, B+P / T | 11 / 3 | 3 / 0 | 3 / 0 | 3 / 0 |
| botsv2 | line mode (keys as of 2026-11-18) | 14 | 5 | 6 | 6 |
| botsv2 | line mode (keys edited 2026-11-19) | 13 | 5 | 5 | 5 |
| kyoushi | line mode | 12 | 12 | 12 | 12 |
| santos | line mode | 21 | 15 | 15 | 17 |
| russell | line mode | 22 | 15 | 15 | 15 |

botsv2 covered steps, entity loose: `ftp_download` @18, `macbook_file_encryption` @33,
`web_scan` @30 (the scanner IP, inside an evidence line only — strict refuses it). Line mode
adds `malicious_account` @34 and `sql_injection` @34 (a `SELECT * FROM mybb_users` notable
whose query selects the keyed mysql events) and, pre-edit, `xss_cookie_theft` @68.

### Why numbers moved

- **Build families: nothing moved.** The only scorer change that touches them is `source=`
  case-folding; their log paths are case-stable, so every number is identical to the
  2026-11-18 `score.log`.
- **botsv2 entity 4/15 → 3/14.** `c2_ssl` shared `web_scan`'s only key (the scanner IP), so
  dedupe drops it from the denominator; one notable now credits one step. Nothing else moved.
- **botsv2 strict 1/14, not the audit's proposed 2/15.** The `.mkv.crypt` misfit names the
  file only inside its evidence line; by the stored notables the `.hwp` is the sole artefact
  present in what/entities.
- **botsv2 line 6/15 → 5/14 @50 pre-edit.** The audit's numbers counted `c2_ssl`; dedupe
  removes that duplicate credit. Post-edit the denominator is 13 (steps with creditable keyed
  events): the cookie key no longer credits `xss_cookie_theft`.

## Reproducing

```bash
uv run python -m portal.modules.security.core.hunt.notables.scoreboard --json \
  --out <run-tree> \
  --keys botsv2=/Volumes/data01/portal5_hunt/corpora/botsv2_keys/keys.jsonl \
  --keys kyoushi=/Volumes/data01/portal5_hunt/corpora/hunt_bed/kyoushi_s1_ingest/keys.jsonl \
  --keys santos=/Volumes/data01/portal5_hunt/corpora/ait_lds_v21/santos_ingest/keys.jsonl \
  --keys russell=/Volumes/data01/portal5_hunt/corpora/ait_lds_v21/russellmitchell_ingest/keys.jsonl \
  --keyed-events botsv2=<keyed_events.jsonl>
```

The keyed-events export is the live locator result sets (one JSON row per event:
`dataset/scenario/step/value/time/source/raw`); regenerate it from the locators in
`keys.jsonl` before re-scoring a new run. Key changes this lane made (all verified live
against `botsv2`, read-only): trivia keys `912345678`/`1502408189`/`ceoberk.png` marked
`credit=false`; `/member.php` now `requires` the `updatexml` payload; the `.hwp` locator
corrected to the NFD phrase (the index stores the filename NFD; the NFC phrase finds 0); the
registry-key locator corrected to the SPL-escaped phrase (a single backslash finds 0; the 119
events sit in WinHostMon 103 / WinEventLog 7 / xmlwineventlog 5 / WinRegistry 4 — none in the
lowercase `winregistry` carrier the runs sample).
