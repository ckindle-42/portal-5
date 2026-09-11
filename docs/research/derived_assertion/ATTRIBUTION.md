# Attribution — external corroborating reference

`DESIGN_DERIVED_ASSERTION_INVARIANT_V1` is primarily a generalization of an
internal Portal 5 pattern: the wiki spine's unit, source, claim, and gate
architecture.

One external project was read as corroboration:

- Project: ApodexAI/FrontierAgent
- URL: https://github.com/ApodexAI/FrontierAgent
- Commit: `9e533db6f6c34d16037ee5ec964c479d0eb51cde`
- License: Apache License 2.0
- Read: 2026-09-10 local time / 2026-09-11 UTC

## Scope of derivation

Architectural corroboration and a failure-mode catalogue. No source code has
been copied into or vendored into the Portal 5 tree. The reference was cloned
to a scratch directory outside the checkout, read end-to-end, and its requested
files were hash/line-count verified before use.

Derived: the concrete DAI-2 mechanism (system assigns the link, the producer
copies the adjacent tag, and the system re-renders the canonical references);
the score-as-derived-annotation artifact layout; and the external catalogue of
globbed locators, malformed markers, orphan footnotes, and deliverable loss.

## Known limitations of the reference

Its strictest evidence-admission tier is default-off and, per upstream's own
comment in `workflows/agent_team/fast_reporter_v1_evidence.py`, is not reached by
the evidence chain. Portal 5 must not represent that tier as proven.

## Not adopted

FrontierAgent's runtime, TUI, sandbox layout, Docker path, approval flow, and the
Apodex-1.1 model family.
