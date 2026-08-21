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
"""

from __future__ import annotations

from .corpus_bed import AnswerKeyEntry

BOTS_ANSWER_KEY: tuple[AnswerKeyEntry, ...] = (
    AnswerKeyEntry(
        dataset="botsv3",
        technique="T1558.004",  # AS-REP Roasting -- BOTS v3's headline Fin7 scenario
        behavioural_spine=("kerberos_asrep_request", "hash_extraction", "offline_crack"),
        sourcetypes=("wineventlog:security",),
    ),
    AnswerKeyEntry(
        dataset="botsv3",
        technique="T1071.001",  # C2 over HTTP -- Fin7's beaconing, BOTS v3
        behavioural_spine=("http_beacon", "periodic_checkin"),
        sourcetypes=("stream:http",),
    ),
    AnswerKeyEntry(
        dataset="botsv2",
        technique="T1496",  # Resource hijacking -- BOTS v2's Frothly cryptomining scenario
        behavioural_spine=("miner_process_spawn", "outbound_stratum_connection"),
        sourcetypes=("xmlwineventlog:sysmon",),
    ),
    AnswerKeyEntry(
        dataset="botsv1",
        technique="T1190",  # Exploit public-facing app -- BOTS v1's web exploitation scenario
        behavioural_spine=("http_exploit_request", "webshell_drop"),
        sourcetypes=("stream:http",),
    ),
)
