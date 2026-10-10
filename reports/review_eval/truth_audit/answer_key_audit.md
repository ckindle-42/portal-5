# BOTS answer-key audit

1 of 27 entries have no problem.

| dataset | technique | problems |
|---|---|---|
| botsv3 | T1558.004 | entity_absent_in_declared_sourcetypes:BSTOLL-L; entity_absent_in_declared_sourcetypes:bstoll; entity_absent_in_declared_sourcetypes:web_admin; entity_absent_in_declared_sourcetypes:null_admin; entity_absent_in_declared_sourcetypes:frothlywebcode |
| botsv3 | T1071.001 | entity_absent_in_declared_sourcetypes:FYODOR-L |
| botsv3 | T1496 | sourcetype_absent:xmlwineventlog:sysmon; entity_absent_in_declared_sourcetypes:BSTOLL-L; entity_absent_in_declared_sourcetypes:bstoll |
| botsv3 | T1005 | entity_absent_in_declared_sourcetypes:ABUNGST-L; entity_absent_in_declared_sourcetypes:abungstein@froth.ly |
| botsv1 | T1190 | entity_on_every_sensor_day:192.168.250.70; same_entity_set_as:botsv1:T1071.001 |
| botsv3 | T1078 | entity_absent_in_declared_sourcetypes:BGIST-L; entity_absent_in_declared_sourcetypes:bgist@froth.ly |
| botsv3 | T1203 | sourcetype_absent:xmlwineventlog:sysmon; entity_absent_in_declared_sourcetypes:FYODOR-L; entity_absent_in_declared_sourcetypes:fyodor@froth.ly |
| botsv3 | T1190 | entity_absent_in_declared_sourcetypes:gacrux.i-06fea586f3d3c8ce8 |
| botsv3 | T1110 | entity_absent_in_declared_sourcetypes:BTUN-L; entity_absent_in_declared_sourcetypes:btun |
| botsv3 | T1098 | entity_absent_in_declared_sourcetypes:null_admin; entity_absent_in_declared_sourcetypes:web_admin |
| botsv3 | T1498 | entity_absent_in_declared_sourcetypes:hoth; entity_absent_in_declared_sourcetypes:matar |
| botsv3 | T1046 | sourcetype_absent:xmlwineventlog:sysmon; entity_absent_in_declared_sourcetypes:PCERF-L; entity_absent_in_declared_sourcetypes:svcvnc |
| botsv2 | T1566.001 | entity_absent_in_declared_sourcetypes:MACLORY-AIR13; entity_absent_in_declared_sourcetypes:kutekitten; same_entity_set_as:botsv2:T1053.005,botsv2:T1091,botsv2:T1005 |
| botsv2 | T1071.001 | entity_absent_in_declared_sourcetypes:MACLORY-AIR13; entity_absent_in_declared_sourcetypes:eidk.duckdns.org |
| botsv2 | T1053.005 | entity_absent_in_declared_sourcetypes:MACLORY-AIR13; entity_absent_in_declared_sourcetypes:kutekitten; same_entity_set_as:botsv2:T1566.001,botsv2:T1091,botsv2:T1005 |
| botsv2 | T1486 | entity_absent_in_declared_sourcetypes:MACLORY-AIR13; entity_absent_in_declared_sourcetypes:kIagerfield; same_entity_set_as:botsv2:T1059.001 |
| botsv2 | T1190 | entity_on_every_sensor_day:www.brewertalk.com |
| botsv2 | T1059.001 | sourcetype_absent:xmlwineventlog:sysmon; entity_absent_in_declared_sourcetypes:MACLORY-AIR13; entity_absent_in_declared_sourcetypes:kIagerfield; same_entity_set_as:botsv2:T1486 |
| botsv2 | T1091 | sourcetype_absent:xmlwineventlog:sysmon; entity_absent_in_declared_sourcetypes:MACLORY-AIR13; entity_absent_in_declared_sourcetypes:kutekitten; same_entity_set_as:botsv2:T1566.001,botsv2:T1053.005,botsv2:T1005 |
| botsv2 | T1583.001 | entities_never_share_an_event |
| botsv2 | T1005 | entity_absent_in_declared_sourcetypes:MACLORY-AIR13; entity_absent_in_declared_sourcetypes:kutekitten; same_entity_set_as:botsv2:T1566.001,botsv2:T1053.005,botsv2:T1091 |
| botsv1 | T1595.002 | same_entity_set_as:botsv1:T1583 |
| botsv1 | T1110 | same_entity_set_as:botsv1:T1592 |
| botsv1 | T1071.001 | none |
| botsv1 | T1583 | entity_absent_in_declared_sourcetypes:40.80.148.42; entity_absent_in_declared_sourcetypes:imreallynotbatman.com; same_entity_set_as:botsv1:T1595.002 |
| botsv1 | T1592 | entity_absent_in_declared_sourcetypes:imreallynotbatman.com; same_entity_set_as:botsv1:T1110 |
| botsv1 | T1071.001 | entity_on_every_sensor_day:192.168.250.70; same_entity_set_as:botsv1:T1190 |
