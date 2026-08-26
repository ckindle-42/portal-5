# BULLY_HUNT_SWEEP_RUN_H5_V1

## assembly_verdict: **PROXY_SCALE**

- integration_fraction: 0.9412 (16/16 modules)
- corpus_fraction: 0.001281
- modules_missing: ['run_preflight']
- degraded_stages: []
- reasons: ['corpus_fraction_0.00128<0.1: 359959 of 281070301 records -- this is another proxy']

## The four standing claims, answered by THIS run

```json
{
  "crogl": {
    "sourcetypes_reviewed": 328,
    "identity_coverage": 1.0,
    "sources_profiled": 5,
    "sources_sampled": 245,
    "comprehension_fraction": 0.0204,
    "claim": "ingests any source"
  },
  "bully": {
    "chain_reach_recall": 1.0,
    "max_pivot_distance": 0,
    "entries_located": null,
    "entries_attempted": null,
    "floor_recall": null,
    "cousins_planted": null,
    "cousins_recovered": null,
    "cousin_recall": null,
    "claim": "finds same/similar on a real haystack"
  },
  "corpus": {
    "records_processed": 359959,
    "records_available": 281070301,
    "fraction": 0.001281,
    "claim": "the real ground is actually used"
  },
  "generator": {
    "cousin_recall_at_distance": {
      "0": 1.0
    },
    "claim": "cousins of what is in the corpus, injected into it"
  }
}
```

## bed_acceptance (A5)

```json
{
  "floor_known_recall": 0.6296296296296297,
  "product_cousin_recall": 1.0,
  "cost_background_fp_rate": null,
  "n_answer_key": 27,
  "n_cousins_injected": 17,
  "n_background_sampled": 0,
  "verdict": "INVALID",
  "reasons": [
    "partial_read:359959/281070301 -- a capped read of a real corpus biases every downstream statistic toward whatever the cap selected",
    "scored_sample_too_small:972<10000 -- recall/FP figures computed on this scored population do not generalise"
  ]
}
```

## scoreboard.update() -- the correctness axis (W.2)

- trust_mean_rank: 1.0
- false_flag_count: 0
```json
{
  "hunt_id": "full_assembly_f4",
  "n_records": 897,
  "catch_count": 897,
  "catch_rate": 1.0,
  "trust_mean_rank": 1.0,
  "discovery_total": 538.2,
  "discovery_mean": 0.6,
  "false_flag_count": 0
}
```

## sweep_summary (H.2/H.4) -- per-entry floor/cousin recall across the sweep

