# DESIGN_BULLY_UNIVERSAL_INTAKE_V1

Full-scope design doc for `TASK_BULLY_UNIVERSAL_INTAKE_AND_INJECT_V1`. Companion to
`DESIGN_BULLY_UNKNOWN_COUSIN_V1.md` and `BULLY_UNKNOWN_COUSIN_RUN_M3_V1.md`, the
latter now carrying a dated errata header pointing here (X.2). This is the fourth
pass in the arc; it is reference documentation for the fix, not a summary of it --
read the modules themselves for the mechanism.

## The arc, and the pattern that repeats

Four passes, each fixing the layer it could see while the layer beneath stayed
wrong:

- **embedding bake-off** assumed a valid corpus; the corpus was contaminated.
- **RELATE (A-M)** assumed valid grading; grading was gated on schema-presence mass.
- **COUSIN_RELATION (C.1-C.8)** assumed the right unit; the unit was a flattened bag.
- **UNKNOWN_COUSIN (D-M/X)** assumed valid intake; intake was CloudTrail-shaped and
  silently returned nothing on every other schema.

M.3's `unknown_cousin_recall 0.973` looked healthy while the capability underneath
did not function on 4 of 5 real sources. Forensic proof, from the run's own JSON:
every published `UNKNOWN_SAME`/`COUSIN` brief shares exactly one shape feature --
`class_present=other` -- and resembles an anchor only because both sides degraded to
all-`other`. An extraction failure at the bottom of the stack became a shared
feature; a shared feature became a confident concern; nothing reported that the
adapter had failed. That is faked-green at the lowest level, and this task exists to
break it.

## RC1 -- intake was a schema normalization pretending not to be

`artifact_graph._ENTITY_FIELDS`/`_TIME_FIELDS`/`_ACTION_FIELDS` were hardcoded
CloudTrail field names. attack_data is Sysmon/osquery: identity lives in
`hostIdentifier`, time in `calendarTime`, and `action` holds `added`/`removed` -- a
diff-type, not a behaviour. Entities went empty, timestamps went unparsed, action
went to `other`, on every non-CloudTrail record. The old docstring's claim that
edges derive from relations "that exist regardless of a source's schema" was false
as written: a field-name list *is* a schema normalization, and universality can
never come from a longer list -- there is always another schema not on it.

**The fix (`field_roles.py`, E.1-E.2).** Infer what a field *is* from how its
values behave, not from what it is called:

- `ENTITY` -- moderate-cardinality, recurring, string-ish, and structurally
  identifier-shaped (an IP, GUID, ARN/email/principal, a path, or a name+digit-run
  token). This structural test is what separates ENTITY from ACTION without a name
  list: a host or user *looks like* an identifier; a verb does not.
- `TIMESTAMP` -- values parse as time (epoch or a wide format list) and roughly
  advance across the sample.
- `ACTION` -- low-cardinality categorical, not identifier-shaped: the verb,
  operation, or event-type field, whatever it is called.
- `PAYLOAD` -- high-cardinality free text, hashes, blobs, or a near-unique
  identifier (a request id, a per-event GUID) that is a record's own name, not a
  thing you pivot on.
- `CONSTANT` -- ~one value across the sample: structurally uninformative alone.

Role is decided by strongest evidence across all predicates at once, not by an
ordered elif cascade -- that ordering bug is exactly how `hostIdentifier` (low
cardinality, entity-shaped) used to land as ACTION when the low-cardinality branch
came first. Three probing-found bugs are fixed in the shipped module: ctime-style
timestamps were unparsed (`_TIME_FORMATS` widened), record ids were mis-tagged as
ENTITY (near-unique identifiers now demote to PAYLOAD via
`_ENTITY_MAX_DISTINCT_RATIO`), and the elif cascade let low-cardinality host ids
land as ACTION (replaced with per-role scoring in `_decide_role`).

`build_graph` (E.2) now consumes a `FieldRoleMap` instead of the name lists; the
name lists survive only as a last-resort hint *inside* inference, never as the
primary path. When a source's role map says `extraction_valid=False` --
insufficient entity or timestamp coverage across the sample -- `build_graph`
attaches a source-level `INSUFFICIENT_VIEW` marker and emits no gradeable units.
That is Q1: an extraction failure is a loud instrument finding, never a silent
collapse into an all-`other` shape that later reads as a shared feature.

