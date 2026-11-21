# FINDING — Hunt Replan E3: per-source localisation and a per-read coverage label

**Slice:** `docs/hunt/ORCACYBER_DEEP_DIVE_3.md` §6 **E3** (property "a source whose own
`[first,last]` is inside its model's summary window gets `mechanism: accelerated`", §2.1/§2.3)
**Lane:** `lane/hunt-e3` · **Base:** `614368b30` (merge of `lane/orcacyber-deep-dive-3`)
**Commits:** `92f78fa6e` (implementation + tests), `957d09490` (two-remainder fix below)

No live Splunk, no `launch.sh`, no `.env`, no held-out set. Everything below is a unit test or a
read of the stored Round-2 run directories on `/Volumes/data01/portal5_hunt/`.

## 1. What changed

| file | change |
|---|---|
| `notables/sample.py` (`coverage_label`) | exact containment is the only `accelerated` test; a proper overlap of the span is `accelerated_partial`; no tolerance constant |
| `notables/sample.py` (`Localisation`) | gains `covered_window` (the sub-range the summary holds) and `scanned_window` (the complement pieces); `mechanism`/`coverage` admit `accelerated_partial` |
| `notables/sample.py` (`localise`) | takes an optional pre-probed `summaries`; on a partial it localises the covered sub-range from the model's summary and each remainder from the index aggregate, then keeps the strongest `LOCALISE_WINDOWS` peaks across both |
| `notables/sample.py` (`_summary_windows`, `_scan_windows`, `_partial_summary`, `_partial_localisation`) | the split, in helpers, so `localise` stays small |
| `notables/behaviours.py` (`_localise_sources`) | one `localise()` per wide **source** over `(facts.first, facts.last + 1e-6)`; `localisation.indexes` is one entry per source (`source`, `sourcetype`, `index`, `covered_window`, `scanned_window`) |
| `notables/behaviours.py` (`_localise_one`, `_localisation_entry`, `_localisation_of`) | per-source helper, receipt row, and the anchors mapping re-keyed by `source_id` (was `index`) |
| `tests/unit/test_hunt_notables_{sample,behaviours}.py` | three tests (one per acceptance property), +89/−2 lines net |

The summary probe (`accel_summaries`, 6 model probes per index) is taken **once per index** and
passed into every per-source `localise()`. Without that, the probes multiply by the source count
(santos: 6 → 72); this keeps the discovery cost exactly where it was while the operand becomes
per-source.

## 2. Decisions the slice text did not settle, and why

1. **`scanned_window` is the complement pieces (a list), not one interval.** The measured case the
   partial path exists for — santos `syslog`, `[1616425561 .. 1642487481]` against the
   Authentication window `[1616425563 .. 1642485679]` — is uncovered on **both** ends (2 s before,
   1,802 s after). One tuple could not state that honestly, so `scanned_window` holds the 0–2
   pieces outside the covered range, and each piece gets its own index-aggregate localise read.
   `covered_window` stays a single tuple (an intersection of two intervals always is one).
2. **A proper overlap is partial, not only a shared end.** Restricting partials to "shares one
   end" would have labelled the santos `syslog` case — the case §2.1 names — `scan`. The rule is
   now: containment ⇒ `accelerated`; any non-empty intersection smaller than the span ⇒
   `accelerated_partial`; otherwise `scan`.
3. **The read-layer split is declared, not issued.** E3's read plan takes its covered-sub-range
   peaks from the model's summary aggregate and its remainder peaks from the index aggregate, and
   records both ranges. E3 does **not** make `RowSet.coverage` carry `accelerated`: that is E0's
   change (`read_anchors` / `_merge_anchored`), and on this tree those two sites still hardcode
   `"scan"`. E3 supplies `Localisation.coverage`/`accel_window` both of which E0's wiring consumes.
4. **`localise_query` is unchanged** — it is still `by host _time` over the whole index. Per-source
   spans stop a source inheriting the union window and the other sources' peak *times*; the
   aggregate still returns every host's buckets in that span, so a source can still be anchored to
   a host it is not on (§2.3's second half). Fixing that is a query-scope change (sourcetype /
   source filter) with its own cost, outside this slice's stated change. **Reported, not fixed.**

## 3. Offline proof

### 3.1 Tests first, then green

The three acceptance tests failed on the pre-change tree with these signals (verbatim pytest):

```
FAILED test_hunt_notables_sample.py::test_a_partially_covered_source_declares_the_covered_and_scanned_ranges
  AssertionError: assert 'indexed' == 'accelerated_partial'
FAILED test_hunt_notables_behaviours.py::test_a_source_inside_one_models_window_localises_accelerated
  KeyError: 'source'                       # the receipt had one entry per index, not per source
FAILED test_hunt_notables_behaviours.py::test_a_sources_span_is_never_compared_to_the_index_union
  assert (1000.0, 2000.000001) in {(1000.0, 9000.000001)}   # the read was over the union
```

After the change, both files:

```
tests/unit/test_hunt_notables_sample.py ..............                   [ 33%]
tests/unit/test_hunt_notables_behaviours.py ............................ [100%]
============================== 42 passed in 0.81s ==============================
```

Gates (full output in the dispatch report): `uv run pytest tests/unit/ -q` → `3060 passed,
22 skipped`; `uv run ruff check .` → `All checks passed!`; `uv run ruff format --check .` →
`1737 files already formatted`; `python3 scripts/complexity_report.py --gate` → `GATE OK`.

One existing test was re-scoped to keep its meaning: `…a_range_outside_it_is_a_scan` used a source
span `[0 .. 7200]` against a window ending at 500 — head overlap, now legitimately
`accelerated_partial` — so its facts span moved to `[600 .. 7200]` (genuinely disjoint), where it
still asserts `indexed`/`scan`/`accel_window`.

### 3.2 What the stored estates say about the operand (lower bound, one model window)

`coding_task/scratch/e3/per_source_classify.py` (run as `PYTHONPATH=. uv run python …`) classifies
each stored wide source's **own** span against the only model window a run records (the
Authentication model's `accel_window`), and the old union operand against the same window:

```
santos: per_window 2500  wide cards 15/17  distinct sources 12
  stored receipt entries 1  block keys ['events', 'indexes', 'notes', 'windows']
  stored accel_window [1616425563.0, 1642485679.000001]
  union span [1616425561 .. 1642487481] -> ['accelerated_partial']
  per-source on that one window: {'accelerated': 14, 'accelerated_partial': 1}
    outside: hb_ait_santos_v2:syslog -> accelerated_partial
kyoushi: per_window 2500  wide cards 16/18  distinct sources 11
  union span [1616425561 .. 1616890440] -> ['accelerated_partial']
  per-source on that one window: {'accelerated': 9, 'accelerated_partial': 7}
    outside: hb_kyoushi_s1_v2:suricata x6 -> accelerated_partial, hb_kyoushi_s1_v2:syslog
russell: per_window 2500  wide cards 16/18  distinct sources 12
  union span [1616425561 .. 1643094188] -> ['accelerated_partial']
  per-source on that one window: {'accelerated': 15, 'accelerated_partial': 1}
    outside: hb_ait_russellmitchell_v2:syslog -> accelerated_partial
```

`stored receipt entries 1` is the stored (pre-E3) run's receipt: one entry, because the stored
run localised once per index. That is the defect E3 removes.

Read this as a **lower bound**: it only uses the Authentication window, which is the sole model
window the stored runs kept. Under the old union operand every source on all three families was
`scan` (the operand contained no model window); under the per-source operand 14/15, 9/16 and 15/16
wide cards are `accelerated` before any other model is considered — the same upper-bound shape
§2.1 reported, now realised by the code. The `union span` line shows the same window judged against
the old operand; with per-source spans it is no longer an operand at all.

Note on counts: the receipt is one entry per **scheduled source** (`_source_groups` groups cards by
`source_id`), so santos carries 12 entries, not 15 — four `suricata` cards share one `source_id`.
`wide cards` above is the card count; `distinct sources` is the receipt's count.

## 4. What the orchestrator runs (live proof)

After an E3 run on the tuned families (the run directory is the orchestrator's):

```bash
RUN=/Volumes/data01/portal5_hunt/hunt_proof_e3_santos/v3/santos   # ← the actual run dir
python3 - "$RUN" <<'PY'
import json, sys
from pathlib import Path

d = Path(sys.argv[1])
p = json.loads((d / "progress.json").read_text())
b = p["stages"]["behaviours"]
entries = b["localisation"]["indexes"]
print("localisation entries:", len(entries))
for e in entries:
    print(f'{str(e.get("source", "<one per index>")):45s} {e["mechanism"]:20s} '
          f'cov={e["coverage"]:20s} accel={e["accel_window"]} '
          f'covered={e.get("covered_window")} scanned={e.get("scanned_window")}')
print("accelerated:", sum(e["mechanism"] == "accelerated" for e in entries))
print("partial:", sum(e["mechanism"] == "accelerated_partial" for e in entries))
print("read coverages:", sorted({str(r.get("coverage")) for r in b["receipts"]}))

s = json.loads((d / "sources.json").read_text())
pw = b.get("per_window") or 0
wide = {c["source_id"] for c in s["cards"]
        if (c.get("facts") or {}).get("events", 0) > pw}
print("wide scheduled sources:", len(wide))
print("indexes block still keyed per index?",
      all(set(e) <= {"index", "width", "hosts", "windows", "events", "mechanism",
                     "model", "coverage", "accel_window", "notes"} for e in entries))
PY
```

**Shows E3 worked:** `localisation entries` equals `wide scheduled sources` and is > 1 (santos 12,
kyoushi 11, russell 12 on the R2 cards); `accelerated` > 0 on at least one family (expect ≥ 9 on
kyoushi, ≥ 14 santos by the lower bound above); at least one entry has
`mechanism: accelerated_partial` with a non-null `covered_window` and non-empty `scanned_window`
(santos `syslog`, kyoushi `suricata`/`syslog`); no entry's `accel_window` equals the union
`[min(first), max(last)+1e-6]` over `sources.json`; the last line prints `False`.

**Shows E3 did not land:** one entry per index (`localisation entries: 1`), every entry `indexed`,
or an entry whose `scanned_window` is empty while `covered_window` is set.

**Not E3's line:** `read coverages` containing `accelerated` is **E0's** acceptance line
(`read_anchors`/`_merge_anchored` still hardcode `"scan"` here). On an E3-only tree expect
`['scan']` (plus `'whole'` for complete sources); that is the E0 gap, not an E3 failure. If E0 has
landed on the merge branch, an `accelerated` or `accelerated_partial` value here is the joint proof.

Run against the **stored R2 santos run** (pre-E3 code) the same command prints the defect:

```
localisation entries: 1
<one per index>         indexed   cov=scan   accel=[1616425563.0, 1642485679.000001] covered=None scanned=None
accelerated: 0
partial: 0
read coverages: ['scan', 'whole']
wide scheduled sources: 12
indexes block still keyed per index? True
```

so the pass condition is: `entries == 12` (not 1), `accelerated` ≥ 14 cards on santos,
`partial` ≥ 1, and the last line `False`.

## 5. Cost and the budget (for E4)

Localisation reads move from ~1 accel localise + 1 index localise **per index** to ~1 accel
localise + 1 index localise **per wide source**, plus one index localise per uncovered remainder
piece on a partial. Model-window probes stay at 6 per index (decision note in §1). On the R2 cards
that is ~12–15 accel + 12–15 index localise reads per family instead of 1–2, all with
`LOCALISE_ROWS` caps; E4's request ceiling is the place that must budget it.
