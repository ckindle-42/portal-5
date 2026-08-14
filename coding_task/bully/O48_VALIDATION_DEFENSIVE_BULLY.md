# VALIDATION_DEFENSIVE_BULLY

How each capability is *proven*, not asserted. Every entry: **CLAIM · TEST
METHOD · INPUT · EXPECTED · EVIDENCE · FAILURE MEANING.** The bar is **semantic
success** — the behavior demonstrably works — never "the symbol exists" or "the
function returns." Synthetic results are never PROVEN. Where a Portal validation
check already covers a property, it is named (`@register(...)` in `scripts/
validation/*.py`); new checks are marked **[NEW CHECK]**.

Global proof rules:
- A capability that cannot be proven on real (non-synthetic) data is BLOCKED, not
  marked done.
- Determinism is proven by re-running with identical inputs and getting an
  identical decision.
- "Compounding" claims require a *second* run observably different because of the
  first — storage alone is not proof.
- Gates that hold green throughout: AW, BR, AZ, BL, BM, BN, BQ.

---

## Component-level

**C1. Episode miss-primitive.**
- CLAIM: `derive_verdict` returns FAILED exactly when red landed and detection
  missed, and never PROVEN on synthetic. TEST: feed (a) landed+detected, (b)
  landed+missed, (c) synthetic-landed episodes. INPUT: fixtures across all three.
  EXPECTED: PROVEN / FAILED / never-PROVEN respectively. EVIDENCE: verdict + the
  code path at `episode.py:156`. FAILURE MEANING: the finding seed is corrupt;
  every downstream cousin decision is untrustworthy.

**C2. Cousin distance is code-deterministic.**
- CLAIM: the 5-axis composite `D` and band are pure functions of inputs. TEST:
  re-run classification on the same Episode + references. EXPECTED: identical
  band/D/per-axis. EVIDENCE: two identical outputs. FAILURE MEANING: a model is
  leaking into the decision — violates code-decides.

**C3. SUB persistence.** CLAIM: coverage/known-cells/baselines survive process
restart. TEST: write, restart, read. EXPECTED: records present with provenance.
EVIDENCE: durable store round-trip. FAILURE MEANING: coverage cannot compound —
the central defect this design fixes would remain. **[NEW CHECK]** coverage-
persistence.

**C4. ORG enforcement.** CLAIM: a hunt cannot start without a recall query and
cannot close without indexing every emission. TEST: attempt a hunt with recall
stubbed out; attempt to close with an un-indexed emission. EXPECTED: both refuse
(tool-enforced, not prompt). EVIDENCE: refusal + no partial state. FAILURE
MEANING: prompting-not-enforcement regression; the knowledge loop is optional and
will rot. **[NEW CHECK]** recall-enforced + universal-index.

## Integration-level

**I1. Red direction is data-only.** CLAIM: MUT changes only scenario dicts; the
executor + lab are byte-identical. TEST: `git diff` on `exec_chain`/`lab` after a
mutation run; run a mutant scenario through the unmodified runner. EXPECTED: zero
executor diff; mutant lands. EVIDENCE: diff + Episode. FAILURE MEANING: the
Red/Bully boundary is broken.

**I2. Episode bridge stable across old/new consumers.** CLAIM: the same Episode
drives both the bench path and the LOOP. TEST: feed one Episode to both. EXPECTED:
consistent correlation reads. EVIDENCE: matching correlations. FAILURE MEANING:
the migration bridge is unsound.

**I3. Council gate is beside, not inside.** CLAIM: `aggregate_opinions` behavior
is unchanged for non-security council workspaces. TEST: run the platform council
checks (BL) before/after adding the gate. EXPECTED: BL green, identical results.
EVIDENCE: BL. FAILURE MEANING: a general primitive regressed for the whole fleet.

## Behavioral (semantic) — the core proofs

**B1. Spatial cousin discovery.** CLAIM: a variant one sub-technique from a
covered attack, which the old token-overlap scored ≈0, is classified NEW with a
large detection-response distance and a cited explanation. TEST: run a known
reference, then a sibling-sub-technique mutant; grade both. INPUT: e.g.
`kerberoast_to_da` reference vs. an AS-REP sibling mutant. EXPECTED: SIMILAR for
the covered path, NEW for the mutant, with the ATT&CK-sibling + silent-detection
axes cited. EVIDENCE: band + per-axis + explanation naming the axis. FAILURE
MEANING: the product does not work — cousins are not being found.

**B2. Suspect-by-default + gates.** CLAIM: a landed cousin is SUSPECT until G0–G3
pass, and a signature-match-only finding caps at G0. TEST: submit (a) evidence-
less, (b) signature-match-only, (c) fully reproducing findings. EXPECTED:
non-finding / G0-capped / promotable respectively. EVIDENCE: gate trace with
snapshot ids + benign result + notable id. FAILURE MEANING: false positives
flow; the bin's purpose fails.

