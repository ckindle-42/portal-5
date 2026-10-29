# R0b corpus fidelity dry run

Stamp: `20261029T013129Z__attack_data-4145e8b60fd8a3d44bc2170d1eb343fe7247387b__mordor-d9d40ef123d2c87d5d3df28c96bcab4f0faccc87__evtx_samples-missing__evtx_mitre-missing__invictus_ir-4667aa9c26330bc3317ed8bd526f4b83cff13602`

Mode: DRY-RUN. No index was created and no HEC events were sent.
Status: PARTIAL.

## Expected input counts

- **attack_data:** 1352 manifest tests (task baseline).
- **mordor:** 111 metadata datasets plus APT29 and APT3 (task baseline).
- **invictus_ir:** 2900 CloudTrail records (task baseline).

## Current source status

| Publisher | Commit | Dirty source paths |
|---|---|---:|
| attack_data | `4145e8b60fd8a3d44bc2170d1eb343fe7247387b` | 644 |
| mordor | `not acquired` | None |
| evtx_samples | `not acquired` | None |
| evtx_mitre | `not acquired` | None |
| invictus_ir | `4667aa9c26330bc3317ed8bd526f4b83cff13602` | 0 |

## Publisher counts

| Publisher | Tests | Files | Events parsed / would ship |
|---|---:|---:|---:|
| attack_data | 1095 | 1420 | 6572304 |
| mordor | 0 | 0 | 0 |
| evtx_samples | 0 | 0 | 0 |
| evtx_mitre | 0 | 0 | 0 |
| invictus_ir | 1 | 55 | 2900 |

## Sourcetype counts

| Sourcetype | Events |
|---|---:|
| MSExchange:Management | 2224 |
| OktaIM2:log | 107 |
| XmlWinEventLog | 5394163 |
| XmlWinEventLog:Microsoft-Windows-Sysmon/Operational | 15 |
| XmlWinEventLog:System | 1 |
| __json | 75 |
| attack_data:unknown | 10 |
| auditd | 7775 |
| aws:cloudfront:accesslogs | 1 |
| aws:cloudtrail | 37431 |
| aws:cloudtrail:lake | 62 |
| azure:monitor:aad | 659 |
| azure:monitor:activity | 9 |
| bro:conn:json | 22 |
| cisco:asa | 335 |
| cisco:cloud_security:dns | 3 |
| cisco:cloud_security:firewall | 345 |
| cisco:cloud_security:proxy | 480 |
| cisco:duo:administrator | 32 |
| cisco:ios | 124 |
| cisco:isovalent | 76 |
| cisco:isovalent:processConnect | 4 |
| cisco:isovalent:processExec | 7 |
| cisco:nvm:flowdata:v2 | 199 |
| cisco:sdwan:access | 3 |
| cisco:sdwan:syslog | 251 |
| cisco:secure_access:security_events_ravpn | 20 |
| cisco:sfw:estreamer | 11 |
| crowdstrike:events:sensor | 64 |
| crushftp:sessionlogs | 2810 |
| gsuite:gmail:bigquery | 4 |
| gws:reports:login | 43 |
| iis | 19895 |
| json_no_timestamp | 178 |
| linux_messages_syslog | 729 |
| linux_secure | 155 |
| log4j | 16 |
| mcp:jsonrpc | 1068 |
| nginx:plus:access | 303 |
| nginx:plus:kv | 332 |
| o365:graph:api | 188 |
| o365:management:activity | 9017 |
| ollama:server | 2094 |
| osquery:results | 106 |
| splunkd_ui_access | 16 |
| stash | 84 |
| stream:tcp | 2 |
| suricata | 383816 |
| sysmon:linux | 709615 |
| vmw-syslog | 210 |
| zscalernss-web | 15 |

## Source counts

