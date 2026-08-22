"""bully.bots_answer_key -- published techniques BOTS v1/v2/v3's official
Splunk write-ups confirm are present in the pre-indexed corpus.

Scorer-plane only (`answer_key_visibility: scorer_only`, C4): this module is
consulted by `corpus_bed.plan_cousins` to build injected needles, and never
imported by anything on the grading path. A cousin is only meaningful as a
variant of a technique known to be genuinely present -- inventing both the
haystack and the needle is what every bully run before this task did.

F.3 (TASK_BULLY_FULL_ASSEMBLY_V1) expanded this from 4 illustrative entries to
a wider transcription of each dataset's own published write-up: BOTS v3
(Taedonggang's attack on the Frothly brewery, including its Fin7-style
Kerberoasting/HTTP-C2 phase already curated pre-F.3), BOTS v2 (Taedonggang
again, plus the Mallory/kutekitten insider-adjacent ransomware and
brewertalk.com web-attack strands), and BOTS v1 (P01s0n1vy's attack on Wayne
Enterprises' imreallynotbatman.com). Every dataset/technique/host/user/IP
pairing below is transcribed from a public BOTS write-up (Splunk's own BOTS
v3 GitHub pages and independently published community write-ups for v1/v2/v3),
not invented -- still a curated selection, not an exhaustive transcription of
each answer key, which is far larger. `sourcetypes` name the general category
BOTS ships that activity under; C.2's live census (26-107 distinct
sourcetypes per index) confirms each category is genuinely present, not that
this module enumerates every event.

`behavioural_spine` is expressed in the shared behaviour-class alphabet
(`telemetry_behavior.BEHAVIOR_CLASSES`), not mnemonic per-technique labels
(T1, TASK_BULLY_REAL_TELEMETRY_V1). `_stub_anchor_record` writes this spine
verbatim into an anchor's `action_sequence`, and `discovery.enrich()`
compares a discovered cluster's class-level `shared_shape` directly against
it -- a mnemonic label like `kerberos_asrep_request` can never match a
`shared_shape` built from real classified telemetry (`auth`, `escalate`,
...), which is why `floor_known_recall` measured 0.0 in C.6 even before the
classifier defect was visible. Each spine step is the class the technique's
OWN sourcetype/event id resolves to via `telemetry_behavior.classify_record`
(e.g. `wineventlog:security` EventCode 4768 -> `auth`), so the floor is
measured against the same vocabulary the classifier actually produces.
"""

from __future__ import annotations

from .corpus_bed import AnswerKeyEntry

