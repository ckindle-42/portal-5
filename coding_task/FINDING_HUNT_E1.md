# FINDING — hunt replan E1: the estate map carries a time range per file

Lane `lane/hunt-e1`, 2026-11-21. Implements slice E1 of `docs/hunt/ORCACYBER_DEEP_DIVE_3.md`
§6 (`### E1`). No hunt run and no Splunk query was issued by this lane: every number below is
either a replay of the changed code through a fake executor or a **read-only** read of the
stored Round-2 run artefacts on `/Volumes/data01/portal5_hunt/`. The live comparison is the
orchestrator's (§ "Live proof").

Scratch (gitignored): `coding_task/scratch/e1/` (a `git archive HEAD` copy of the pre-change
tree, used for the failing-first run).

## What changed

- `index_facts` reads the per-file map as
  `| tstats count min(_time) as first max(_time) as last where index=<i> by sourcetype source host`
  — the **same single query**, same row count, same `METADATA_ROWS` cap. The host map query is
  unchanged; `_meta_rows(..., span=True)` is the only difference between the two.
- `IndexFile` gains `first` / `last` (default `0.0`, appended after `hosts`, so the existing
  positional constructions `IndexFile(path, events, hosts)` still mean what they did).
- `_group_files` carries `(host, count, first, last)` per aggregate row (`_FileRow`);
  `_files_of` keeps the `total != events ⇒ no files` completeness test and takes a file's span
  as min/max across its host rows (`_rows_span`).
- `file_span(facts, item)` is the one read-time resolver: a file with `last > 0` uses its own
  range; a pre-E1 file (`0.0`) falls back to the source's span — i.e. today's behaviour. E2
  consumes this rather than re-deriving it.
- `cards._facts` serialises `first`/`last` into `sources.json:cards[].facts.files[]`;
  `run._fact_dict` reads them back.

Note on the brief's file list: `_fact_dict` lives in `notables/run.py`, not `sample.py`; that is
the one file outside the brief's list, and it is the function the brief names by signature.

## Offline proof

### 1. Failing first — HEAD's map carries no time

`git archive HEAD portal config tests/unit/test_hunt_notables_sample.py` into
`coding_task/scratch/e1/head`, then `index_facts` on the same fake executor at HEAD:

```
['| tstats count min(_time) as first max(_time) as last where index="ix" by sourcetype',
 '| tstats count where index="ix" by sourcetype source host',
 '| tstats count where index="ix" by sourcetype host',
 '| tstats count where index="ix" by sourcetype _time span=1d']
(IndexFile(path='/a.log', events=1, hosts=('h1',)),)
```

The new test module cannot even import against HEAD (`ImportError: cannot import name
'file_span'`), and the property it pins — `facts.files[].first/last` — has nothing to read.

Same replay on this lane's tree:

```
['| tstats count min(_time) as first max(_time) as last where index="ix" by sourcetype',
 '| tstats count min(_time) as first max(_time) as last where index="ix" by sourcetype source host',
 '| tstats count where index="ix" by sourcetype host',
 '| tstats count where index="ix" by sourcetype _time span=1d']
(IndexFile(path='/a.log', events=1, hosts=('h1',), first=100.0, last=900.0),) (100.0, 900.0)
```

### 2. Backward compatibility on the real stored runs

Every Round-2 run predates E1, so its `sources.json` file facts have no `first`/`last`. Loading
each through the real `card_from_dict` → `_fact_dict` → `file_span` path:

| family | sources | files | files without a range | span of the first file | its source's span |
|---|---:|---:|---:|---|---|
| santos | 17 | 89 | 89 | `(1642085133.0, 1642458113.0)` | `(1642085133.0, 1642458113.0)` |
| kyoushi | 18 | 80 | 80 | `(1616453872.0, 1616869019.0)` | `(1616453872.0, 1616869019.0)` |
| russell | 18 | 91 | 91 | `(1642686439.0, 1643061469.0)` | `(1642686439.0, 1643061469.0)` |

