"""bully.bots_answer_key -- published techniques BOTS v1/v2/v3's official
Splunk write-ups confirm are present in the pre-indexed corpus.

Scorer-plane only (`answer_key_visibility: scorer_only`, C4): this module is
consulted by `corpus_bed.plan_cousins` to build injected needles, and never
imported by anything on the grading path. A cousin is only meaningful as a
variant of a technique known to be genuinely present -- inventing both the
haystack and the needle is what every bully run before this task did.

This is a small, illustrative curated set of the most widely documented BOTS
scenarios (Fin7's AS-REP roasting and HTTP C2 in BOTS v3, the Frothly
cryptomining scenario in BOTS v2, the Joomla/Struts web exploitation in BOTS
v1) -- not an exhaustive transcription of Splunk's full answer key, which is
far larger. `sourcetypes` name the general category BOTS ships that activity
under; C.2's live census (26-107 distinct sourcetypes per index) confirms
each category is genuinely present, not that this module enumerates every
event.

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
    ),
    AnswerKeyEntry(
        dataset="botsv3",
        technique="T1071.001",  # C2 over HTTP -- Fin7's beaconing, BOTS v3
        # http_beacon, periodic_checkin -- both stream:http records of the
        # same beaconing traffic -> c2_exfil, c2_exfil.
        behavioural_spine=("c2_exfil", "c2_exfil"),
        sourcetypes=("stream:http",),
    ),
    AnswerKeyEntry(
        dataset="botsv2",
        technique="T1496",  # Resource hijacking -- BOTS v2's Frothly cryptomining scenario
        # miner_process_spawn -> xmlwineventlog:sysmon EventCode 1 (process
        # create) -> execute; outbound_stratum_connection -> sysmon
        # EventCode 3 (network connection) -> c2_exfil.
        behavioural_spine=("execute", "c2_exfil"),
        sourcetypes=("xmlwineventlog:sysmon",),
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
    ),
)
