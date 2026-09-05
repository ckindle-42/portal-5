# Compliance reasoning implementation decision

The reasoning layer uses native Python on the existing SQLite compliance
repository. This preserves the bitemporal register, immutable revision and
anchor model, authenticated review lifecycle, and single-host operational
constraints already delivered by V2, while giving the assessment path direct
access to deterministic constraint and expression evaluators. OSCAL exchange,
Utopia, StrictDoc/CISO adaptation, and PROV-O interchange are deferred: none is
required to answer or verify the twelve operator questions, and introducing an
additional representation would create synchronization risk without improving
source-text determinations. The earlier note that P2 could not begin before
R1-R6 was therefore superseded by the landed canonical store and is closed.