## RC2 -- one schema in the whole corpus, so nothing ever caught RC1

Every dataset in the M.3 eval was attack_data. The system silently reduced to a
single schema and reported nothing wrong because no second schema was ever present
to disagree with it. A universality claim requires a plural corpus by construction
(Q2) -- it is not provable on a corpus that happens to be uniform.

**The fix.** Two planes, deliberately kept separate:

- `blend.py` (E.3) -- a deterministic, offline fixture composing records from
  CloudTrail, Sysmon, osquery, and a firewall/syslog line into one time-ordered,
  provenance-tagged stream. No live dependency, so E.1/E.2 and every grader test can
  exercise true plurality in CI, always, regardless of lab availability.
- `inject_plane.py` + `scripts/bully_inject_capture.py` (E.5) -- the live plane.
  Drives real activity in the lab (benign baseline plus labelled attack chains from
  already-wired authorized tooling), interleaves it sparsely into a much larger
  benign stream across every wired schema, and reads it back through the existing
  `SplunkQueryInPlaceConnector` (no new write path to the grader's side). This is
  permanent infrastructure: every future bully run, every future universality claim,
  and the eventual training corpus draw from it. It is built once, reused forever --
  not a throwaway fixture for this task alone.

Both planes produce the same record shape, so downstream code (field-role
inference, artifact graph, grading) is identical regardless of which one fed it.
The live plane fails closed: if the lab is unreachable or a secret is missing, the
script exits non-zero with a clear reason, the run falls back to the E.3 fixture,
and the run states plainly which plane produced its numbers. No synthetic
stand-in is ever silently substituted for a live capture.

## RC3 -- the baseline had a content-independent remarkability floor

`baseline._feature_tokens` emitted `level={unit.level}` plus size/span/edge buckets
that L1/L2 units structurally cannot produce (a single artifact has no multi-edge
mix, a bare pair has a narrow span range). M.3 fit on L1/L2 units and scored L4
units, so every scored unit carried never-seen tokens and scored ~0.95 remarkable
regardless of content -- median 0.9953 against a 0.6 threshold. Proven with the
repo's own code: fit 100 copies of a unit and score that identical unit -- the only
configuration that should return ~0.0 returned ~0.7 under the old tokens.

This also means the M.3 conclusion that invictus's benign control failing (1.0) was
because the environment is compromised was **wrong** -- perfectly clean data failed
identically. Chasing a "pristine corpus" next would have fixed nothing.

**The fix (E.4).** Drop the `level=` token. Require fit and score to occur at the
same unit level -- assert it; a level mismatch is a caught error, not a silent
floor. Remarkability now measures content, not a fit/score level gap: fitting N
copies of a unit and scoring that identical unit returns ~0.0.

## RC4 -- the M.1 ladder validated the wrong variable

`rho 0.9999` was reported on `combined_distance`, but the decision (`NOVEL` vs
match) uses `shape_distance`, which is non-monotone across the M.3 rungs (0.0, 0.0,
0.571, 0.0, 1.0) -- the reported number said nothing about the variable that
decides. Worse, the cross-vocabulary rung was built from the class names
themselves (`Authenticate`/`Enumerate`/`Invoke`), which only proves the table
already maps those verbs together -- it never exercises the hard case
(`Add-LocalGroupMember -> escalate`) the rung exists to test.

**The fix (U.3').** Build the cross-vocabulary rung from real verbs of a genuinely
different schema captured by E.5 (the Windows/Sysmon expression of a chain whose
anchor is CloudTrail), literally disjoint from the anchor's tokens. Validate
monotonicity on `shape_distance`, the deciding variable, not `combined_distance`.
The rung's recovery rate becomes the honest number sizing the deferred learned
action classifier -- see Scope below.

## RC5 -- INSUFFICIENT_VIEW conflation, fourth occurrence

Five of ten published M.3 briefs carried
`what_could_not_be_seen: ["shape", "vocabulary"]` -- neither channel observable --
and raised a concern anyway, instead of reporting instrument failure. A relation
where both channels are unobservable carries no information; grading it into
`UNKNOWN_SAME`/`COUSIN` manufactures a concern out of blindness.

**The fix (M.4).** When the best-matching relation has both `shape.unobservable`
and `vocabulary.unobservable` true, `resolve_unit_outcome` routes to
`INSUFFICIENT_VIEW`, never a concern outcome, regardless of what the raw distance
math would otherwise decide.

## RC6 -- headline metrics counted silences out of the denominator, novelty into the cousin number

532 of 643 M.3 eval datasets produced no unit at all and were simply absent from
the recall denominator. Separately, `unknown_cousin_recall` was 75% `NOVEL`
outcomes, which never consult the anchor library -- so the headline recall number
was dominated by a metric that does not test matching at all.

**The fix (M.4).** `cousin_recall` (`UNKNOWN_SAME` + `COUSIN`, library-dependent) is
reported separately from `novelty_recall` (`NOVEL`, library-independent). The
cousin-subset shuffle control is computed over the cousin subset only -- shuffling
the library and re-measuring `NOVEL`-dominated recall proves nothing about whether
the library's content matters. Absolute recall (over every dataset carrying known
activity) is published beside conditional recall (unit-forming datasets only), so a
silence -- extraction produced no unit at all -- is visible instead of quietly
excluded.

## Standing principles this task adds (Q1-Q4)

- **Q1** -- intake extracts honestly or declares itself blind. No extraction
  failure may become a gradeable feature; an unextractable source is a
  source-level `INSUFFICIENT_VIEW`, reported loudly, refused for scoring.
- **Q2** -- universality is proven on plural data or it is not proven. Any
  universality claim cites a run over >=3 genuinely different schemas.
- **Q3** -- generated ground truth is sealed on the grading plane only. E.5 reuses
  `specimen_ledger.SpecimenLedger` (the same hash-chained, append-only wall
  `cousin_calibration_bench.py` already uses for blind-grade-then-join truth) --
  `source_lane="live_lab"` for the live plane, `"replay_mutation"` for the E.3
  fixture. No second sealing mechanism is built. The grader is handed captured
  records only; the ledger is joined after grading, never before.
- **Q4** -- injected activity is labelled at the artifact level (family, technique,
  chain_id, step_idx), in the ledger's `provenance` field, so recovery is
  measurable per artifact, per unit, and per family -- not just "did the window
  alarm."

## Scope calls, deliberate

- **The learned action classifier stays a follow-on.** `ActionClassifier` (in
  `artifact_graph.py`) is already a protocol seam; this task ships the
  deterministic default behind it plus the honest cross-vocabulary ladder rung
  (U.3') that finally *sizes* the learned work. Swapping a learned instrument in
  now, under a grader whose intake this task is still proving, repeats the exact
  mistake of the prior three passes: building on an unverified foundation.
- **The inject/capture plane is permanent infrastructure**, not a throwaway test
  fixture for this task. It is built once, in `inject_plane.py` plus
  `scripts/bully_inject_capture.py`, and every later universality claim, bully run,
  and the eventual training corpus draw from it rather than re-deriving generation
  logic per task.

## Residual risks, carried openly

- Role inference is heuristic and will misfile some fields (a path as an entity, a
  rare categorical as payload). It is honest and measurable where a name list was
  neither -- every run publishes per-source role maps so misfiling is visible.
  Name-hints remain a last-resort fallback inside inference.
- The verb->class seam stays deterministic and unlearned. U.3''s cross-vocabulary
  recovery rate is its sizing; until a learned classifier lands, cross-vocabulary
  matching under-recovers, and that number is published, not explained away.
- Generator coverage bounds what the plane can prove -- it exercises the families
  the lab's authorized tooling can produce; families it cannot generate are stated
  out of scope for a given run, never assumed covered.
- The baseline can still be poisoned by activity present throughout the fit window;
  E.5 fits benign-only windows by construction (`injected=False`), and that
  assumption is reported every run.
- Structural grouping still misses combinations the graph does not connect (an
  attack spread across entities with no shared key or causal link). The
  unconnected-artifact rate, now split from extraction failure, is the honest bound
  and is reported every run.
- Thresholds remain judgement, recorded on every relation; a change is a
  re-baseline, not a silent tune.
