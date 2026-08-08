---
id: SEC_BENCH-combined-corpus-validation-20260731
kind: what
title: Combined corpus blue validation and detection-design backlog (2026-07-31)
sources:
- type: bench-security
  path: bench-run:combined-corpus-blue-validation:2026-07-31
- type: code
  path: portal/modules/security/core/corpus_coverage.py
- type: code
  path: portal/modules/security/core/blue_orchestrate.py
- type: code
  path: portal/modules/security/core/exec_chain.py
- type: code
  path: portal/modules/security/core/siem/capture_enrichment.py
- type: code
  path: scripts/security_replay_verify.py
- type: code
  path: config/security_corpus.yaml
last_generated_commit: 9623f6b25b3e922bd0cf4b3885a926a4728b26a1
claims: []
confidence: high
tags:
- agentic-blue
- corpus
- detection-design
- provenance
- purple-team
- security
- validation
- verified-v1
created_at: 1785540000.0
updated_at: 1785634440.0
---

The live-probed combined-corpus gate passed at this stopping point. The planning
catalog holds 93 scenario entries, of which 21 are theory or generic web/cloud
entries with no deployed replay target and are explicitly excluded, with reasons,
by the corpus contract — leaving 72 backed lab exercises. Thirty-six of the 72
now have schema-v2, episode-scoped, scenario-valid Portal captures with real
PCAPs. The live lane covers 9 target techniques, the current live-probed external
labeled lane intersects 14, and their union covers 18 of the 25 backed target
techniques. This means the available data is safe to use for detection design;
it does not mean blue quality passed, and external data remains ineligible as
lab-scenario proof.

The first twelve scoreable captures were shipped through the production replay
path and independently confirmed indexed in Splunk. The twelfth is
`vuln_struts2_rce`: its first recapture exposed a malformed command payload,
and its corrected capture now requires both the S2-045 sandbox-bypass request
and correlated `X-Cmd-Output: uid=... gid=...` response evidence. Detection-only
`X-Test` output, an exploit-shaped request without command proof, and identity
output without the exploit request are all negative controls and cannot certify
T1190.

The source-stratified strong three-section validation produced:

| Lane | Cells | Confirmed | Exact | Parent | Tactic |
| --- | ---: | ---: | ---: | ---: | ---: |
| Portal live capture replay | 11 | 0 | 0 | 0 | 0 |
| Public labeled corpus | 16 | 5 | 1 | 2 | 3 |

The external exact hit was T1190. T1003.003 was reported only as parent T1003;
T1189 was reported as same-tactic T1190. The other confirmed cells,
T1552.005 and T1595, were misclassified. The live verdict distribution was
eight `RULED_OUT`, two `ANOMALOUS_UNCLASSIFIED`, and one `UNRESOLVED`.

The three Meta3 captures had stale stored target metadata (`10.10.11.10`) after
DHCP repair moved vmid 113 to `10.10.11.13`. Replay now resolves the current
catalog target and reports the stale metadata as a warning. A corrected rerun
verified all three cells queried `.13`; all remained `RULED_OUT`, so target
drift was a real correctness defect but not the dominant recall failure.

The packet captures themselves contain the expected discriminators: the
phpMyAdmin capture includes `/phpmyadmin/`, `pma_username`, and
`nt authority\local service`; Rails includes `/missing404`, `web_console`, and
`nt authority\system`. The retriever instead returned benign leading ICMPv6
records as its representative packet sample, then repeatedly requested
irrelevant Windows log data. HugeGraph also reached decoded `uid=0(root)`
response evidence but exhausted orchestration without classification. The
primary failure is therefore evidence selection and convergence, not missing
red execution proof.

Detection design proceeds in this order:

1. Relevance-rank decoded HTTP request/response and packet evidence before
   representative sampling; preserve scenario-neutral operation while making
   T1190 and T1059 discriminators retrievable.
2. Stop host-log fallback when the requested source is absent and strong
   network/application evidence is already available; prevent repeated
   irrelevant Windows queries for Linux/web episodes.
3. Add deterministic convergence for high-confidence execution response
   evidence such as `uid=... gid=...`, then validate HugeGraph and the other
   web exploit captures.
4. Improve exact technique discrimination for T1552.005, T1595, T1189, and
   T1003.003.
5. Design the Windows/AD discriminators for T1558.003, T1558.004, T1110.003,
   T1078, T1550.002, and T1557.001; then convert T1053.005, T1083, and T1552
   from anomaly-only outcomes to classified findings.
6. Acquire or produce valid data before scoring the remaining backed coverage
   gaps: T1003.001, T1003.006, T1021.002, T1059.004, T1203, T1210,
   T1505.003, T1548.001, and T1592.

Spine-coverage expansion remains deferred until this design and validation
backlog is complete.

## Why

