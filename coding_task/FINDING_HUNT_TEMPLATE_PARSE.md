# FINDING — Template parser & card sampling dropped the attack lines (`access_combined`)

Lane `lane/hunt-template-parse`, worktree `/Users/chris/projects/portal-5-hunt-template-parse`,
base `e5c478e59`. Brief `coding_task/BRIEF_HUNT_TEMPLATE_PARSE_FIX.md`.

Held-out sets (`hb_ait_wheeler`, `hb_cloudobs_aws`, `botsv1`) were never opened, queried or
read. No live Splunk query or mutation, no `launch.sh`, `.env` never read or sourced. Everything
below was measured offline against the **stored round-3 runs** under
`/Volumes/data01/portal5_hunt/hunt_proof_r3_{santos,russell,kyoushi}/v3/<family>` (read-only,
training families only).

## Root cause (two independent defects)

**1. Template induction hardcoded quoted payloads.** `words()` erased quote characters and split
every quoted phrase into whitespace words before template mining, so the tokens of a quoted
string (User-Agent, request, referrer) competed for literal slots. The santos card's stored model
is the receipt — two templates whose literals include the sampled UAs word by word:

```text
tokens: [null, "-", "-", null, null, null, "HTTP/1.1", null, null, null, "Mozilla/5.0",
         "(X11; Linux x86_64)", "AppleWebKit/537.36", "(KHTML, like Gecko)",
         "HeadlessChrome/95.0.4638.69", "Safari/537.36"]   (count 66; Firefox variant count 53)
```

A WPScan line (different UA, therefore a different token **count**) matched no template and
`parse_row` returned `fields = {}`; every such line went to misfits (santos receipt:
`events_out_of_structure 40,354 / 31.3%`; russell: `0` rows in hour 03 of `events`).

**2. The card sample collapsed onto the newest file.** `_sample_source` read the sample with a
pooled `| head 40` per window over the top-2 sources; arrival order means the newest file's rows
fill the head. Kyoushi's stored card: `sample.hosts = ['acme_mail', 'mail']` — all 120 lines from
horde webmail while the graded file `/apache2/intranet...log.4` (408,477 events, host
`intranet_server`, **rank 1 by events**) was in the route and still got zero sample lines.

## The fix

- `parse.py`: `words()` now keeps a quoted phrase **whole** (one token, quotes stripped); the
  miner (`_cells`/`_constant`/`_mine`) keeps a position literal only when every line in the
  bucket shares one **unquoted** value — a value that came from a quoted string is always a
  variable. Unquoted lines tokenize exactly as before.
- `sample.py`/`run.py`: the card sample (`read_card_sample`) draws up to 6 files (`SAMPLE_FILES`,
  20 lines each — same 120-line budget) chosen round-robin by lead host (`sample_files`), each
  read inside the source window holding that file's own last event; single-file or file-less
  sources keep the pooled read.

## Offline proof (real stored lines, read-only)

Replay: `uv run python coding_task/scratch/replay_proof.py` (scratch script; output below).
"BEFORE" parses each run's own stored template model (`sources.json` `template`); "AFTER"
re-induces from a real 120-line windowed sample (3 slices × 40 newest) of that run's own stored
real lines (ledger `values_extracted`), then parses every real target line.

```text
== santos: targets 9,732 (2,002 WPScan/python-requests) — BEFORE dropped 2002/2002 (fields {})
   AFTER: dropped 0/9732; WPScan "HEAD /...thumb.php HTTP/1.1" 404 line →
   {template: '* - - * * * * * *', v1: '172.21.128.119', v2: '[17/Jan/2022:11:22:35 +0000]',
    v3: 'HEAD /wp-content/themes/ElegantEstate/thumb.php HTTP/1.1', v4: '404', v5: '146'}
== russell: targets 3,356 (2,499 hour-03 python-requests) — BEFORE dropped 2499/2499 (fields {})
   AFTER: dropped 0/3356
== kyoushi: targets 6,431 (10 misfit python-requests lines) — BEFORE dropped 10/10 (fields {})
   AFTER: dropped 0/6431
```

Regression: the fixed induction re-parses each run's previously-keyed stored events
(`regression_check.py`): santos 19,999/20,000; russell 20,000/20,000; kyoushi 19,995/20,000.

Spread on the stored facts (property 2): kyoushi picks `horde-access.log,
other_vhosts_access.log.2, intranet...log.4, mail...log.2, other_vhosts_access.log.1,
intranet...log.1` → hosts `{acme_mail, cloud_share, intranet_server, webserver}` (stored sample:
`['acme_mail', 'mail']`); santos picks reach `intranet.smith.santos.com-access.log` (the graded
file) → hosts `{cloud_share, hayes_mail, intranet_server, webserver}`; russell likewise reaches
its graded `.log.2` and `.log.4` files.

Gates: `uv run pytest tests/unit/ -q` (3,085 passed, 22 skipped), `uv run ruff check .`,
`uv run ruff format --check .`, `python3 scripts/complexity_report.py --gate` — all green.
`uv run mypy portal/` reports 650 errors, **all pre-existing at HEAD** (verified identical in a
throwaway worktree at `e5c478e59`); zero are in the files this lane touched.

## Orchestrator live-proof command

```bash
uv run python -m portal.modules.security.core.hunt.notables \
  --index hb_ait_santos_v2 --out /Volumes/data01/portal5_hunt/hunt_fix_r4/santos \
  --stage all --family santos \
  --knowledge-store /Volumes/data01/portal5_hunt/knowledge/knowledge_v2_20261116.duckdb \
  --knowledge-families kyoushi,russell
```

Worked when: `sources.json` card `hb_ait_santos_v2:access_combined` has
`template.states.kept >= 1` with **no UA/request literal in any `tokens` list**, card
`sample.hosts` includes `intranet_server` (spread read), and the behaviours receipt's
`events_out_of_structure` share falls from 0.313 toward the card's misfit share (<0.05).
Then the scoreboard's `C0 ... labelled lines read verbatim` rises from 1,004 and
`wpscan`/`attacker_http`/`dirb` become reachable. Not fixed if: the card's template tokens still
carry `Mozilla/5.0`-style literals, `sample.hosts` still lacks the graded host, or
`events_out_of_structure` stays >100k on the same index. (Same command shape for
`hb_ait_russellmitchell_v2` / `hb_kyoushi_s1_v2`; expect russell hour-03 rows in `events`.)

## Residual (reported, not fixed)

A numeric token constant across the whole sample stays a literal by design (syslog `port 22`
identity is pinned by test). An all-200 quiet-hour sample would still drop novel-404 lines: an
unrepresentative all-200 replay sample dropped 2,463/2,499 russell targets. The windowed sample
the card stage draws is mixed-status in practice (the replay's 3×40 sample dropped 0). If the
live proof still shows status-identity drops, the next change is a narrow `_VAR_TOKEN` extension
— operator call.