```json
{
  "n_done": 27,
  "n_not_attempted": 0,
  "entries_done": [
    "botsv3:T1558.004:BSTOLL-L|bstoll|web_admin|null_admin|frothlywebcode",
    "botsv3:T1071.001:FYODOR-L|45.77.53.176",
    "botsv3:T1496:BSTOLL-L|bstoll",
    "botsv1:T1190:imreallynotbatman.com|192.168.250.70",
    "botsv3:T1078:BGIST-L|bgist@froth.ly",
    "botsv3:T1203:FYODOR-L|fyodor@froth.ly",
    "botsv3:T1190:gacrux.i-06fea586f3d3c8ce8|tomcat7",
    "botsv3:T1110:BTUN-L|btun",
    "botsv3:T1098:null_admin|web_admin",
    "botsv3:T1498:hoth|matar",
    "botsv3:T1046:PCERF-L|svcvnc",
    "botsv1:T1595.002:40.80.148.42|imreallynotbatman.com",
    "botsv1:T1110:23.22.63.114|imreallynotbatman.com",
    "botsv1:T1071.001:192.168.250.40|imreallynotbatman.com",
    "botsv1:T1583:40.80.148.42|imreallynotbatman.com",
    "botsv1:T1592:23.22.63.114|imreallynotbatman.com",
    "botsv1:T1071.001:192.168.250.70|imreallynotbatman.com",
    "botsv3:T1005:ABUNGST-L|abungstein@froth.ly",
    "botsv2:T1566.001:MACLORY-AIR13|kutekitten",
    "botsv2:T1071.001:MACLORY-AIR13|eidk.duckdns.org",
    "botsv2:T1053.005:MACLORY-AIR13|kutekitten",
    "botsv2:T1486:MACLORY-AIR13|kIagerfield",
    "botsv2:T1190:www.brewertalk.com|45.77.65.211",
    "botsv2:T1059.001:MACLORY-AIR13|kIagerfield",
    "botsv2:T1091:MACLORY-AIR13|kutekitten",
    "botsv2:T1583.001:eidk.hopto.org|eidk.duckdns.org",
    "botsv2:T1005:MACLORY-AIR13|kutekitten"
  ],
  "entries_not_attempted": [],
  "n_located": 17,
  "n_cousins_planted": 17,
  "n_cousins_recovered": 17,
  "floor_recall": 0.6296,
  "cousin_recall": 1.0,
  "results": [
    {
      "technique": "T1558.004",
      "dataset": "botsv3",
      "located": true,
      "cousin_planted": true,
      "cousin_id": "cz-botsv3-T1558.004-000-REVOCABULARY-00-d0",
      "cousin_recovered": true,
      "distance": 0,
      "records_read": 36870,
      "units": 539,
      "seconds": 30.38
    },
    {
      "technique": "T1071.001",
      "dataset": "botsv3",
      "located": true,
      "cousin_planted": true,
      "cousin_id": "cz-botsv3-T1071.001-000-REVOCABULARY-00-d0",
      "cousin_recovered": true,
      "distance": 0,
      "records_read": 36647,
      "units": 539,
      "seconds": 29.92
    },
    {
      "technique": "T1496",
      "dataset": "botsv3",
      "located": true,
      "cousin_planted": true,
      "cousin_id": "cz-botsv3-T1496-000-REVOCABULARY-00-d0",
      "cousin_recovered": true,
      "distance": 0,
      "records_read": 36895,
      "units": 539,
      "seconds": 29.79
    },
    {
      "technique": "T1190",
      "dataset": "botsv1",
      "located": false,
      "cousin_planted": false,
      "cousin_id": null,
      "cousin_recovered": null,
      "distance": null,
      "records_read": 27235,
      "units": 1026,
      "seconds": 20.45
    },
    {
      "technique": "T1078",
      "dataset": "botsv3",
      "located": true,
      "cousin_planted": true,
      "cousin_id": "cz-botsv3-T1078-000-REVOCABULARY-00-d0",
      "cousin_recovered": true,
      "distance": 0,
      "records_read": 36667,
      "units": 539,
      "seconds": 29.59
    },
    {
      "technique": "T1203",
      "dataset": "botsv3",
      "located": true,
      "cousin_planted": true,
      "cousin_id": "cz-botsv3-T1203-000-REVOCABULARY-00-d0",
      "cousin_recovered": true,
      "distance": 0,
      "records_read": 36672,
      "units": 539,
      "seconds": 29.56
    },
    {
      "technique": "T1190",
      "dataset": "botsv3",
      "located": true,
      "cousin_planted": true,
      "cousin_id": "cz-botsv3-T1190-000-REVOCABULARY-00-d0",
      "cousin_recovered": true,
      "distance": 0,
      "records_read": 60378,
      "units": 1030,
      "seconds": 48.74
    },
    {
      "technique": "T1110",
      "dataset": "botsv3",
      "located": true,
      "cousin_planted": true,
      "cousin_id": "cz-botsv3-T1110-000-REVOCABULARY-00-d0",
      "cousin_recovered": true,
      "distance": 0,
      "records_read": 43496,
      "units": 539,
      "seconds": 34.03
    },
    {
      "technique": "T1098",
      "dataset": "botsv3",
      "located": false,
      "cousin_planted": false,
      "cousin_id": null,
      "cousin_recovered": null,
      "distance": null,
      "records_read": 9,
      "units": 14,
      "seconds": 1.16
    },
    {
      "technique": "T1498",
      "dataset": "botsv3",
      "located": true,
      "cousin_planted": true,
      "cousin_id": "cz-botsv3-T1498-000-REVOCABULARY-00-d0",
      "cousin_recovered": true,
      "distance": 0,
      "records_read": 37020,
      "units": 539,
      "seconds": 30.54
    },
    {
      "technique": "T1046",
      "dataset": "botsv3",
      "located": true,
      "cousin_planted": true,
      "cousin_id": "cz-botsv3-T1046-000-REVOCABULARY-00-d0",
      "cousin_recovered": true,
      "distance": 0,
      "records_read": 36930,
      "units": 539,
      "seconds": 29.87
    },
    {
      "technique": "T1595.002",
      "dataset": "botsv1",
      "located": false,
      "cousin_planted": false,
      "cousin_id": null,
      "cousin_recovered": null,
      "distance": null,
      "records_read": 25346,
      "units": 1026,
      "seconds": 18.21
    },
    {
      "technique": "T1110",
      "dataset": "botsv1",
      "located": false,
      "cousin_planted": false,
      "cousin_id": null,
      "cousin_recovered": null,
      "distance": null,
      "records_read": 27456,
      "units": 1026,
      "seconds": 19.54
    },
    {
      "technique": "T1071.001",
      "dataset": "botsv1",
      "located": false,
      "cousin_planted": false,
      "cousin_id": null,
      "cousin_recovered": null,
      "distance": null,
      "records_read": 5498,
      "units": 1010,
      "seconds": 5.29
    },
    {
      "technique": "T1583",
      "dataset": "botsv1",
      "located": false,
      "cousin_planted": false,
      "cousin_id": null,
      "cousin_recovered": null,
      "distance": null,
      "records_read": 25346,
      "units": 1026,
      "seconds": 17.84
    },
    {
      "technique": "T1592",
      "dataset": "botsv1",
      "located": false,
      "cousin_planted": false,
      "cousin_id": null,
      "cousin_recovered": null,
      "distance": null,
      "records_read": 27456,
      "units": 1026,
      "seconds": 19.3
    },
    {
      "technique": "T1071.001",
      "dataset": "botsv1",
      "located": false,
      "cousin_planted": false,
      "cousin_id": null,
      "cousin_recovered": null,
      "distance": null,
      "records_read": 5512,
      "units": 1011,
      "seconds": 5.08
    },
    {
      "technique": "T1005",
      "dataset": "botsv3",
      "located": true,
      "cousin_planted": true,
      "cousin_id": "cz-botsv3-T1005-000-REVOCABULARY-00-d0",
      "cousin_recovered": true,
      "distance": 0,
      "records_read": 46570,
      "units": 887,
      "seconds": 38.19
    },
    {
      "technique": "T1566.001",
      "dataset": "botsv2",
      "located": true,
      "cousin_planted": true,
      "cousin_id": "cz-botsv2-T1566.001-000-REVOCABULARY-00-d0",
      "cousin_recovered": true,
      "distance": 0,
      "records_read": 7719,
      "units": 524,
      "seconds": 11.82
    },
    {
      "technique": "T1071.001",
      "dataset": "botsv2",
      "located": true,
      "cousin_planted": true,
      "cousin_id": "cz-botsv2-T1071.001-000-REVOCABULARY-00-d0",
      "cousin_recovered": true,
      "distance": 0,
      "records_read": 7724,
      "units": 526,
      "seconds": 11.4
    },
    {
      "technique": "T1053.005",
      "dataset": "botsv2",
      "located": true,
      "cousin_planted": true,
      "cousin_id": "cz-botsv2-T1053.005-000-REVOCABULARY-00-d0",
      "cousin_recovered": true,
      "distance": 0,
      "records_read": 7734,
      "units": 526,
      "seconds": 11.24
    },
    {
      "technique": "T1486",
      "dataset": "botsv2",
      "located": true,
      "cousin_planted": true,
      "cousin_id": "cz-botsv2-T1486-000-REVOCABULARY-00-d0",
      "cousin_recovered": true,
      "distance": 0,
      "records_read": 7739,
      "units": 526,
      "seconds": 11.27
    },
    {
      "technique": "T1190",
      "dataset": "botsv2",
      "located": false,
      "cousin_planted": false,
      "cousin_id": null,
      "cousin_recovered": null,
      "distance": null,
      "records_read": 8042,
      "units": 524,
      "seconds": 5.57
    },
    {
      "technique": "T1059.001",
      "dataset": "botsv2",
      "located": true,
      "cousin_planted": true,
      "cousin_id": "cz-botsv2-T1059.001-000-REVOCABULARY-00-d0",
      "cousin_recovered": true,
      "distance": 0,
      "records_read": 7744,
      "units": 526,
      "seconds": 11.33
    },
    {
      "technique": "T1091",
      "dataset": "botsv2",
      "located": true,
      "cousin_planted": true,
      "cousin_id": "cz-botsv2-T1091-000-REVOCABULARY-00-d0",
      "cousin_recovered": true,
      "distance": 0,
      "records_read": 7749,
      "units": 526,
      "seconds": 11.34
    },
    {
      "technique": "T1583.001",
      "dataset": "botsv2",
      "located": false,
      "cousin_planted": false,
      "cousin_id": null,
      "cousin_recovered": null,
      "distance": null,
      "records_read": 400287,
      "units": 1024,
      "seconds": 237.26
    },
    {
      "technique": "T1005",
      "dataset": "botsv2",
      "located": true,
      "cousin_planted": true,
      "cousin_id": "cz-botsv2-T1005-000-REVOCABULARY-00-d0",
      "cousin_recovered": true,
      "distance": 0,
      "records_read": 7754,
      "units": 526,
      "seconds": 11.71
    }
  ]
}
```

