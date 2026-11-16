# MISFIT report — do rare out-of-structure lines get raised?

Offline answer to one question per training corpus: **does the `misfit` generator raise the
entity-less quiet step (kyoushi's one-line reverse_shell), and what does that cost on benign
sources?** Every number below was produced by running the real generator code
(`behaviours.collect_misfits`, `misfit.generate_misfit`) over the stored Stage-3 cards and the
on-disk gather logs — no Splunk, no model, no synthetic data. It complements
`RELATE_LINKAGE_REPORT.md` §4, which showed the line is absent from the behaviour store.

## Mechanism being measured

- **Behaviours stage** now claims each read row against *every* card of its source (any
  partition part, any consumer kind). Rows no card claims are out-of-structure: they are
  counted per source, grouped by a content-free **token-class shape** (letters→`a`, digits→`9`,
  punctuation kept), sampled (3 lines per shape), and stored in `misfits`/`misfit_stats`
  tables next to the behaviour table. Each card receipt records `events_out_of_structure`
  and `unparsed_share`.
- **`misfit` generator** (default-enabled, no content dictionaries) ranks shapes from sources
  that are *otherwise well understood*: card coverage ≥ 0.9 (`MISFIT_MIN_COVERAGE`) **and**
  observed misfit share ≤ 1% of lines read (`MISFIT_MAX_SHARE`) — learned from the run, not
  declared per source. Measure = shape's share of the source's read lines; sources are
  interleaved so one noisy source cannot monopolise the 300-notable budget.

## Replay setup and its declared divergences

| Corpus | Cards (stored) | Raw logs | Labels |
|---|---|---|---|
| kyoushi | `snap_s3_6648dc6/results/hunt/knowledge_s3a/kyoushi/sources.json` (43 cards) | `corpora/hunt_bed/kyoushi_s1/gather/` | `kyoushi_s1_ingest/keys.jsonl` (408,038 lines) |
| santos | `…/knowledge_s3a/santos/sources.json` (147 cards) | `corpora/ait_lds_v21/santos/gather/` | `santos_ingest/keys.jsonl` (47,367 lines) |

(roots under `/Volumes/data01/portal5_hunt/`). Per source, files listed in the card's indexed
`facts.sources` were found under `gather/<host>/logs/…` and stride-sampled to a 12,000-line
per-source budget (files ≤ 2,500 lines read whole — `error.log.2`, the 4-line reverse_shell
file, is read whole). Divergences from a live run: the live stage reads the newest
`per_window` events of 12 time slices instead of a stride sample; `_time` is unknown offline
(all timestamps 0.0, so evidence windows are meaningless offline); coverage comes from the
stored cards rather than a fresh cards stage.

## 1. Kyoushi — reverse_shell IS raised, at rank 12 of 136

The line `bash: 196: Bad file descriptor` (`intranet_server` `/apache2/error.log.2` line 3,
labels `escalate`,`reverse_shell`) is out-of-structure for the `hb_kyoushi_s1:error.log` card
(template header of 5 tokens; the line has 5 whitespace tokens and matches no template), and
it is raised:

```
rank 12  source=hb_kyoushi_s1:error.log  events=1  measure=1.43e-04 (1 of 7,009 lines read)
shape: aaaa: 999: aaa aaaa aaaaaaaaaa
query: search index="hb_kyoushi_s1" (source="/apache2/error.log" OR source="/apache2/error.log.1"
       OR source="/apache2/error.log.2" OR source="/apache2/error.log.3" OR source="/apache2/error.log.4")
       "descriptor" "bash" | head 5
```

The query's literal terms both occur in the labelled line, so the scoreboard's coverage rule
can attribute it — the step is reachable without any entity pivot. It is rank 12, not rank 1:
six source groups interleave before/around it (eve.json's uncarded `event_type`s at
measure 5.8e-05, dnsmasq's startup banner at 8.4e-05, …), and within `error.log` one Apache
notice shape ties at the same 1-of-7,009 measure. All 7 `error.log` shapes are kept (the
other 6 are Apache `mpm_prefork`/`core` notice lines — including `error.log.2` lines 1, 2
and 4 — which are equally out-of-structure).

A second attack-bearing notable appears at rank 111 (`audit.log`, `type=USER_START …
op=PAM:session_open acct="msperl"` — labels `attacker_change_user`,`escalate`; audit `kv`
variants that fit no card partition).

## 2. Santos — no quiet misfit step to raise; the escalation leaves audit misfits

Santos's quiet step (dnsteal exfiltration) lives inside `dnsmasq.log` and **parses into the
card structure** — it is not a misfit and this generator does not claim to surface it. The
only `dnsmasq.log` misfit is the startup banner (rank 1, benign). Two attack-bearing notables
are raised, both `audit.log` shapes at the escalation minute (ranks 37 and 45:
`type=USER_START … op=PAM:session_open` and `type=LOGIN … old-auid=4294967295 auid=1002`,
labels `attacker_change_user`,`escalate`).

## 3. Cost — benign misfit notables per run

| Corpus | Shapes seen | Kept notables | Attack-bearing | **Benign** | Shapes gated out |
|---|---|---|---|---|---|
| kyoushi | 3,667 | 136 | 2 | **134** | 549 low coverage + 2,982 poorly-understood source |
| santos | 4,755 | 66 | 2 | **64** | 1,338 low coverage + 3,351 poorly-understood source |

Benign kept notables by source:

- **kyoushi (134):** `eve.json` 64 (uncarded `event_type` partitions — lines that parse as
  JSON but fit no card's part), `audit.log` 40, `mail.info` 8, `mail.log` 8, `error.log` 6,
  `fast.log` 7, `dnsmasq.log` 1.
- **santos (64):** `fast.log` 20, `error.log` 16, `audit.log` 8, `mail.info` 7, `mail.log` 7,
  `logstash-plain-2022-01-13-1.log` 5, `dnsmasq.log` 1.

The gates are what keep the cost bounded: sources like kyoushi `syslog` (37,203 of 42,840
sampled lines misfit — 86.8%, card coverage 0.90) or `system.journal.txt` (65.2%) are
excluded as *poorly understood* despite passing card coverage, and `stats.log`
(coverage 0.87), `mainlog`, `redis.log` etc. fail the coverage gate. Without the
misfit-share gate, `syslog` alone filled the entire 300 budget with one-off shapes and the
reverse_shell notable was cut — measured, then fixed by the gate plus source interleaving
(both declared defaults; no threshold was tuned after seeing corpus numbers).

136 and 66 kept notables are within the 300 budget, so every attack-bearing misfit survives
to the judge stage; the benign cost is judge requests, not lost signal.

## Appendix — how the numbers were produced (all offline)

1. Load stored cards: `card_from_dict` over `sources.json`; keep sources with ≥1
   behaviours-usable card (`card_consumers`).
2. For each source, locate `facts.sources` files under every `gather/<host>/logs/`, count
   lines, stride-sample to the 12,000-line budget (files ≤ 2,500 lines whole), recording
   `(host, file, 1-based line)` per sampled row.
3. Claim each row exactly as the stage does: `parse_row(raw, card.fmt, card.columns,
   card.template_model)` with fields and `card.in_part(fields)` for any card of the source.
4. Feed unclaimed rows through the real `collect_misfits`, and the result through the real
   `generate_misfit` with `facts_by_source` rebuilt from the stored card facts.
5. Label attribution: a notable is attack-bearing when any line of its shape matches
   `(host, source, line)` in `keys.jsonl`.

Replay runtime: kyoushi 6.7 s, santos 9.8 s (Apple silicon, single process). The replay
script is not committed (it is scratch tooling for this report); the procedure above
reproduces it from the named modules.
