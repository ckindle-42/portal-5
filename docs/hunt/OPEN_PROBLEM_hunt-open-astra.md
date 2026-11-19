# Shared source names break sourcetype attribution

I audited the four stored burst runs under `snap_burst_14a3a1a/results/hunt/burst`. Each card targets one sourcetype. When indexed source names exist, the raw read selects solely by source. Splunk can therefore fill that card's capped read with a different sourcetype. Reproducing queries constructed with the same helper have the same exposure.

| Family | Sourcetypes whose first eight sources overlap another type | All sourcetypes | Shared source names |
|---|---:|---:|---:|
| botsv2 | 19 | 104 | 16 |
| kyoushi | 0 | 36 | 0 |
| santos | 0 | 126 | 0 |
| russell | 0 | 127 | 0 |

I deduplicated cards by sourcetype, inverted every recorded source list, and tested the first eight entries against that ownership map. A second pairwise intersection of source lists gave the same counts. In botsv2, eleven types share the source name `gacrux`. These counts establish ambiguous selection. The saved cards alone cannot establish how many attack events were displaced or a change in recall.

## The existing rank-one result has incorrect provenance

The burst DuckDB contains 4,530 distinct raw lines under the threat card. The card metadata reports **two indexed events** for that sourcetype. An independent, unrestricted-time discovery read of that sourcetype (`head 100 | stats count by sourcetype source`) returned two. The earlier BOTSV2_DIAGNOSIS identified the traffic/threat mix-up. The new measurements show its magnitude on the current baseline: at least 4,528 distinct lines could not have come from the claimed type. This compromises the evidence for the single notable responsible for both top-50 steps. The traffic events themselves may be real.

A source-only discovery read of the newest 100 events from `gacrux` returned 32 status, 44 transaction details and 24 variables rows. Adding the database card's type returned 96 database rows. Conversely, the Sysmon source-only probe returned 100 rows under a renamed type. Combining its indexed type with the source returned zero. The correction therefore constrains shared routes only. Discovery records shared ownership across the full metadata result before truncating per-card sources. Cards retain that information for downstream reads. Historical receipts without this field retain their original route.

The run needs fresh cards and behaviours. Re-ranking the stored rows preserves the attribution error. I predict the comparison-family top-50 counts will remain 12, 14 and 15. On botsv2 the defensible null prediction is **0–2/15**: the present two credits may disappear until the correctly attributed traffic card independently recovers them. Source scoping alone does not establish a recall improvement.

## An observed single timestamp was treated as an unknown time range

All ten single-timestamp source cards across the four runs recorded `no_sample` (five botsv2, two kyoushi, two santos, one russell). The card sampler searched the 48 hours preceding the run date. The five botsv2 sources each contained one event in 2017. Two of them already generated top-50 source-first-seen entries, despite the hunt never reading their events. Time bounds now include the observed maximum timestamp, using the search transport's microsecond precision, and single-timestamp sources get one window at the observed time.

## Source-level sampling can miss events even when the whole source fits

The stored stream:ftp receipt read 237 of 1,490 indexed events. Its allocation was 383 × 12 = 4,596. A read-only discovery query returned all 1,490 rows in one request. Both admitted Korean attachment-name events are present after Unicode NFC normalization. Applying the production parser and stored cards offline keyed 1,460 rows into ten behaviours. **Zero** of those ten retained the attachment on their actor/action/object, example raw line or reproducing query. The object role generalizes all 505 distinct method parameters to a wildcard on the 725-row transfer card. Sampling and representation are independently lossy.

The behaviour reader now requests the entire observed range once when the complete indexed source route fits its existing row and source budgets. It records the selection and any count shortfall. Large or truncated source routes keep stratified reads. One full-range FTP read removes 23 searches and recovers 1,253 additional source rows. That is an observed input recovery and a projected request saving, not a new ranked step.