| Sanitized source | Events |
|---|---:|
| `/var/log/auth` | 3 |
| `/var/log/kern` | 727 |
| `/var/log/nms/containers/service-proxy/serviceproxy-access.log` | 250 |
| `/var/log/osquery/osqueryd.results.log` | 3 |
| `/var/log/syslog` | 2 |
| `AuditLogs.SignIns` | 188 |
| `MSExchange:Management` | 2224 |
| `Okta` | 107 |
| `Syslog:Linux-Sysmon/Operational` | 709615 |
| `XmlWinEventLog` | 3767 |
| `XmlWinEventLog:Application` | 56 |
| `XmlWinEventLog:Auditing` | 536 |
| `XmlWinEventLog:MSSQLSERVER` | 25 |
| `XmlWinEventLog:Microsoft-Windows-Eventlog` | 17 |
| `XmlWinEventLog:Microsoft-Windows-IIS-W3SVC-WP` | 4 |
| `XmlWinEventLog:Microsoft-Windows-PowerShell/Operational` | 609875 |
| `XmlWinEventLog:Microsoft-Windows-ProcessExitMonitor` | 18 |
| `XmlWinEventLog:Microsoft-Windows-Security-SPP` | 1455 |
| `XmlWinEventLog:Microsoft-Windows-Sysmon/Operational` | 4712999 |
| `XmlWinEventLog:Microsoft-Windows-TaskScheduler` | 2 |
| `XmlWinEventLog:Microsoft-Windows-TerminalServices-RemoteConnectionManager` | 3 |
| `XmlWinEventLog:Security` | 61447 |
| `XmlWinEventLog:System` | 3972 |
| `XmlWinEventLog:Windows-Sysmon/Operational` | 3 |
| `__json` | 62 |
| `app.log` | 59 |
| `attack_data:unknown` | 10 |
| `auditd` | 7775 |
| `aws_asl` | 62 |
| `aws_cloudfront_accesslogs` | 1 |
| `aws_cloudtrail` | 37431 |
| `azure` | 659 |
| `bro` | 22 |
| `cisco:ios` | 74 |
| `cisco:isovalent` | 51 |
| `cisco:isovalent:processExec` | 5 |
| `cisco:sdwan:access` | 3 |
| `cisco:sdwan:syslog` | 1 |
| `cisco:sfw:estreamer` | 2 |
| `cisco_cloud_security_addon` | 828 |
| `cisco_isovalent` | 25 |
| `crowdstrike` | 64 |
| `crushftp:sessionlogs` | 2810 |
| `duo` | 32 |
| `gws:reports:login` | 43 |
| `http:bulkawsbedrock` | 178 |
| `http:gsuite` | 4 |
| `iis` | 19895 |
| `kubernetes` | 13 |
| `linux_secure` | 152 |
| `mcp.log` | 1068 |
| `nginx` | 303 |
| `nginx:plus:kv` | 332 |
| `not_applicable` | 728 |
| `o365` | 9016 |
| `o365:management:activity` | 1 |
| `osquery:results` | 103 |
| `server.log` | 2035 |
| `splunkd_ui_access` | 16 |
| `stream:tcp` | 2 |
| `suricata` | 383816 |
| `vmw-syslog` | 210 |
| `zscaler` | 15 |

## Host counts

