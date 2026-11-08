"""bully.telemetry_behavior -- behaviour classes from REAL telemetry.

The defect this closes was masked for eight runs and became the whole result
the moment the hunt stood on real data. In the C.6 corpus run every cousin
cluster's shared shape was:

    cc-0045: {'unknown': 4912, 'other': 1}
    cc-0046: {'unknown': 1339, 'other': 39}
    cc-0049: {'unknown': 83}

Real BOTS verbs classify to `unknown`, so clusters formed on the ABSENCE of
classification -- everything is unknown, so everything resembles everything.
That cascaded into `discovery_rate 0.964`, degeneracy `0.915
ANOMALOUS_UNCLASSIFIED`, background false-positive rate `0.911`, and most
damningly `floor_known_recall 0.0`: zero of four techniques recovered from a
corpus that PUBLISHES the answers, while injected cousins scored 0.4 because
we generated them with spines we chose.

Why the previous approaches could not work on real data:

  * `pyramid.default_behavior_classifier` is a substring table over verb text.
    Real telemetry does not carry verbs: a Windows logon is EventCode `4624`,
    a Sysmon process create is `1`, a DNS query is a `stream:dns` record with
    a `query` field, a Suricata alert is a signature id. There is no verb to
    match.
  * `behavior_classifier`'s learned model was fitted on `universe.py`'s
    synthetic tokens, which embed the class name in the string. With zero
    seen trigrams naive Bayes reduces to `argmax(prior)` and `_MIN_CONFIDENCE`
    gates on the prior, so an unrecognisable real verb takes the majority
    class -- and the majority class was `collect` at 95.8%.

The correction is to read behaviour the way the telemetry actually encodes
it: **per sourcetype, from the fields that sourcetype uses**. A Windows
security log means something specific by `4624`; `stream:dns` means something
specific by a query record; `pan:traffic` means something by an allow. These
are documented, stable, vendor-defined semantics -- not guesses, and not a
model that has to learn them from tokens that do not exist.

This is deliberately NOT a signature database. It maps an observable to a
BEHAVIOUR CLASS (auth, enumerate, execute, escalate, collect, destroy,
persist, evade, lateral, c2_exfil) -- the same small alphabet the pyramid and
series work already use. It says "this event is an authentication", never
"this event is technique T1078". Naming a technique remains enrichment, and
discovery remains data-intrinsic.

Coverage is honest: a sourcetype with no mapping returns `""` (unclassified),
never `unknown` or a majority-class guess, so an unreadable source is visibly
unreadable rather than silently uniform. `coverage_report` publishes per-
sourcetype classified fractions and the output-class entropy so a collapse is
detectable the way C.6's was not.

Pure compute (COLD). No I/O, no model, no training.

**This module is scoped to answer-keyed corpora, and is a VALIDATION
INSTRUMENT, never the primary discovery path** (I.5, TASK_BULLY_
INVESTIGATION_V1). It is a curated, per-sourcetype mapping over a fixed
ten-class alphabet chosen in advance -- on universal data there is no reason
that alphabet is the right one, and no amount of table-writing closes the
gap (T.3 left ~100 sourcetypes unreadable: `OktaIM2:log`, `ms:aad:signin`,
`windows:powershell`, `aws:cloudtrail`, every `gen:*`). `behavior_inference`
is the universal path: it infers behaviour classes from OBSERVABLE
STRUCTURE, with no table and no fixed alphabet, and is the primary source
for spines and shapes. This module's coverage measures how much of the BED
(the answer-keyed corpora) it can name -- never a claim of universal
capability -- and it remains useful for exactly two things: naming an
inferred class against the answer key's own vocabulary
(`behavior_inference.name_from_answer_key`), and validating a run's floor
against published ground truth. No discovery path may import or call it.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

ALGORITHM_VERSION = "telemetry-behavior-v1"

# The shared behavioural alphabet. Unchanged from pyramid/series work.
BEHAVIOR_CLASSES: tuple[str, ...] = (
    "auth",
    "enumerate",
    "execute",
    "escalate",
    "collect",
    "destroy",
    "persist",
    "evade",
    "lateral",
    "c2_exfil",
)

# ── Windows Security (wineventlog:security) ────────────────────────────────
# Vendor-documented event ids. These are stable, published semantics.
_WINSEC_EVENTS: dict[str, str] = {
    "4624": "auth",  # successful logon
    "4625": "auth",  # failed logon
    "4768": "auth",  # kerberos TGT requested
    "4769": "auth",  # kerberos service ticket
    "4771": "auth",  # kerberos pre-auth failed
    "4776": "auth",  # NTLM credential validation
    "4634": "auth",  # logoff
    "4648": "lateral",  # explicit-credential logon (runas / pivot)
    "4672": "escalate",  # special privileges assigned
    "4673": "escalate",  # privileged service called
    "4728": "escalate",  # member added to global group
    "4732": "escalate",  # member added to local group
    "4756": "escalate",  # member added to universal group
    "4720": "persist",  # user account created
    "4722": "persist",  # user account enabled
    "4738": "persist",  # user account changed
    "4697": "persist",  # service installed
    "4698": "persist",  # scheduled task created
    "4688": "execute",  # process created
    "4689": "execute",  # process exited
    "5140": "collect",  # network share accessed
    "5145": "collect",  # share object checked
    "4663": "collect",  # object access attempted
    "4656": "collect",  # handle to object requested
    "4726": "destroy",  # user account deleted
    "1102": "evade",  # audit log cleared
    "4719": "evade",  # audit policy changed
    "5156": "c2_exfil",  # filtering platform permitted connection
}

# ── Sysmon (xmlwineventlog:sysmon) ─────────────────────────────────────────
_SYSMON_EVENTS: dict[str, str] = {
    "1": "execute",  # process create
    "2": "evade",  # file creation time changed
    "3": "c2_exfil",  # network connection
    "4": "evade",  # sysmon service state changed
    "5": "execute",  # process terminated
    "6": "persist",  # driver loaded
    "7": "execute",  # image loaded
    "8": "lateral",  # CreateRemoteThread
    "9": "collect",  # RawAccessRead
    "10": "collect",  # ProcessAccess
    "11": "persist",  # file created
    "12": "persist",  # registry key create/delete
    "13": "persist",  # registry value set
    "14": "persist",  # registry key rename
    "15": "collect",  # FileCreateStreamHash
    "17": "lateral",  # pipe created
    "18": "lateral",  # pipe connected
    "22": "enumerate",  # DNS query
    "23": "destroy",  # file delete archived
    "26": "destroy",  # file delete logged
}

# ── Network / stream sourcetypes: behaviour is the PROTOCOL's purpose ──────
_STREAM_SOURCETYPE: dict[str, str] = {
    "stream:dns": "enumerate",
    "stream:ldap": "enumerate",
    "stream:arp": "enumerate",
    "stream:icmp": "enumerate",
    "stream:smb": "lateral",
    "stream:http": "c2_exfil",
    "stream:tcp": "c2_exfil",
    "stream:udp": "c2_exfil",
    "stream:smtp": "c2_exfil",
    "stream:mysql": "collect",
    "aws:cloudwatchlogs:vpcflow": "c2_exfil",
    "pan:traffic": "c2_exfil",
    "cisco:asa": "c2_exfil",
    "access_combined": "c2_exfil",
}

# `suricata` is deliberately ABSENT from `_STREAM_SOURCETYPE` above (I.5,
# TASK_BULLY_INVESTIGATION_V1): the T.3 run mapped every `suricata` record to
# `evade` unconditionally and that one line alone supplied 44.8% of all
# classified behaviour (20,317 of 45,356) -- a Suricata alert is a
# DETECTION OF potentially any of several behaviours (a trojan's C2 beacon,
# a privilege-gain exploit, a DoS), and non-alert Suricata records
# (`dns`/`flow`/`http`/`tls`/`fileinfo`, live-verified against botsv1/v3)
# are protocol telemetry, not a verdict at all. Collapsing all of it to one
# class manufactures a dominant class rather than reading one.
#
# `suricata` records land in this lab's Splunk with NO field extraction --
# the entire JSON event sits in `_raw` (live-verified: `fields` carries only
# Splunk's own `_bkt`/`_cd`/`_indextime`/... metadata) -- so the alert's
# `event_type` and, for an alert, `alert.category` are read by parsing
# `_raw` directly. Only the small set of categories below are confident
# enough to name a behaviour; everything else (informational categories,
# an empty category, protocol-only records with no confident mapping) is
# left unmapped and VISIBLE -- unmapped-and-honest beats wrong-and-dominant.
_SURICATA_CATEGORY_MAP: dict[str, str] = {
    "a network trojan was detected": "c2_exfil",
    "attempted administrator privilege gain": "escalate",
    "successful administrative privilege gain": "escalate",
    "web application attack": "execute",
    "attempted information leak": "collect",
    "denial of service": "destroy",
    "detection of a denial of service attack": "destroy",
}

# Non-alert Suricata `event_type`s: only `dns` (a query/answer pair) is a
# confident enough protocol purpose to name; `flow`/`http`/`tls`/`fileinfo`/
# etc. describe connection metadata, not a behaviour, and stay unmapped.
_SURICATA_EVENT_TYPE_MAP: dict[str, str] = {
    "dns": "enumerate",
}

# ── Host / endpoint sourcetypes ────────────────────────────────────────────
_HOST_SOURCETYPE: dict[str, str] = {
    "WinRegistry": "persist",
    "WinHostMon": "enumerate",
    "Script:ListeningPorts": "enumerate",
    "Script:GetEndpointInfo": "enumerate",
    "osquery:results": "enumerate",
    "osquery:info": "enumerate",
    "osquery_results": "enumerate",  # underscore variant, T.3 live capture
    "osquery_info": "enumerate",  # underscore variant, T.3 live capture
    "netstat": "enumerate",
    "openPorts": "enumerate",
    "ps": "execute",
    "top": "execute",
    "who": "auth",
    "symantec:ep:agent:file": "evade",
}

# auditd/linux_audit: the syscall or record type carries the behaviour.
_AUDITD_TYPES: dict[str, str] = {
    "USER_AUTH": "auth",
    "USER_LOGIN": "auth",
    "CRED_ACQ": "auth",
    "USER_ROLE_CHANGE": "escalate",
    "ADD_USER": "persist",
    "EXECVE": "execute",
    "SYSCALL": "execute",
    "PATH": "collect",
    "USER_CMD": "execute",
    "ANOM_ABEND": "evade",
    "CONFIG_CHANGE": "evade",
}

_FIELD_EVENTCODE = ("EventCode", "EventID", "event_id", "eventcode", "signature_id")
_FIELD_AUDIT_TYPE = ("type", "record_type")

# One line may carry SEVERAL `key=value` pairs (live: `EventCode=4634
# TimeCreated=2026-11-07 07:29:27`). A new pair starts only at an
# identifier-like key preceded by line start or whitespace, so a value may
# contain spaces and an inner `=` (base64 padding, `foo=a=b`) never splits.
_KV_PAIR_BOUNDARY = re.compile(r"(?:^|\s)([^\W\d]\w*)=")


def _raw_kv_fields(record: dict[str, Any]) -> dict[str, str]:
    """This lab's Splunk only surfaces a field in captured JSON when the
    search itself referenced it (live-verified against botsv3: a plain
    `search index=botsv3 "BSTOLL-L"` returns none of `EventCode`/
    `ComputerName`/..., but adding `EventCode=4689` as a search term makes
    Splunk return it) -- so a capture that doesn't already know which field
    it wants sees none of them. Two real wire shapes need parsing directly
    from `_raw` rather than depending on which fields happened to be
    referenced upstream:

      * Windows EventLog/auditd -- line-oriented `key=value`.
      * A JSON-bodied event (e.g. an injected cousin) shipped under a
        sourcetype whose OWN extraction rules expect a different wire
        format (`wineventlog:security`'s classic-text rules, not JSON) --
        live-verified: HEC's automatic JSON field extraction is skipped
        entirely in that case, leaving the JSON only in `_raw` text.
    """
    raw = record.get("_raw")
    if not isinstance(raw, str):
        return {}
    stripped = raw.strip()
    if stripped.startswith("{"):
        try:
            parsed = json.loads(stripped)
        except (json.JSONDecodeError, TypeError):
            parsed = None
        if isinstance(parsed, dict):
            return {k: str(v) for k, v in parsed.items() if not isinstance(v, (dict, list))}
    out: dict[str, str] = {}
    for line in raw.splitlines():
        boundaries = list(_KV_PAIR_BOUNDARY.finditer(line))
        if not boundaries:
            continue
        for i, m in enumerate(boundaries):
            end = boundaries[i + 1].start() if i + 1 < len(boundaries) else len(line)
            out.setdefault(m.group(1), line[m.end() : end].strip())
    return out


def _dig(record: dict[str, Any], *names: str) -> str | None:
    for n in names:
        v = record.get(n)
        if v not in (None, ""):
            return str(v).strip()
        # dotted / nested
        cur: Any = record
        ok = True
        for part in n.split("."):
            if isinstance(cur, dict) and part in cur:
                cur = cur[part]
            else:
                ok = False
                break
        if ok and cur not in (None, "", {}):
            return str(cur).strip()
    raw_fields = _raw_kv_fields(record)
    for n in names:
        v = raw_fields.get(n)
        if v not in (None, ""):
            return v
    return None


def _norm_sourcetype(sourcetype: str) -> str:
    return (sourcetype or "").strip()


def _parse_suricata_json(record: dict[str, Any]) -> dict[str, Any]:
    """This lab's Splunk does no field extraction for `suricata` (live-
    verified: `fields` carries only Splunk's own metadata, the whole event
    sits in `_raw` as JSON) -- so read the alert's `event_type`/`alert`
    block by parsing `_raw` directly. Falls back to the record itself for
    already-flattened inputs (e.g. tests, or a future extraction fix)."""
    raw = record.get("_raw")
    if isinstance(raw, str) and raw.strip().startswith("{"):
        try:
            parsed = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            parsed = None
        if isinstance(parsed, dict):
            return parsed
    return record


def classify_record(record: dict[str, Any], sourcetype: str) -> str:
    """Behaviour class for ONE real telemetry record, read the way its
    sourcetype encodes behaviour. Returns "" when this sourcetype has no
    mapping -- honest unclassified, never a majority-class guess."""
    st = _norm_sourcetype(sourcetype)
    low = st.lower()

    # Windows security: the event id IS the behaviour. `wineventlog:security`
    # and bare `WinEventLog` both surface live (T.3, TASK_BULLY_REAL_
    # TELEMETRY_V1); Splunk's TA-windows add-on separately ships the same
    # data under `windows:security`, a naming variant this run's own capture
    # exposed -- `unmapped_sourcetypes` is what is supposed to drive this.
    if ("wineventlog" in low or ("windows" in low and "security" in low)) and "sysmon" not in low:
        code = _dig(record, *_FIELD_EVENTCODE)
        if code and code in _WINSEC_EVENTS:
            return _WINSEC_EVENTS[code]
        return ""

    # Sysmon (`xmlwineventlog:sysmon`, `windows:sysmon` -- both contain
    # "sysmon", so no separate branch is needed for the TA-windows variant)
    if "sysmon" in low:
        code = _dig(record, *_FIELD_EVENTCODE)
        if code and code in _SYSMON_EVENTS:
            return _SYSMON_EVENTS[code]
        return ""

    # auditd / linux_audit -- `linux:auditd` is the TA-linux add-on's own
    # naming for the same data (T.3 live capture).
    if low in ("auditd", "linux_audit", "linux:auditd"):
        t = _dig(record, *_FIELD_AUDIT_TYPE)
        if t:
            key = t.upper().split(":")[0]
            if key in _AUDITD_TYPES:
                return _AUDITD_TYPES[key]
        return ""

    # Suricata: a DETECTION of potentially several behaviours, never one
    # fixed class (I.5) -- derive from the alert's signature category where
    # available, otherwise leave unmapped and visible.
    if low == "suricata":
        parsed = _parse_suricata_json(record)
        event_type = str(parsed.get("event_type") or "").strip().lower()
        if event_type == "alert":
            alert = parsed.get("alert")
            category = (
                str(alert.get("category") or "").strip().lower() if isinstance(alert, dict) else ""
            )
            return _SURICATA_CATEGORY_MAP.get(category, "")
        return _SURICATA_EVENT_TYPE_MAP.get(event_type, "")

    # protocol streams and network appliances: the protocol's purpose
    if st in _STREAM_SOURCETYPE:
        return _STREAM_SOURCETYPE[st]

    # host/endpoint inventories
    if st in _HOST_SOURCETYPE:
        return _HOST_SOURCETYPE[st]

    return ""


# Content-derived classification reads the event fields without consulting sourcetype.

_CONTENT_EVENTCODE = ("eventcode", "eventid", "event_id")
_CONTENT_COMMAND_FIELDS = (
    "commandline",
    "command_line",
    "cmdline",
    "cmd",
    "proctitle",
    "scriptblocktext",
    "process",
    "parameters",
)
_CONTENT_PATH_FIELDS = ("targetfilename", "filename", "file_path", "path", "objectid")
_CONTENT_SKIP_KEYS = frozenset(
    {
        "_time",
        "_indextime",
        "_cd",
        "_bkt",
        "_serial",
        "_sourcetype",
        "_raw",
        "timestamp",
        "utctime",
        "timecreated",
        "eventtime",
    }
)

# PowerShell engine, script-block, and operational events indicate execution.
_POWERSHELL_EVENTS: dict[str, str] = {
    "400": "execute",
    "403": "execute",
    "600": "execute",
    "800": "execute",
    "4103": "execute",
    "4104": "execute",
}
# Windows service installation indicates persistence.
_SERVICE_EVENTS: dict[str, str] = {"7045": "persist"}

# Endpoint-agent event names map to their behaviour classes.
_EDR_EVENTS: dict[str, str] = {
    "processrollup2": "execute",
    "processrollup2v19": "execute",
    "networkconnectip4": "c2_exfil",
    "networkconnectip6": "c2_exfil",
    "dnsrequest": "enumerate",
    "filedeleteinfo": "destroy",
    "filewritten": "persist",
    "sensitiveprocessaccess": "collect",
    "remotethreadcreated": "lateral",
    "serviceinstalled": "persist",
    "userlogon": "auth",
}

# Cisco ASA syslog message IDs distinguish execution from connection events.
_ASA_MESSAGE_CLASS: dict[str, str] = {
    "111008": "execute",
    "111009": "execute",
    "111010": "execute",
    "302013": "c2_exfil",
    "302014": "c2_exfil",
    "302015": "c2_exfil",
    "302016": "c2_exfil",
    "302017": "c2_exfil",
    "302018": "c2_exfil",
    "113039": "auth",
    "605005": "auth",
}
_ASA_MESSAGE_RE = re.compile(r"%ASA-\d-(\d+)")
_CMDLET_RE = re.compile(r"Cmdlet\s+([A-Za-z][\w-]*)", re.IGNORECASE)
_SSH_AUTH_RE = re.compile(
    r"(?:sshd.*(?:Accepted|Failed) (?:password|publickey)|authentication failure|"
    r"Accepted (?:password|publickey)|Failed password)",
    re.IGNORECASE,
)
_XML_EVENT_ID = re.compile(r"<EventID(?:\s[^>]*)?>([^<]+)</EventID>", re.IGNORECASE)
_XML_DATA = re.compile(r"<Data\s+Name=['\"]([^'\"]+)['\"]>(.*?)</Data>", re.IGNORECASE | re.DOTALL)

# Credential stores and persistence locations are classified from event paths.
_COLLECT_PATH_MARKERS = (
    "\\windows\\system32\\config\\sam",
    "\\windows\\system32\\config\\system",
    "\\windows\\system32\\config\\security",
    "ntds.dit",
    "/etc/shadow",
    "/etc/gshadow",
    "/etc/passwd",
    "id_rsa",
    ".ssh/",
    ".aws/credentials",
    "lsass.dmp",
)
_PERSIST_PATH_MARKERS = (
    "\\startup\\",
    "\\tasks\\",
    "\\currentversion\\run",
    "/etc/cron",
    "/etc/systemd/",
    ".bashrc",
    "authorized_keys",
)

# Specific command patterns precede generic interpreter patterns.
_COMMAND_RULES: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(
            r"vssadmin\s+delete|wmic\s+shadowcopy\s+delete|rm\s+-rf\s+/|wbadmin\s+delete|"
            r"fsutil\s+usn\s+deletejournal|recoveryenabled\s+no|dd\s+if=/dev/zero|"
            r"\bshred\b|wipefs|\bmkfs\b|drop\s+table|drop\s+database"
        ),
        "destroy",
    ),
    (
        re.compile(
            r"wevtutil\s+cl|clear-eventlog|auditpol\s+/clear|set-mppreference.*disable|"
            r"netsh\s+advfirewall\s+set.*off|logman\s+stop|reg\s+delete.*\\run"
        ),
        "evade",
    ),
    (
        re.compile(
            r"schtasks\s+/create|schtasks\s+-create|new-scheduledtask|\bsc(?:\.exe)?\s+create|"
            r"new-service|\bsc(?:\.exe)?\s+config|reg\s+add.*\\(?:run|runonce|services)\b|"
            r"new-itemproperty.*\\run|crontab|systemctl\s+enable|\buseradd\b|"
            r"net\s+user\s+\S+\s+\S+\s+/add|new-localuser|add-localgroupmember"
        ),
        "persist",
    ),
    (
        re.compile(
            r"\bsudo\b|\bsu\b(?::|\s+-)|runas\s+|"
            r"net\s+localgroup\s+administrators\s+\S+\s+/add|add-localgroupmember|"
            r"set-executionpolicy|whoami\s+/priv|sedebugprivilege|icacls\s+.*grant|takeown\s+/f"
        ),
        "escalate",
    ),
    (
        re.compile(
            r"psexec|wmic\s+/node:|enter-pssession|new-pssession|"
            r"invoke-command.*computername|winrs\b|\bsmbclient\b|net\s+use\s+\\\\|copy-item\s+\\\\"
        ),
        "lateral",
    ),
    (
        re.compile(
            r"procdump|lsass|comsvcs\.dll|minidump|reg\s+save|ntdsutil|esentutl|"
            r"vssadmin\s+create\s+shadow|cat\s+/etc/|get-content|tar\s+-?c?zf|"
            r"compress-archive|\b7z\s+a\b|search-mailbox"
        ),
        "collect",
    ),
    (
        re.compile(
            r"\bcurl\b|\bwget\b|invoke-webrequest|\biwr\b|invoke-restmethod|downloadstring|"
            r"downloadfile|certutil\s+-urlcache|bitsadmin\s+/transfer|\bftp\b|\bnc\b|ncat|socat|"
            r"rclone|aws\s+s3\s+cp|azcopy|mshta\s+https?:|regsvr32.*https?:"
        ),
        "c2_exfil",
    ),
    (
        re.compile(
            r"\bwhoami\b|\bnet\s+user\b|\bnet\s+group\b|\bnet\s+localgroup\b|\bnet\s+view\b|"
            r"nltest|dsquery|dsget|adfind|get-aduser|get-adcomputer|get-adgroup|systeminfo|"
            r"ipconfig|ifconfig|\bhostname\b|uname\s+-a|netstat|route\s+print|arp\s+-a|getmac|"
            r"nslookup|\bdig\b|\bping\b|quser|qwinsta|get-childitem|get-wmiobject|reg\s+query|"
            r"\btasklist\b|get-process|get-service|\bsc\s+query|schtasks\s+/query"
        ),
        "enumerate",
    ),
    (
        re.compile(
            r"powershell|pwsh|cmd\s*/c|\bcmd(?:\.exe)?\b|bash\s+-c|sh\s+-c|\bpython[23]?\b|"
            r"perl\s|ruby\s|rundll32|regsvr32|mshta|cscript|wscript|msiexec|installutil|"
            r"regasm|regsvcs|certutil|wmic\b|systemd-run"
        ),
        "execute",
    ),
)

# Process names can identify tools when no command line is present.
_TOOL_RULES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"procdump|mimikatz|ntdsutil|vssadmin"), "collect"),
    (re.compile(r"psexec|wsmprovhost|winrs"), "lateral"),
    (
        re.compile(r"nmap|masscan|adfind|nltest|whoami|dsquery|net\.exe|systeminfo|socketfilterfw"),
        "enumerate",
    ),
    (re.compile(r"schtasks|useradd|adduser"), "persist"),
    (re.compile(r"sudo|\bsu\b"), "escalate"),
    (re.compile(r"\bcurl\b|\bwget\b|\bnc\b|ncat|socat"), "c2_exfil"),
    (
        re.compile(r"powershell|pwsh|\bcmd\.exe\b|\bbash\b|\bsh\b|rundll32|regsvr32|mshta"),
        "execute",
    ),
)


def _content_key(name: str) -> str:
    return name.strip().lower().replace(" ", "_")


def _flatten_content(value: Any, out: dict[str, str], prefix: str = "") -> None:
    """Flatten nested JSON to lowercase dotted keys plus their leaf alias."""
    if not isinstance(value, dict):
        return
    for key, inner in value.items():
        name = _content_key(f"{prefix}{key}")
        if isinstance(inner, dict):
            _flatten_content(inner, out, f"{name}.")
        elif isinstance(inner, (list, tuple)):
            for item in inner:
                if isinstance(item, dict):
                    _flatten_content(item, out, f"{name}.")
                elif item not in (None, ""):
                    out.setdefault(name, str(item))
        elif inner not in (None, ""):
            out.setdefault(name, str(inner))
            out.setdefault(_content_key(str(key)), str(inner))


def _strip_wrapping_quotes(value: str) -> str:
    text = value.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {'"', "'"}:
        return text[1:-1]
    return text


def _kv_content_fields(text: str) -> dict[str, str]:
    """Lowercase key=value fields and keep the line when it has no message."""
    raw = _raw_kv_fields({"_raw": text})
    if not raw:
        return {}
    out = {
        _content_key(key): _strip_wrapping_quotes(value)
        for key, value in raw.items()
        if value.strip()
    }
    if "message" not in out:
        out["_text"] = text
    return out


def _parse_raw_content(raw: str) -> dict[str, str]:
    """Fields carried by a raw record: JSON, Windows Event XML, or key=value."""
    text = raw.strip()
    if not text:
        return {}
    if text.startswith("{"):
        try:
            parsed = json.loads(text)
        except (json.JSONDecodeError, TypeError):
            parsed = None
        if isinstance(parsed, dict):
            out: dict[str, str] = {}
            _flatten_content(parsed, out)
            return out
    if text.startswith("<"):
        out = {}
        if code := _XML_EVENT_ID.search(text):
            out["eventid"] = code.group(1).strip()
        for name, value in _XML_DATA.findall(text):
            clean = re.sub(r"\s+", " ", value).strip()
            if clean:
                out[_content_key(name)] = clean
        if channel := re.search(r"<Channel>([^<]+)</Channel>", text):
            out["channel"] = channel.group(1).strip()
        if provider := re.search(r"<Provider\s+Name=['\"]([^'\"]+)['\"]", text):
            out["provider"] = provider.group(1).strip()
        if out:
            return out
    out = _kv_content_fields(text)
    if out:
        return out
    return {"_text": text}


def _content_fields(record: dict[str, Any]) -> dict[str, str]:
    fields: dict[str, str] = {}
    _flatten_content(record, fields)
    raw = record.get("_raw")
    if isinstance(raw, str):
        for key, value in _parse_raw_content(raw).items():
            fields.setdefault(key, value)
    return {key: value for key, value in fields.items() if key not in _CONTENT_SKIP_KEYS}


def _first(fields: dict[str, str], names: tuple[str, ...]) -> str:
    for name in names:
        value = fields.get(name)
        if value:
            return value
    return ""


def _is_sysmon_event(fields: dict[str, str]) -> bool:
    marker = " ".join(
        fields.get(key, "") for key in ("channel", "logname", "provider", "provider_name", "source")
    ).lower()
    if "sysmon" in marker:
        return True
    return any(
        key in fields for key in ("processguid", "targetfilename", "image", "destinationport")
    )


def _class_from_event_id(fields: dict[str, str]) -> str:
    raw = _first(fields, _CONTENT_EVENTCODE)
    if not raw:
        return ""
    match = re.match(r"\s*(\d+)", raw)
    if match is None:
        return ""
    code = match.group(1)
    if _is_sysmon_event(fields) and code in _SYSMON_EVENTS:
        return _SYSMON_EVENTS[code]
    if code in _WINSEC_EVENTS:
        return _WINSEC_EVENTS[code]
    if code in _POWERSHELL_EVENTS:
        return _POWERSHELL_EVENTS[code]
    if code in _SERVICE_EVENTS:
        return _SERVICE_EVENTS[code]
    return ""


def _content_command_text(fields: dict[str, str]) -> str:
    for name in _CONTENT_COMMAND_FIELDS:
        if value := fields.get(name):
            return value
    audit_args = " ".join(fields.get(f"a{i}", "") for i in range(10)).strip()
    return audit_args


def _command_class(text: str) -> str:
    low = text.lower()
    for pattern, cls in _COMMAND_RULES:
        if pattern.search(low):
            return cls
    return ""


def _refine_event(base: str, fields: dict[str, str]) -> str:
    if base == "execute":
        return _command_class(_content_command_text(fields)) or base
    if base == "persist":
        path = _first(fields, _CONTENT_PATH_FIELDS).lower()
        if any(marker in path for marker in _COLLECT_PATH_MARKERS):
            return "collect"
        return base
    if base == "c2_exfil":
        port = _first(fields, ("destinationport", "dest_port", "dst_port", "destination_port"))
        if port in {"445", "139", "3389", "22"}:
            return "lateral"
        if port == "53":
            return "enumerate"
    return base


def _cloudtrail_class(event_name: str) -> str:
    low = event_name.strip().lower()
    if low in {
        "assumerole",
        "assumerolewithsaml",
        "assumerolewithwebidentity",
        "getsessiontoken",
        "getfederationtoken",
        "consolelogin",
    }:
        return "auth"
    if low.startswith(("createpolicyversion", "putuserpolicy", "putrolepolicy", "putgrouppolicy")):
        return "escalate"
    if low.startswith(("attachuserpolicy", "attachrolepolicy", "attachgrouppolicy")):
        return "escalate"
    if low.startswith(("addusertogroup", "updateroleassumerolepolicyt", "updateassumerolepolicy")):
        return "escalate"
    if low.startswith(
        ("createuser", "createloginprofile", "createaccesskey", "updateloginprofile")
    ):
        return "persist"
    if low.startswith(("getsecretvalue", "getparameter", "getobject", "getpassworddata")):
        return "collect"
    if low.startswith(("download", "export")):
        return "collect"
    if low.startswith(("describe", "list", "lookup", "get")):
        return "enumerate"
    if low.startswith(("delete", "terminate", "remove", "stop")):
        return "destroy"
    if low.startswith(("create", "run", "start", "invoke", "send", "publish", "execute")):
        return "execute"
    if low.startswith(("put", "update", "modify", "set", "enable", "disable")):
        return "persist"
    return ""


def _operation_class(operation: str) -> str:
    low = operation.strip().lower()
    if any(token in low for token in ("login", "logon", "loggedin", "signin", "authenticate")):
        return "auth"
    if any(token in low for token in ("inboxrule", "mailredirect", "forwarding")):
        return "persist"
    if "permission" in low:
        return "escalate" if low.startswith(("add", "set", "grant", "new")) else "persist"
    if low.startswith(("download", "export", "filesync")) or "download" in low:
        return "collect"
    if low.startswith(("delete", "remove")):
        return "destroy"
    if low.startswith(("new", "create", "add", "set", "update")):
        return "persist"
    if low.startswith(("search", "get", "list", "find", "read", "view", "preview")):
        return "enumerate"
    if low.startswith("send"):
        return "c2_exfil"
    if low.startswith("invoke"):
        return "execute"
    return ""


def _azure_operation_class(operation: str) -> str:
    low = operation.strip().lower()
    if "sign-in" in low or "signin" in low or "login" in low:
        return "auth"
    if "add member to role" in low or ("role" in low and low.startswith("add")):
        return "escalate"
    if "consent" in low or "reset password" in low:
        return "persist"
    if low.startswith(("delete", "wipe")):
        return "destroy"
    if low.startswith(("add", "create", "update", "reset", "set")):
        return "persist"
    if low.startswith(("list", "get")):
        return "enumerate"
    return ""


def _azure_resource_action(action: str) -> str:
    low = action.strip().lower()
    if low.endswith("/write"):
        return "persist"
    if low.endswith("/delete"):
        return "destroy"
    if low.endswith("/read"):
        return "enumerate"
    if low.endswith("/action"):
        return "execute"
    return ""


def _generic_event_type(value: str) -> str:
    low = value.strip().lower()
    if any(token in low for token in ("login", "logon", "signin", "sign-in", "session.start")):
        return "auth"
    if any(token in low for token in ("authentication", "sso")):
        return "auth"
    if "dns" in low:
        return "enumerate"
    if any(token in low for token in ("delete", "remove", "terminate", "stop")):
        return "destroy"
    if any(token in low for token in ("process", "exec", "command")):
        return "execute"
    if any(token in low for token in ("network", "connection", "connect")):
        return "c2_exfil"
    if any(token in low for token in ("download", "export", "read", "get")):
        return "collect"
    if any(token in low for token in ("create", "write", "add", "update", "set", "install")):
        return "persist"
    if any(token in low for token in ("list", "search", "query", "enumerate", "discover")):
        return "enumerate"
    return ""


def _kubernetes_verb_class(verb: str) -> str:
    low = verb.strip().lower()
    if low in {"get", "list", "watch"}:
        return "enumerate"
    if low in {"create", "update", "patch"}:
        return "persist"
    if low in {"delete", "deletecollection"}:
        return "destroy"
    if low in {"exec", "attach", "portforward"}:
        return "execute"
    return ""


def _category_class(category: str) -> str:
    low = category.strip().lower()
    if "signin" in low or "sign-in" in low:
        return "auth"
    return _SURICATA_CATEGORY_MAP.get(low, "")


def _class_from_event_type(fields: dict[str, str]) -> str:
    event_type = _first(fields, ("eventtype", "event_type", "event_name"))
    if not event_type:
        return ""
    low = event_type.strip().lower()
    if low == "alert":
        return _category_class(fields.get("alert.category", ""))
    return _generic_event_type(low)


def _class_from_platform_fields(fields: dict[str, str]) -> str:
    if event_name := fields.get("eventname"):
        return _cloudtrail_class(event_name)
    if operation := fields.get("operation"):
        return _operation_class(operation)
    if operation_name := fields.get("operationname"):
        return _azure_operation_class(operation_name)
    if simple := fields.get("event_simplename"):
        return _EDR_EVENTS.get(simple.strip().lower(), "") or _generic_event_type(simple)
    if (action := _first(fields, ("authorization.action", "action"))) and "/" in action:
        return _azure_resource_action(action)
    if cls := _class_from_event_type(fields):
        return cls
    if (category := fields.get("category")) and (cls := _category_class(category)):
        return cls
    if (verb := fields.get("verb")) and (cls := _kubernetes_verb_class(verb)):
        return cls
    if fields.get("readonly", "").strip().lower() == "true":
        return "enumerate"
    return ""


def _class_from_path_fields(fields: dict[str, str]) -> str:
    tool = _first(fields, ("image", "exe", "process_name", "comm", "processpath")).lower()
    for pattern, cls in _TOOL_RULES:
        if pattern.search(tool):
            return cls
    path = _first(fields, _CONTENT_PATH_FIELDS).lower()
    if any(marker in path for marker in _COLLECT_PATH_MARKERS):
        return "collect"
    if any(marker in path for marker in _PERSIST_PATH_MARKERS):
        return "persist"
    return ""


def _cmdlet_class(cmdlet: str) -> str:
    low = cmdlet.strip().lower()
    if "search" in low and "mailbox" in low:
        return "collect"
    if "permission" in low:
        return "escalate"
    if low.startswith(("search", "get", "find", "list", "read")):
        return "enumerate"
    if low.startswith(("export", "download")):
        return "collect"
    if low.startswith(("remove", "delete", "disable", "clear")):
        return "destroy"
    if low.startswith(("new", "set", "add", "enable", "install")):
        return "persist"
    return ""


def _unstructured_text(fields: dict[str, str]) -> str:
    """Command text from a message, or from a line that is not a field dump."""
    message = _first(fields, ("message", "raw"))
    if message:
        return message
    if any(key != "_text" for key in fields):
        return ""
    return fields.get("_text", "")


def _class_from_raw_format(fields: dict[str, str]) -> str:
    audit_type = fields.get("type")
    if audit_type:
        key = audit_type.upper().split(":")[0]
        if key in _AUDITD_TYPES:
            return _AUDITD_TYPES[key]
    text = _unstructured_text(fields)
    if not text:
        return ""
    if match := _ASA_MESSAGE_RE.search(text):
        return _ASA_MESSAGE_CLASS.get(match.group(1), "")
    for match in _CMDLET_RE.finditer(text):
        if cls := _cmdlet_class(match.group(1)):
            return cls
    if _SSH_AUTH_RE.search(text):
        return "auth"
    return _command_class(text)


_ADMIN_ACTIONS: dict[str, str] = {
    "admin_login": "auth",
    "policy_create": "persist",
    "policy_update": "persist",
    "user_create": "persist",
    "user_update": "persist",
    "policy_bulk_delete": "evade",
    "bypass_create": "evade",
    "user_delete": "destroy",
}
_LATERAL_FLOW_PORTS = {"3389", "445", "139", "5985", "5986", "22"}
_EXFIL_FLOW_PORTS = {"21", "25", "587", "465"}
_FLOW_PORT_FIELDS = (
    "id.resp_p",
    "dest_port",
    "dst_port",
    "destinationport",
    "destination_port",
    "resp_p",
    "dport",
)
_TRANSFER_BYTES = 10_000_000
_SCANNER_UA_RE = re.compile(
    r"\b(?:gobuster|nikto|sqlmap|dirbuster|ffuf|wpscan|nuclei|masscan|zgrab)\b",
    re.IGNORECASE,
)
_DNS_QTYPE_RE = re.compile(r"\b\d+ \((?:A|AAAA|CNAME|TXT|MX|PTR|NS|SOA)\)")
_DNS_RCODE_RE = re.compile(r"\b(?:NOERROR|NXDOMAIN|SERVFAIL|REFUSED)\b")
_HTTP_COMMAND_RE = re.compile(r"(?:^|[?&*])command=([A-Za-z0-9_]+)")
_HTTP_COMMAND_CLASS = {
    "zip": "collect",
    "createfile": "persist",
    "runcustomcmd": "execute",
    "delete": "destroy",
}
_SYSLOG_TEXT_RULES: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(
            r"authentication failure|Accepted (?:password|publickey)|Failed password|"
            r"%SEC_LOGIN-\d-LOGIN_(?:SUCCESS|FAILED)|%SSH-5-SSH2_(?:USERAUTH|CLOSE|SESSION)|"
            r"%SYS-6-LOGOUT|AAA_RESULT_(?:REJECT|ACCEPT)",
            re.IGNORECASE,
        ),
        "auth",
    ),
    (re.compile(r"%AAA-6-USER_PRIVILEGE_UPDATE", re.IGNORECASE), "escalate"),
    (re.compile(r"%SYS-5-CONFIG_I\b", re.IGNORECASE), "persist"),
    (
        re.compile(r"\[vob\.user\.ssh\.enabled\]|SSH access has been enabled", re.IGNORECASE),
        "persist",
    ),
    (re.compile(r"File download\b", re.IGNORECASE), "collect"),
    (re.compile(r"\bDispatch\s+\S+\.(?:get|list)\b", re.IGNORECASE), "enumerate"),
    (re.compile(r"\bDispatch\s+\S+\.set\b", re.IGNORECASE), "persist"),
)
_TACTIC_CLASSES: tuple[tuple[str, str], ...] = (
    ("command and control", "c2_exfil"),
    ("exfiltration", "c2_exfil"),
    ("lateral movement", "lateral"),
    ("credential access", "collect"),
    ("defense evasion", "evade"),
    ("privilege escalation", "escalate"),
    ("persistence", "persist"),
    ("discovery", "enumerate"),
    ("execution", "execute"),
    ("impact", "destroy"),
    ("collection", "collect"),
)
_HTTP_COLLECT_MARKERS = (
    "/.env",
    "/.git/",
    "wp-config",
    "web.config",
    "/etc/passwd",
    "/etc/shadow",
    "id_rsa",
    ".aws/credentials",
)


def _identity_event_class(fields: dict[str, str]) -> str:
    name = _first(fields, ("event.name", "event_name")).strip().lower()
    event_type = fields.get("event.type", "").strip().lower()
    if "unenroll" in name or name.startswith("bypass"):
        return "evade"
    if name.startswith("login_") or name in {"login", "logout"} or event_type == "login":
        return "auth"
    return ""


def _admin_action_class(fields: dict[str, str]) -> str:
    action = fields.get("action.name", "").strip().lower()
    if not action:
        raw = fields.get("action", "").strip().lower()
        if raw and "/" not in raw and " " not in raw:
            action = raw
    if not action:
        return ""
    detail = " ".join(
        fields.get(key, "") for key in ("target.details", "description", "outcome", "details")
    ).lower()
    if action == "user_update" and "bypass" in detail:
        return "evade"
    return _ADMIN_ACTIONS.get(action, "")


def _syslog_text_class(fields: dict[str, str]) -> str:
    text = _first(fields, ("syslog_descriptor", "message", "_text"))
    if not text:
        return ""
    for pattern, cls in _SYSLOG_TEXT_RULES:
        if pattern.search(text):
            return cls
    return ""


def _tactic_class(fields: dict[str, str]) -> str:
    text = _first(fields, ("mitreattackgroups", "mitre_attack_groups")).lower()
    if not text:
        return ""
    for needle, cls in _TACTIC_CLASSES:
        if needle in text:
            return cls
    return ""


def _flow_service_class(service: str) -> str:
    tokens = {part.strip() for part in re.split(r"[,/]", service.lower()) if part.strip()}
    if tokens & {"smb", "rdp", "ssh"}:
        return "lateral"
    if tokens & {"ftp", "smtp"}:
        return "c2_exfil"
    if "dns" in tokens:
        return "enumerate"
    return ""


def _flow_port_class(fields: dict[str, str]) -> str:
    port = _first(fields, _FLOW_PORT_FIELDS).split(".", 1)[0]
    marker = fields.get("proto") or fields.get("conn_state") or fields.get("service")
    if not marker:
        return ""
    if port in _LATERAL_FLOW_PORTS:
        return "lateral"
    if port in _EXFIL_FLOW_PORTS:
        return "c2_exfil"
    if port == "53":
        return "enumerate"
    return ""


def _flow_class(fields: dict[str, str]) -> str:
    if _first(fields, ("http_method", "requestmethod", "uri_path", "method")):
        return ""
    if cls := _flow_service_class(fields.get("service", "")):
        return cls
    return _flow_port_class(fields)


def _dns_class(fields: dict[str, str]) -> str:
    query = _first(fields, ("query", "query_name", "qname", "dns.query"))
    if query and query not in {"-", "."} and "." in query and " " not in query:
        return "enumerate"
    text = fields.get("_text", "")
    if text and _DNS_QTYPE_RE.search(text) and _DNS_RCODE_RE.search(text):
        return "enumerate"
    return ""


def _threat_class(fields: dict[str, str]) -> str:
    name = _first(
        fields, ("threatname", "threat_name", "threatcategory", "threat_category")
    ).lower()
    if not name or name in {"none", "null", "-", "n/a"}:
        return ""
    if "phish" in name or "scam" in name:
        return ""
    if "dos" in name or "denial of service" in name:
        return "destroy"
    if "exploit" in name:
        return "execute"
    if any(token in name for token in ("virus", "malware", "trojan", "adware", "miner", "ransom")):
        return "c2_exfil"
    return ""


def _executed_process_class(fields: dict[str, str]) -> str:
    binary = fields.get("binary", "")
    arguments = fields.get("arguments", "")
    if not binary and not arguments:
        return ""
    return _command_class(f"{binary} {arguments}")


def _request_target(fields: dict[str, str]) -> str:
    """URL, query, or request body the record names, else an unstructured line."""
    parts = [
        fields.get(name, "")
        for name in (
            "uri_path",
            "url",
            "http.url",
            "http.uri",
            "uri_query",
            "request_body",
            "requestbody",
        )
    ]
    target = " ".join(part for part in parts if part and part != "-")
    return target or _unstructured_text(fields)


def _http_path_class(target: str) -> str:
    """Class a request target. A field dump is not a request."""
    lowered = target.lower()
    if not lowered:
        return ""
    if "/recovery/backup" in lowered:
        return "collect"
    if "/recovery/restore" in lowered:
        return "persist"
    if any(marker in lowered for marker in _HTTP_COLLECT_MARKERS):
        return "collect"
    if match := _HTTP_COMMAND_RE.search(target):
        return _HTTP_COMMAND_CLASS.get(match.group(1).lower(), "")
    return ""


def _http_transfer_class(fields: dict[str, str]) -> str:
    method = _first(fields, ("http_method", "requestmethod", "method")).upper()
    size = 0
    for name in ("bytes_out", "bytes_in", "requestsize", "responsesize"):
        raw = fields.get(name, "").replace(",", "")
        if raw.isdigit():
            size = max(size, int(raw))
    if size < _TRANSFER_BYTES:
        return ""
    if method in {"POST", "PUT", "PATCH"}:
        return "c2_exfil"
    if method in {"GET", "HEAD"}:
        return "collect"
    return ""


def _http_class(fields: dict[str, str]) -> str:
    target = _request_target(fields)
    if cls := _http_path_class(target):
        return cls
    agent = _first(fields, ("http_user_agent", "useragent", "user_agent")) or target
    if agent and _SCANNER_UA_RE.search(agent):
        return "enumerate"
    return _http_transfer_class(fields)


def _class_from_network_content(fields: dict[str, str]) -> str:
    for matcher in (
        _identity_event_class,
        _admin_action_class,
        _syslog_text_class,
        _tactic_class,
        _flow_class,
        _dns_class,
        _threat_class,
        _executed_process_class,
        _http_class,
    ):
        if cls := matcher(fields):
            return cls
    return ""


def classify_content(record: dict[str, Any], sourcetype: str = "") -> str:
    """Classify an event from its content without consulting the sourcetype."""
    del sourcetype
    fields = _content_fields(record)
    if not fields:
        return ""
    base = _class_from_event_id(fields)
    if base:
        return _refine_event(base, fields)
    if (command := _content_command_text(fields)) and (cls := _command_class(command)):
        return cls
    for matcher in (
        _class_from_platform_fields,
        _class_from_path_fields,
        _class_from_raw_format,
        _class_from_network_content,
    ):
        if cls := matcher(fields):
            return cls
    return ""


ClassifierFn = Callable[[dict[str, Any], str], str]


@dataclass(frozen=True)
class CoverageReport:
    """Per-sourcetype classified fraction and output-class entropy.

    C.6 published a classifier `learned_coverage` of 0.963 while every real
    verb resolved to `unknown`; coverage measured on synthetic held-out data
    said nothing about real telemetry. This report is computed on the records
    the run actually captured, so a collapse is visible in the run that
    suffers it."""

    n_records: int
    n_classified: int
    coverage: float
    by_sourcetype: dict[str, dict[str, Any]]
    class_distribution: dict[str, int]
    class_entropy_bits: float
    degenerate: bool
    unmapped_sourcetypes: tuple[str, ...]
    class_concentration: dict[str, float]
    source_concentration: dict[str, float]
    concentration_reasons: tuple[str, ...]

    @property
    def concentrated(self) -> bool:
        return bool(self.concentration_reasons)

    def to_dict(self) -> dict[str, Any]:
        return {
            "algorithm_version": ALGORITHM_VERSION,
            "n_records": self.n_records,
            "n_classified": self.n_classified,
            "coverage": round(self.coverage, 4),
            "by_sourcetype": self.by_sourcetype,
            "class_distribution": dict(self.class_distribution),
            "class_entropy_bits": round(self.class_entropy_bits, 4),
            "degenerate": self.degenerate,
            "unmapped_sourcetypes": list(self.unmapped_sourcetypes),
            "class_concentration": dict(self.class_concentration),
            "source_concentration": dict(self.source_concentration),
            "concentration_reasons": list(self.concentration_reasons),
            "concentrated": self.concentrated,
        }


# A classifier whose output collapses toward one class carries no information
# however high its coverage. C.6's real-verb entropy was 0.302 bits of 2.0.
MIN_CLASS_ENTROPY_BITS = 1.0

# Entropy alone did not catch the T.3 suricata collapse (2.28 bits,
# `degenerate=False`) because entropy is a whole-distribution statistic and
# T.3's real distribution still had several other populated classes. These
# two ceilings catch it directly: no single class may be more than 40% of
# everything classified, and no single sourcetype may supply more than 90%
# of any one class's members. T.3's `evade` was 44.8% of all classified
# behaviour (fails the first) and 100% of it came from `suricata` alone
# (fails the second) -- a permanent regression case for both.
MAX_CLASS_SHARE = 0.40
MAX_SOURCE_SHARE_OF_CLASS = 0.90


def coverage_report(
    records: list[tuple[dict[str, Any], str]],
    *,
    classifier: ClassifierFn | None = None,
    min_entropy: float = MIN_CLASS_ENTROPY_BITS,
    max_class_share: float = MAX_CLASS_SHARE,
    max_source_share_of_class: float = MAX_SOURCE_SHARE_OF_CLASS,
) -> CoverageReport:
    """Measure the classifier on the records a run ACTUALLY captured."""
    import math
    from collections import Counter, defaultdict

    fn = classifier or classify_record
    per_st: dict[str, list[int]] = defaultdict(lambda: [0, 0])  # [total, classified]
    dist: Counter[str] = Counter()
    by_class_source: dict[str, Counter[str]] = defaultdict(Counter)
    unmapped: set[str] = set()

    for record, sourcetype in records:
        cls = fn(record, sourcetype)
        per_st[sourcetype][0] += 1
        if cls:
            per_st[sourcetype][1] += 1
            dist[cls] += 1
            by_class_source[cls][sourcetype] += 1
        else:
            unmapped.add(sourcetype)

    n = len(records)
    n_cls = sum(dist.values())
    total = sum(dist.values()) or 1
    entropy = -sum((c / total) * math.log2(c / total) for c in dist.values() if c)

    by_st = {
        st: {
            "records": v[0],
            "classified": v[1],
            "coverage": round(v[1] / v[0], 4) if v[0] else 0.0,
        }
        for st, v in sorted(per_st.items())
    }

    class_concentration = {cls: round(count / total, 4) for cls, count in dist.items()}
    source_concentration = {
        cls: round(max(counter.values()) / sum(counter.values()), 4)
        for cls, counter in by_class_source.items()
    }
    concentration_reasons: list[str] = []
    for cls, share in sorted(class_concentration.items()):
        if share > max_class_share:
            concentration_reasons.append(f"class_concentration:{cls}={share}")
    for cls, share in sorted(source_concentration.items()):
        if share > max_source_share_of_class:
            dominant = max(by_class_source[cls].items(), key=lambda kv: kv[1])[0]
            concentration_reasons.append(f"source_concentration:{cls}<-{dominant}={share}")

    return CoverageReport(
        n_records=n,
        n_classified=n_cls,
        coverage=(n_cls / n) if n else 0.0,
        by_sourcetype=by_st,
        class_distribution=dict(dist),
        class_entropy_bits=entropy,
        degenerate=(entropy < min_entropy),
        unmapped_sourcetypes=tuple(sorted(st for st in unmapped if per_st[st][1] == 0)),
        class_concentration=class_concentration,
        source_concentration=source_concentration,
        concentration_reasons=tuple(concentration_reasons),
    )
