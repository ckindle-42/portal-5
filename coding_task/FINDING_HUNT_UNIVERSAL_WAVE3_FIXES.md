# FINDING — Universal Hunt wave-3 forensic fixes (sentinel anchors, flow links, sampling floor, exact UID scoring)

Lane: `lane/hunt-universal-sentinel-and-sampling-fix` · Brief: `BRIEF_HUNT_UNIVERSAL_WAVE3_FIXES.md`
All changes universal/signature-free in `portal/modules/security/core/hunt/`; corpus-aware scoring stays in `scripts/hunt_bed/`.

## Root causes (code-verified; live confirmation is the orchestrator's)

1. **Sentinel anchors** — `spine.classify` had no unset/placeholder filter: `auid=4294967295`
   (auditd's `(uint32)-1`) became `user:4294967295`, anchoring cases and linking cron/webmail noise.
   Fix: `spine.is_sentinel_value` (casefolded set: `4294967295 -1 0.0.0.0 :: 127.0.0.1 ::1 - (empty)
   (none) (null) none null n/a unknown`), applied to identity kinds (user/address/hostname/domain) in
   `classify` and the typed-field override path of `entities_for`; relate's seed pivots (`_entities`)
   and inventory flow values (`_flows`) drop the same set. `root`, `SYSTEM`, real users/IPs untouched
   (uid `0` is still excluded only by the pre-existing `len<2` guard, not by the sentinel set).

2. **0 flow links** — inventory field records carry their own `role` (`_field_record`, incl.
   structural/vocabulary fields selected as `object` that the card's planned `roles` never name),
   but `_flow_steps` dropped it and relate's `_step_role` re-derived the role from the card plan →
   `""` → `_role_transition` false → every such flow censored as `flow_roles`. Past live receipts in
   this repo show exactly that: `REPORT_HUNT_VERDICT_santos.md` ("flows_skipped: 17,
   censored.flow_roles: 17") and `REPORT_HUNT_VERDICT_kyoushi.md` (21 skipped as flow_roles).
   Fix: `_flow_steps` carries `role`; `_step_role` prefers the recorded role, card-plan lookup stays
   as the legacy fallback. Residual design behavior (not changed): a flow whose value spans >24 h at
   its endpoints is still window-censored by `_link_flows` — a case is one day by design.

3. **Sampling floor** — `per_window_events` capped every slice at 2,500 even when a lone source's
   share of the 400 k stage budget was 33,333/window; a 95,871-event source therefore never qualified
   for the whole read (`_is_complete_source` budget = 2,500×12 = 30 k) and sampled ~5 k via value
   spans. Fix: allocation is the source's share (`TOTAL // sources // 12`); the 2,500 ceiling now
   applies only to *sampled* slices inside `read_behaviour_source` (and `window_activity`), so the
   multi-file sampled worst case (32 files × 3 windows × 2,500 = 240 k) is unchanged and whole reads
   stay bounded by the stage budget. A ~95 k lone source now reads **whole** — rare bursts included.

4. **Inflated zeek scoring** — `hb_uwf_zeek24` keys carry month-wide `start_epoch..end_epoch`
   windows, so any benign row "hit". Measured on the real corpus: 95,364/95,871 ingested raws exceed
   the 400-char evidence excerpt and only 3.0% of uids survive it — uid/excerpt matching alone cannot
   work. Fix: exact line scoring via the ingest manifest (`uwf_zeek24_manifest/digests.jsonl`,
   digest = `sha256(host|source|raw)[:24]`, verified against the real Exfiltration CSV rows):
   `score_corpus` joins store raws → manifest digests → tactic, keyed by full-raw sha256 and the
   400-char prefix; evidence hits only exact attack lines. `row_precision` added to scores and
   PROOF_RECEIPT.md. Falls back to window scoring when no manifest is present.

## Gates (this lane)

- `uv run pytest tests/unit/ -q` → 3590 passed, 22 skipped.
- Brief slice `-k "spine or relate or behaviour or blind or verdict"` (unit+security) → 204 passed.
- `uv run ruff check .` / `ruff format --check .` → clean.
- `uv run python scripts/complexity_report.py --gate` → GATE OK.
- `uv run mypy portal/` → 582 errors in 35 files, **all pre-existing**: identical count at HEAD in a
  scratch worktree; zero errors in any changed file (errors live in scripts/validation, tests/wfe, …).

## Orchestrator live verification

Re-run the blind proof on the five corpora (keys + manifests already on disk):

```bash
uv run python scripts/hunt_bed/prove_universal_blind.py --all-proof \
  --keys-dir /Volumes/data01/hunt_keys --out-dir results/hunt_proofs/wave3_fixes
```

What shows the fixes worked:
- `hb_uwf_zeek24` receipt: `events` ≈ 95,871 (whole read, `read_mode=whole` in behaviours receipt),
  `scoring_method` starts "exact ingest-manifest", `row_precision` ≤ 1 and attack-step recall no
  longer 1.0-from-benign; Exfiltration recall reflects the 23 real rows.
- `hb_ait_wardbeck` cases.json: no case anchored on `user:4294967295`; top case is a real actor.
- `hb_ait_wilson` / `hb_ait_wardbeck` / `hb_ics_pcap` relate receipt: `censored.flow_roles` drops
  toward 0 and top cases show `why=... N flow links` with N > 0 where endpoint episodes are ≤24 h.
Failure signals: zeek `events` still ~5,000; `flow_roles` still == flows; sentinel entity reappears
in entities.duckdb (`SELECT value FROM entities WHERE value='4294967295'`).