| Sanitized host | Events |
|---|---:|
| `01566s-win16-ir.threebeesco.com` | 9 |
| `111111111111` | 28496 |
| `121521347698` | 75 |
| `121522247101` | 50 |
| `123599847101` | 93 |
| `123837392027` | 2900 |
| `151521547504` | 116 |
| `174313347505` | 10 |
| `591511666666` | 7 |
| `731544447609` | 1150 |
| `760111141337` | 4196 |
| `AITWSAP8NFSHOYS.aitne.intern` | 2 |
| `AR-LIN-1` | 3 |
| `AR-WIN-1` | 911 |
| `AR-WIN-DC` | 4 |
| `ATTACKPC.attackrange.local` | 64 |
| `ATTACK_PC.attackrange.lan` | 6 |
| `AttackBox-Win10` | 1743 |
| `DC01.doazlab.com` | 15 |
| `DC01.snapattack.labs` | 6 |
| `DESKTOP-39DIRD1` | 833 |
| `DESKTOP-92OQLA1` | 89 |
| `DESKTOP-ABC123.contoso.local` | 5 |
| `DESKTOP-DEF456.contoso.local` | 2 |
| `DESKTOP-FDRM976` | 1 |
| `DESKTOP-O4UAANR` | 1 |
| `Dev-Win10-1` | 5 |
| `EC2AMAZ-0DB3IKH` | 1 |
| `EC2AMAZ-1CL0VOR` | 3 |
| `EC2AMAZ-1QDNI6F` | 1 |
| `EC2AMAZ-2RSGUKB` | 30 |
| `EC2AMAZ-33G95PI` | 23 |
| `EC2AMAZ-34S98QL` | 9 |
| `EC2AMAZ-7DETGRN` | 14 |
| `EC2AMAZ-8HFGKTD` | 14 |
| `EC2AMAZ-9JTOML5` | 156 |
| `EC2AMAZ-CEMU0P7` | 8 |
| `EC2AMAZ-DQLCHMU` | 1 |
| `EC2AMAZ-EELNTI1` | 4 |
| `EC2AMAZ-EF4NERB` | 10 |
| `EC2AMAZ-EHFFLMC` | 1 |
| `EC2AMAZ-EOK3QDV` | 2 |
| `EC2AMAZ-FDH4SRN` | 9 |
| `EC2AMAZ-FMQTR36` | 4 |
| `EC2AMAZ-I1DH4UO` | 172 |
| `EC2AMAZ-I41BETP` | 22649 |
| `EC2AMAZ-I41BETP.attackrange.local` | 13993 |
| `EC2AMAZ-IANIF3B` | 5 |
| `EC2AMAZ-IPCFDUP` | 3 |
| `EC2AMAZ-J5R8T5M` | 16 |
| `EC2AMAZ-M3380E5` | 4 |
| `EC2AMAZ-NNKUICG` | 17 |
| `EC2AMAZ-QLNTJ56` | 4 |
| `EC2AMAZ-R83JA6I` | 43 |
| `EC2AMAZ-S1BSHGU` | 2 |
| `EC2AMAZ-S49B0M9` | 19 |
| `EC2AMAZ-T09VU2I` | 131 |
| `EC2AMAZ-TJL6EBN` | 143 |
| `EC2AMAZ-TLJH2O4` | 24117 |
| `EC2AMAZ-TLJH2O4.attackrange.local` | 7046 |
| `EC2AMAZ-UGL8NO0` | 10 |
| `HaagMSIX` | 3263 |
| `MSEDGEWIN10.snapattack.labs` | 5 |
| `SLABS-DC.snapattack.labs` | 3 |
| `WIN-GM4EB5GIVO0` | 58 |
| `WIN-QQ6SF2TB3S8` | 58 |
| `WIN10-21H1.attackrange.local` | 6 |
| `WIN10-21H1.snapattack.labs` | 19 |
| `WIN11-22H2` | 2 |
| `WIN11-22H2-X64.snapattack.labs` | 4 |
| `WS06.doazlab.com` | 4 |
| `Win10Victim` | 4 |
| `WinDev2202Eval` | 4 |
| `WinDev2204Eval` | 7 |
| `XmlWinEventLog` | 227 |
| `api-41e72ada.duosecurity.com` | 32 |
| `ar-linux` | 819 |
| `ar-linux-2` | 47 |
| `ar-win` | 353 |
| `ar-win-1` | 322 |
| `ar-win-1.attackrange.local` | 3 |
| `ar-win-10` | 4 |
| `ar-win-10.attackrange.local` | 208 |
| `ar-win-11.attackrange.local` | 2 |
| `ar-win-12.attackrange.local` | 2 |
| `ar-win-13.attackrange.local` | 2 |
| `ar-win-14.attackrange.local` | 2 |
| `ar-win-15.attackrange.local` | 2 |
| `ar-win-16.attackrange.local` | 2 |
| `ar-win-17.attackrange.local` | 2 |
| `ar-win-18.attackrange.local` | 2 |
| `ar-win-19.attackrange.local` | 2 |
| `ar-win-2` | 216 |
| `ar-win-2.attackrange.local` | 17352 |
| `ar-win-20.attackrange.local` | 2 |
| `ar-win-21.attackrange.local` | 2 |
| `ar-win-22.attackrange.local` | 2 |
| `ar-win-23.attackrange.local` | 2 |
| `ar-win-24.attackrange.local` | 2 |
| `ar-win-25.attackrange.local` | 2 |
| `ar-win-26.attackrange.local` | 2 |
| `ar-win-27.attackrange.local` | 2 |
| `ar-win-28.attackrange.local` | 2 |
| `ar-win-29.attackrange.local` | 2 |
| `ar-win-3` | 29 |
| `ar-win-3.attackrange.local` | 342 |
| `ar-win-30.attackrange.local` | 2 |
| `ar-win-31.attackrange.local` | 2 |
| `ar-win-32.attackrange.local` | 2 |
| `ar-win-33.attackrange.local` | 2 |
| `ar-win-34.attackrange.local` | 2 |
| `ar-win-35.attackrange.local` | 2 |
| `ar-win-36.attackrange.local` | 1 |
| `ar-win-37.attackrange.local` | 2 |
| `ar-win-38.attackrange.local` | 2 |
| `ar-win-39.attackrange.local` | 2 |
| `ar-win-4` | 10 |
| `ar-win-4.attackrange.local` | 175 |
| `ar-win-40.attackrange.local` | 2 |
| `ar-win-41.attackrange.local` | 2 |
| `ar-win-42.attackrange.local` | 2 |
| `ar-win-43.attackrange.local` | 2 |
| `ar-win-44.attackrange.local` | 2 |
| `ar-win-45.attackrange.local` | 2 |
| `ar-win-46.attackrange.local` | 2 |
| `ar-win-47.attackrange.local` | 2 |
| `ar-win-48.attackrange.local` | 2 |
| `ar-win-49.attackrange.local` | 2 |
| `ar-win-5` | 19 |
| `ar-win-5.attackrange.local` | 220 |
| `ar-win-50.attackrange.local` | 2 |
| `ar-win-51.attackrange.local` | 2 |
| `ar-win-52.attackrange.local` | 1 |
| `ar-win-55.attackrange.local` | 1 |
| `ar-win-6` | 4 |
| `ar-win-6.attackrange.local` | 216 |
| `ar-win-7` | 16 |
| `ar-win-7.attackrange.local` | 175 |
| `ar-win-8` | 16 |
| `ar-win-8.attackrange.local` | 175 |
| `ar-win-9` | 13 |
| `ar-win-9.attackrange.local` | 176 |
| `ar-win-dc` | 256 |
| `ar-win-dc-2` | 228 |
| `ar-win-dc.attackrange.local` | 5844 |
| `ar-win-dc2` | 54 |
| `ar-win.attackrange.local` | 8721 |
| `ar-win.nas.domain` | 57 |
| `attack_pc.attack_range.local` | 23 |
| `daftpunk.net` | 4 |
| `dangrus.EvilEmpireDC.org` | 1 |
| `dc.attack_range.lan` | 2 |
| `dc03-vm.lab3.localdomain` | 4 |
| `dummy-hostname.example.com` | 15 |
| `ip-0A000111.attackrange.local` | 2788 |
| `ip-10-0-254-126` | 1 |
| `ip-10-0-254-144` | 3 |
| `ip-10-0-254-161` | 2 |
| `ip-10-0-254-166` | 1 |
| `ip-10-0-254-177` | 7 |
| `ip-10-0-254-203` | 3 |
| `ip-10-0-254-35` | 3 |
| `ip-10-0-254-58` | 3 |
| `ip-10-0-254-65` | 3 |
| `ip-10-0-255-10` | 3 |
| `ip-10-0-255-129` | 3 |
| `ip-10-0-255-148` | 1 |
| `ip-10-0-255-249` | 7 |
| `ip-10-0-255-250` | 1 |
| `ip-10-0-255-66` | 3 |
| `ip-10-0-255-68` | 3 |
| `ip-10-0-255-92` | 6 |
| `ip-10-0-75-145` | 1 |
| `ip-10-0-76-137` | 4 |
| `ip-10-0-76-183` | 3 |
| `ip-10-0-76-196` | 3 |
| `ip-10-0-76-88` | 3 |
| `ip-172-16-0-50.us-east-2.compute.internal` | 1 |
| `mswin-ADFS.attackrange.local` | 20 |
| `mswin-dc01.attackrange.local` | 67 |
| `mswin-exch01.attackrange.local` | 29 |
| `mswin-server.attackrange.local` | 277 |
| `project-london-dc.iris.local` | 31109 |
| `project-london-host` | 240605 |
| `project-mumbai-dc.iris.local` | 33648 |
| `project-mumbai-host` | 287812 |
| `project-saopaulo-host` | 2556 |
| `soc101win11` | 26721 |
| `songoku` | 110 |
| `splunk-uf-test.rasoul-test.local` | 7 |
| `sysmonlinux-bpatel-44382-8629` | 2447 |
| `sysmonlinux-ctus-attack-range-2212` | 31564 |
| `sysmonlinux-ctus-attack-range-5501` | 80458 |
| `sysmonlinux-ctus-attack-range-6628` | 4955 |
| `sysmonlinux-ctus-attack-range-7283` | 15453 |
| `sysmonlinux-ctus-attack-range-8383` | 42892 |
| `sysmonlinux-mhaag-attack-range-8786` | 4 |
| `sysmonlinux-tcontreras-attack-range-1796` | 34682 |
| `sysmonlinux-tcontreras-attack-range-1898` | 24996 |
| `sysmonlinux-tcontreras-attack-range-216` | 171398 |
| `sysmonlinux-tcontreras-attack-range-4134` | 101971 |
| `sysmonlinux-tcontreras-attack-range-643` | 183145 |
| `sysmonlinux-tcontreras-attack-range-9361` | 14563 |
| `test-lab` | 6 |
| `ubun2004` | 3 |
| `ubuntu` | 13 |
| `ubuntu24` | 9 |
| `ubuntuuefi` | 6 |
| `unknown` | 1046045 |
| `vegeta` | 86 |
| `victim_pc.attack_range.lan` | 37 |
| `victim_pc.attack_range.local` | 38 |
| `win-client-4137150` | 6199 |
| `win-dc-11.attackrange.local` | 8785 |
| `win-dc-128.attackrange.local` | 85983 |
| `win-dc-129.attackrange.local` | 7190 |
| `win-dc-137.attackrange.local` | 2069 |
| `win-dc-141.attackrange.local` | 23519 |
| `win-dc-15.attackrange.local` | 6260 |
| `win-dc-156.attackrange.local` | 5657 |
| `win-dc-158.attackrange.local` | 5402 |
| `win-dc-169.attackrange.local` | 12584 |
| `win-dc-177.attackrange.local` | 15089 |
| `win-dc-1796611.attackrange.local` | 6225 |
| `win-dc-18.attackrange.local` | 9870 |
| `win-dc-185.attackrange.local` | 13170 |
| `win-dc-201.attackrange.local` | 5202 |
| `win-dc-228.attackrange.local` | 26141 |
| `win-dc-233.attackrange.local` | 12106 |
| `win-dc-235.attackrange.local` | 7921 |
| `win-dc-250.attackrange.local` | 14631 |
| `win-dc-255.attackrange.local` | 6230 |
| `win-dc-259.attackrange.local` | 7031 |
| `win-dc-262.attackrange.local` | 789 |
| `win-dc-266.attackrange.local` | 4369 |
| `win-dc-272.attackrange.local` | 15683 |
| `win-dc-281.attackrange.local` | 2949 |
| `win-dc-283.attackrange.local` | 9387 |
| `win-dc-291.attackrange.local` | 124166 |
| `win-dc-293.attackrange.local` | 206703 |
| `win-dc-299.attackrange.local` | 295444 |
| `win-dc-339.attackrange.local` | 20003 |
| `win-dc-342.attackrange.local` | 6324 |
| `win-dc-3574060.attackrange.local` | 6475 |
| `win-dc-362.attackrange.local` | 3129 |
| `win-dc-363.attackrange.local` | 4058 |
| `win-dc-365.attackrange.local` | 26109 |
| `win-dc-385.attackrange.local` | 4623 |
| `win-dc-387.attackrange.local` | 22727 |
| `win-dc-391.attackrange.local` | 7767 |
| `win-dc-392.attackrange.local` | 2208 |
| `win-dc-397.attackrange.local` | 31128 |
| `win-dc-410.attackrange.local` | 96846 |
| `win-dc-414.attackrange.local` | 3321 |
| `win-dc-417.attackrange.local` | 330 |
| `win-dc-429.attackrange.local` | 72867 |
| `win-dc-431.attackrange.local` | 18569 |
| `win-dc-444.attackrange.local` | 18020 |
| `win-dc-456.attackrange.local` | 5847 |
| `win-dc-463.attackrange.local` | 3193 |
| `win-dc-469.attackrange.local` | 24558 |
| `win-dc-480.attackrange.local` | 17783 |
| `win-dc-493.attackrange.local` | 6208 |
| `win-dc-495.attackrange.local` | 19332 |
| `win-dc-4997286.attackrange.local` | 6259 |
| `win-dc-500.attackrange.local` | 6390 |
| `win-dc-549.attackrange.local` | 5958 |
| `win-dc-553.attackrange.local` | 496 |
| `win-dc-555.attackrange.local` | 17736 |
| `win-dc-56.attackrange.local` | 104565 |
| `win-dc-575.attackrange.local` | 102 |
| `win-dc-58.attackrange.local` | 78880 |
| `win-dc-61.attackrange.local` | 6216 |
| `win-dc-622.attackrange.local` | 51561 |
| `win-dc-633.attackrange.local` | 13696 |
| `win-dc-638.attackrange.local` | 9533 |
| `win-dc-639.attackrange.local` | 8907 |
| `win-dc-644.attackrange.local` | 28784 |
| `win-dc-654.attackrange.local` | 46964 |
| `win-dc-655.attackrange.local` | 4120 |
| `win-dc-663.attackrange.local` | 7625 |
| `win-dc-676.attackrange.local` | 18828 |
| `win-dc-6764986.attackrange.local` | 7004 |
| `win-dc-681.attackrange.local` | 795 |
| `win-dc-690.attackrange.local` | 3448 |
| `win-dc-692.attackrange.local` | 6238 |
| `win-dc-704.attackrange.local` | 5598 |
| `win-dc-721.attackrange.local` | 7166 |
| `win-dc-7216619.attackrange.local` | 6386 |
| `win-dc-725.attackrange.local` | 287 |
| `win-dc-73.attackrange.local` | 86818 |
| `win-dc-748.attackrange.local` | 8533 |
| `win-dc-763.attackrange.local` | 10167 |
| `win-dc-770.attackrange.local` | 9358 |
| `win-dc-775.attackrange.local` | 25 |
| `win-dc-792.attackrange.local` | 3112 |
| `win-dc-800.attackrange.local` | 9842 |
| `win-dc-807.attackrange.local` | 7167 |
| `win-dc-819.attackrange.local` | 38901 |
| `win-dc-826.attackrange.local` | 9840 |
| `win-dc-837.attackrange.local` | 24959 |
| `win-dc-841.attackrange.local` | 761 |
| `win-dc-8537412.attackrange.local` | 7010 |
| `win-dc-86.attackrange.local` | 2576 |
| `win-dc-862.attackrange.local` | 526 |
| `win-dc-875.attackrange.local` | 6606 |
| `win-dc-876.attackrange.local` | 13009 |
| `win-dc-877.attackrange.local` | 128086 |
| `win-dc-888.attackrange.local` | 36648 |
| `win-dc-889.attackrange.local` | 58624 |
| `win-dc-89.attackrange.local` | 12582 |
| `win-dc-890.attackrange.local` | 10508 |
| `win-dc-892.attackrange.local` | 11618 |
| `win-dc-893.attackrange.local` | 6276 |
| `win-dc-906.attackrange.local` | 8088 |
| `win-dc-918.attackrange.local` | 6459 |
| `win-dc-919.attackrange.local` | 14473 |
| `win-dc-92.attackrange.local` | 6588 |
| `win-dc-930.attackrange.local` | 6556 |
| `win-dc-932.attackrange.local` | 2202 |
| `win-dc-934.attackrange.local` | 10155 |
| `win-dc-935.attackrange.local` | 8211 |
| `win-dc-942.attackrange.local` | 6274 |
| `win-dc-957.attackrange.local` | 6947 |
| `win-dc-960.attackrange.local` | 104009 |
| `win-dc-966.attackrange.local` | 9269 |
| `win-dc-970.attackrange.local` | 10575 |
| `win-dc-974.attackrange.local` | 17294 |
| `win-dc-982.attackrange.local` | 55635 |
| `win-dc-bpatel-09140-457.attackrange.local` | 2 |
| `win-dc-ct-attack-range-304.attackrange.local` | 26846 |
| `win-dc-ctus-attack-range-141.attackrange.local` | 25530 |
| `win-dc-ctus-attack-range-146.attackrange.local` | 3121 |
| `win-dc-ctus-attack-range-188.attackrange.local` | 18759 |
| `win-dc-ctus-attack-range-192.attackrange.local` | 3980 |
| `win-dc-ctus-attack-range-221.attackrange.local` | 6758 |
| `win-dc-ctus-attack-range-271.attackrange.local` | 9668 |
| `win-dc-ctus-attack-range-295.attackrange.local` | 4961 |
| `win-dc-ctus-attack-range-355.attackrange.local` | 9211 |
| `win-dc-ctus-attack-range-403.attackrange.local` | 25377 |
| `win-dc-ctus-attack-range-460.attackrange.local` | 10940 |
| `win-dc-ctus-attack-range-478.attackrange.local` | 10891 |
| `win-dc-ctus-attack-range-487` | 67 |
| `win-dc-ctus-attack-range-487.attackrange.local` | 119947 |
| `win-dc-ctus-attack-range-502.attackrange.local` | 18863 |
| `win-dc-ctus-attack-range-506.attackrange.local` | 1453 |
| `win-dc-ctus-attack-range-54.attackrange.local` | 4 |
| `win-dc-ctus-attack-range-574.attackrange.local` | 2 |
| `win-dc-ctus-attack-range-616.attackrange.local` | 2620 |
| `win-dc-ctus-attack-range-657.attackrange.local` | 62307 |
| `win-dc-ctus-attack-range-661.attackrange.local` | 14061 |
| `win-dc-ctus-attack-range-702.attackrange.local` | 7325 |
| `win-dc-ctus-attack-range-759.attackrange.local` | 6627 |
| `win-dc-ctus-attack-range-801.attackrange.local` | 28154 |
| `win-dc-ctus-attack-range-854.attackrange.local` | 86859 |
| `win-dc-ctus-attack-range-865.attackrange.local` | 51267 |
| `win-dc-ctus-attack-range-921.attackrange.local` | 44119 |
| `win-dc-ctus-attack-range-961.attackrange.local` | 1 |
| `win-dc-ctus-attack-range-994.attackrange.local` | 2916 |
| `win-dc-emcginnis-47905-664.attackrange.local` | 24 |
| `win-dc-exch01.attackrange.local` | 149 |
| `win-dc-lstella-22548-813.attackrange.local` | 3 |
| `win-dc-lstella-92811-83.attackrange.local` | 15 |
| `win-dc-lstella-92811-948.attackrange.local` | 8 |
| `win-dc-mhaag-attack-range-139.attackrange.local` | 9827 |
| `win-dc-mhaag-attack-range-206.attackrange.local` | 15 |
| `win-dc-mhaag-attack-range-270.attackrange.local` | 286 |
| `win-dc-mhaag-attack-range-331.attackrange.local` | 65 |
| `win-dc-mhaag-attack-range-540.attackrange.local` | 21 |
| `win-dc-mhaag-attack-range-602.attackrange.local` | 92 |
| `win-dc-mhaag-attack-range-622.attackrange.local` | 256 |
| `win-dc-mhaag-attack-range-702.attackrange.local` | 255 |
| `win-dc-mhaag-attack-range-84.attackrange.local` | 131 |
| `win-dc-mhaag-attack-range-909.attackrange.local` | 9 |
| `win-dc-mvelazco-02713-392.attackrange.local` | 553 |
| `win-dc-range-02713-392.attackrange.local` | 2 |
| `win-dc-root-17044-552.attackrange.local` | 4 |
| `win-dc-root-42062-811.attackrange.local` | 1 |
| `win-dc-tcontreras-attack-range-173.attackrange.local` | 16107 |
| `win-dc-tcontreras-attack-range-213.attackrange.local` | 1769 |
| `win-dc-tcontreras-attack-range-356.attackrange.local` | 16320 |
| `win-dc-tcontreras-attack-range-362.attackrange.local` | 9669 |
| `win-dc-tcontreras-attack-range-462.attackrange.local` | 5443 |
| `win-dc-tcontreras-attack-range-478.attackrange.local` | 1936 |
| `win-dc-tcontreras-attack-range-492.attackrange.local` | 2849 |
| `win-dc-tcontreras-attack-range-53.attackrange.local` | 9884 |
| `win-dc-tcontreras-attack-range-677.attackrange.local` | 14 |
| `win-dc-tcontreras-attack-range-682.attackrange.local` | 3695 |
| `win-dc-tcontreras-attack-range-72.attackrange.local` | 1324 |
| `win-dc-tcontreras-attack-range-891.attackrange.local` | 4523 |
| `win-host-10.attackrange.local` | 2917 |
| `win-host-100.attackrange.local` | 158 |
| `win-host-107` | 1167 |
| `win-host-11.attackrange.local` | 4107 |
| `win-host-14.attackrange.local` | 2877 |
| `win-host-166.attackrange.local` | 5388 |
| `win-host-236.attackrange.local` | 6759 |
| `win-host-243` | 1829 |
| `win-host-246.attackrange.local` | 23358 |
| `win-host-267.attackrange.local` | 10368 |
| `win-host-273.attackrange.local` | 5523 |
| `win-host-286.attackrange.local` | 2566 |
| `win-host-29.attackrange.local` | 1814 |
| `win-host-296.attackrange.local` | 16258 |
| `win-host-301` | 2695 |
| `win-host-316.attackrange.local` | 2320 |
| `win-host-340` | 14135 |
| `win-host-347.attackrange.local` | 649 |
| `win-host-353.attackrange.local` | 5370 |
| `win-host-36.attackrange.local` | 3634 |
| `win-host-374.attackrange.local` | 4343 |
| `win-host-439` | 2587 |
| `win-host-456.attackrange.local` | 7993 |
| `win-host-470.attackrange.local` | 6505 |
| `win-host-5.attackrange.local` | 85363 |
| `win-host-522` | 9445 |
| `win-host-542.attackrange.local` | 54349 |
| `win-host-574.attackrange.local` | 2726 |
| `win-host-61.attackrange.local` | 2742 |
| `win-host-623.attackrange.local` | 5512 |
| `win-host-672.attackrange.local` | 10835 |
| `win-host-681.attackrange.local` | 10096 |
| `win-host-692.attackrange.local` | 937 |
| `win-host-696.attackrange.local` | 99 |
| `win-host-702` | 44643 |
| `win-host-703` | 1766 |
| `win-host-724.attackrange.local` | 12714 |
| `win-host-8.attackrange.local` | 2969 |
| `win-host-847.attackrange.local` | 51800 |
| `win-host-867.attackrange.local` | 2686 |
| `win-host-874.attackrange.local` | 1670 |
| `win-host-884` | 5356 |
| `win-host-895.attackrange.local` | 2346 |
| `win-host-917.attackrange.local` | 6618 |
| `win-host-926.attackrange.local` | 10651 |
| `win-host-944` | 5316 |
| `win-host-96.attackrange.local` | 2391 |
| `win-host-977.attackrange.local` | 10518 |
| `win-host-979.attackrange.local` | 17096 |
| `win-host-987.attackrange.local` | 44043 |
| `win-host-ct-attack-range-726` | 3042 |
| `win-host-ctus-attack-range-102` | 9004 |
| `win-host-ctus-attack-range-115` | 8626 |
| `win-host-ctus-attack-range-140` | 4066 |
| `win-host-ctus-attack-range-144` | 7991 |
| `win-host-ctus-attack-range-17` | 8757 |
| `win-host-ctus-attack-range-176` | 2564 |
| `win-host-ctus-attack-range-212` | 27455 |
| `win-host-ctus-attack-range-225` | 4003 |
| `win-host-ctus-attack-range-245` | 4796 |
| `win-host-ctus-attack-range-249` | 30854 |
| `win-host-ctus-attack-range-276` | 6734 |
| `win-host-ctus-attack-range-306` | 4041 |
| `win-host-ctus-attack-range-328` | 3039 |
| `win-host-ctus-attack-range-459` | 6782 |
| `win-host-ctus-attack-range-538` | 37903 |
| `win-host-ctus-attack-range-589` | 4162 |
| `win-host-ctus-attack-range-635` | 4067 |
| `win-host-ctus-attack-range-732` | 3997 |
| `win-host-ctus-attack-range-780` | 4013 |
| `win-host-ctus-attack-range-801` | 848 |
| `win-host-ctus-attack-range-933` | 4132 |
| `win-host-mhaag-attack-range-117` | 107 |
| `win-host-mhaag-attack-range-128` | 4 |
| `win-host-mhaag-attack-range-18` | 282 |
| `win-host-mhaag-attack-range-563` | 1 |
| `win-host-mhaag-attack-range-569.attackrange.local` | 5 |
| `win-host-mhaag-attack-range-622` | 53 |
| `win-host-mhaag-attack-range-803` | 257 |
| `win-host-mhaag-attack-range-979` | 1768 |
| `win-host-mvelazco-02713-447.attackrange.local` | 809 |
| `win-host-root-17044-47.attackrange.local` | 4 |
| `win-host-tcontreras-attack-range-179` | 2624 |
| `win-host-tcontreras-attack-range-276` | 894 |
| `win-host-tcontreras-attack-range-292` | 1762 |
| `win-host-tcontreras-attack-range-468` | 868 |
| `win-host-tcontreras-attack-range-933` | 1776 |
| `win-host-tcontreras-attack-range-971` | 6578 |
| `win-host-tcontreras-attack-range-985` | 10656 |
| `win-host-test` | 1 |
| `win10-base` | 20 |
| `wks01-vm.lab3.localdomain` | 5 |
| `wks02-vm` | 1 |
| `ws106.elec.01.crimsonia.net` | 6 |
| `wsus-srv-01.contoso.local` | 5 |

