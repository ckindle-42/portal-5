# SPINE_THIN_CONTRACT_V1 — the post-P0 wiki/spine obligation

`TASK_BULLY_P0_SPINE_REDUCTION_V1.md` A7. This is a KEEP-FACT/human-owned
doc, not a fenced `WIKI:GENERATED` obligation — hand-authored and edited
directly, same as `CLAUDE.md`. `TASK_BULLY_P1_SPINE_V1.md` through
`TASK_BULLY_P7_CUTOVER_PROOF_V1.md` target the rules below; none of them may
re-introduce the machinery P0 removed.

## What a new package owes the spine, post-P0

1. **One surface glob** in `config/spine_surfaces.yaml` (BR, `scripts/validation/wiki.py::check_spine_code_coverage`).
   Every `.py` file under the declared glob is covered for free — no
   per-file unit, no per-file citation.
2. **At most a couple of live-probe claim-units**, and only if the package
   exposes a volatile count actually worth guarding (a table tally, a
   registered-server count, a threshold). A claim binds one number in one
   unit's body to one probe (`portal.platform.wiki.claims.PROBES`) — see
   `unit-fact-persona-roster` for the pattern.

That is the entire obligation. No unit per phase, no unit per file outside
the wiki engine itself (`portal/platform/wiki/` stays per-file as the
extraction-guarantee boundary — check AJ), no `last_generated_commit` pin,
no re-stamp on ordinary edits, no two-commit dance.

## What P0 deleted (A1) — do not re-introduce

- The `last_generated_commit` field on `KnowledgeUnit` (`schema.py`).
- `drift.py`'s `PinHealth`/`pin_health` axis (phantom/stale/unpinned).
- `scripts/validation/wiki.py::check_spine_drift`'s (BS) pins sub-checks.
- `scripts/repin_stale.py` and the `chore(spine): re-pin units stale after
  <change>` commit pattern it produced.

A fact change — editing a `unit-fact-*` body, or running `sync-config` to
re-derive one from live config — is **one commit**. There is no pin to
re-stamp in a second commit.

## What P0 kept (A2/A3) — the anti-drift core

- **`claims`** (`portal/platform/wiki/claims.py`): a unit declares, in
  frontmatter, that a live quantity in its body must match a named probe's
  live result. `scripts/validation/wiki.py::check_spine_drift` (BS)
  HARD-FAILs — never baselined — when a claim's declared text disagrees
  with the probe. This is what catches "unit says 138, code says 130."
- **Doc path references** (`drift.py::broken_path_refs`): a repo-relative
  path named in a Tier-1 doc must exist (or be `git check-ignore`d). Also
  part of BS, also HARD-FAIL.
- **BR surface coverage** (`coverage.py` + `check_spine_code_coverage`):
  every declared surface has a covering, gate-passing unit; every eligible
  `.py` file falls under some declared surface.

## What P0 changed (A4) — AW scope

`scripts/validation/wiki.py::check_wiki_facts_current` (AW) now governs only
the **KEEP-FACT set** (`claims.fact_unit_ids()`: units carrying executable
`claims`, plus `unit-fact-*` live-config-derived units) — not every unit
that happens to feed a Tier-1 `WIKI:GENERATED` block. Editing ordinary prose
in a Tier-1 doc (the 555 blocks P0.3 collapsed back to plain text across 25
docs) triggers **no** `sync-config` obligation and **no** AW failure. A
KEEP-FACT block going stale — the doc block copy diverging from its unit's
current body — still fails AW exactly as before.

## What P0 shrank (A5) — corpus reduction, and where it stopped

P0.1's manifest classified all 719 canonical units at P0's start:

- **KEEP-FACT (14)**: kept, fenced, AW-governed.
- **RELEASE (552)**: prose feeding a generated block with no claim and no
  volatile fact. P0.3 un-fenced every one back to plain prose in its Tier-1
  doc(s) — this is the reduction that actually landed: the AW/fence tax on
  this prose is gone, unconditionally, in P0.3.
- **ARCHIVE (153)**: prose-only, referenced by no live generated block.

P0.4 ran the real archive bridge rule (`portal.platform.wiki.archive`,
no override, no `--superseded-by`) against the ARCHIVE bucket plus the
now-orphaned RELEASE bucket (705 candidates total; P0.3's un-fencing left
the manifest's own classifier re-scoring most of RELEASE into ARCHIVE, since
"referenced by a live generated block" is no longer true for almost any of
them). **Result: 0 archived, 705 blocked** — see
`docs/SPINE_P0_ARCHIVE_RUN.md` for the full tally and reasons. The dominant
refusal (1660 instances across 705 units) is `check_archivable`'s rule 3,
"cites a live code/config source" — this corpus's RELEASE/ARCHIVE prose is
overwhelmingly grounded in real files (`config/backends.yaml`,
`config/portal.yaml`, deploy manifests, module source), just not in a way
that makes it a *volatile fact* worth a `claims` entry. That is the bridge
rule working as designed, not a P0 shortfall: archiving prose whose
assertions a live file still determines would strand real grounding, and P0
does not weaken `check_archivable` to force a bigger number.

**Consequence for the exit criteria**: `portal_wiki/canonical/` still holds
719 files after P0 — the file-count shrink A5 anticipated does not land for
this corpus without further, non-mechanical work (a `--superseded-by`
editorial pass per unit, or an operator-approved change to what counts as
archivable). What *does* land, unconditionally, is A4's tax removal (P0.3) —
the load-bearing exit criterion ("editing ordinary prose triggers no
`sync-config` / AW obligation") — which does not depend on file count. This
gap between "the fence tax is gone" and "the corpus is smaller" is flagged
here for operator review rather than closed by weakening a safety check.

Archiving (for whatever P0.4 does move, and for any future
`--superseded-by` pass) is a move to `portal_wiki/archive/`, never a delete
— full history retained, reachability from the live store enforced by BT
(`check_archive_reachability`).

## Wiki MCP (:8931)

Assessed and **kept** (`docs/SPINE_P0_WIKI_MCP_RETENTION.md`, A6): the one
live consumer is the Claude Code agent discovery workflow this build itself
runs under (`CLAUDE.md` Rule 13 / `TASK_BULLY_00_MASTER_V1.md` §13), not any
Portal 5 runtime code path. No config change follows.

## Validator catalogue, post-P0

The wiki/spine family in `scripts/validation/wiki.py` is five checks:

| Check | Letter | What it proves |
|---|---|---|
| `wiki_core` | AJ | schema + provenance + import-clean + MCP tools importable |
| `wiki_facts_current` | AW | KEEP-FACT units current vs live config; their generated blocks match; migrated docs carry no un-fenced substance |
| `spine_code_coverage` | BR | every declared surface covered; every eligible file under a declared surface; manifest fresh |
| `spine_drift` | BS | claims hold (HARD-FAIL); no dead Tier-1 doc path refs (HARD-FAIL) |
| `archive_reachability` | BT | no live unit or doc block reaches an archived id |

The pins/phantom sub-checks that used to sit inside BS are gone from this
catalogue — not disabled, not baselined, removed. `scripts/validate_system.py`
holds this same five-check set for the wiki family (see its docstring/check
list for the authoritative registration order).

## Rollback

Every P0 step is a plain `git revert` — a reduction with no external state.
Archived units are retained on disk, so restoring one is a move back, not a
re-derivation.
