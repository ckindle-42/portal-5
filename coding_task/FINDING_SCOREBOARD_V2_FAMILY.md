# FINDING — the scoreboard refused every `_v2` run on its family label

Lane `lane/scoreboard-v2-family`, branch base `653247fb5`. Code and offline tests only; the
orchestrator re-scores the stored run.

## 1. What was wrong

`_honesty()` compared the notables receipt's `excluded_family` (`santos`) against the family
label the scoreboard derives from the run directory or index (`santos_v2`) and raised
`the notables receipt excludes 'santos', not 'santos_v2': the run under test learned from its
own family`. The run had not leaked anything: `similar_to_known` recorded
`index_unseen: true`, `excluded_family: "santos"`, `loaded_families: ["kyoushi", "russell"]`.

Reproduced on the stored run by disabling only the new normalisation:

```bash
tmp=/private/var/folders/1r/140k52_x789f31ybwq9bt2300000gn/T/opencode/score-v2-family
mkdir -p "$tmp"
ln -sfn /Users/chris/projects/portal-5-hunt-proof-run/coding_task/scratch/hunt_proof_20261120T232700/v2/santos "$tmp/santos_v2"
uv run python -m portal.modules.security.core.hunt.notables.scoreboard --out "$tmp/santos_v2" \
  --keys santos_v2=/Volumes/data01/portal5_hunt/corpora/ait_lds_v21/santos_ingest/keys.jsonl
# scoreboard: the notables receipt excludes 'santos', not 'santos_v2': the run under test learned from its own family
```
(with `_corpus_family` monkeypatched to identity — the output above is the pre-fix comparison).

## 2. The fix

`_corpus_family(label, run_index, excluded)` maps a label that names a tuned `_v2` index back to
the corpus family, using the existing `scripts.lab.splunk_setup.plan.TUNED` registry
(`TUNED_BY_TARGET`, loaded lazily through `importlib` so `mypy portal/` does not start checking
`scripts/`). Names accepted for the corpus: the registry `key`, `source_index` and `target_index`,
each also with the `hb_` prefix removed, matched against the label with a trailing `_v2` removed.
The receipt's family is accepted only when the registry key starts with it (the store family is a
shortening of the corpus stem: `russell` for `russellmitchell`). Any other label, or any index the
registry does not own, is compared exactly as before — the guard stays strict.

`_honesty()` calls it before the comparison; `spine.py` and `stage2.py` reuse `_honesty`, so no
call site changed.

## 3. Proof on the stored run (offline, real receipt)

`santos` run at
`/Users/chris/projects/portal-5-hunt-proof-run/coding_task/scratch/hunt_proof_20261120T232700/v2/santos`:

| invocation | result |
|---|---|
| `--out .../v2/santos` (dir named `santos`, brief §4 command) | scores, `honesty … excluded santos`, exit 0 |
| `--out $tmp/santos_v2` (symlink to the same run, the failing label) | scores, `family santos_v2  index hb_ait_santos_v2`, `excluded santos`, exit 0 |
| the same symlink renamed `kyoushi_v2` | refuses, exit 2: `excludes 'santos', not 'kyoushi_v2'` |

`santos` line under the `_v2` label: `recall top50 16/21   top100 17/21   all 18/21`,
`C0 ceiling steps 11/21`, `judge AUC 0.952` (identical to the `santos`-named score — the label
never changed the measurement, only the honesty guard).

## 4. What is unproven

- Nothing was run against Splunk, a live engine or a held-out set: the scoreboard reads the stored
  receipt only. The orchestrator's re-score is the live proof.
- The registered `_v2` indexes were not probed this run.
