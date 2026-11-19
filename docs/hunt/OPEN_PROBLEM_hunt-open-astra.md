# Shared source names break sourcetype attribution

I audited the four stored burst runs under `snap_burst_14a3a1a/results/hunt/burst`. Each card targets one sourcetype. When indexed source names exist, the raw read selects solely by source. Splunk can therefore fill that card's capped read with a different sourcetype. Reproducing queries constructed with the same helper have the same exposure.

| Family | Sourcetypes whose first eight sources overlap another type | All sourcetypes | Shared source names |
|---|---:|---:|---:|
| botsv2 | 19 | 104 | 16 |
| kyoushi | 0 | 36 | 0 |
| santos | 0 | 126 | 0 |
| russell | 0 | 127 | 0 |

I deduplicated cards by sourcetype, inverted every recorded source list, and tested the first eight entries against that ownership map. A second pairwise intersection of source lists gave the same counts. In botsv2, eleven types share the source name `gacrux`. These counts establish ambiguous selection. The saved cards alone cannot establish how many attack events were displaced or a change in recall.