## Fidelity counters

- Unknown sourcetype: 10 / 6575204 (0.00%).
- Unknown host: 1046045 / 6575204 (15.91%).
- Date-fallback timestamps: 648677 / 6575204 (9.87%).
- Missing event and manifest dates: 0 / 6575204 (0.00%).
- Leak replacements: source 6808, host 227.
- Residual leak values after sourcetype replacement: 2979.
- Distinct source values checked: 60.
- Distinct host values checked: 493.

## Cousins selected for deletion

Read-only Splunk census: raw 225, tstats 225, reconciled `True`.

| Source | Sourcetype | Host | Events |
|---|---|---|---:|
| `portal5:corpus:cousin:cz-T1071.001-REIDENTITY-20` | `stream:http` | `corpus-cousin-cz-T1071.001-REIDENTITY-20` | 10 |
| `portal5:corpus:cousin:cz-T1071.001-REORDER_MINOR-40` | `stream:http` | `corpus-cousin-cz-T1071.001-REORDER_MINOR-40` | 10 |
| `portal5:corpus:cousin:cz-T1071.001-RESCHEMA-10` | `wineventlog:security` | `corpus-cousin-cz-T1071.001-RESCHEMA-10` | 10 |
| `portal5:corpus:cousin:cz-T1071.001-REVOCABULARY-00` | `stream:http` | `corpus-cousin-cz-T1071.001-REVOCABULARY-00` | 10 |
| `portal5:corpus:cousin:cz-T1071.001-SCATTER-30` | `stream:http` | `corpus-cousin-cz-T1071.001-SCATTER-30` | 5 |
| `portal5:corpus:cousin:cz-T1071.001-SCATTER-30` | `wineventlog:security` | `corpus-cousin-cz-T1071.001-SCATTER-30` | 5 |
| `portal5:corpus:cousin:cz-T1190-REIDENTITY-20` | `stream:http` | `corpus-cousin-cz-T1190-REIDENTITY-20` | 10 |
| `portal5:corpus:cousin:cz-T1190-REORDER_MINOR-40` | `stream:http` | `corpus-cousin-cz-T1190-REORDER_MINOR-40` | 10 |
| `portal5:corpus:cousin:cz-T1190-RESCHEMA-10` | `wineventlog:security` | `corpus-cousin-cz-T1190-RESCHEMA-10` | 10 |
| `portal5:corpus:cousin:cz-T1190-REVOCABULARY-00` | `stream:http` | `corpus-cousin-cz-T1190-REVOCABULARY-00` | 10 |
| `portal5:corpus:cousin:cz-T1190-SCATTER-30` | `stream:http` | `corpus-cousin-cz-T1190-SCATTER-30` | 5 |
| `portal5:corpus:cousin:cz-T1190-SCATTER-30` | `wineventlog:security` | `corpus-cousin-cz-T1190-SCATTER-30` | 5 |
| `portal5:corpus:cousin:cz-T1496-REIDENTITY-20` | `xmlwineventlog:sysmon` | `corpus-cousin-cz-T1496-REIDENTITY-20` | 10 |
| `portal5:corpus:cousin:cz-T1496-REORDER_MINOR-40` | `xmlwineventlog:sysmon` | `corpus-cousin-cz-T1496-REORDER_MINOR-40` | 10 |
| `portal5:corpus:cousin:cz-T1496-RESCHEMA-10` | `stream:http` | `corpus-cousin-cz-T1496-RESCHEMA-10` | 10 |
| `portal5:corpus:cousin:cz-T1496-REVOCABULARY-00` | `xmlwineventlog:sysmon` | `corpus-cousin-cz-T1496-REVOCABULARY-00` | 10 |
| `portal5:corpus:cousin:cz-T1496-SCATTER-30` | `stream:http` | `corpus-cousin-cz-T1496-SCATTER-30` | 5 |
| `portal5:corpus:cousin:cz-T1496-SCATTER-30` | `wineventlog:security` | `corpus-cousin-cz-T1496-SCATTER-30` | 5 |
| `portal5:corpus:cousin:cz-T1558.004-REIDENTITY-20` | `wineventlog:security` | `corpus-cousin-cz-T1558.004-REIDENTITY-20` | 15 |
| `portal5:corpus:cousin:cz-T1558.004-REORDER_MINOR-40` | `wineventlog:security` | `corpus-cousin-cz-T1558.004-REORDER_MINOR-40` | 15 |
| `portal5:corpus:cousin:cz-T1558.004-RESCHEMA-10` | `stream:http` | `corpus-cousin-cz-T1558.004-RESCHEMA-10` | 15 |
| `portal5:corpus:cousin:cz-T1558.004-REVOCABULARY-00` | `wineventlog:security` | `corpus-cousin-cz-T1558.004-REVOCABULARY-00` | 15 |
| `portal5:corpus:cousin:cz-T1558.004-SCATTER-30` | `stream:http` | `corpus-cousin-cz-T1558.004-SCATTER-30` | 5 |
| `portal5:corpus:cousin:cz-T1558.004-SCATTER-30` | `wineventlog:security` | `corpus-cousin-cz-T1558.004-SCATTER-30` | 5 |
| `portal5:corpus:cousin:cz-T1558.004-SCATTER-30` | `xmlwineventlog:sysmon` | `corpus-cousin-cz-T1558.004-SCATTER-30` | 5 |

