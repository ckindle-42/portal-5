# DESIGN_BULLY_ANALYST_LOOP_V1

Design doc for `TASK_BULLY_ANALYST_LOOP_V1`. Inherits `TASK_BULLY_00_MASTER_V1`,
`TASK_BULLY_LOOP_REINTEGRATION_V1`, `TASK_BULLY_SCOREBOARD_CONFORMANCE_V1`.

## The flywheel as one picture

```
universal intake -> entity correlation -> series alignment -> pyramid grade
                                                                    |
                                                     SAME / SIMILAR / ANOMALOUS_UNCLASSIFIED
                                                                    |
                                                        analyst_loop.raise_concern
                                              (gated ONLY by compounding.should_escalate)
                                                                    |
                                                          notification (fire-and-forget)
                                                                    |
                                                            analyst reviews
                                                                    |
                              +----------------------+----------------------+
                              |                       |                      |
                         CONFIRMED                 BENIGN                 UNSURE
                              |                       |                      |
                    compounding.write_outcome_as_anchor (EVERY verdict writes)
                              |                       |                      |
                  ESCALATE, ANALYST_CONFIRMED   BENIGN_CLOSE,          ANOMALOUS_UNCLASSIFIED,
                                                ANALYST_CONFIRMED        weak / SYSTEM_GENERATED
                              |                       |                      |
                              +----------------------+----------------------+
                                                       |
                                        anchor library grows either way
                                                       |
                              next cycle: should_escalate() checks nearest match;
                              a BENIGN_CLOSE anchor suppresses that neighbourhood
                                                       |
                                    quieter (noise fell) AND sharper
                                    (confirmed side of corpus grew) --
                                              THAT is maturation
```

Everything above the notification line already existed (universal intake,
correlation, series alignment, the pyramid axis, the cousin grader).
Everything below the analyst box already existed too
(`compounding.write_outcome_as_anchor`, `compounding.should_escalate`,
`anchors.load_confirmed_finding`, the T0-T3 analyst corpus, BIN, handoff).
The hinge in the middle — a queue, a verdict capture, a write-back call —
was never built. `analyst_loop.py` is that hinge, not a new organ.

## Why this is not a gate

A gate decides what deserves attention before an analyst sees it. This
design has none: `NOTIFYING_CLASSES = {SAME, SIMILAR, ANOMALOUS_UNCLASSIFIED}`
fires on every one of them, unconditionally, every cycle. The *only* place a
concern can fail to reach an analyst is `compounding.should_escalate`
returning `False`, and that function's only "no" case is a relation whose
nearest match is a `BENIGN_CLOSE` anchor an analyst already closed. That is
knowledge earned by a prior verdict, not a threshold tuned by an operator.
No score, count, or confidence value anywhere in `analyst_loop.py` decides
whether to notify — the class alone decides whether it is eligible
(`concern_class`), and the corpus alone decides whether it is suppressed.

## The BIN-gate mismatch (why BIN stays downstream)

BIN's gate chain is built for a different question: *is this a provoked
detection claim strong enough to promote?*

- **G-1** requires an approved mutation scope. An observed unknown cousin was
  never mutated into existence; it was found. G-1 fails immediately.
- **G1a** requires a draft SPL/Sigma rule replayed against a capture. The
  rule is the thing an analyst writes *after* confirmation — it does not
  exist yet at notification time. G1a blocks.
- **G1b** requires the behaviour re-executed three times. You cannot
  re-execute an adversary on demand in an observed telemetry stream. G1b
  blocks.
- **G2** requires discriminators tested against a benign corpus, which
  presupposes the discriminator (again, post-confirmation) already exists.
  G2 blocks.

Routing the concern-notification path through BIN means `AWAITING_OPERATOR`
is never reached and `promotion._notify_queue_arrival` (promotion.py:555)
never fires — the alert silently dies in a gate chain built for a different
artifact. So `analyst_loop.py` reuses only the *dispatcher* BIN's
notification path reuses (`NotificationDispatcher`, the same channel set,
fire-and-forget, never fatal) and calls it directly from the observed lane.
BIN is entered later and separately, once a family has *matured* through
repeated confirmation into something with a rule to replay — untouched by
this task, and never on the concern-notification path.

## Three-way verdicts and T0-T3 tiering

`CONFIRMED` / `BENIGN` / `UNSURE` are deliberately not `promote`/`kill`: an
analyst who genuinely cannot tell yet must be able to say so without that
being coerced into a decision either direction.

| verdict     | outcome written              | `analyst_confirmed` | tier               | corpus effect |
|-------------|-------------------------------|----------------------|---------------------|----------------|
| `CONFIRMED` | `ESCALATE`                    | `True`                | `ANALYST_CONFIRMED` | scoreable, raises confidence |
| `BENIGN`    | `BENIGN_CLOSE`                 | `True`                | `ANALYST_CONFIRMED` | scoreable; feeds `should_escalate` suppression |
| `UNSURE`    | `ANOMALOUS_UNCLASSIFIED`       | `False`               | `SYSTEM_GENERATED`  | retained (T2-like), enters retrieval, cannot raise confidence (G.2) |

Every row writes. There is no verdict that is discarded — "nothing" is
still knowledge (`BENIGN_CLOSE`), and "not sure yet" is still knowledge
(weak, `SYSTEM_GENERATED`), matching `analyst_corpus`'s T0-T3 tiering where
T2/T3 participate in retrieval but a graded pair involving them is
unscoreable rather than thrown away.

## Maturation as the success measure

The acceptance measure is not precision/recall against a fixed answer key —
it is cycle-over-cycle behaviour on *identical* telemetry:
`analyst_loop.maturation_report` compares concerns raised in cycle N vs
cycle N+1 over the same capture. A system that learned raises **fewer**
concerns (benign neighbourhoods suppressed by earned `BENIGN_CLOSE`
knowledge) while **retaining** every confirmed one. That is the shape of
"quieter and sharper" (X5); a system that does not get quieter has not
learned, and the run reports that plainly rather than smoothing it over.

## Errata on the handoff criterion

Earlier task files (including passages in prior drafts of the master task)
described reaching `handoff.build_package` as an autonomous milestone the
loop could complete on its own. That criterion was unsatisfiable as stated:
`handoff.build_package` requires a `PROMOTED` candidate, and `PROMOTED`
requires an operator to drive BIN through to completion (`AWAITING_OPERATOR`
-> operator confirmation). No autonomous run — however many cycles, however
mature the corpus — can produce a `PROMOTED` candidate by itself, because
the state machine has no autonomous path into it by design (BIN's whole
point is that promotion is an operator decision, not a system one). Any
future task that wants an autonomous acceptance criterion touching handoff
must gate on something upstream of `PROMOTED` (e.g. `AWAITING_OPERATOR`
reached, or a scripted-operator confirmation explicitly labelled as such),
not on `handoff.build_package` running unattended.

## Standing principles

S/N/P/Q/R/V/W from prior tasks remain in force, joined by X1-X5 as stated in
`TASK_BULLY_ANALYST_LOOP_V1.md`.
