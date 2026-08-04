---
id: unit-design-spine-drift-census
kind: mixed
title: "Spine drift census \u2014 binding doc prose to live code"
sources:
- type: code
  path: portal/platform/wiki/claims.py
- type: code
  path: portal/platform/wiki/drift.py
- type: code
  path: tests/unit/test_spine_drift.py
last_generated_commit: 2bb0179ddd35a16c593a3e50a612847b2c172972
claims:
- probe: validate.checks
  pattern: '{value} validate checks'
confidence: high
tags:
- drift
- spine
- verified-v1
- wiki
created_at: 1785825842.272556
updated_at: 1785859017.192845
---

Three gates guarded the spine and none of them objected while README asserted 60
benchmark workspaces against a live 65 and 22 MCP servers against a live 21:
 `AW` passes by comparing a generated block with its own unit body, `BR` passes by
proving a new code surface is cited by *some* unit without asking whether the
citation is true, and the retired `AK` ledger check bound zero docs —
honestly, but leaving no doc-currency signal in the harness at all.
Of 567 generated blocks across 25 Tier-1 docs, 7 came from a machine-derived
`unit-fact-*` unit; the remaining 560 were authored prose with no executable link
to code. Check `BS` closes that gap, bringing the harness to 74 validate checks
(`BT` later asserting archived units stay unreachable from the live store; the
doc-ledger `AK` check was removed once the ledger was emptied in
TASK_WIKI_ZERO_DEBT_V1).

A **claim** binds a figure in a unit body to a live probe. The claim names the
probe and a `pattern` containing `{value}`; the probe result is substituted and
the result must appear in the body. There is deliberately no second copy of the
number — an earlier draft allowed `equals: 65`, which compared the probe with
itself and passed while the body still read 60. `equals` and `contains` survive
only for structural invariants the prose describes qualitatively, such as the
backend type set becoming `[ollama, omlx]` when the oMLX backend landed.

Claims are opt-in. Prose explaining *why* a design is shaped a certain way has
nothing to assert, and demanding an assertion from it would produce exactly the
mass-stubbing this project refused when it declined to force 100% code-surface
coverage. Units whose body states a countable quantity without declaring a claim
are reported as visible debt instead, so the next units to instrument are always
known without a fuzzy signal being promoted to a failure.

The census carries two further axes. **Pin health** classifies every unit that
cites a repo-local path: 461 units shipped pinned to `05e42ec2`, a SHA absent
from all 1904 commits, so `last_generated_commit` was decoration rather than a
stale anchor — that is reported as `phantom`, distinct from units whose pin
resolves but whose cited sources have moved since. **Doc path references**
reports repo-relative paths named in Tier-1 docs that do not exist and are not
gitignored — `portal/<workspace-or-persona>` is suppressed as an OpenAI-style
served model id by checking the live roster (so retired ids such as
`portal/auto-agentic-ornith` are still reported while live ones are not), and a
path git itself reports as intentionally untracked (`git check-ignore`, e.g. a
scratch task file under `coding_task/` or a harness-written directory like
`results/candidates/`) is not a broken reference — it was never going to exist
in any checkout, so its absence is not drift.

`TASK_WIKI_ZERO_DEBT_V1` deleted `config/spine_drift_baseline.yaml`: claims,
pins, and doc refs are all absolute now, with nothing left to ratchet or
tolerate. The census is re-runnable outside CI as `python3 -m portal_wiki
drift`, which exits non-zero on any claim violation or any drift at all.

## Why

The census exists because the three prior gates certified a doc's block
against its own unit body or proved a code surface had *some* citation —
never that the cited prose was true — which is how README carried a wrong
workspace count with every gate green. The mechanism is grounded in the
code it describes: `claims.py` defines the probes and the `{value}`
pattern contract, `drift.py` classifies pin health and broken doc path
references (delegating "is this path allowed to be missing" to `git
check-ignore` rather than a hand-maintained allowlist, so a renamed or
newly-ignored path never needs a second update to stay accurate), and
`tests/unit/test_spine_drift.py` locks the behavior. The declared claim on
`validate.checks` keeps the unit's own count honest, and the
`phantom`/`stale`/`unpinned` vocabulary is re-derivable by re-running the
census rather than trusting this prose.
