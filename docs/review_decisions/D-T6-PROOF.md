---
id: D-T6-PROOF
question: At a fixed one-concern workload, which of C1-C4 are proven by the default no-reader path over real stratified replay windows?
stage: window
why_not_binding: "The latest state reports the binding stage as unmeasured because every earlier BOTS paired product slice was excluded before execution; T6 measures source/window completeness and reports downstream truth gaps without claiming a measured binding stage."
arms:
  - legacy_funnel
  - review_d0
metric: "C1-C4 claim rules in TASK_REVIEW_06_PROOF_V1, with bootstrap 95% intervals over the same real windows and truth rows; workload B is one concern per window in both arms."
adopt_if: "No product arm is promoted. Mark each claim PROVEN only by its contract rule, PARTIAL only when the review point estimate exceeds the legacy control and intervals overlap, and UNPROVEN otherwise or when its interval cannot be estimated."
anti_goals:
  - tune no threshold, weight, cutoff, prompt, or sample after seeing a headline metric
  - add no proxy, synthetic, injected, or newly executed exercise truth
  - emit no attack, chain, target tool, or emulation operation
status: PREREGISTERED
---
The control is the shipped legacy funnel. The candidate is the T3 default `review_d0` configuration
with `no_reader`; the configuration is unchanged. The same windows and independent truth items are
scored by both arms. B is fixed at one raised concern per window so queue truncation is explicit
and does not depend on either arm's result. The proof uses only already-indexed Splunk telemetry,
certified recorded captures, and corpus-derived evidence twins. If the required independent truth
or separate-day benign windows are absent, the associated claim remains UNPROVEN with the exact
sample and rejection counts reported.
