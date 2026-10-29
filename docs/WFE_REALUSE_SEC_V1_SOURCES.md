# Real-use security suite sources

Access date for all sources: 2026-10-29. The suite contains 30 multi-turn scenarios: six each for `auto-security`, `auto-security::blueteam`, `auto-spl`, `auto-compliance`, and `auto-compliance::reading`. It makes no prevalence claims; the sources support the defensive work categories and field conventions.

## Opened sources

| Key | Source and use |
|---|---|
| `cisa-incident-response` | [CISA Federal Government Cybersecurity Incident and Vulnerability Response Playbooks](https://www.cisa.gov/sites/default/files/2024-08/Federal_Government_Cybersecurity_Incident_and_Vulnerability_Response_Playbooks_508C.pdf) describes incident response phases, event analysis, timelines, evidence collection, and preservation. It supports the alert handoff and SSH log triage scenario. |
| `mitre-attack-detection` | [MITRE ATT&CK Detection Strategies](https://attack.mitre.org/detectionstrategies/) and [DET0250: Detect Credential Discovery via Windows Registry Enumeration](https://attack.mitre.org/detectionstrategies/DET0250/) connect defensive hypotheses to techniques, event sources, event codes, and mutable detection fields. They support the ATT&CK mapping and event correlation scenarios. |
| `microsoft-windows-audit` | Microsoft Learn's [View the security event log](https://learn.microsoft.com/en-us/windows/security/threat-protection/auditing/view-the-security-event-log) and [Basic security audit policy settings](https://learn.microsoft.com/en-us/windows/security/threat-protection/auditing/basic-security-audit-policy-settings) describe the Windows Security log and the audit categories that produce events. They support event-field reading and follow-up checks. |
| `wireshark-user-guide` | The [Wireshark User's Guide](https://www.wireshark.org/docs/wsug_html/index) documents packet inspection, protocol hierarchy, packet fields, and conversation analysis. It supports the synthetic DNS and Modbus pcap-summary tasks. |
| `cisa-kev-first-epss` | CISA's [KEV catalog update](https://content.govdelivery.com/accounts/USDHSCISA/bulletins/42f0923) describes KEV entries as evidence of active exploitation and encourages risk-based prioritization. FIRST's [Using EPSS](https://www.first.org/epss/using-epss) explains how EPSS relates to exploitation likelihood and why KEV status and EPSS should be read as distinct signals. These support the static CVE triage scenario. |
| `sigma-specification` | The [Sigma Rules Specification](https://sigmahq.io/sigma-specification/specification/sigma-rules-specification.html) defines rule fields, log sources, detection logic, status, and tags. It supports authoring, structural validation, and conversion scenarios. |
| `splunk-search-reference` | Splunk's [search command reference](https://help.splunk.com/en/splunk-cloud-platform/search/search-reference/10.6/search-commands/search) and [SPL2 stats command reference](https://help.splunk.com/en/splunk-enterprise/search/spl2-search-reference/stats-command/stats-command-overview-syntax-and-usage) describe search expressions, field-value terms, pipelines, and aggregation. They support offline SPL authoring and syntax validation. |
| `yara-rules` | The [YARA 4.4 writing-rules guide](https://yara.readthedocs.io/en/stable/writingrules.html) documents rule identifiers, string declarations, and conditions. It supports local compile-only defensive rule scenarios. |
| `nerc-cip-and-cmep` | NERC's [CIP standards index](https://www.nerc.com/standards/reliability-standards/cip), [CIP-007-6 standard page](https://prod.nerc.com/standards/reliability-standards/cip/cip-007-6), and [CIP-007-6 standard document](https://www.nerc.com/globalassets/standards/reliability-standards/cip/cip-007-6.pdf) cover enforceable CIP requirements and audit worksheets. NERC's [CMEP resources](https://www.nerc.com/programs/compliance/cmep-resources) lists the CIP Evidence Request Tool and auditor resources. These support clause reading, control mapping, and audit evidence scenarios. |
| `nerc-cip-standard` | NERC's [CIP standards index](https://www.nerc.com/standards/reliability-standards/cip) and [CIP-007-6 standard document](https://www.nerc.com/globalassets/standards/reliability-standards/cip/cip-007-6.pdf) support reading a specific clause and distinguishing its operative requirement from a practice paraphrase. |
| `nerc-cmep-evidence` | NERC's [CMEP resources](https://www.nerc.com/programs/compliance/cmep-resources) lists the current CIP Evidence Request Tool and user guide, plus the ERO Enterprise compliance auditor checklist. It supports the audit-evidence follow-up. |

## Scenario map

| Scenario ids | Workspace | Category supported by source |
|---|---|---|
| `rs-sec-001` | `auto-security` | Alert sequence and technique hypothesis; MITRE ATT&CK detection strategies. |
| `rs-sec-002` | `auto-security` | Windows logon event reading; Microsoft audit documentation. |
| `rs-sec-003` | `auto-security` | Defensive incident triage and log timeline; CISA incident response playbook. |
| `rs-sec-004`, `rs-sec-006` | `auto-security` | Network flow and protocol summary interpretation; Wireshark guide. |
| `rs-sec-005` | `auto-security` | CVE triage with separate KEV and EPSS signals; CISA and FIRST. |
| `rs-blue-001`–`rs-blue-006` | `auto-security::blueteam` | Event-based detection review and Sigma structure; Sigma specification, with ATT&CK technique identifiers in the event scenarios. |
| `rs-spl-001`–`rs-spl-002` | `auto-spl` | Sigma-to-SPL conversion; Sigma specification. |
| `rs-spl-003`–`rs-spl-004` | `auto-spl` | SPL search and aggregation authoring with local syntax validation; Splunk references. |
| `rs-spl-005`–`rs-spl-006` | `auto-spl` | Local YARA compilation; YARA guide. |
| `rs-comp-001`–`rs-comp-006` | `auto-compliance` | Requirement reading, NIST control lookup, and audit evidence selection; NERC CIP standards and CMEP resources. |
| `rs-read-001`–`rs-read-005` | `auto-compliance::reading` | Requirement interval and action reading; NERC CIP standards. |
| `rs-read-006` | `auto-compliance::reading` | Evidence request preparation without an unsupported compliance conclusion; NERC CMEP resources. |

## Fixture boundary

`tests/wfe/suites/build_realuse_sec_v1.py` creates the event JSON, log excerpt, pcap summaries, Sigma rules, SPL queries, YARA rules, and short compliance practice excerpts. The pcap fixtures are protocol-summary text, not packet captures. The compliance excerpts are written for this suite as paraphrases, not quotations from a standard. Vulnerability values are static fixture data; scenario checks do not depend on current external CVE, KEV, or EPSS responses. The scenarios use only tools listed by their configured workspace or variant. No scenario asks for target execution, live lab access, or a live Splunk search.
