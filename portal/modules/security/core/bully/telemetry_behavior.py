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
"""

from __future__ import annotations

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
    "suricata": "evade",
    "access_combined": "c2_exfil",
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
    return None


def _norm_sourcetype(sourcetype: str) -> str:
    return (sourcetype or "").strip()


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

    # protocol streams and network appliances: the protocol's purpose
    if st in _STREAM_SOURCETYPE:
        return _STREAM_SOURCETYPE[st]

    # host/endpoint inventories
    if st in _HOST_SOURCETYPE:
        return _HOST_SOURCETYPE[st]

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
        }


# A classifier whose output collapses toward one class carries no information
# however high its coverage. C.6's real-verb entropy was 0.302 bits of 2.0.
MIN_CLASS_ENTROPY_BITS = 1.0


def coverage_report(
    records: list[tuple[dict[str, Any], str]],
    *,
    classifier: ClassifierFn | None = None,
    min_entropy: float = MIN_CLASS_ENTROPY_BITS,
) -> CoverageReport:
    """Measure the classifier on the records a run ACTUALLY captured."""
    import math
    from collections import Counter, defaultdict

    fn = classifier or classify_record
    per_st: dict[str, list[int]] = defaultdict(lambda: [0, 0])  # [total, classified]
    dist: Counter[str] = Counter()
    unmapped: set[str] = set()

    for record, sourcetype in records:
        cls = fn(record, sourcetype)
        per_st[sourcetype][0] += 1
        if cls:
            per_st[sourcetype][1] += 1
            dist[cls] += 1
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
    return CoverageReport(
        n_records=n,
        n_classified=n_cls,
        coverage=(n_cls / n) if n else 0.0,
        by_sourcetype=by_st,
        class_distribution=dict(dist),
        class_entropy_bits=entropy,
        degenerate=(entropy < min_entropy),
        unmapped_sourcetypes=tuple(sorted(st for st in unmapped if per_st[st][1] == 0)),
    )