## claim_guard: disqualified_stages=['investigate_anchors']

## starvation_check (K.3): **FAIL**

```json
{
  "verdict": "FAIL",
  "findings": [
    {
      "stage": "investigate_anchors",
      "records_received": 0,
      "stream_total": 359959,
      "fraction": 0.0,
      "reason": "investigate_anchors received 0 of 359959 records (0.00000<0.01) while reporting OK -- starved"
    },
    {
      "stage": "plant_and_measure_cousins",
      "records_received": 0,
      "stream_total": 359959,
      "fraction": 0.0,
      "reason": "plant_and_measure_cousins received 0 of 359959 records (0.00000<0.01) while reporting OK -- starved"
    }
  ],
  "min_fraction": 0.01
}
```

## Per-stage timings, records received, and outputs

- **resolve_indexes** (corpus_bed) -- OK, 0.0s, records_received=0
- **discover_index_range** (inject_plane) -- OK, 7.283s, records_received=0
- **investigate_anchors** (investigation_pivot) -- OK, 361.369s, records_received=0
- **plant_and_measure_cousins** (adaptive_scope) -- OK, 0.0s, records_received=0
- **stream_corpus_sample** (corpus_bed) -- OK, 426.912s, records_received=0
- **infer_field_roles** (field_roles) -- OK, 19.56s, records_received=38119
- **classify_telemetry** (telemetry_behavior) -- OK, 0.027s, records_received=38119
- **infer_universal_behaviors** (behavior_inference) -- OK, 0.165s, records_received=38119
- **build_artifact_graph** (artifact_graph) -- OK, 3.306s, records_received=38119
- **resolve_entities_and_timelines** (correlation) -- OK, 0.292s, records_received=38119
- **fit_baseline** (baseline) -- OK, 0.01s, records_received=38119
- **discover_and_cluster** (discovery) -- OK, 785.208s, records_received=38119
- **series_and_level** (series_cousin) -- OK, 0.004s, records_received=38119
- **level_match** (pyramid) -- OK, 1.69s, records_received=38119
- **grade_to_loop_contract** (loop_grader) -- OK, 0.021s, records_received=38119
- **resolve_unit_outcomes** (unit_outcome) -- OK, 0.044s, records_received=38119
- **raise_and_verdict_concerns** (analyst_loop) -- OK, 0.003s, records_received=38119

Total duration: 1605.89s

## Full stage outputs

