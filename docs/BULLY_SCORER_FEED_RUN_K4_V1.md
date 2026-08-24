# BULLY_SCORER_FEED_RUN_K4_V1

## assembly_verdict: **PROXY_SCALE**

- integration_fraction: 1.0 (16/16 modules)
- corpus_fraction: 0.00128
- modules_missing: []
- degraded_stages: []
- reasons: ['corpus_fraction_0.00128<0.1: 359772 of 281069927 records -- this is another proxy']

## The four standing claims, answered by THIS run

```json
{
  "crogl": {
    "sourcetypes_reviewed": 325,
    "identity_coverage": 1.0,
    "claim": "ingests any source"
  },
  "bully": {
    "chain_reach_recall": 1.0,
    "max_pivot_distance": 0,
    "claim": "finds same/similar on a real haystack"
  },
  "corpus": {
    "records_processed": 359772,
    "records_available": 281069927,
    "fraction": 0.00128,
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
  "floor_known_recall": 0.037037037037037035,
  "product_cousin_recall": 1.0,
  "cost_background_fp_rate": null,
  "n_answer_key": 27,
  "n_cousins_injected": 5,
  "n_background_sampled": 0,
  "verdict": "INVALID",
  "reasons": [
    "partial_read:359772/281069927 -- a capped read of a real corpus biases every downstream statistic toward whatever the cap selected",
    "scored_sample_too_small:971<10000 -- recall/FP figures computed on this scored population do not generalise"
  ]
}
```

## scoreboard.update() -- the correctness axis (W.2)

- trust_mean_rank: 1.0
- false_flag_count: 0
```json
{
  "hunt_id": "full_assembly_f4",
  "n_records": 859,
  "catch_count": 859,
  "catch_rate": 1.0,
  "trust_mean_rank": 1.0,
  "discovery_total": 515.4,
  "discovery_mean": 0.6,
  "false_flag_count": 0
}
```

- found_anchor: T1558.004 (botsv3)

## starvation_check (K.3): **PASS**

```json
{
  "verdict": "PASS",
  "findings": [],
  "min_fraction": 0.01
}
```

## Per-stage timings, records received, and outputs

- **resolve_indexes** (corpus_bed) -- OK, 0.0s, records_received=0
- **discover_index_range** (inject_plane) -- OK, 27.19s, records_received=0
- **investigate_anchors** (investigation_pivot) -- OK, 1.874s, records_received=0
- **plant_and_measure_cousins** (adaptive_scope) -- OK, 6.658s, records_received=0
- **stream_corpus_sample** (corpus_bed) -- OK, 388.394s, records_received=0
- **infer_field_roles** (field_roles) -- OK, 19.407s, records_received=38040
- **classify_telemetry** (telemetry_behavior) -- OK, 0.028s, records_received=38040
- **infer_universal_behaviors** (behavior_inference) -- OK, 0.165s, records_received=38040
- **build_artifact_graph** (artifact_graph) -- OK, 3.343s, records_received=38040
- **resolve_entities_and_timelines** (correlation) -- OK, 0.279s, records_received=38040
- **fit_baseline** (baseline) -- OK, 0.01s, records_received=38040
- **discover_and_cluster** (discovery) -- OK, 770.615s, records_received=38040
- **series_and_level** (series_cousin) -- OK, 0.003s, records_received=38040
- **level_match** (pyramid) -- OK, 1.644s, records_received=38040
- **grade_to_loop_contract** (loop_grader) -- OK, 0.019s, records_received=38040
- **resolve_unit_outcomes** (unit_outcome) -- OK, 0.044s, records_received=38040
- **raise_and_verdict_concerns** (analyst_loop) -- OK, 0.003s, records_received=38040

