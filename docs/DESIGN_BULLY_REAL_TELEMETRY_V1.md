# DESIGN_BULLY_REAL_TELEMETRY_V1

Design note for `TASK_BULLY_REAL_TELEMETRY_V1`, which makes the behaviour
classifier read the corpus C.6 connected the hunt to, and closes three guard
holes C.6's own numbers exposed.

## What C.6 established

C.6 (`TASK_BULLY_CORPUS_BED_V1`) connected the hunt to the real bed:
281,069,416 records across `botsv1` (33.4M), `botsv2` (226.3M), `botsv3`
(2.0M) and `portal5_lab` (19.3M), with Lane A present and real BOTS
sourcetypes (`wineventlog:security`, `xmlwineventlog:sysmon`,
`stream:dns/http/smb/ldap`, `suricata`, `pan:traffic`, `auditd`,
`osquery:results`). Entity resolution became real for the first time --
`entities_per_record 0.299` (D.4 read `1.11` on self-authored data) with
1,363 cross-source entities (22.8%), a number the synthetic universe was
structurally incapable of producing. `SCATTER` cousin recovery was 4/4,
recall 1.0 -- the flagship cross-source claim fully recovered on real data.

## What C.6 broke on: the all-`unknown` shape

Every cousin cluster's shared shape in C.6 was dominated by two labels:

    cc-0045: {'unknown': 4912, 'other': 1}
    cc-0046: {'unknown': 1339, 'other': 39}
    cc-0049: {'unknown': 83}

`unknown` and `other` are not behaviour classes -- they are what
`artifact_graph.DeterministicActionClassifier` (the classifier `build_graph`
actually ran in the C.6 hot path) returns when it has no recognisable verb:
`unknown` when no `action`-role field was inferred at all, `other` when one
was inferred but matched nothing in its substring table. Real BOTS records
carry neither a free verb field nor vocabulary the table's needles
(`"logon"`, `"exec"`, `"grant"`, ...) were written against -- a Windows
logon is EventCode `4624`, not the word "logon". So every real record
collapsed to the same two labels, every cluster's shared shape became
`{unknown, other}` in different proportions, and clustering on the ABSENCE
of classification made every cluster resemble every other cluster.

That cascade produced `discovery_rate 0.964`, degeneracy `0.915
ANOMALOUS_UNCLASSIFIED`, background false-positive rate `0.911`, and most
damningly **`floor_known_recall 0.0`**: zero of four answer-key techniques
recovered from a corpus that *publishes the answers*, while injected cousins
still scored 0.4 because cousin recovery is entity/remarkability-driven
(`row["entity_id"]` matched against the cousin's injected host,
`concern_raised`), not class-sequence-driven -- SCATTER's 4/4 stood
independent of this defect.

`pyramid.default_behavior_classifier` carries the identical structural flaw
(a hand-written substring table over verb text) but was not the classifier
actually exercised in the C.6 grading path; `behavior_classifier`'s learned
model was fitted on `universe.py` tokens that embed the class name in the
string, so on zero seen real trigrams naive Bayes reduces to
`argmax(prior)` and takes the majority class regardless of input. Neither
approach can read telemetry that carries no verb, which is what real
telemetry universally is.

## The correction: read behaviour the way telemetry encodes it

`bully.telemetry_behavior` maps an observable to a behaviour class
(auth, enumerate, execute, escalate, collect, destroy, persist, evade,
lateral, c2_exfil) **per sourcetype, from the fields that sourcetype
actually uses** -- a Windows security log's EventCode, a Sysmon EventCode,
an auditd record type, a stream sourcetype's protocol purpose. These are
vendor-documented, stable semantics, not guesses and not a model that has
to learn them from tokens that do not exist. An unmapped sourcetype returns
`""`, never `unknown` or a majority-class guess -- an unreadable source is
visibly unreadable.

`artifact_graph.build_graph`'s default classifier
(`TelemetryActionClassifier`) now prefers `telemetry_behavior.classify_record`
whenever a record's real sourcetype is recoverable (`__source_id` carrying
`lab-splunk:<sourcetype>`, set by `inject_plane.capture_records`), and falls
back to the legacy verb-substring table only for synthetic/verb-only input
that carries no sourcetype -- `universe.py`'s generated tokens still embed
the class name in the string and so still classify correctly through that
path. `series_cousin.series_from_logs` gained the same seam
(`sourcetype_of`) for the attack-episode loader; `discovery.py`'s shape path
needed no direct change, because a discovered cluster's `shared_shape` is
read straight from `Artifact.action_class`, which `build_graph` now derives
correctly.