## Before/after shape

| Property | Publisher record | Current lab copy (task baseline 2026-10-10) | This run after |
|---|---|---|---|
| Sourcetype | Declared or event channel | About 10 Portal types plus `corpus:raw` | Not indexed in dry run |
| Source | Declared source or channel | `portal5:corpus:<src>:<test path>` | Not indexed in dry run |
| Host | Event host or account id | `corpus-<src>` | Not indexed in dry run |
| Body | XML, JSON, or line as published | Some Windows bodies flattened | Preserved by plan |

## Extraction checks

Not run: this lane does not create the index or ship events.

## Not ingested

- **flaws.cloud:** public CTF CloudTrail has no labels and is not benign background.
- **CloudTrail ATT&CK research:** an API-to-tactic table, not telemetry.
- **DARPA OpTC:** only the ground-truth PDF is present; the approximately 1 TB captures were not fetched.

## Missing or failed inputs

- Missing source tree: `mordor` (/Volumes/data01/portal5_hunt/sources/mordor).
- Missing source tree: `evtx_samples` (/Volumes/data01/portal5_hunt/sources/evtx_samples).
- Missing source tree: `evtx_mitre` (/Volumes/data01/portal5_hunt/sources/evtx_mitre).
- Read failure: `attack_data/windows-sysmon.log` (missing_file).
- Read failure: `attack_data/windows-sysmon.log` (missing_file).
- Read failure: `attack_data/windows-sysmon.log` (missing_file).
- Read failure: `attack_data/windows-sysmon.log` (missing_file).
- Read failure: `attack_data/windows-sysmon.log` (missing_file).
- Read failure: `attack_data/dns-sysmon.log` (missing_file).
- Read failure: `attack_data/windows-sysmon.log` (missing_file).
- Read failure: `attack_data/windows-sysmon.log` (missing_file).
- Read failure: `attack_data/windows-sysmon.log` (missing_file).
- Read failure: `attack_data/windows-sysmon.log` (missing_file).
- Read failure: `attack_data/windows-sysmon.log` (missing_file).
- Read failure: `attack_data/windows-sysmon.log` (missing_file).
- Read failure: `attack_data/wsus-suricata.log` (missing_file).
- Read failure: `attack_data/dataset_file.log` (missing_file).
- Read failure: `attack_data/react2shell.log` (missing_file).
- Read failure: `attack_data/copilot_prompts.log` (missing_file).
