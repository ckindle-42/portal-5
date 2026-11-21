# FINDING — hunt replan slice D10 (S0 cause, delivered)

Lane `lane/hunt-d10`, brief `coding_task/BRIEF_HUNT_D10.md`, spec
`docs/hunt/ORCACYBER_DEEP_DIVE_2.md` §5 D10. Offline only: the hunt pipeline was **not** run
(operator hold) and the live lab Splunk was not queried at all — every number below is a re-score
of the six stored runs under
`/Users/chris/projects/portal-5-hunt-proof-run/coding_task/scratch/hunt_proof_20261120T232700/`.
Held-out sets (`hb_ait_wheeler`, `hb_cloudobs_aws`, `botsv1`) were never opened.

## What the slice changed

`portal/modules/security/core/hunt/notables/scoreboard.py`

1. **`C0 causes` for per-line families.** A line-mode family now derives a cause per step from the
   read the run actually recorded, in the same vocabulary the entity mode already used:
   `covered | instrument | not_surfaced | censored | unreached`. Derived from
   `_line_reachability` (did the run read one of its labelled lines verbatim) and the ledger's cut
   reads (`capped` or `reason`, matched to the step's labelled file paths), plus D0's
   `evidence_absent` count. Declared causes (`keys` row or `--causes`) still win and are marked
   `cause_source: audit`.
   - `covered` = a notable covers one of its labelled lines at @50 **and** the run read one.
   - `instrument` = the line scan credits a notable at @50 on lines the run never read — the
     deep dive's "gains that are claim-matching against the raw log on disk, so they are not
     findings".
   - `not_surfaced` = the run read its lines and no notable covers them at @50.
   - `censored` = no line was read and a read of one of its files was cut (`capped`) or declined
     (`reason`, e.g. D1's `READ_FILES_MAX` omission row).
   - `unreached` = its lines were never read and no read of its files was cut.
2. **Printed, not just stored.** `C0 causes  <counts>`, then `C0 causes steps  <cause>: <step>
   (<n>/<N> absent)…` for the four non-covered causes, then the cause rule. The `@50` raw recall
   line is unchanged, so `covered + instrument` is exactly the raw `@50` count and `covered` alone
   is the read-relative one.

`portal/modules/security/core/hunt/notables/receipt.py`

3. **`progress.json:honesty` is written by every stage write** (`progress_update`), so no run can
   carry a null. The block holds the knowledge facts (`similar_to_known`: loaded families,
   excluded family, item count, embedding model, reliability AUC) and the merge declaration
   (`merge_method`, `weights_source`, `merge_weights`) — the two facts that previously existed
   only nested under `stages.notables`, which is how the S5 `weights_source: "default"` escaped a
   verdict. The extraction is shared with the scoreboard's `_honesty`, whose exclusion guard is
   unchanged (leak detection still raises).

## The acceptance property, proved on the stored runs

**No family reports an empty cause.** All six stored runs, printed by the same command the
orchestrator's ladder uses (`--keys <family>=<keys.jsonl>`):

```
=== v2/kyoushi
C0 ceiling  steps 7/12 reachable  labelled lines read verbatim 287/408038
C0 causes  covered 7, instrument 4, unreached 1
C0 causes steps  instrument: attacker_http, dirb, webshell_upload, webshell_cmd   unreached: reverse_shell
=== control/kyoushi
C0 ceiling  steps 11/12 reachable  labelled lines read verbatim 1944/408038
C0 causes  covered 11, unreached 1
C0 causes steps  unreached: reverse_shell
=== v2/santos
C0 ceiling  steps 11/20 reachable  labelled lines read verbatim 3002/47367
C0 causes  covered 8, instrument 8, not_surfaced 3, unreached 2
C0 causes steps  instrument: traceroute, network_scan, dns_scan, service_scan, wpscan, webshell_cmd,
  attacker_http, dirb   not_surfaced: exfiltration-service, attacker_change_user, attacker_vpn
  unreached: webshell_upload, crack_passwords (44/44 absent)
=== control/santos
C0 ceiling  steps 12/21 reachable  labelled lines read verbatim 866/47367
C0 causes  covered 11, instrument 4, not_surfaced 1, unreached 5
C0 causes steps  instrument: network_scan, service_scan, webshell_cmd, webshell_upload
  not_surfaced: attacker_vpn   unreached: traceroute, dns_scan, exfiltration-service,
  attacker_change_user, crack_passwords
=== v2/russell
C0 ceiling  steps 11/21 reachable  labelled lines read verbatim 2502/61862
C0 causes  covered 9, instrument 4, not_surfaced 2, unreached 7
C0 causes steps  instrument: service_scan, dirb, wpscan, attacker_http
  not_surfaced: exfiltration-service, attacker_vpn   unreached: traceroute, dns_scan, network_scan,
  webshell_cmd, dnsteal-dropped, webshell_upload, crack_passwords (49/49 absent)
=== control/russell
C0 ceiling  steps 15/22 reachable  labelled lines read verbatim 725/61862
C0 causes  covered 14, instrument 1, not_surfaced 1, unreached 6
C0 causes steps  instrument: service_scan   not_surfaced: attacker_vpn   unreached: traceroute,
  dns_scan, network_scan, dnsteal-dropped, exfiltration-service, crack_passwords
```

Three checks that the cause is read-relative rather than a second recall number:

- `covered` equals the run's read-relative covered@50 in every case (7/11/8/11/9/14), so a step
  the measurement credits on unread lines never reads as found.
- `covered + instrument` equals the raw @50 count on the same run (kyoushi control 11+0=11,
  santos _v2 8+8=16, russell _v2 9+4=13), so the split is the read-relative correction and
  nothing else.
- `crack_passwords` on santos `_v2` prints `(44/44 absent)` beside `unreached` — the step the
  index cannot contain (D0's `evidence_absent`) is named with its cause, exactly as §5 D10 asks.

**`censored` does not fire on any stored run, and that is a finding, not a gap.** On the pre-D1
code that produced these runs the eight-file route cap dropped files **silently** — no ledger row
— so there is nothing to mark as cut (verified: `ledger.jsonl` on santos `_v2` holds 785 rows and
**0** with `capped`/`reason` that name a `source=` path). D1's `record_skipped_read` writes a row
per omitted file with a reason, which is what makes `censored` reachable on a fresh run. The
derivation of `censored` itself is proved by
`test_a_line_family_names_a_cause_for_every_step` (a fixture with a `row_cap` read of the step's
own file).

**`progress.json:honesty` is never null.** Re-running the write path on a copy of the stored
santos `_v2` notables receipt (`coding_task/scratch/d10/honesty_proof/`, a copy — the proof run
was not written to) produces:

```json
{
 "knowledge": "loaded",
 "families": ["kyoushi", "russell"],
 "excluded_family": "santos",
 "knowledge_items": 1631,
 "embedding_model": "google/embeddinggemma-2",
 "reliability_auc": 0.4428853446620584,
 "merge_method": "weighted",
 "weights_source": "default",
 "merge_weights": {"alerts": 0, "deviation": 26, "misfit": 6, "peer_rare": 0, "similar_to_known": 31}
}
```

The stored runs themselves still have no `honesty` key — they were written before this change, and
the scoreboard only reads a run, so re-scoring them will not add one. A fresh run gets it from its
first stage write (`test_progress_declares_honesty_from_the_first_stage` asserts the cards-stage
block, which declares knowledge as not loaded yet).

## Net test lines

`+97` (one test per acceptance property: `test_a_line_family_names_a_cause_for_every_step` +57 in
`tests/unit/test_hunt_scoreboard.py`, `test_progress_declares_honesty_from_the_first_stage` +40 in
`tests/unit/test_hunt_product_path.py`); no test deleted or replaced.

## What is not proved here

- The orchestrator's live proof (`… --stage behaviours --family santos`, then the scoreboard on
  the fresh run) has not been run: the operator hold forbids it. Everything above is a re-score of
  stored runs plus the unit gates.
- `censored` firing on a fresh D1-era run is reasoned from `record_skipped_read`, not observed.
- `covered`/`instrument` uses the @50 cut, matching the entity mode's `_cause_row` and the plan's
  headline cut; a family whose acceptance moves to @100 would need that constant changed in one
  place (`_line_cause`).