260 stored files, all read as `last == 0.0`, all resolving to their source's span — the stated
fallback, on real artefacts, not a fixture. The graded santos file is present in the flaggers
(the run's map has `{"path": "/apache2/intranet.smith.santos.com-access.log", "events": 9462,
"hosts": ["intranet_server"]}`, sourcetype `access_combined`).

### 3. Scoreboard / ledger interaction

`scoreboard._index_paths` selects ledger rows by the substring `"by sourcetype source"`, which
the new query still contains, and counts only cells starting with `/`; the two added epoch cells
do not enter that set, so `len(found) != rows` is unchanged and E6's defect/fix is untouched by
E1. `_ledger_has_value` is a substring test over `values_extracted` — also unaffected.

### 4. Tests — 3 added, net **+102** lines (`tests/unit/test_hunt_notables_sample.py`)

| test | property pinned |
|---|---|
| `test_estate_map_carries_each_files_own_time_range` | one source query with `min(_time)/max(_time)`; a file on two hosts spans `min(first)..max(last)` (1000–4000) and **differs** from its sourcetype's span (0–5000); `cards._facts` → `_fact_dict` round-trip preserves it |
| `test_a_file_without_a_time_range_falls_back_to_its_source_span` | `file_span` returns the source span for a `0.0` file and the file's own range when present |
| `test_the_estate_map_still_declares_no_files_when_the_counts_do_not_add_up` | `total != events ⇒ files == ()` and `files_incomplete:<sourcetype>` recorded |

### 5. Gates

```
uv run pytest tests/unit/ -q          -> 3060 passed, 22 skipped
uv run ruff check .                   -> All checks passed!
uv run ruff format --check .          -> 1737 files already formatted
python3 scripts/complexity_report.py --gate -> GATE OK (all totals within ceilings)
uv run mypy portal/                   -> 650 errors, all in scripts/ and tests/ reached
                                         transitively; 0 in the touched modules (pre-existing)
```

## Live proof (orchestrator)

**1. Rebuild one family's estate map.** The cards stage writes `sources.json`; reuse the stored
santos window (`start 0.0`, `end 1795279316.86…` from the R2 run's own `sources.json`):

```bash
uv run python -m portal.modules.security.core.hunt.notables \
  --index hb_ait_santos_v2 --out /Volumes/data01/portal5_hunt/e1proof/santos \
  --stage cards --start 0 --end 1795279317
```

**2. Read the graded file's range out of the new map.**

```bash
uv run python -c "
import json
d = json.load(open('/Volumes/data01/portal5_hunt/e1proof/santos/sources.json'))
for c in d['cards']:
    for f in (c['facts'].get('files') or []):
        if f['path'] == '/apache2/intranet.smith.santos.com-access.log':
            print(c['sourcetype'], f['path'], 'events', f['events'], 'first', f['first'], 'last', f['last'])
            print('sourcetype span', c['facts']['first'], c['facts']['last'])
"
```

**3. The live truth, one read-only `tstats` over the same window.**

```bash
uv run python -c "
from portal.modules.security.core.hunt.notables.run import default_search
q = '| tstats min(_time) as first max(_time) as last where index=hb_ait_santos_v2 ' \
    'by sourcetype source | where source=\"/apache2/intranet.smith.santos.com-access.log\"'
for row in default_search().iter_post(q, 0.0, 1795279317.0):
    print(dict(row))
"
```

**Pass:** step 2 prints a non-zero `first`/`last` for the graded file that matches step 3 within
one second, and that pair is **not** equal to the sourcetype span printed on the second line
(the D3 §6 E1 live-proof reading: the file's window is the 2022-01-17 burst, the sourcetype
starts 01-13 **[REPORTED]** in D3 §1.2, not re-measured here). Every file on every card carries
integer `first`/`last` keys.

**Fail:** any file fact without `first`/`last`, `first == 0` on a file with events, the pair
equal to the sourcetype span, or a second source query in `ledger.jsonl` (the map must stay one
query).