This record exists because a validation gate is only trustworthy if the
numbers behind it are re-derivable from the corpus contract and the
scenario catalog that produced them. The catalog totals and exclusions
are grounded in `config/security_corpus.yaml` (`scenario_scope:
excluded_from_lab_replay`) and `portal/modules/security/core/exec_chain.py`
(`SCENARIOS`), and the replay/provenance semantics are grounded in the
replay and capture scripts it cites — so the "93/21/72" and technique
coverage figures in this record can be recomputed instead of taken on
faith. The update block on 2026-08-01 documents what changed since the
original stopping point, preserving the historical verdict while keeping
the record honest about its own revision.

## Stopping point and resume order

The deterministic recipe lane has certified the current Vulhub batch through
`vuln_laravel_rce`. The last capture proves both T1190 and T1059 with a
correlated Ignition request and an independent target-side file postcondition.
The attack image contract was hardened at the same boundary so an empty support
artifact can no longer pass verification.

**Update 2026-08-01: items 1–3 below are done.** Item 1 (Drupal/Gitea/
phpMyAdmin target setup) and item 2 (Confluence theory classification) were
completed and pushed in an earlier pass. Item 3 (legacy VM + mission recapture)
is now complete: all 7 legacy-VM scenarios, 16 of 21 Meta3 scenarios (4
deferred, see below), and all 5 mission scenarios were live-verified through
`scripts/security_capture_recipes.py`, certified on 2 consecutive runs each,
and pushed to `main` (commits `896ed501`…`30db5863`). Several pre-existing
infra bugs were root-caused and fixed along the way rather than worked around:
`collect.py`'s `since` UnboundLocalError (silently broke all AD-only
`windows:security` collection), `blue.py`'s meta3 DHCP-drift telemetry
mis-routing, and multiple missing-`target_host`/missing-`vulhub_env` scenario
definitions that had never actually resolved a real target. A recurring
ground-truth correction also surfaced repeatedly: several scenarios declared
`T1059.004` (Unix Shell) for evidence that was actually a Windows `cmd.exe`/
PowerShell exec (real ID: `T1059`) — corrected wherever found, following the
precedent `meta3_tomcat_manager`'s own signal patterns had already set.

Four Meta3 scenarios remain deferred as structurally blocked, not merely
unattempted:
- `meta3_axis2_deploy` — a live msf deploy with an untested default payload
  crashed the Meta3 VM outright; axis2:axis2 creds are confirmed
  check-vulnerable, but no safe retry (a payload confirmed to have a
  reachable LHOST) has been attempted since.
- `meta3_glassfish_deploy` — no working admin credential found despite
  extensive guessing and reading the SHA-256-hashed admin-keyfile.
- `meta3_manageengine` — persistent 503 confirmed structural: Apache's
  mod_jk AJP proxy to the Tomcat backend is broken even from loopback on the
  target itself, with all proxy modules commented out in `httpd.conf`.
- `meta3_web_exploit` — vague multi-port scenario with no technique beyond
  what `meta3_iis_http` already covers; no distinct exploit to recapture.

**What remains: item 4.** Re-run live replay for every valid capture,
regenerate the source-stratified corpus report, and only then resume the
six-step detection-design backlog above (still fully unstarted). Spine-coverage
expansion remains deferred until that backlog is complete. The four deferred
Meta3 scenarios above should be revisited opportunistically but are not
blocking item 4.

<!-- Original resume order, kept for reference; the numbered items above are
     resolved as of 2026-08-01 except where noted. -->

1. Reconcile target setup and proof contracts for `vuln_drupal_rce`,
   `vuln_gitea_rce`, and `vuln_phpmyadmin_rce`.
2. Decide whether `vuln_confluence_rce` has a reproducible initialized,
   licensed lab target. Keep it in the lab denominator only if that target
   contract can be satisfied; otherwise classify it explicitly as theory.
3. Add deterministic recipes and recapture the legacy VM families:
   `ad_full_compromise`, `asrep_to_lateral`, `ctf_multi_service`,
   `kerberoast_to_da`, `mbptl_ctf_full_chain`, `relay_to_shell`, and
   `web_to_root`; the remaining Meta3 scenarios (`meta3_axis2_deploy`,
   `meta3_elasticsearch_rce`, `meta3_ftp_backdoor`, `meta3_full_chain`,
   `meta3_glassfish_deploy`, `meta3_iis_http`, `meta3_jenkins_rce`,
   `meta3_jmx_rce`, `meta3_linux_privesc`, `meta3_manageengine`,
   `meta3_mysql_exploit`, `meta3_psexec`, `meta3_smb_exploit`,
   `meta3_snmp_enum`, `meta3_ssh_brute`, `meta3_struts_rce`,
   `meta3_tomcat_manager`, `meta3_web_exploit`, `meta3_webdav_upload`,
   `meta3_winrm_weakpass`, and `meta3_wordpress_ninja`); and the mission
   scenarios (`mission_ad_enumerate_exploit`, `mission_meta3_lateral_pivot`,
   `mission_meta3_recon_exploit`, `mission_vulhub_multi_target`, and
   `mission_vulhub_web_exploit`).
4. Re-run live replay for every valid capture, regenerate the source-stratified
   corpus report, and only then resume the six-step detection-design backlog
   above. Spine-coverage expansion remains deferred.
