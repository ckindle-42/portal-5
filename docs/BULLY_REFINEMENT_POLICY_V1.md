# Defensive Bully refinement policy v1

TRAIN is periodic, operator-launched refinement subordinate to the knowledge
loop. It is never an inline hunt stage and readiness never auto-launches it.
HARV surfaces readiness only when the role corpus meets its size floor and has
at least one family or coverage cell absent from the last trained dataset.

The refinement targets are the three model-backed investigation seats:
`hunter → tool`, `analyst → reasoning`, and `disprover → expert`. An
operator-served alias is consumed by LOOP on the corresponding investigation
seat. `cousin_engine.grade()` is deterministic
(`_decompose → _weighted_composite → _classify_relationship`) and is therefore
not a training target. Its weights and thresholds are changed only through the
versioned cousin-calibration policy and a fresh frozen evaluation.

Candidate acceptance has three fail-closed evidence legs: intake floors,
candidate-vs-incumbent delta on the general security bench, and model canary.
Passing only places the candidate in the existing operator verdict queue;
`serve()` remains a separate authenticated confirmation.