**B3. Adversarial council kills a bad finding.** CLAIM: an unrebutted material
objection blocks promotion regardless of votes. TEST: a finding with a majority
"confirm" but one seat naming missing evidence the finding lacks. EXPECTED:
BLOCK. EVIDENCE: gate decision + the material objection + failed/absent rebuttal.
FAILURE MEANING: the council is democratic, not adversarial — the thesis fails.

**B4. Temporal cousin + cause disambiguation.** CLAIM: a detection firing weaker/
later than its baseline (sources intact) is classified attacker-evolution, and a
zeroed telemetry source is classified telemetry-failure. TEST: inject both
patterns into the firing series (model held constant via canary). EXPECTED:
correct causes; only attacker-evolution raises a suspect finding. EVIDENCE:
drift verdict + cause + canary proof. FAILURE MEANING: drift is misread; ops
noise becomes false attacker signal or vice versa.

**B5. Structurally-valid mutation.** CLAIM: mutants stay inside the grammar and
reach the detection surface. TEST: generate mutants across dimensions; dispatch.
EXPECTED: no grammar rejections; mutants land and produce Episodes. EVIDENCE:
landed mutants + lineage. FAILURE MEANING: mutation is random noise, not cousin
generation.

**B6. Distance-weighted scoring.** CLAIM: a far NEW cousin can exceed a known-bad
in value, and ANOMALOUS is never ranked below CONFIRMED. TEST: score a far NEW
cousin vs. a known-bad catch vs. an ANOMALOUS. EXPECTED: NEW value ≥ known-bad;
ANOMALOUS rank ≥ CONFIRMED not violated. EVIDENCE: scoreboard + BN. FAILURE
MEANING: novelty is punished (BN regression) — the scoreboard fights the product.

## Cousin-engine specific

**CU1. Embedding finds, structure grades.** CLAIM: semantic retrieval surfaces
candidates, but the band is decided by the structured axes. TEST: a semantically
distant but detection-response-identical pair → DIFFERENT (not NEW). EXPECTED:
DIFFERENT. EVIDENCE: per-axis showing detection-response ≈0. FAILURE MEANING:
arbitrary semantic distance is masquerading as novelty.

## Bin specific

**BI1. Analyst-visible G3 is real.** CLAIM: G3 measures a notable surfacing in
the SOC console under queue load, not the harness god-view. TEST: create a
notable under load; verify it appears via the console/index path. EXPECTED:
visible → pass; god-view-only → fail. EVIDENCE: notable id + index-wait. FAILURE
MEANING: findings invisible to real analysts are promoted.

## Council specific

**CO1. Quorum uses the full roster (non-voter counts).** COVERED BY **BL**. TEST:
a seat abstains; quorum denominator unchanged. EXPECTED: BL green. FAILURE
MEANING: absent seats inflate agreement.

**CO2. Disagreement → ANOMALOUS preserved.** CLAIM: seats sharing a signal but
unable to agree on one technique yields ANOMALOUS_UNCLASSIFIED. TEST:
conflicting-technique opinions. EXPECTED: ANOMALOUS, not DISMISS. EVIDENCE:
`council_agreement` output. FAILURE MEANING: emerging-threat novelty is
discarded (I8 violation).

## Drift specific

**DR1. Model held constant.** COVERED BY `model-canary`. TEST: a quant/template
change with attacker behavior fixed → NOT attacker-evolution. EXPECTED: not
misread. EVIDENCE: canary report. FAILURE MEANING: model drift is misattributed
to attackers.

## Mutation specific

**MU1. Budget bounds wander.** CLAIM: the mutation budget caps dimensions +
distance. TEST: set budget=1 dimension; generate. EXPECTED: only that dimension
varies. EVIDENCE: mutation lineage. FAILURE MEANING: uncontrolled fuzzing.

## Compounding — the hardest proofs

**CP1. Second hunt is different because of the first.** CLAIM: hunt N+1
retrieves N's emissions and changes behavior (neighborhood pick or suppressed
dead cell). TEST: run two hunts; show N's outcome altered N+1's target choice or
suppressed a cell. EXPECTED: an observable behavioral delta traceable to N.
EVIDENCE: TGT decision citing N's SUB records + ORG recall hits. FAILURE MEANING:
"storage is not learning" — the loop does not close.

**CP2. Known-cell steering.** CLAIM: a cell marked benign/covered/dead is
multiplicatively deprioritised next time. TEST: mark a cell; re-run TGT.
EXPECTED: that cell ranks below open cells. EVIDENCE: target scores. FAILURE
MEANING: negative results do not steer; effort is wasted repeatedly.

