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

A source-only discovery read of the newest 100 events from `gacrux` returned 32 status, 44 transaction details and 24 variables rows. Adding the database card's type returned 96 database rows. Conversely, the Sysmon source-only probe returned 100 rows under a renamed type. Combining its indexed type with the source returned zero. The correction therefore constrains shared routes only. Discovery records shared ownership across the full metadata result before truncating per-card sources. Cards retain that information for downstream reads. When loading older cards, the behaviour and case paths infer shared ownership from the recorded source lists. Previously stored raw rows retain their original attribution.

The run needs fresh cards and behaviours. Re-ranking the stored rows preserves the attribution error. I predict the comparison-family top-50 counts will remain 12, 14 and 15. On botsv2 the defensible null prediction is **0–2/15**: the present two credits may disappear until the correctly attributed traffic card independently recovers them. Source scoping alone does not establish a recall improvement.

## An observed single timestamp was treated as an unknown time range

All ten single-timestamp source cards across the four runs recorded `no_sample` (five botsv2, two kyoushi, two santos, one russell). The card sampler searched the 48 hours preceding the run date. The five botsv2 sources each contained one event in 2017. Two of them already generated top-50 source-first-seen entries, despite the hunt never reading their events. Time bounds now include the observed maximum timestamp, using the search transport's microsecond precision, and single-timestamp sources get one window at the observed time.

## Source-level sampling can miss events even when the whole source fits

The stored stream:ftp receipt read 237 of 1,490 indexed events. Its allocation was 383 × 12 = 4,596. A read-only discovery query returned all 1,490 rows in one request. Both admitted Korean attachment-name events are present after Unicode NFC normalization. Applying the production parser and stored cards offline keyed 1,460 rows into ten behaviours. **Zero** of those ten retained the attachment on their actor/action/object, example raw line or reproducing query. The object role generalizes all 505 distinct method parameters to a wildcard on the 725-row transfer card. Sampling and representation are independently lossy.

The behaviour reader now requests the entire observed range once when the complete indexed source route fits its existing row and source budgets. It records the selection and any count shortfall. Large or truncated source routes keep stratified reads. One full-range FTP read uses 23 fewer searches than the 24-window plan and returns 1,253 more rows than the stored receipt. That is an observed input recovery and a projected request saving, not a new ranked step.

## Two ranked source anomalies already point to concrete episodes

I took every source-first-seen or source-burst entry in the stored botsv2 top 50 (12 windows), with no key-based selection. I read the newest 383 events or fewer in each window, using the stored per-window allocation and the source route corrected for overlap. The experiment grouped parsed rows by the card's actor, action and object field, selected the group with the most distinct observed object values, and retained its chronological endpoints. No key entered grouping or selection.

Four windows had a group with multiple distinct objects. At stored file position 33 one client retrieved seven distinct FTP objects; the last was the admitted Korean attachment. At position 46 the Apache error template covered 345 distinct object values in 348 rows; the episode's evidence carried the scanner address. The other two groups carried no admitted artefact. Scoring the four groups' descriptions and endpoint evidence after selection locates three steps from two episodes, versus the current baseline's two from one incorrectly attributed behaviour. This is a bounded discovery replay with frozen ranks. The Apache address earns two credits because of the entity scoreboard's shared key. Its evidence directly supports web scanning; it does not by itself demonstrate a separate C2 session.

### Four-family scoreboard replay

Using the production episode formatter, I replayed the same bounded reads on each family's stored ranking. The official scoreboard reported:

| Family | Steps at 50 / 100 / all | Resolved source windows in the first 50 |
|---|---|---:|
| botsv2 | 3 / 3 / 4 of 15 | 4 |
| kyoushi | 12 / 12 / 12 of 12 | 6 |
| santos | 14 / 16 / 17 of 21 | 0 |
| russell | 15 / 15 / 16 of 22 | 2 |

Botsv2 covered two of four scenarios at every cut. The unit is a shared actor, action and object field inside an already-ranked anomalous source window. Evidence shows its distinct object count, earliest and latest sampled objects, endpoint lines, source query and bounds. The primary rank and LOFO merge weights stay the same. Two distinct objects are necessary to report multiple objects. The first 50 positions and the existing family's per-window read limit bound discovery cost. No weight or score threshold was fitted. Qualification used frozen ranks, and the clean four-family run still needs to verify the earlier routing and sampling changes together with this stage.

### Independent transport check and live handoff

A second discovery pass called the production resolver through the bounded Splunk job/result transport, from copies of the four stored rankings. The runs issued 9, 12, 4 and 6 source-window reads on botsv2, kyoushi, santos and russell. They returned 2,345, 10,075, 1,940 and 1,868 rows respectively. No read reported an error. The official scoreboard reproduced the table above. The Apache card calls its inferred program field “does”; use the endpoint lines and repeated request paths to interpret this template. The three-credit score includes one FTP transfer step and two credits for a shared IP. There is no third scenario.

From the reviewed checkout in the orchestrator environment, with the existing Pipeline and lab Splunk credentials exported:

```bash
bash coding_task/RUN_HUNT_OPEN_ASTRA.sh
```

The command creates a fresh run directory under `coding_task/scratch/`, runs each named build index in turn, excludes its own family from the knowledge store, and writes `score.log`. My predictions at 50 are botsv2 3/15 from at least two behaviour notables and 2/4 scenarios, kyoushi 12/12, santos 14/21 and russell 15/22. Inspect `stages.notables.source_windows` in each `progress.json` for read counts and unresolved windows, then inspect the actual notables and endpoint evidence. Fewer than three steps, a single carrying notable, or a decline on a comparison family misses the target. Live chat rendering and case quality require separate product verification.
