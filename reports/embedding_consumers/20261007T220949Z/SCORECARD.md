# EmbeddingGemma 2 consumer scorecard — 20261007T220949Z

Phase-3 gate (every consumer MEASURED or BLOCKED-with-reason): **PASS**

| consumer | area | kind | status | primary metric | incumbent | candidate | hint |
|---|---|---|---|---|---|---|---|
| router | inference | collapse | MEASURED | accuracy | 0.9041095890410958 | 0.7945 | WORSE |
| harmful_intent | inference | collapse | MEASURED | recall_harmful@fp_budget | 0.1143 | 0.9143 | BETTER |
| tool_preselect | inference | collapse | MEASURED | recall@k | no preselection: all 61 schemas every turn | 0.9247 | WORSE |
| memory_recall_floor | inference | upgrade | MEASURED | precision_injected | 0.215 | 0.235 | PARITY |
| memory_salience | inference | upgrade | MEASURED | f1 | 0.1395 | 0.9595 | BETTER |
| memory_dedup | inference | new | MEASURED | dup_suppression_at_fp | 0.0 | 0.75 | BETTER |
| memory_entities | inference | upgrade | MEASURED | merge_precision/recall | 0.0 | 0.2333 | BETTER |
| memory_recall | inference | collapse | MEASURED | recall@4 | 0.925 | 0.975 | BETTER |
| rag_first_stage | retrieval | collapse | MEASURED | recall@20 + final nDCG | 0.9562 | 0.391 | WORSE |
| compliance_retrieval | retrieval | collapse | MEASURED | findability parity | 0.816 | 0.81 | PARITY |
| compliance_crosswalk | retrieval | new | MEASURED | seed recall@k | 1.0 | 0.4571 | INCONCLUSIVE |
| owui_attachment_rag | retrieval | collapse | MEASURED | recall@k | 0.617 | 0.8298 | BETTER |
| unified_recall | retrieval | new | BLOCKED (media generation out of scope by operator decision (2026-10-07: not needed); no generated artifacts exist) | cross-modal recall@5 |  |  | INCONCLUSIVE |
| audio_recordings | retrieval | new | MEASURED | recall@5 | 1.0 | 1.0 | PARITY |
| wiki_search | retrieval | upgrade | MEASURED | self-retrieval recall@5 | 0.4255 | 0.8298 | BETTER |
| refusal_classifier | security | collapse | MEASURED | f1 | 0.5402 | 0.8724 | BETTER |
| field_journal | security | upgrade | BLOCKED (only 3 journal entries exist (floor is 20); revisit once the journal has grown) | recall@5 |  |  | INCONCLUSIVE |
| attack_mapping | security | new | MEASURED | recall@5 | 0.0 | 0.88 | BETTER |
| spl_library | security | upgrade | MEASURED | recall@5 | 0.025 | 0.95 | BETTER |
| ics_advisories | security | upgrade | BLOCKED (asset_inventory emits only host/protocol/role hints (no vendor or product string field); 40 lab pcaps tried, 0 ICS-protocol assets, 0 with a product string. The only pcaps on this host are IT attack-episode captures) | recall@5 |  |  | INCONCLUSIVE |
| bully_projection | security | collapse | MEASURED | discovery precision (identity diagnostic classified) | 0.717391 | 0.565217 | WORSE |
| bully_novelty | security | new | MEASURED | AUC benign-vs-novel | None | 1.0 | INCONCLUSIVE |
| vuln_severity | security | collapse | MEASURED | macro_f1 | 0.8777 | 0.378 | WORSE |
| binary_similarity | security | new | MEASURED | recall@5 | 0.5 | 0.5 | PARITY |
| media_alignment | measurement | new | BLOCKED (media generation out of scope by operator decision (2026-10-07: not needed); no generated artifacts exist. `gen_media` is available if wanted later) | rank1_vs_shuffled |  |  | INCONCLUSIVE |
| cad_resemblance | measurement | new | MEASURED | rank1_vs_shuffled | 0.4667 | 0.3333 | INCONCLUSIVE |
| assertion_coverage | measurement | upgrade | MEASURED | agreement_with_judge | 1.0 | 0.7649 | INCONCLUSIVE |
| fleet_behavior | measurement | new | MEASURED | evidence only (no verdict) | None | 0.8096 | INCONCLUSIVE |
| failure_clustering | measurement | new | MEASURED | cluster purity | 0.8413 | 0.9683 | BETTER |
| config_lint | hygiene | new | MEASURED | flag precision | None | 0.2 | INCONCLUSIVE |
| doc_affinity | hygiene | new | MEASURED | recall of known-stale units | 0.0 | 0.0316 | INCONCLUSIVE |
| data_schema_linking | companion | new | MEASURED | recall@3 | 0.175 | 0.85 | BETTER |
| generation_dedup | companion | new | MEASURED | precision@threshold | None | 1.0 | BETTER |