**CP3. Economic compounding.** CLAIM: cost-per-cousin falls across the program's
runs. TEST: compute the cost ledger over ≥ N hunts. EXPECTED: a downward trend.
EVIDENCE: cost ledger series. FAILURE MEANING: the system is not getting more
efficient — a core promise unmet.

## Training

**TR1. Flywheel closes end-to-end.** CLAIM: HARV corpus → LoRA → fuse → GGUF →
`ollama create` → acceptance+canary → confirm-serve produces a served model.
TEST: run the pipeline on a real harvested corpus. EXPECTED: a served, named
Ollama model with a full provenance chain. EVIDENCE: model version ← dataset ←
emissions; acceptance report. FAILURE MEANING: the fifth feed is storage, not
learning. NOTE: if the GGUF-convert tool is unavailable, TR1 is honest-BLOCKED
(documented), not faked.

**TR2. Trained specialist actually helps.** CLAIM: a later hunt using the trained
seat smells cousins measurably better than the same hunt without it, and beats
retrieval+playbook alone. TEST: ablation — base / base+ORG / base+playbook /
base+both / trained. EXPECTED: trained wins by a measurable margin, else the
model is DECLINED (not shipped). EVIDENCE: ablation deltas. FAILURE MEANING:
training is not justified — declining is the correct, honest outcome.

**TR3. No catastrophic forgetting.** COVERED BY `candidate_eval` + `model-canary`.
TEST: the specialist on general competence. EXPECTED: no regression beyond
threshold, else DECLINED. EVIDENCE: acceptance report. FAILURE MEANING: a sharper
cousin-smeller that got dumber overall was shipped.

## SOC-context

**SC1. Benign quiet (alert-fatigue).** COVERED BY **BQ**. TEST: benign corpus
through the bin. EXPECTED: G2 rejects; benign notifications count as false flags
on Axis 4. FAILURE MEANING: the system floods analysts.

**SC2. Recall vs emergent corpus.** COVERED BY **AZ**. TEST: detection recall
against the emergent-miss corpus. EXPECTED: AZ green. FAILURE MEANING: coverage
regressed under the new pipeline.

## Label-blind boundary

**LB1. Production grading is label-blind.** COVERED BY **BM**. TEST: attempt to
route a ground-truth label into the production grader/gate. EXPECTED: refused;
only the offline HARV oracle may read labels; World A/B split intact. EVIDENCE:
BM. FAILURE MEANING: the answer key leaked into hunting — results are worthless.

## Performance / resource

**PF1. Memory bound holds.** CLAIM: council roster + concurrent work stay under
the unified-memory cap; training never runs during a live hunt. TEST: run a
bounded roster + attempt to launch training during a hunt. EXPECTED: within cap;
training refuses/queues. EVIDENCE: memory trace + refusal. FAILURE MEANING:
OOM/contention on the single box.

## Regression / gates

**RG1. All standing gates green.** CLAIM: AW/BR/AZ/BL/BM/BN/BQ pass after every
migration step. TEST: `validate_system.py`. EXPECTED: green. EVIDENCE: the run.
FAILURE MEANING: the migration broke a standing invariant — stop and fix before
proceeding.

**RG2. Spine coverage ratchet.** COVERED BY **BR**. TEST: new `security/core/*`
files under the manifest surface. EXPECTED: covered at zero new-unit cost, BR
green. FAILURE MEANING: doc debt introduced.

## End-to-end

**E2E1. Full hunt → exit.** CLAIM: TGT→LOOP→MUT→RED→Episode→BR→BIN→HEART→SCORE→
operator-confirm→HND runs on the live lab and promotes exactly one real,
reproduced, analyst-visible, council-cleared cousin into a family-generalizing
detection that fires-on-attack / quiet-on-benign / no-regression. TEST: one
complete engagement on a real vulhub target. EXPECTED: the whole chain with a
real Episode (not synthetic) and an operator-confirmed detection. EVIDENCE: the
decision log from target-pick to detection deploy. FAILURE MEANING: the organism
does not live end-to-end — the design is not done.

**E2E2. Honest-BLOCKED path.** CLAIM: when a capability is missing (e.g. GGUF
convert), the system blocks with a reason and the other feeds continue. TEST:
disable the convert tool. EXPECTED: TRAIN halts with a clear blocker; hunting +
feeds 1–4/6 proceed. EVIDENCE: the blocker + continued operation. FAILURE
MEANING: faked-green — the worst failure mode.

---

## Definition of validated

The Defensive Bully is validated when B1–B6, CP1–CP3, TR1–TR3, E2E1–E2E2 pass on
**real** data, every standing gate (AW/BR/AZ/BL/BM/BN/BQ) is green, and every
capability that cannot yet be proven is explicitly honest-BLOCKED with a recorded
reason — never marked complete on a synthetic pass or a symbol-exists check.
