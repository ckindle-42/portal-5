# Bully SA7 Phase 0 Gate — L.10

Result: **GREEN**

Generated from the live census and planner proof in `docs/BULLY_DATA_PLANE_CENSUS_LIVE_V1.json`.

## Checks

- `query_in_place`: PASS
- `schemas_discovered`: PASS
- `semantic_bindings_declared`: PASS
- `time_comparability_declared`: PASS
- `entity_resolution_confidence_provenance`: PASS
- `catalog_drives_selection`: PASS
- `volume_quality_sensitivity`: PASS
- `complete_query_audit`: PASS
- `non_telemetry_sources_connected`: PASS
- `advisories_sparse_signatures`: PASS
- `census_published`: PASS

## Evidence

```json
{
  "audit_entries": 11,
  "blind_spots": 34,
  "non_telemetry_sources": [
    "asset-identity-context",
    "case-history",
    "detection-coverage",
    "live-advisories"
  ],
  "planner_proof_hash": "0bd44cea80579c4c",
  "source_count": 8
}
```

## Named remainder

The Proxmox inventory endpoint was unavailable during the live run. Asset/identity context is nevertheless connected from indexed entities; the inventory finding remains explicit in the census and is not treated as observed.
