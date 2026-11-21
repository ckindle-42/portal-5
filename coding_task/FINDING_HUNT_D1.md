# FINDING — hunt replan D1: the read approximates a per-file read

Lane `lane/hunt-d1`, 2026-11-21. Implements slice D1 of
`docs/hunt/ORCACYBER_DEEP_DIVE_2.md` §5 (RC1, §3.1). No hunt run was made; the offline
numbers below replay the **real lab index facts** captured as read-only `tstats`
(`coding_task/scratch/d1/facts_*.json`) through the changed read path, and the live
numbers are **read-only** search jobs against the lab Splunk. The full hunt proof is
the orchestrator's (§ "Live proof" at the end).

## What changed

- `index_facts` now reads `by sourcetype source host` and carries every indexed file
  with its count and hosts (`SourceFacts.files`), instead of names only, ranked by
  volume, with the card's `sources` list no longer cut at 12.
- The behaviour read (`read_files` in `sample.py`, used by every behaviour read path)
  issues **one read per file with its own `head`**: the file's share of one source-wide
  slice, spread over the windows its share of the schedule needs, never above a pooled
  read's per-read cap. A source small enough to read whole still returns every event.
- Every `(source, file, window)` read lands a ledger row (the existing read observer,
  whose query now names the file) and a receipt line (`progress.json:
  stages.behaviours.files`, with `events_available` per file); per-source receipts gain
  `files_indexed` / `files_routed` / `files_omitted`.
- `READ_FILES_MAX = 32` files per source read; past it each unread file is written to
  `ledger.jsonl` with `reason: read_files_cap` and appears in the receipt.
- `progress.json: stages.behaviours.searches` reports the stage's own search count by
  kind (`total`, `seconds`, `by_kind`).
- A card persisted before this change has no `files`, so the read falls back to the old
  pooled route rather than silently reading a subset; the fact round-trip
  (cards → `sources.json` → `facts_by_source`) is verified identical for 21 files.

## Offline replay on the real facts (uniform-time model of `head`)

| family | files | D1 reads (pooled today) | D1 rows | labelled file (rank) | rows from it | stored run's read rows |
|---|---:|---:|---:|---|---:|---:|
| santos | 21 | 122 (24) | 60,059 | `intranet…access.log` (14) | **1,725** | 21,562 |
| kyoushi | 26 | 109 (24) | 56,373 | `intranet…access.log.4` (1) | 30,000 | 18,786 |
| russell | 21 | 219 (24) | 60,130 | `intranet…access.log.2` (4) | 3,460 | 20,963 |

Same facts, pooled 8-file route (today's path, same model): 30,000 rows and **0** from
the santos or russell labelled files (kyoushi's is rank 1 so it already dominated).

`READ_FILES_MAX = 8` on the same facts: 8 routed, 13 / 18 / 13 files declared
`read_files_cap`, one ledger row each — the omission path is exercised on real data.

Behaviour-stage file reads across **every** activity source (estimate from the same
rule): santos 473, kyoushi 651, russell 571 — against ~336 today and a 2,000-request
budget. The deep dive's "21 files × 14 windows = 294 searches for access_combined
alone" is an underestimate on this estate: `syslog` has 53 files and `linux_secure` 14,
so the literal product is ~2,300 requests for santos and would exhaust the budget. The
implemented rule spreads each file's windows by the share of the slice its budget can
hold, which keeps the reads ≈ `windows + files`.

## Live read-only probes (lab Splunk, search jobs, same window)

The window is the four-hour bucket where the labelled file carries the most events; the
pooled query is the stored run's own ledger query verbatim (8 source names, `| head
1250`).

| family | window | pooled `head 1250` rows | of which labelled file | one per-file read | scan / duration |
|---|---|---:|---:|---|---|
| santos | 2022-01-17 08:00 (8,218 file events) | 1,250 over 2 files | **0** | 575 rows | 3,000 / 0.41 s |
| kyoushi | 2021-03-23 20:00 (406,402) | 1,250 over 3 files | 1,220 | 1,250 rows | 2,858 / 0.40 s |
| russell | 2022-01-24 00:00 (7,698) | 1,250 over 1 file | 1,250 | 346 rows | 2,791 / 0.41 s |

So a single-file read costs ~3 k scanned events and 0.4 s, and the santos file — rank 14
of 21 and outside the eight-name route — is never reached by the pooled read in the
window where it carries the whole web intrusion.

## Limits this slice does not fix

- **Host starvation inside a multi-host file.** A source path can exist on several
  hosts (`/horde/horde-access.log` carries 119,321 events over `mail`, `hayes_mail` and
  `rogersturnbull_mail`; `postfix_syslog` has 4,445 `(source, host)` pairs). The read
  unit is the file, so a multi-host file's `head` is still arrival order across its
  hosts. Making the unit `(file, host)` would multiply reads by the host count and is
  not affordable on this estate; anchored reads do carry `host=`.
- **The row budget is the nominal slice, not today's realised rows.** Rows rise where
  the pooled read starved (santos access 21,562 → ≤60,000 cap) and stay flat where it
  did not (single-file sources are capped at the pooled per-read head).
- No run has been made: `attacker_http`/`dirb`/`wpscan` becoming reachable (C0 11 → 14)
  and the store's intranet event counts are unproven until the orchestrator runs the
  behaviours stage on `hb_ait_santos_v2`.