Total duration: 1219.68s

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
    "n_investigations": 1,
    "n_events": 6,
    "n_answer_key_entries_tried": 1,
    "found_technique": "T1558.004",
    "found_dataset": "botsv3"
  },
  "plant_and_measure_cousins": {
    "n_planted": 5,
    "dry_run": false,
    "inject_reports": [
      {
        "cousin_id": "cz-botsv3-T1558.004-000-REVOCABULARY-00-d0",
        "sourcetypes_used": [
          "wineventlog:security"
        ],
        "n_events": 3,
        "ok": true
      },
      {
        "cousin_id": "cz-botsv3-T1558.004-000-RESCHEMA-10-d0",
        "sourcetypes_used": [
          "wineventlog:security"
        ],
        "n_events": 3,
        "ok": true
      },
      {
        "cousin_id": "cz-botsv3-T1558.004-000-REIDENTITY-20-d0",
        "sourcetypes_used": [
          "wineventlog:security"
        ],
        "n_events": 3,
        "ok": true
      },
      {
        "cousin_id": "cz-botsv3-T1558.004-000-SCATTER-30-d0",
        "sourcetypes_used": [
          "wineventlog:security"
        ],
        "n_events": 3,
        "ok": true
      },
      {
        "cousin_id": "cz-botsv3-T1558.004-000-REORDER_MINOR-40-d0",
        "sourcetypes_used": [
          "wineventlog:security"
        ],
        "n_events": 3,
        "ok": true
      }
    ],
    "by_distance": {
      "0": {
        "total": 5,
        "reached": 5,
        "recall": 1.0
      }
    },
    "max_reached_distance": 0,
    "zero_hop_only": true
  },
  "stream_corpus_sample": {
    "n_records_wide_fit": 359772,
    "wide_fitted_units": 99049,
    "resumed_from_checkpoint": false,
    "n_sourcetypes_covered": 325,
    "n_sourcetypes_available": 430,
    "sample_report": {
      "algorithm_version": "score-sample-v1",
      "sourcetypes_seen": 245,
      "sourcetypes_sampled": 245,
      "records_seen": 359772,
      "records_sampled": 38040,
      "per_sourcetype_cap": 200,
      "sample_fraction": 0.105734,
      "truncated_at_max_total": false,
      "largest_sourcetype_share": 0.0053
    },
    "scorer_input_verdict": {
      "verdict": "OK",
      "reasons": [],
      "sourcetypes_in_scorer_input": 245,
      "sourcetypes_covered_by_stream": 325,
      "scorer_sourcetype_fraction": 0.7538,
      "largest_sourcetype_share": 0.0053
    },
    "coverage_note": "this run optimizes sourcetype/event-type coverage, not raw corpus volume -- corpus_fraction will read low against F.4's literal 0.10 floor by design (operator decision); see stage docstring"
  },
  "infer_field_roles": {
    "extraction_valid": true,
    "n_fields": 144
  },
  "classify_telemetry": {
    "algorithm_version": "telemetry-behavior-v1",
    "n_records": 38040,
    "n_classified": 5577,
    "coverage": 0.1466,
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
        "records": 3,
        "classified": 3,
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
        "classified": 152,
        "coverage": 0.76
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
        "classified": 21,
        "coverage": 0.105
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
        "records": 71,
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
      "enumerate": 2424,
      "execute": 472,
      "auth": 251,
      "escalate": 15,
      "c2_exfil": 1611,
      "collect": 203,
      "persist": 200,
      "lateral": 200,
      "evade": 201
    },
    "class_entropy_bits": 2.257,
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
      "enumerate": 0.4346,
      "execute": 0.0846,
      "auth": 0.045,
      "escalate": 0.0027,
      "c2_exfil": 0.2889,
      "collect": 0.0364,
      "persist": 0.0359,
      "lateral": 0.0359,
      "evade": 0.036
    },
    "source_concentration": {
      "enumerate": 0.0825,
      "execute": 0.4237,
      "auth": 0.7968,
      "escalate": 1.0,
      "c2_exfil": 0.1241,
      "collect": 0.9852,
      "persist": 1.0,
      "lateral": 1.0,
      "evade": 0.995
    },
    "concentration_reasons": [
      "class_concentration:enumerate=0.4346",
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
    "actions_profiled": 24,
    "schemas_seen": 5,
    "classes_inferred": 6,
    "cross_schema_classes": 1,
    "cross_schema_fraction": 0.1667,
    "largest_class_members": 17
  },
  "build_artifact_graph": {
    "n_artifacts": 38040,
    "n_units": 971
  },
  "resolve_entities_and_timelines": {
    "n_entities": 859,
    "n_timelines": 859
  },
  "fit_baseline": {
    "fitted_units": 100020
  },
  "discover_and_cluster": {
    "algorithm_version": "discovery-v1",
    "units_examined": 971,
    "discovered": 971,
    "rejected_unremarkable": 0,
    "rejected_incoherent": 0,
    "discovery_rate": 1.0,
    "n_clusters": 9
  },
  "series_and_level": {
    "n_series": 859
  },
  "level_match": {
    "n_matches": 9
  },
  "grade_to_loop_contract": {
    "assessments": 859
  },
  "resolve_unit_outcomes": {
    "n_outcomes": 971,
    "by_outcome": {
      "NOVEL": 971
    }
  },
  "raise_and_verdict_concerns": {
    "n_concerns": 0
  }
}
```
