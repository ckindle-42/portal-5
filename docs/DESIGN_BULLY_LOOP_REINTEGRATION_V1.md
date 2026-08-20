# DESIGN_BULLY_LOOP_REINTEGRATION_V1

Design doc for `TASK_BULLY_LOOP_REINTEGRATION_V1`. Companion to
`DESIGN_BULLY_UNKNOWN_COUSIN_V1.md` and `DESIGN_BULLY_UNIVERSAL_INTAKE_V1.md`,
both of which carry a dated header (2026-08-20) pointing here. This is the sixth
pass in the arc and the first to connect the organ to the loop and run it.

## The one loop, with the evidence

There is one loop, and it has existed in this codebase since P1. The module
docstring calls it an "autonomous purple-team hunt loop"; `FINAL_ARCHITECTURE`
lays out every organ; `scoreboard.py` already declares the success function:

```
imperfect multi-source data (Crogl-style universal intake)
   -> behavioural signature
   -> grade against what is KNOWN (the cousin engine)
   -> the ones that are SIMILAR-but-not-known bubble up as
      ANOMALOUS_UNCLASSIFIED               <- THE PRODUCT
   -> investigation arm adds context / intent (malicious vs benign)
   -> analyst confirms
   -> handoff turns the confirmed cousin into a family-generalizing
      SIEM detection (Sigma/SPL), proven against replayed capture
   -> training flywheel folds it back in, so next time it is KNOWN
```

`scoreboard.py` (`_discovery_value`, `_is_catch`) states this outright and has
from the start: `ANOMALOUS_UNCLASSIFIED` is the concept's primary product and
always scores at least at the discovery floor; `SAME` (known-bad) scores ZERO
on the discovery axis. Bully is the loop; Crogl-style universal intake is the
source-agnostic reach that feeds it. They were never three separate efforts —
they are three positions on one loop.

## What went wrong across five passes (the organ-on-a-bench diagnosis)

Every pass — bake-off, RELATE, `cousin_relation`, `UNKNOWN_COUSIN`,
`UNIVERSAL_INTAKE` — rebuilt the grader-and-intake organ better
(`cousin_relation`, `artifact_graph`, `field_roles`, `unit_outcome`,
`baseline`, `blend`, `inject_plane`) and measured it in a standalone script the
orchestrator never calls. Proof, at HEAD `8de95f1a`:

```
$ grep -n "from .cousin_engine import" portal/modules/security/core/bully/orchestrator.py
40:from .cousin_engine import CoverageView, grade, retrieve_candidate_axes
$ grep -n "assessment = grade(signature, candidates, coverage)" .../orchestrator.py
683:    assessment = grade(signature, candidates, coverage)
```

The live loop still grades with `cousin_engine` (last touched 2026-08-16); the
entire reform (Aug 19-20: `field_roles`, `artifact_graph`, `unit_outcome`,
`baseline`, `blend`, `inject_plane`) is a parallel organ the orchestrator has
never imported. Every "honest run" measured a detached organ on a bench: no
scoreboard, no investigation arm, no handoff, no flywheel. The loop's own
product has never once been produced or measured in this workstream. That is
the milestone this task completes.

## The pyramid altitude correction

Diagnosed against MITRE's *Summiting the Pyramid* (extending Bianco's Pyramid
of Pain to detection engineering): every reform grader scored similarity on
payload strings — verb names, field values, sourcetypes — which are L1
(ephemeral values) / L2 (tool artifacts), the most evadable layer. Two
implementations of one technique share no payload tokens by definition, which
is why cross-vocabulary recovery kept needing rescue every pass. A cousin that
survives a change of tooling exists only at L3, the behavioural choke point
(the invariant action-class sequence: `auth -> enumerate -> escalate`). The
system had no axis to express this, so a sourcetype match and an
invariant-behaviour match scored on the same flat scale and were
indistinguishable. `pyramid.py` (R.1) supplies the axis; `loop_grader.py`
(R.2) makes the loop grader level-first: the relationship is decided by
*where* a match holds, not just how close it is.

## The reintegration seam

`loop_grader.grade_for_loop` produces a `CousinAssessment` in the loop's own
vocabulary (`RELATIONSHIPS`/`RESPONSES` from `contracts.py`), so
`orchestrator._analyzing` can call it in place of `cousin_engine.grade` with
no downstream change — the scoreboard, BIN gate, investigation arm, handoff,
and training flywheel all already exist and already consume a
`CousinAssessment`; only the producer changes (R.4). `cousin_engine` stays
in-tree for one release as a labelled, unreferenced rollback path; a follow-on
cleanup task deletes it once the R.6 run is accepted.

## Series over single events (R.3c) and the unit of analysis (R.3b)

Two further corrections compound with the pyramid axis. First: an
`attack_data` technique is not one record, it is an ordered series of logs,
and the observed thing is an entity's stitched timeline — also a series. So
cousinhood must be decided by ordered sequence alignment of two behavioural
spines (`series_cousin.py`), not point-to-point signature comparison; order is
signal, and an inserted or omitted step is a cousin, not a break. Second: the
unit the series is built from is the cross-source entity timeline, not the
single record or single source. Analysts stitch sparse per-source artifacts
into one narrative by entity identity (`jsmith` / `jsmith@corp.com` /
`CORP\jsmith` / `10.0.1.45`, one principal); `correlation.py` performs that
stitching so `INSUFFICIENT_VIEW` becomes a property of a unit *after*
correlation, never a per-source completeness gate at ingest.

## The live-loop run design (R.6)

`scripts/bully_loop_milestone_run.py` is a loop *caller*: it drives both
generator halves (R.5a real-tooling chains against the agent-controlled lab;
R.5b the procedurally-generated, schema-agnostic source universe), captures
the blended universal telemetry, and runs the actual orchestrated `run_hunt`
loop over the capture — intake, entity resolution, timeline assembly,
behavioural series construction, series-alignment cousin decision,
`loop_grader`, scoreboard, BIN gate, investigation arm, and handoff for
operator-confirmed cousins. It reports the loop's own scoreboard, not a
standalone intake metric. A genuine environment blocker is `BLOCKED` with its
reason; synthetic data is never presented as a live loop run (R4).

## The event generator, two complementary halves (R.5)

Authenticity and a measurable haystack are different jobs the prior task
conflated. R.5a extends the existing `inject_plane._LIVE_CHAINS` real-tooling
driver for authentic labelled chains. R.5b (`universe.py`) is the correction
to the previous generator's ceiling: it procedurally invents never-before-seen
source shapes (varying field naming, nesting, information level) rather than
enumerating a fixed set, and realizes implanted cousins by behavioural spine
only — sharing no schema, field names, or vocabulary with their parent — so
recovery is provably behavioural, not lexical.

## Standing principles carried

S1-S7, N1-N5, P1-P5, Q1-Q4 from prior tasks remain in force, joined by R1-R7 as
stated in `TASK_BULLY_LOOP_REINTEGRATION_V1.md`.
