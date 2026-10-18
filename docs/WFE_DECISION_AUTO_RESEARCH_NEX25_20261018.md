# WFE decision — auto-research, Nex-N2.5-mini screen (2026-10-18)

The seat is not changed by this document.

| | Nex-N2-mini (seat) | Nex-N2.5-mini (challenger) |
|---|---|---|
| Campaign | `wfe_research_nex25_20261018`, research_production 36 × 3 | same |
| PASS | 103/108 | 87/87 (curtailed: 21 rows saved) |
| Paired sign test | — | 2 wins / 0 losses / 27 ties, NOT_SEPARATED (curtailed after res-multihop-02) |
| Wall s median (p90) | **4.5** (6.2) | 5.7 (12.0) |

Both arms were at the suite's ceiling. The seat's 5 failures were all on repeat 2 of multi-hop
tasks: it called graph_recall, got an empty memory, and answered "unknown" without searching the
knowledge base (a seat finding: it gives up after a memory miss). The challenger's published
lead is on open-web research (BrowseComp, Toolathlon), which this KB-only suite does not exercise.

**Recommendation: keep N2-mini.** It's faster, and N2.5 is not separated on the lane's measured
job. Revisit only if a web-research suite exists. Speed fields are absent on these rows (tool-loop
timing gap, fixed in T6 f0478a6f after this run), so the comparison uses wall time.
- auto-research: operator 2026-10-18 confirmed keep Nex-N2-mini (N2.5 not separated, slower).
