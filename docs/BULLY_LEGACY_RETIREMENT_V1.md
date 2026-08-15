# Defensive Bully P7 legacy retirement record

The new module is authoritative. Legacy files remain only where a historical
read path or acceptance bench still needs them; no production hunt delegates
its decision to them.

| Legacy asset | Authoritative replacement | Disposition / retained evidence |
|---|---|---|
| `growth_loop.py` | BIN + HND proof legs | Removed from the live tree after callers/tests were ported. `handoff.validate_spl_syntax` owns its deterministic gate; Git retains history. |
| `continuous_eval.py` | SCORE + PLT | Removed from the live tree after replacement validation landed; Git retains history. |
| `unknown_defense.py` U1 grade | BR-COUSIN + calibration bench | LOOP records BR-COUSIN as the authoritative relationship. U1 remains inside blue/agentic acceptance benches and as an explanation comparator only. |
| blue/blue-orchestrate driver role | LOOP | `bully.orchestrator` is the sole hunt sequencer. Blue orchestration section runners remain the model-acceptance/investigation lane. |
| `capability_graph` cold rebuild | SUB `coverage_cells` + on-demand readout | LOOP seeds content-idempotently once, then reads persisted cells across restarts. Older compliance/response reports retain their historical graph read path. |
| `agentic_blue_eval.Episode` | `core.episode.Episode` | Legacy class is documented as acceptance-bench-only; LOOP/evidence use the authoritative Episode. |

Rollback restores a feed mode to `shadow` or `off`; it does not delete new
records or resurrect a retired production caller. Historical modules and test
fixtures are retained specifically so pre-cutover evidence remains readable.
