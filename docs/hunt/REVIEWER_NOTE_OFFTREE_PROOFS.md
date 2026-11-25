# Reviewer note: hunt proof results are kept off-tree on purpose

The committed R3 verdicts (`coding_task/REPORT_HUNT_VERDICT_R3_*.md`, 2026-11-21) all read
"falls short". They are **not the current state**. Later fixes (`332992311` hunt-template-parse,
`hunt-wide-estate-clock`) were re-proved live, and the solo re-proofs of all four R3 families and the
held-out proofs on unseen corpora passed the OrcaCyber plan's acceptance bars.

Those results are deliberately **not committed**, so hunter models cannot read results, keys or
history. Reviewers should read them at `/Volumes/data01/hunt_proofs/` (next to `hunt_keys/`, which
the hunter never reads) before concluding anything from the in-tree R3 verdicts.

Known open item: the santos judge AUC is inverted. The brief for it is in `coding_task/`.