BOTS_ANSWER_KEY: tuple[AnswerKeyEntry, ...] = (
    AnswerKeyEntry(
        dataset="botsv3",
        technique="T1558.004",  # AS-REP Roasting -- BOTS v3's headline Fin7 scenario
        # kerberos_asrep_request, hash_extraction (both wineventlog:security
        # 4768 kerberos TGT requests -- pre-auth-disabled AS-REQ then the
        # AS-REP carrying the crackable hash) -> auth, auth; offline_crack is
        # off-host (no BOTS telemetry) but the on-host follow-through BOTS
        # does capture is a privilege escalation -> escalate.
        behavioural_spine=("auth", "auth", "escalate"),
        sourcetypes=("wineventlog:security",),
        # The documented multi-stage chain of this scenario (A3,
        # TASK_BULLY_ADAPTIVE_REACH_V1): a public S3 bucket
        # (`frothlywebcode`) leaks AS-REP-roastable service-account
        # credentials (`web_admin`, `null_admin`), which lead to the
        # compromised endpoint (`BSTOLL-L`, discovered via its own user
        # `bstoll`). Five entities sharing NO identifier -- only a pivot
        # chain connects them. `reach_report` requires at least two
        # entities not collapsing to the anchor itself (A3); a single-
        # entity expectation (I.6's shape) is refused as degenerate.
        entities=("BSTOLL-L", "bstoll", "web_admin", "null_admin", "frothlywebcode"),
    ),
    AnswerKeyEntry(
        dataset="botsv3",
        technique="T1071.001",  # C2 over HTTP -- Fin7's beaconing, BOTS v3
        # http_beacon, periodic_checkin -- both stream:http records of the
        # same beaconing traffic -> c2_exfil, c2_exfil.
        behavioural_spine=("c2_exfil", "c2_exfil"),
        sourcetypes=("stream:http",),
        entities=("FYODOR-L", "45.77.53.176"),
    ),
    AnswerKeyEntry(
        # F.3 correction: the published Coinhive/Monero cryptomining incident
        # (Symantec EP signatures 30356/30358 on `BSTOLL-L`, the same host
        # this file's first entry names) is BOTS v3's, not v2's -- confirmed
        # against jamesgibbins.com/botsv3 and independent community
        # write-ups. Moved from `dataset="botsv2"` (pre-F.3) accordingly.
        dataset="botsv3",
        technique="T1496",  # Resource hijacking -- Frothly cryptomining on BSTOLL-L
        # miner_process_spawn -> xmlwineventlog:sysmon EventCode 1 (process
        # create) -> execute; outbound_stratum_connection -> sysmon
        # EventCode 3 (network connection) -> c2_exfil.
        behavioural_spine=("execute", "c2_exfil"),
        sourcetypes=("xmlwineventlog:sysmon",),
        entities=("BSTOLL-L", "bstoll"),
    ),
    AnswerKeyEntry(
        dataset="botsv3",
        technique="T1005",  # Data from Local System -- staged collection ahead of exfil
        # wineventlog:security 4663 object access attempted -> collect.
        behavioural_spine=("collect",),
        sourcetypes=("wineventlog:security",),
        entities=("ABUNGST-L", "abungstein@froth.ly"),
    ),
    AnswerKeyEntry(
        dataset="botsv1",
        technique="T1190",  # Exploit public-facing app -- BOTS v1's web exploitation scenario
        # http_exploit_request, webshell_drop -- both stream:http records
        # (the only sourcetype this entry declares) -> c2_exfil, c2_exfil.
        # Residual risk: stream:http's single mapping cannot distinguish an
        # exploit request from a webshell drop -- see module docstring.
        behavioural_spine=("c2_exfil", "c2_exfil"),
        sourcetypes=("stream:http",),
        entities=("imreallynotbatman.com", "192.168.250.70"),
    ),
    # ── F.3 (TASK_BULLY_FULL_ASSEMBLY_V1) additions ────────────────────────
    # botsv3 (Taedonggang vs. Frothly): jamesgibbins.com/botsv3, splunk/botsv3.
    AnswerKeyEntry(
        dataset="botsv3",
        technique="T1078",  # Valid Accounts -- reuse of a compromised domain account
        # wineventlog:security 4624 successful logon (the compromised
        # bgist@froth.ly account authenticating from an unexpected host)
        # -> auth.
        behavioural_spine=("auth",),
        sourcetypes=("wineventlog:security",),
        entities=("BGIST-L", "bgist@froth.ly"),
    ),
    AnswerKeyEntry(
        dataset="botsv3",
        technique="T1203",  # Exploitation for Client Execution -- macro-enabled phish opened
        # xmlwineventlog:sysmon EventCode 1 (process create) from the
        # spawned Office child process -> execute.
        behavioural_spine=("execute",),
        sourcetypes=("xmlwineventlog:sysmon",),
        entities=("FYODOR-L", "fyodor@froth.ly"),
    ),
    AnswerKeyEntry(
        dataset="botsv3",
        technique="T1190",  # Exploit public-facing app -- Struts2 (CVE-2017-9791) on the web tier
        # stream:http records of the exploit request against the gacrux
        # Tomcat/Struts host -> c2_exfil, c2_exfil.
        behavioural_spine=("c2_exfil", "c2_exfil"),
        sourcetypes=("stream:http",),
        entities=("gacrux.i-06fea586f3d3c8ce8", "tomcat7"),
    ),
    AnswerKeyEntry(
        dataset="botsv3",
        technique="T1110",  # Brute Force against a domain account
        # wineventlog:security 4625 repeated failed logon -> auth, auth.
        behavioural_spine=("auth", "auth"),
        sourcetypes=("wineventlog:security",),
        entities=("BTUN-L", "btun"),
    ),
    AnswerKeyEntry(
        dataset="botsv3",
        technique="T1098",  # Account Manipulation -- null_admin added to a privileged group
        # wineventlog:security 4732 member added to local group -> escalate.
        behavioural_spine=("escalate",),
        sourcetypes=("wineventlog:security",),
        entities=("null_admin", "web_admin"),
    ),
    AnswerKeyEntry(
        dataset="botsv3",
        technique="T1498",  # Network Denial of Service -- memcached amplification against hoth
        # stream:udp reflected/amplified traffic -> c2_exfil.
        behavioural_spine=("c2_exfil",),
        sourcetypes=("stream:udp",),
        entities=("hoth", "matar"),
    ),
    AnswerKeyEntry(
        dataset="botsv3",
        technique="T1046",  # Network Service Discovery -- hdoor.exe scanning
        # xmlwineventlog:sysmon EventCode 22 (DNS query) as the scan's
        # resolution traffic -> enumerate.
        behavioural_spine=("enumerate",),
        sourcetypes=("xmlwineventlog:sysmon",),
        entities=("PCERF-L", "svcvnc"),
    ),
    # botsv2 (Taedonggang vs. Frothly again, plus the Mallory/kutekitten and
    # brewertalk.com strands): christiant.io/splunkbotsv2 and companion
    # community write-ups.
    AnswerKeyEntry(
        dataset="botsv2",
        technique="T1566.001",  # Phishing: malicious attachment -- password-protected zip
        # stream:smtp delivery of the phishing email -> c2_exfil.
        behavioural_spine=("c2_exfil",),
        sourcetypes=("stream:smtp",),
        entities=("MACLORY-AIR13", "kutekitten"),
    ),
    AnswerKeyEntry(
        dataset="botsv2",
        technique="T1071.001",  # C2 over HTTP -- fpsaud beaconing to dynamic DNS
        # stream:http beaconing to the eidk.* dynamic-DNS domains ->
        # c2_exfil, c2_exfil.
        behavioural_spine=("c2_exfil", "c2_exfil"),
        sourcetypes=("stream:http",),
        entities=("MACLORY-AIR13", "eidk.duckdns.org"),
    ),
    AnswerKeyEntry(
        dataset="botsv2",
        technique="T1053.005",  # Scheduled Task -- PowerShell C2 persistence
        # wineventlog:security 4698 scheduled task created -> persist.
        behavioural_spine=("persist",),
        sourcetypes=("wineventlog:security",),
        entities=("MACLORY-AIR13", "kutekitten"),
    ),
    AnswerKeyEntry(
        dataset="botsv2",
        technique="T1486",  # Data Encrypted for Impact -- ransomware (.crypt) on kutekitten
        # wineventlog:security 4663 object access attempted, one per
        # encrypted-file touch -> collect.
        behavioural_spine=("collect",),
        sourcetypes=("wineventlog:security",),
        entities=("MACLORY-AIR13", "kIagerfield"),
    ),
    AnswerKeyEntry(
        dataset="botsv2",
        technique="T1190",  # Exploit public-facing app -- SQLi on brewertalk.com/member.php
        # stream:http records of the updatexml() injection -> c2_exfil,
        # c2_exfil.
        behavioural_spine=("c2_exfil", "c2_exfil"),
        sourcetypes=("stream:http",),
        entities=("www.brewertalk.com", "45.77.65.211"),
    ),
    AnswerKeyEntry(
        dataset="botsv2",
        technique="T1059.001",  # PowerShell -- Empire framework deployment
        # xmlwineventlog:sysmon EventCode 1 (process create) for
        # powershell.exe -> execute.
        behavioural_spine=("execute",),
        sourcetypes=("xmlwineventlog:sysmon",),
        entities=("MACLORY-AIR13", "kIagerfield"),
    ),
    AnswerKeyEntry(
        dataset="botsv2",
        technique="T1091",  # Replication Through Removable Media -- Alcor Micro USB malware
        # xmlwineventlog:sysmon EventCode 11 (file created) for the
        # USB-delivered dropper -> persist.
        behavioural_spine=("persist",),
        sourcetypes=("xmlwineventlog:sysmon",),
        entities=("MACLORY-AIR13", "kutekitten"),
    ),
    AnswerKeyEntry(
        dataset="botsv2",
        technique="T1583.001",  # Acquire Infrastructure: Domains -- eidk.* dynamic DNS
        # stream:dns resolution of the dynamic-DNS C2 domains -> enumerate.
        behavioural_spine=("enumerate",),
        sourcetypes=("stream:dns",),
        entities=("eidk.hopto.org", "eidk.duckdns.org"),
    ),
    AnswerKeyEntry(
        dataset="botsv2",
        technique="T1005",  # Data from Local System -- staged files ahead of exfil/encryption
        # wineventlog:security 4663 object access attempted -> collect.
        behavioural_spine=("collect",),
        sourcetypes=("wineventlog:security",),
        entities=("MACLORY-AIR13", "kutekitten"),
    ),
    # botsv1 (P01s0n1vy vs. Wayne Enterprises' imreallynotbatman.com):
    # community write-ups (jayngng, andickinson, and others).
    AnswerKeyEntry(
        dataset="botsv1",
        technique="T1595.002",  # Active Scanning: Vulnerability Scanning -- Acunetix
        # stream:http scan traffic against the Joomla site -> c2_exfil.
        behavioural_spine=("c2_exfil",),
        sourcetypes=("stream:http",),
        entities=("40.80.148.42", "imreallynotbatman.com"),
    ),
    AnswerKeyEntry(
        dataset="botsv1",
        technique="T1110",  # Brute Force -- Joomla admin panel
        # stream:http repeated login POSTs against /joomla/administrator ->
        # c2_exfil, c2_exfil.
        behavioural_spine=("c2_exfil", "c2_exfil"),
        sourcetypes=("stream:http",),
        entities=("23.22.63.114", "imreallynotbatman.com"),
    ),
    AnswerKeyEntry(
        dataset="botsv1",
        technique="T1071.001",  # C2 over HTTP -- webshell follow-through after brute force
        # stream:http webshell command traffic on the secondary victim ->
        # c2_exfil.
        behavioural_spine=("c2_exfil",),
        sourcetypes=("stream:http",),
        entities=("192.168.250.40", "imreallynotbatman.com"),
    ),
    AnswerKeyEntry(
        dataset="botsv1",
        technique="T1583",  # Acquire Infrastructure -- P01s0n1vy's phishing domain infra
        # stream:dns resolution of the lookalike phishing domains -> enumerate.
        behavioural_spine=("enumerate",),
        sourcetypes=("stream:dns",),
        entities=("40.80.148.42", "imreallynotbatman.com"),
    ),
    AnswerKeyEntry(
        dataset="botsv1",
        technique="T1592",  # Gather Victim Host Information -- recon ahead of the scan
        # stream:dns resolution traffic from the reconnaissance host ->
        # enumerate.
        behavioural_spine=("enumerate",),
        sourcetypes=("stream:dns",),
        entities=("23.22.63.114", "imreallynotbatman.com"),
    ),
    AnswerKeyEntry(
        dataset="botsv1",
        technique="T1071.001",  # C2 over HTTP -- webshell command channel on the primary victim
        # stream:http webshell command traffic on the primary Joomla host ->
        # c2_exfil.
        behavioural_spine=("c2_exfil",),
        sourcetypes=("stream:http",),
        entities=("192.168.250.70", "imreallynotbatman.com"),
    ),
)