```json
{
  "resolve_indexes": [
    "portal5_lab",
    "botsv1",
    "botsv2",
    "botsv3"
  ],
  "discover_index_range": {
    "n_indexes": 4
  },
  "investigate_anchors": {
    "n_entries_in_scope": 27,
    "n_entries_attempted": 27,
    "n_entries_not_attempted": 0,
    "n_located": 17,
    "floor_recall": 0.6296,
    "span_seconds": 600.0
  },
  "plant_and_measure_cousins": {
    "n_planted": 17,
    "n_recovered": 17,
    "cousin_recall": 1.0,
    "dry_run": false,
    "by_distance": {
      "0": {
        "total": 17,
        "reached": 17,
        "recall": 1.0
      }
    },
    "max_reached_distance": 0,
    "zero_hop_only": true
  },
  "stream_corpus_sample": {
    "n_records_wide_fit": 359959,
    "wide_fitted_units": 100299,
    "resumed_from_checkpoint": false,
    "n_sourcetypes_covered": 328,
    "n_sourcetypes_available": 434,
    "sample_report": {
      "algorithm_version": "score-sample-v1",
      "sourcetypes_seen": 245,
      "sourcetypes_sampled": 245,
      "records_seen": 359959,
      "records_sampled": 38119,
      "per_sourcetype_cap": 200,
      "sample_fraction": 0.105898,
      "truncated_at_max_total": false,
      "largest_sourcetype_share": 0.0052
    },
    "scorer_input_verdict": {
      "verdict": "OK",
      "reasons": [],
      "sourcetypes_in_scorer_input": 245,
      "sourcetypes_covered_by_stream": 328,
      "scorer_sourcetype_fraction": 0.747,
      "largest_sourcetype_share": 0.0052
    },
    "coverage_note": "this run optimizes sourcetype/event-type coverage, not raw corpus volume -- corpus_fraction will read low against F.4's literal 0.10 floor by design (operator decision); see stage docstring"
  },
  "infer_field_roles": {
    "extraction_valid": true,
    "n_fields": 144
  },
  "classify_telemetry": {
    "algorithm_version": "telemetry-behavior-v1",
    "n_records": 38119,
    "n_classified": 5598,
    "coverage": 0.1469,
    "by_sourcetype": {
      "ActiveDirectory": {
        "records": 13,
        "classified": 0,
        "coverage": 0.0
      },
      "Linux:SELinuxConfig": {
        "records": 52,
        "classified": 0,
        "coverage": 0.0
      },
      "MSAD:NT6:Health": {
        "records": 200,
        "classified": 0,
        "coverage": 0.0
      },
      "MSAD:NT6:SiteInfo": {
        "records": 200,
        "classified": 0,
        "coverage": 0.0
      },
      "MSExchange:Management": {
        "records": 200,
        "classified": 0,
        "coverage": 0.0
      },
      "OktaIM2:log": {
        "records": 200,
        "classified": 0,
        "coverage": 0.0
      },
      "Perfmon:CPU": {
        "records": 200,
        "classified": 0,
        "coverage": 0.0
      },
      "Perfmon:LogicalDisk": {
        "records": 200,
        "classified": 0,
        "coverage": 0.0
      },
      "Perfmon:Memory": {
        "records": 200,
        "classified": 0,
        "coverage": 0.0
      },
      "Perfmon:NTDS": {
        "records": 200,
        "classified": 0,
        "coverage": 0.0
      },
      "Perfmon:Network": {
        "records": 200,
        "classified": 0,
        "coverage": 0.0
      },
      "Perfmon:Network_Interface": {
        "records": 200,
        "classified": 0,
        "coverage": 0.0
      },
      "Perfmon:PhysicalDisk": {
        "records": 200,
        "classified": 0,
        "coverage": 0.0
      },
      "Perfmon:Process": {
        "records": 200,
        "classified": 0,
        "coverage": 0.0
      },
      "Perfmon:Processor": {
        "records": 200,
        "classified": 0,
        "coverage": 0.0
      },
      "Perfmon:System": {
        "records": 200,
        "classified": 0,
        "coverage": 0.0
      },
      "PerfmonMk:Process": {
        "records": 200,
        "classified": 0,
        "coverage": 0.0
      },
      "Powershell:ScriptExecutionSummary": {
        "records": 200,
        "classified": 0,
        "coverage": 0.0
      },
      "Script:GetEndpointInfo": {
        "records": 22,
        "classified": 22,
        "coverage": 1.0
      },
      "Script:InstalledApps": {
        "records": 200,
        "classified": 0,
        "coverage": 0.0
      },
      "Script:ListeningPorts": {
        "records": 200,
        "classified": 200,
        "coverage": 1.0
      },
      "Unix:ListeningPorts": {
        "records": 200,
        "classified": 0,
        "coverage": 0.0
      },
      "Unix:SSHDConfig": {
        "records": 19,
        "classified": 0,
        "coverage": 0.0
      },
      "Unix:Service": {
        "records": 200,
        "classified": 0,
        "coverage": 0.0
      },
      "Unix:Update": {
        "records": 13,
        "classified": 0,
        "coverage": 0.0
      },
      "Unix:Uptime": {
        "records": 4,
        "classified": 0,
        "coverage": 0.0
      },
      "Unix:UserAccounts": {
        "records": 200,
        "classified": 0,
        "coverage": 0.0
      },
      "Unix:Version": {
        "records": 5,
        "classified": 0,
        "coverage": 0.0
      },
      "WebLogic_Access_Combined": {
        "records": 200,
        "classified": 0,
        "coverage": 0.0
      },
      "WinEventLog": {
        "records": 200,
        "classified": 155,
        "coverage": 0.775
      },
      "WinHostMon": {
        "records": 200,
        "classified": 200,
        "coverage": 1.0
      },
      "WinRegistry": {
        "records": 200,
        "classified": 200,
        "coverage": 1.0
      },
      "WindowsUpdateLog": {
        "records": 200,
        "classified": 0,
        "coverage": 0.0
      },
      "XmlWinEventLog": {
        "records": 200,
        "classified": 0,
        "coverage": 0.0
      },
      "['mcp:jsonrpc', 'mcp:jsonrpc']": {
        "records": 200,
        "classified": 0,
        "coverage": 0.0
      },
      "__json": {
        "records": 75,
        "classified": 0,
        "coverage": 0.0
      },
      "access_combined": {
        "records": 200,
        "classified": 200,
        "coverage": 1.0
      },
      "alternatives": {
        "records": 4,
        "classified": 0,
        "coverage": 0.0
      },
      "amazon-ssm-agent": {
        "records": 200,
        "classified": 0,
        "coverage": 0.0
      },
      "amazon-ssm-agent-too_small": {
        "records": 200,
        "classified": 0,
        "coverage": 0.0
      },
      "apache:error": {
        "records": 200,
        "classified": 0,
        "coverage": 0.0
      },
      "apache_error": {
        "records": 200,
        "classified": 0,
        "coverage": 0.0
      },
      "auditd": {
        "records": 200,
        "classified": 0,
        "coverage": 0.0
      },
      "aws:cloudtrail": {
        "records": 200,
        "classified": 0,
        "coverage": 0.0
      },
      "aws:cloudtrail:lake": {
        "records": 62,
        "classified": 0,
        "coverage": 0.0
      },
      "aws:cloudwatch": {
        "records": 200,
        "classified": 0,
        "coverage": 0.0
      },
      "aws:cloudwatch:guardduty": {
        "records": 1,
        "classified": 0,
        "coverage": 0.0
      },
      "aws:cloudwatchlogs": {
        "records": 200,
        "classified": 0,
        "coverage": 0.0
      },
      "aws:cloudwatchlogs:vpcflow": {
        "records": 200,
        "classified": 200,
        "coverage": 1.0
      },
      "aws:config:rule": {
        "records": 200,
        "classified": 0,
        "coverage": 0.0
      },
      "aws:description": {
        "records": 200,
        "classified": 0,
        "coverage": 0.0
      },
      "aws:elb:accesslogs": {
        "records": 200,
        "classified": 0,
        "coverage": 0.0
      },
      "aws:rds:audit": {
        "records": 200,
        "classified": 0,
        "coverage": 0.0
      },
      "aws:rds:error": {
        "records": 5,
        "classified": 0,
        "coverage": 0.0
      },
      "aws:s3:accesslogs": {
        "records": 200,
        "classified": 0,
        "coverage": 0.0
      },
      "azure:monitor:aad": {
        "records": 200,
        "classified": 0,
        "coverage": 0.0
      },
      "azure:monitor:activity": {
        "records": 9,
        "classified": 0,
        "coverage": 0.0
      },
      "bandwidth": {
        "records": 200,
        "classified": 0,
        "coverage": 0.0
      },
      "bash_history": {
        "records": 100,
        "classified": 0,
        "coverage": 0.0
      },
      "bootstrap": {
        "records": 10,
        "classified": 0,
        "coverage": 0.0
      },
      "bro:conn:json": {
        "records": 22,
        "classified": 0,
        "coverage": 0.0
      },
      "cisco:asa": {
        "records": 200,
        "classified": 200,
        "coverage": 1.0
      },
      "cisco:duo:administrator": {
        "records": 32,
        "classified": 0,
        "coverage": 0.0
      },
      "cisco:ios": {
        "records": 124,
        "classified": 0,
        "coverage": 0.0
      },
      "cisco:isovalent": {
        "records": 76,
        "classified": 0,
        "coverage": 0.0
      },
      "cisco:isovalent:processConnect": {
        "records": 4,
        "classified": 0,
        "coverage": 0.0
      },
      "cisco:isovalent:processExec": {
        "records": 7,
        "classified": 0,
        "coverage": 0.0
      },
      "cisco:nvm:flowdata:v2": {
        "records": 199,
        "classified": 0,
        "coverage": 0.0
      },
      "cisco:sdwan:syslog": {
        "records": 1,
        "classified": 0,
        "coverage": 0.0
      },
      "cisco:sfw:estreamer": {
        "records": 11,
        "classified": 0,
        "coverage": 0.0
      },
      "cloud-init": {
        "records": 200,
        "classified": 0,
        "coverage": 0.0
      },
      "cloud-init-output": {
        "records": 23,
        "classified": 0,
        "coverage": 0.0
      },
      "code42:api": {
        "records": 88,
        "classified": 0,
        "coverage": 0.0
      },
      "code42:computer": {
        "records": 51,
        "classified": 0,
        "coverage": 0.0
      },
      "code42:org": {
        "records": 17,
        "classified": 0,
        "coverage": 0.0
      },
      "code42:security": {
        "records": 30,
        "classified": 0,
        "coverage": 0.0
      },
      "code42:user": {
        "records": 192,
        "classified": 0,
        "coverage": 0.0
      },
      "collectd": {
        "records": 200,
        "classified": 0,
        "coverage": 0.0
      },
      "config_file": {
        "records": 9,
        "classified": 0,
        "coverage": 0.0
      },
      "corpus:probe": {
        "records": 1,
        "classified": 0,
        "coverage": 0.0
      },
      "corpus:raw": {
        "records": 200,
        "classified": 0,
        "coverage": 0.0
      },
      "cpu": {
        "records": 200,
        "classified": 0,
        "coverage": 0.0
      },
      "cron-too_small": {
        "records": 44,
        "classified": 0,
        "coverage": 0.0
      },
      "crowdstrike:events:sensor": {
        "records": 64,
        "classified": 0,
        "coverage": 0.0
      },
      "crushftp:sessionlogs": {
        "records": 200,
        "classified": 0,
        "coverage": 0.0
      },
      "csp-violation": {
        "records": 200,
        "classified": 0,
        "coverage": 0.0
      },
      "df": {
        "records": 200,
        "classified": 0,
        "coverage": 0.0
      },
      "dmesg": {
        "records": 200,
        "classified": 0,
        "coverage": 0.0
      },
      "dpkg": {
        "records": 23,
        "classified": 0,
        "coverage": 0.0
      },
      "error-too_small": {
        "records": 1,
        "classified": 0,
        "coverage": 0.0
      },
      "errors": {
        "records": 200,
        "classified": 0,
        "coverage": 0.0
      },
      "errors-too_small": {
        "records": 200,
        "classified": 0,
        "coverage": 0.0
      },
      "ess_content_importer": {
        "records": 33,
        "classified": 0,
        "coverage": 0.0
      },
      "fortigate_event": {
        "records": 200,
        "classified": 0,
        "coverage": 0.0
      },
      "fortigate_traffic": {
        "records": 200,
        "classified": 0,
        "coverage": 0.0
      },
      "fortigate_utm": {
        "records": 200,
        "classified": 0,
        "coverage": 0.0
      },
      "ftp:access": {
        "records": 200,
        "classified": 0,
        "coverage": 0.0
      },
      "gen:freetext:awfpi-9": {
        "records": 200,
        "classified": 0,
        "coverage": 0.0
      },
      "gen:freetext:chucv-14": {
        "records": 200,
        "classified": 0,
        "coverage": 0.0
      },
      "gen:freetext:eiasc-7": {
        "records": 200,
        "classified": 0,
        "coverage": 0.0
      },
      "gen:freetext:grgfl-16": {
        "records": 200,
        "classified": 0,
        "coverage": 0.0
      },
      "gen:freetext:hmgeo-22": {
        "records": 200,
        "classified": 0,
        "coverage": 0.0
      },
      "gen:freetext:hyxnu-17": {
        "records": 200,
        "classified": 0,
        "coverage": 0.0
      },
      "gen:freetext:onzzh-30": {
        "records": 200,
        "classified": 0,
        "coverage": 0.0
      },
      "gen:freetext:ophvw-12": {
        "records": 200,
        "classified": 0,
        "coverage": 0.0
      },
      "gen:freetext:qraxb-3": {
        "records": 200,
        "classified": 0,
        "coverage": 0.0
      },
      "gen:freetext:zlgqf-34": {
        "records": 200,
        "classified": 0,
        "coverage": 0.0
      },
      "gen:freetext:zyoqu-36": {
        "records": 200,
        "classified": 0,
        "coverage": 0.0
      },
      "gen:numeric:azhuz-13": {
        "records": 200,
        "classified": 0,
        "coverage": 0.0
      },
      "gen:numeric:dmdjf-28": {
        "records": 200,
        "classified": 0,
        "coverage": 0.0
      },
      "gen:numeric:ibxjx-20": {
        "records": 200,
        "classified": 0,
        "coverage": 0.0
      },
      "gen:numeric:jhblz-33": {
        "records": 200,
        "classified": 0,
        "coverage": 0.0
      },
      "gen:numeric:moybc-38": {
        "records": 200,
        "classified": 0,
        "coverage": 0.0
      },
      "gen:numeric:qgmzo-10": {
        "records": 200,
        "classified": 0,
        "coverage": 0.0
      },
      "gen:numeric:qmrhh-2": {
        "records": 200,
        "classified": 0,
        "coverage": 0.0
      },
      "gen:numeric:tjole-5": {
        "records": 200,
        "classified": 0,
        "coverage": 0.0
      },
      "gen:numeric:umqjr-32": {
        "records": 200,
        "classified": 0,
        "coverage": 0.0
      },
      "gen:numeric:xbjrd-15": {
        "records": 200,
        "classified": 0,
        "coverage": 0.0
      },
      "gen:path:ejxmp-31": {
        "records": 200,
        "classified": 0,
        "coverage": 0.0
      },
      "gen:path:gztyq-29": {
        "records": 200,
        "classified": 0,
        "coverage": 0.0
      },
      "gen:path:jbtfr-26": {
        "records": 200,
        "classified": 0,
        "coverage": 0.0
      },
      "gen:path:oangs-27": {
        "records": 200,
        "classified": 0,
        "coverage": 0.0
      },
      "gen:path:ocvcw-39": {
        "records": 200,
        "classified": 0,
        "coverage": 0.0
      },
      "gen:path:ojzpl-37": {
        "records": 200,
        "classified": 0,
        "coverage": 0.0
      },
      "gen:path:sjdbi-4": {
        "records": 200,
        "classified": 0,
        "coverage": 0.0
      },
      "gen:path:xqwws-23": {
        "records": 200,
        "classified": 0,
        "coverage": 0.0
      },
      "gen:syscall:owupk-11": {
        "records": 200,
        "classified": 0,
        "coverage": 0.0
      },
      "gen:syscall:phkip-35": {
        "records": 200,
        "classified": 0,
        "coverage": 0.0
      },
      "gen:syscall:skcvj-21": {
        "records": 200,
        "classified": 0,
        "coverage": 0.0
      },
      "gen:syscall:vubsl-8": {
        "records": 200,
        "classified": 0,
        "coverage": 0.0
      },
      "gen:syscall:wntvn-0": {
        "records": 200,
        "classified": 0,
        "coverage": 0.0
      },
      "gen:verb:binzw-24": {
        "records": 200,
        "classified": 0,
        "coverage": 0.0
      },
      "gen:verb:syngk-25": {
        "records": 200,
        "classified": 0,
        "coverage": 0.0
      },
      "gen:verb:ukpom-6": {
        "records": 200,
        "classified": 0,
        "coverage": 0.0
      },
      "gen:verb:vybpx-1": {
        "records": 200,
        "classified": 0,
        "coverage": 0.0
      },
      "gen:verb:xklbg-19": {
        "records": 200,
        "classified": 0,
        "coverage": 0.0
      },
      "gen:verb:yupxs-18": {
        "records": 200,
        "classified": 0,
        "coverage": 0.0
      },
      "gsuite:gmail:bigquery": {
        "records": 4,
        "classified": 0,
        "coverage": 0.0
      },
      "gws:reports:login": {
        "records": 43,
        "classified": 0,
        "coverage": 0.0
      },
      "hardware": {
        "records": 11,
        "classified": 0,
        "coverage": 0.0
      },
      "history-2": {
        "records": 2,
        "classified": 0,
        "coverage": 0.0
      },
      "ids:alert": {
        "records": 1,
        "classified": 0,
        "coverage": 0.0
      },
      "iis": {
        "records": 200,
        "classified": 0,
        "coverage": 0.0
      },
      "interfaces": {
        "records": 200,
        "classified": 0,
        "coverage": 0.0
      },
      "iostat": {
        "records": 200,
        "classified": 0,
        "coverage": 0.0
      },
      "json_no_timestamp": {
        "records": 178,
        "classified": 0,
        "coverage": 0.0
      },
      "lastlog": {
        "records": 200,
        "classified": 0,
        "coverage": 0.0
      },
      "linux:auditd": {
        "records": 200,
        "classified": 0,
        "coverage": 0.0
      },
      "linux:syslog": {
        "records": 200,
        "classified": 0,
        "coverage": 0.0
      },
      "linux_audit": {
        "records": 200,
        "classified": 0,
        "coverage": 0.0
      },
      "linux_messages_syslog": {
        "records": 200,
        "classified": 0,
        "coverage": 0.0
      },
      "linux_secure": {
        "records": 200,
        "classified": 0,
        "coverage": 0.0
      },
      "localhost-5": {
        "records": 30,
        "classified": 0,
        "coverage": 0.0
      },
      "log4j": {
        "records": 16,
        "classified": 0,
        "coverage": 0.0
      },
      "lsof": {
        "records": 200,
        "classified": 0,
        "coverage": 0.0
      },
      "maillog-too_small": {
        "records": 6,
        "classified": 0,
        "coverage": 0.0
      },
      "mcp:jsonrpc": {
        "records": 153,
        "classified": 0,
        "coverage": 0.0
      },
      "ms:aad:audit": {
        "records": 31,
        "classified": 0,
        "coverage": 0.0
      },
      "ms:aad:signin": {
        "records": 200,
        "classified": 0,
        "coverage": 0.0
      },
      "ms:o365:management": {
        "records": 200,
        "classified": 0,
        "coverage": 0.0
      },
      "ms:o365:reporting:messagetrace": {
        "records": 200,
        "classified": 0,
        "coverage": 0.0
      },
      "mysql:connection:stats": {
        "records": 200,
        "classified": 0,
        "coverage": 0.0
      },
      "mysql:database": {
        "records": 106,
        "classified": 0,
        "coverage": 0.0
      },
      "mysql:errorLog": {
        "records": 98,
        "classified": 0,
        "coverage": 0.0
      },
      "mysql:instance:stats": {
        "records": 200,
        "classified": 0,
        "coverage": 0.0
      },
      "mysql:server:stats": {
        "records": 200,
        "classified": 0,
        "coverage": 0.0
      },
      "mysql:status": {
        "records": 200,
        "classified": 0,
        "coverage": 0.0
      },
      "mysql:tableStatus": {
        "records": 200,
        "classified": 0,
        "coverage": 0.0
      },
      "mysql:table_io_waits_summary_by_index_usage": {
        "records": 200,
        "classified": 0,
        "coverage": 0.0
      },
      "mysql:transaction:details": {
        "records": 200,
        "classified": 0,
        "coverage": 0.0
      },
      "mysql:transaction:stats": {
        "records": 200,
        "classified": 0,
        "coverage": 0.0
      },
      "mysql:user": {
        "records": 150,
        "classified": 0,
        "coverage": 0.0
      },
      "mysql:variables": {
        "records": 200,
        "classified": 0,
        "coverage": 0.0
      },
      "mysqld-8": {
        "records": 3,
        "classified": 0,
        "coverage": 0.0
      },
      "nessus:scan": {
        "records": 65,
        "classified": 0,
        "coverage": 0.0
      },
      "netstat": {
        "records": 200,
        "classified": 200,
        "coverage": 1.0
      },
      "network:http-decoded": {
        "records": 200,
        "classified": 0,
        "coverage": 0.0
      },
      "network:packet": {
        "records": 200,
        "classified": 0,
        "coverage": 0.0
      },
      "o365:management:activity": {
        "records": 200,
        "classified": 0,
        "coverage": 0.0
      },
      "ollama:server": {
        "records": 200,
        "classified": 0,
        "coverage": 0.0
      },
      "openPorts": {
        "records": 200,
        "classified": 200,
        "coverage": 1.0
      },
      "osquery:info": {
        "records": 200,
        "classified": 200,
        "coverage": 1.0
      },
      "osquery:results": {
        "records": 200,
        "classified": 200,
        "coverage": 1.0
      },
      "osquery:warning": {
        "records": 110,
        "classified": 0,
        "coverage": 0.0
      },
      "osquery_info": {
        "records": 200,
        "classified": 200,
        "coverage": 1.0
      },
      "osquery_results": {
        "records": 200,
        "classified": 200,
        "coverage": 1.0
      },
      "osquery_warning": {
        "records": 200,
        "classified": 0,
        "coverage": 0.0
      },
      "out-3": {
        "records": 17,
        "classified": 0,
        "coverage": 0.0
      },
      "package": {
        "records": 200,
        "classified": 0,
        "coverage": 0.0
      },
      "pan:system": {
        "records": 200,
        "classified": 0,
        "coverage": 0.0
      },
      "pan:threat": {
        "records": 2,
        "classified": 0,
        "coverage": 0.0
      },
      "pan:traffic": {
        "records": 200,
        "classified": 200,
        "coverage": 1.0
      },
      "portal5:test": {
        "records": 1,
        "classified": 0,
        "coverage": 0.0
      },
      "protocol": {
        "records": 200,
        "classified": 0,
        "coverage": 0.0
      },
      "ps": {
        "records": 200,
        "classified": 200,
        "coverage": 1.0
      },
      "stash": {
        "records": 84,
        "classified": 0,
        "coverage": 0.0
      },
      "stream:arp": {
        "records": 200,
        "classified": 200,
        "coverage": 1.0
      },
      "stream:dhcp": {
        "records": 200,
        "classified": 0,
        "coverage": 0.0
      },
      "stream:dns": {
        "records": 200,
        "classified": 200,
        "coverage": 1.0
      },
      "stream:ftp": {
        "records": 200,
        "classified": 0,
        "coverage": 0.0
      },
      "stream:http": {
        "records": 200,
        "classified": 200,
        "coverage": 1.0
      },
      "stream:icmp": {
        "records": 200,
        "classified": 200,
        "coverage": 1.0
      },
      "stream:igmp": {
        "records": 200,
        "classified": 0,
        "coverage": 0.0
      },
      "stream:ip": {
        "records": 200,
        "classified": 0,
        "coverage": 0.0
      },
      "stream:irc": {
        "records": 1,
        "classified": 0,
        "coverage": 0.0
      },
      "stream:ldap": {
        "records": 200,
        "classified": 200,
        "coverage": 1.0
      },
      "stream:mapi": {
        "records": 200,
        "classified": 0,
        "coverage": 0.0
      },
      "stream:mysql": {
        "records": 200,
        "classified": 200,
        "coverage": 1.0
      },
      "stream:sip": {
        "records": 12,
        "classified": 0,
        "coverage": 0.0
      },
      "stream:smb": {
        "records": 200,
        "classified": 200,
        "coverage": 1.0
      },
      "stream:smtp": {
        "records": 200,
        "classified": 200,
        "coverage": 1.0
      },
      "stream:snmp": {
        "records": 12,
        "classified": 0,
        "coverage": 0.0
      },
      "stream:tcp": {
        "records": 200,
        "classified": 200,
        "coverage": 1.0
      },
      "stream:udp": {
        "records": 200,
        "classified": 200,
        "coverage": 1.0
      },
      "suricata": {
        "records": 200,
        "classified": 20,
        "coverage": 0.1
      },
      "symantec:ep:agent:file": {
        "records": 200,
        "classified": 200,
        "coverage": 1.0
      },
      "symantec:ep:agt_system:file": {
        "records": 200,
        "classified": 0,
        "coverage": 0.0
      },
      "symantec:ep:behavior:file": {
        "records": 200,
        "classified": 0,
        "coverage": 0.0
      },
      "symantec:ep:packet:file": {
        "records": 200,
        "classified": 0,
        "coverage": 0.0
      },
      "symantec:ep:risk:file": {
        "records": 1,
        "classified": 0,
        "coverage": 0.0
      },
      "symantec:ep:scan:file": {
        "records": 30,
        "classified": 0,
        "coverage": 0.0
      },
      "symantec:ep:scm_system:file": {
        "records": 200,
        "classified": 0,
        "coverage": 0.0
      },
      "symantec:ep:security:file": {
        "records": 47,
        "classified": 0,
        "coverage": 0.0
      },
      "symantec:ep:traffic:file": {
        "records": 200,
        "classified": 0,
        "coverage": 0.0
      },
      "syslog": {
        "records": 200,
        "classified": 0,
        "coverage": 0.0
      },
      "target:postcondition": {
        "records": 42,
        "classified": 0,
        "coverage": 0.0
      },
      "time": {
        "records": 8,
        "classified": 0,
        "coverage": 0.0
      },
      "top": {
        "records": 200,
        "classified": 200,
        "coverage": 1.0
      },
      "usersWithLoginPrivs": {
        "records": 200,
        "classified": 0,
        "coverage": 0.0
      },
      "vmstat": {
        "records": 200,
        "classified": 0,
        "coverage": 0.0
      },
      "vmw-syslog": {
        "records": 200,
        "classified": 0,
        "coverage": 0.0
      },
      "web:access": {
        "records": 200,
        "classified": 0,
        "coverage": 0.0
      },
      "web_ping": {
        "records": 200,
        "classified": 0,
        "coverage": 0.0
      },
      "weblogic_stdout": {
        "records": 200,
        "classified": 0,
        "coverage": 0.0
      },
      "who": {
        "records": 200,
        "classified": 200,
        "coverage": 1.0
      },
      "windows:event": {
        "records": 200,
        "classified": 0,
        "coverage": 0.0
      },
      "windows:powershell": {
        "records": 200,
        "classified": 0,
        "coverage": 0.0
      },
      "windows:security": {
        "records": 200,
        "classified": 1,
        "coverage": 0.005
      },
      "windows:sysmon": {
        "records": 200,
        "classified": 0,
        "coverage": 0.0
      },
      "windows:system": {
        "records": 200,
        "classified": 0,
        "coverage": 0.0
      },
      "wineventlog:security": {
        "records": 200,
        "classified": 0,
        "coverage": 0.0
      },
      "xmlwineventlog": {
        "records": 200,
        "classified": 0,
        "coverage": 0.0
      },
      "xmlwineventlog:sysmon": {
        "records": 131,
        "classified": 0,
        "coverage": 0.0
      },
      "yum-too_small": {
        "records": 63,
        "classified": 0,
        "coverage": 0.0
      },
      "zscalernss-web": {
        "records": 15,
        "classified": 0,
        "coverage": 0.0
      }
    },
    "class_distribution": {
      "enumerate": 2442,
      "execute": 468,
      "auth": 250,
      "c2_exfil": 1622,
      "escalate": 12,
      "collect": 203,
      "persist": 200,
      "lateral": 200,
      "evade": 201
    },
    "class_entropy_bits": 2.2479,
    "degenerate": false,
    "unmapped_sourcetypes": [
      "ActiveDirectory",
      "Linux:SELinuxConfig",
      "MSAD:NT6:Health",
      "MSAD:NT6:SiteInfo",
      "MSExchange:Management",
      "OktaIM2:log",
      "Perfmon:CPU",
      "Perfmon:LogicalDisk",
      "Perfmon:Memory",
      "Perfmon:NTDS",
      "Perfmon:Network",
      "Perfmon:Network_Interface",
      "Perfmon:PhysicalDisk",
      "Perfmon:Process",
      "Perfmon:Processor",
      "Perfmon:System",
      "PerfmonMk:Process",
      "Powershell:ScriptExecutionSummary",
      "Script:InstalledApps",
      "Unix:ListeningPorts",
      "Unix:SSHDConfig",
      "Unix:Service",
      "Unix:Update",
      "Unix:Uptime",
      "Unix:UserAccounts",
      "Unix:Version",
      "WebLogic_Access_Combined",
      "WindowsUpdateLog",
      "XmlWinEventLog",
      "['mcp:jsonrpc', 'mcp:jsonrpc']",
      "__json",
      "alternatives",
      "amazon-ssm-agent",
      "amazon-ssm-agent-too_small",
      "apache:error",
      "apache_error",
      "auditd",
      "aws:cloudtrail",
      "aws:cloudtrail:lake",
      "aws:cloudwatch",
      "aws:cloudwatch:guardduty",
      "aws:cloudwatchlogs",
      "aws:config:rule",
      "aws:description",
      "aws:elb:accesslogs",
      "aws:rds:audit",
      "aws:rds:error",
      "aws:s3:accesslogs",
      "azure:monitor:aad",
      "azure:monitor:activity",
      "bandwidth",
      "bash_history",
      "bootstrap",
      "bro:conn:json",
      "cisco:duo:administrator",
      "cisco:ios",
      "cisco:isovalent",
      "cisco:isovalent:processConnect",
      "cisco:isovalent:processExec",
      "cisco:nvm:flowdata:v2",
      "cisco:sdwan:syslog",
      "cisco:sfw:estreamer",
      "cloud-init",
      "cloud-init-output",
      "code42:api",
      "code42:computer",
      "code42:org",
      "code42:security",
      "code42:user",
      "collectd",
      "config_file",
      "corpus:probe",
      "corpus:raw",
      "cpu",
      "cron-too_small",
      "crowdstrike:events:sensor",
      "crushftp:sessionlogs",
      "csp-violation",
      "df",
      "dmesg",
      "dpkg",
      "error-too_small",
      "errors",
      "errors-too_small",
      "ess_content_importer",
      "fortigate_event",
      "fortigate_traffic",
      "fortigate_utm",
      "ftp:access",
      "gen:freetext:awfpi-9",
      "gen:freetext:chucv-14",
      "gen:freetext:eiasc-7",
      "gen:freetext:grgfl-16",
      "gen:freetext:hmgeo-22",
      "gen:freetext:hyxnu-17",
      "gen:freetext:onzzh-30",
      "gen:freetext:ophvw-12",
      "gen:freetext:qraxb-3",
      "gen:freetext:zlgqf-34",
      "gen:freetext:zyoqu-36",
      "gen:numeric:azhuz-13",
      "gen:numeric:dmdjf-28",
      "gen:numeric:ibxjx-20",
      "gen:numeric:jhblz-33",
      "gen:numeric:moybc-38",
      "gen:numeric:qgmzo-10",
      "gen:numeric:qmrhh-2",
      "gen:numeric:tjole-5",
      "gen:numeric:umqjr-32",
      "gen:numeric:xbjrd-15",
      "gen:path:ejxmp-31",
      "gen:path:gztyq-29",
      "gen:path:jbtfr-26",
      "gen:path:oangs-27",
      "gen:path:ocvcw-39",
      "gen:path:ojzpl-37",
      "gen:path:sjdbi-4",
      "gen:path:xqwws-23",
      "gen:syscall:owupk-11",
      "gen:syscall:phkip-35",
      "gen:syscall:skcvj-21",
      "gen:syscall:vubsl-8",
      "gen:syscall:wntvn-0",
      "gen:verb:binzw-24",
      "gen:verb:syngk-25",
      "gen:verb:ukpom-6",
      "gen:verb:vybpx-1",
      "gen:verb:xklbg-19",
      "gen:verb:yupxs-18",
      "gsuite:gmail:bigquery",
      "gws:reports:login",
      "hardware",
      "history-2",
      "ids:alert",
      "iis",
      "interfaces",
      "iostat",
      "json_no_timestamp",
      "lastlog",
      "linux:auditd",
      "linux:syslog",
      "linux_audit",
      "linux_messages_syslog",
      "linux_secure",
      "localhost-5",
      "log4j",
      "lsof",
      "maillog-too_small",
      "mcp:jsonrpc",
      "ms:aad:audit",
      "ms:aad:signin",
      "ms:o365:management",
      "ms:o365:reporting:messagetrace",
      "mysql:connection:stats",
      "mysql:database",
      "mysql:errorLog",
      "mysql:instance:stats",
      "mysql:server:stats",
      "mysql:status",
      "mysql:tableStatus",
      "mysql:table_io_waits_summary_by_index_usage",
      "mysql:transaction:details",
      "mysql:transaction:stats",
      "mysql:user",
      "mysql:variables",
      "mysqld-8",
      "nessus:scan",
      "network:http-decoded",
      "network:packet",
      "o365:management:activity",
      "ollama:server",
      "osquery:warning",
      "osquery_warning",
      "out-3",
      "package",
      "pan:system",
      "pan:threat",
      "portal5:test",
      "protocol",
      "stash",
      "stream:dhcp",
      "stream:ftp",
      "stream:igmp",
      "stream:ip",
      "stream:irc",
      "stream:mapi",
      "stream:sip",
      "stream:snmp",
      "symantec:ep:agt_system:file",
      "symantec:ep:behavior:file",
      "symantec:ep:packet:file",
      "symantec:ep:risk:file",
      "symantec:ep:scan:file",
      "symantec:ep:scm_system:file",
      "symantec:ep:security:file",
      "symantec:ep:traffic:file",
      "syslog",
      "target:postcondition",
      "time",
      "usersWithLoginPrivs",
      "vmstat",
      "vmw-syslog",
      "web:access",
      "web_ping",
      "weblogic_stdout",
      "windows:event",
      "windows:powershell",
      "windows:sysmon",
      "windows:system",
      "wineventlog:security",
      "xmlwineventlog",
      "xmlwineventlog:sysmon",
      "yum-too_small",
      "zscalernss-web"
    ],
    "class_concentration": {
      "enumerate": 0.4362,
      "execute": 0.0836,
      "auth": 0.0447,
      "c2_exfil": 0.2897,
      "escalate": 0.0021,
      "collect": 0.0363,
      "persist": 0.0357,
      "lateral": 0.0357,
      "evade": 0.0359
    },
    "source_concentration": {
      "enumerate": 0.0819,
      "execute": 0.4274,
      "auth": 0.8,
      "c2_exfil": 0.1233,
      "escalate": 1.0,
      "collect": 0.9852,
      "persist": 1.0,
      "lateral": 1.0,
      "evade": 0.995
    },
    "concentration_reasons": [
      "class_concentration:enumerate=0.4362",
      "source_concentration:collect<-stream:mysql=0.9852",
      "source_concentration:escalate<-WinEventLog=1.0",
      "source_concentration:evade<-symantec:ep:agent:file=0.995",
      "source_concentration:lateral<-stream:smb=1.0",
      "source_concentration:persist<-WinRegistry=1.0"
    ],
    "concentrated": true
  },
  "infer_universal_behaviors": {
    "algorithm_version": "behavior-inference-v1",
    "actions_profiled": 23,
    "schemas_seen": 5,
    "classes_inferred": 7,
    "cross_schema_classes": 1,
    "cross_schema_fraction": 0.1429,
    "largest_class_members": 16
  },
  "build_artifact_graph": {
    "n_artifacts": 38119,
    "n_units": 972
  },
  "resolve_entities_and_timelines": {
    "n_entities": 897,
    "n_timelines": 897
  },
  "fit_baseline": {
    "fitted_units": 101271
  },
  "discover_and_cluster": {
    "algorithm_version": "discovery-v1",
    "units_examined": 972,
    "discovered": 972,
    "rejected_unremarkable": 0,
    "rejected_incoherent": 0,
    "discovery_rate": 1.0,
    "n_clusters": 9
  },
  "series_and_level": {
    "n_series": 897
  },
  "level_match": {
    "n_matches": 9
  },
  "grade_to_loop_contract": {
    "assessments": 897
  },
  "resolve_unit_outcomes": {
    "n_outcomes": 972,
    "by_outcome": {
      "NOVEL": 972
    }
  },
  "raise_and_verdict_concerns": {
    "n_concerns": 0
  }
}
```