`bots_answer_key.py`'s `behavioural_spine` fields moved from mnemonic
per-technique labels (`"kerberos_asrep_request"`, `"hash_extraction"`) to
the shared behaviour-class alphabet, because `_stub_anchor_record` writes
that spine verbatim into an anchor's `action_sequence`, and
`discovery.enrich()` compares a discovered cluster's class-level
`shared_shape` directly against it -- a mnemonic label can never match a
`shared_shape` built from classified telemetry regardless of how correct the
classifier is. This is what `floor_known_recall 0.0` was actually
measuring, on top of the classifier defect: T1558.004's
`("kerberos_asrep_request", "hash_extraction", "offline_crack")` becomes
`("auth", "auth", "escalate")` (both AS-REP steps are `wineventlog:security`
EventCode `4768`, resolving to `auth`); T1071.001's
`("http_beacon", "periodic_checkin")` becomes `("c2_exfil", "c2_exfil")`
(both are `stream:http` records).

## Three guard holes C.6 exposed in its own output

1. **`records_read: 0` with `is_haystack: true`.** `assess_bed`'s partial-read
   check was `if records_read and total and records_read < total * 0.5`; zero
   is falsy in Python, so the check never ran. A run that read nothing passed
   as a haystack.
2. **The scale floors never ran.** `MIN_SCORED_UNITS` and
   `MIN_FIT_TO_SCORE_RATIO` were specified in `TASK_BULLY_CORPUS_BED_V1` but
   never landed in `corpus_bed.py`, and `assess_bed` took no
   `units_fitted`/`units_scored` parameters at all. C.6 scored 200 units
   against what should have been a 10,000-unit floor, and `is_haystack`
   stayed `true` throughout.
3. **`floor_known_recall: 0.0` did not FAIL.** `bed_acceptance` failed on
   zero *cousin* recall (`zero_cousin_recall`) with no equivalent check for
   zero *floor* recall, so C.6's verdict came out `FAIL` only via the
   background false-positive rate. A system that cannot find a corpus's own
   published known-bads has a broken floor and must fail on that specifically
   -- floor gates the product (T5): a high product number is meaningless if
   the floor is zero.

`corpus_bed.assess_bed` now hard-fails `is_haystack=False` on
`records_read == 0` before the partial-read branch runs at all; takes
required keyword-only `units_fitted`/`units_scored` (so a caller that omits
them gets a `TypeError`, not a guard that silently never checks scale); and
enforces `MIN_SCORED_UNITS` / `MIN_FIT_TO_SCORE_RATIO`. `bed_acceptance` now
fails on `floor_known_recall == 0.0` with its own `zero_floor_recall` reason,
independent of the cousin-recall check.

## Errata: `docs/BULLY_CORPUS_BED_RUN_C6_V1.md`

The bed C.6 stood on was real -- the corpus binding, real cross-source
entity resolution (`entities_per_record 0.299`, 1,363 cross-source
entities), and SCATTER cousin recall (4/4, 1.0) all stand as reported. But
the classifier could not read that real data: `floor_known_recall: 0.0`
means every shape-based figure in that run (`discovery_rate`, the
degeneracy verdict, every cousin cluster's `shared_shape`) describes
*unclassified* records, not a genuine absence of structure. And that run's
`is_haystack: true` was produced by a guard that short-circuited on
`records_read: 0` -- a hole this task closes permanently with a regression
test pinned to C.6's exact numbers.

## What T.3/T.4 measure

T.3 re-runs at roughly C.6's scale with only the classifier changed, as a
cheap diagnostic: does `floor_known_recall` recover, and does any cluster
still carry an all-unclassified shared shape? It is explicitly *not* an
accepted result -- at C.6's scale it will correctly report
`scored_sample_too_small` against the T.2 scale floors. T.4 is the long run,
gated on T.3 showing a non-zero floor: full corpus stream, `MIN_SCORED_UNITS`
or more scored, no wall-clock cap, floor/product/cost published as three
separate numbers with throughput.

## Residual risks (carried from the task doc)

- **The sourcetype mappings are curated, and curation is a form of
  prescription.** They map observables to a ten-class behavioural alphabet
  using vendor-documented semantics -- never to specific ATT&CK techniques --
  so discovery stays data-intrinsic and naming stays enrichment. An unmapped
  sourcetype is invisible to shape-based discovery; `unmapped_sourcetypes` is
  published every run precisely so it can drive what gets mapped next.
  Coverage will never be complete and must not be claimed as such.
- **Class assignment is a judgement per sourcetype.** `stream:http ->
  c2_exfil` is right for beaconing and wrong for ordinary browsing;
  `Perfmon` is deliberately unmapped rather than forced. These are
  re-baseline decisions, recorded, and the false-positive rate will move
  when they change.
- **BOTS answer keys are human artifacts and not exhaustive** -- a "false
  positive" against them may be a genuine finding, so background FP on BOTS
  is an upper bound on error, not a count of mistakes.
- **A non-zero floor does not prove discovery.** Lanes A/B are pre-labelled;
  only Lane C generates genuine novelty, and the discovery claim still needs
  it.
- **T.3 is deliberately below the scale floors** and will report
  `scored_sample_too_small`. That is correct: it is a diagnostic, and its
  numbers must never be quoted as an accepted result.
