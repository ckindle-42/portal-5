# Bully SA7 — Data-Plane Census V1

This is the Phase 0 implementation and gate record for
`TASK BULLY SA7 DATA PLANE AND INVESTIGATION V1.md`.

## Implemented contract

| Phase item | Implementation | Status |
|---|---|---|
| 0.1 connector contract | `bully/connectors.py`: common `read` surface for ingest and query-in-place connectors | Green in hermetic tests |
| 0.2 record adapter | `source_adapters.py`: record-shaped adapter with `raw_events` compatibility alias | Green |
| 0.3 schema discovery | `SourceSchema`, inferred nested fields, types, cardinality, null rates, fingerprint | Green |
| 0.4 semantic binding | per-source metadata bindings; unavailable meanings remain absent | Green |
| 0.5 time alignment | `TimeBinding` records representation, transform, resolution, and comparability | Green |
| 0.6 entity resolution | explicit aliases/unified IDs, confidence, and provenance; no fuzzy merge | Green |
| 0.7 query translation | native SPL/KQL/SQL/API forms retained in `NativeQuery` | Green |
| 0.8 catalog | versioned `SourceCatalog` and `CatalogPlanner`; exclusions carry reasons | Green |
| 0.9 volume strategy | indexed/tiered strategy with sampling rule and bias statement | Green |
| 0.10 quality | duplicate, gap, parse-failure, null-rate, and grade reporting | Green |
| 0.11 access/audit | credential fail-closed wrapper, sensitivity policy, append-only query audit | Green |
| 0.12 non-telemetry | advisory, case history, inventory, and coverage adapters | Contract green; live sources pending |
| 0.13 drift | fingerprint comparison and catalog invalidation on drift | Green |
| 0.14 acquisition gaps | capability-gap report derived from the catalog | Green |
| 0.15 census | `DataPlane.census()` publishes profiles and blind spots | Green |

## Current gate evidence

`tests/security/bully/test_sa7_data_plane.py` proves the data-plane behavior in
an isolated run. The catalog planner selects sources from capabilities rather
than source-name branches, and query-in-place results remain outside the
catalog/store. Existing SA1 adapter tests also remain green.

## Operational gate

The operational Phase 0 gate is **honest-BLOCKED** at this checkout. The code
has the connector contract, but no configured live connectors are present for
the four required non-telemetry classes (advisories, case/ticket history,
asset/identity inventory, and coverage-as-data). The hermetic callback connector
is test infrastructure, not evidence that those sources are connected for real.

Required next evidence before Phase A:

- a live query-in-place source with a recorded native query and audit entry;
- real advisory, case/analyst-decision, asset/identity, and coverage records;
- a generated census from those profiles, including sensitivity and freshness;
- live re-profile evidence for one changed source schema.

No investigation-base or later-phase work is claimed by this record. The phase
map requires Phase A to stop until these data-plane conditions are met.
