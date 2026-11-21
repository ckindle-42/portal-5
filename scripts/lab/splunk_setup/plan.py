"""One source of truth for the Splunk setup: sourcetype classes, CIM bindings, acceleration set.

Everything in this module is data plus pure functions, so the runbook, the reindex planner and
the conf renderers cannot disagree with each other. The measured inventory that drives the
routing table is in ``inventory.json`` (regenerated from the ingest receipts with
``python -m scripts.lab.splunk_setup inventory``).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

APP_NAME = "portal5_hunt_setup"
CORPORA = Path("/Volumes/data01/portal5_hunt/corpora")

#: Index the lab keeps deliberately untuned (§8.4 of the realism doc): the degradation control.
CONTROL_INDEX = "botsv2"
CONTROL_REASON = (
    "botsv2 is pre-indexed BOTS buckets with no raw source on disk, so its sourcetypes cannot "
    "be normalised at all; it is also where the two-name split was measured, which is the "
    "degradation the hunt must keep meeting"
)

#: Window for every accelerated model. A SOC's -30d/-90d would return nothing here: the
#: families' events are 2021-03 and 2022-01, i.e. years outside a rolling window.
ACCEL_WINDOW = "-10y"


@dataclass(frozen=True)
class IndexSpec:
    key: str
    source_index: str
    target_index: str
    root: Path
    receipt: Path
    entity_field: str
    default_year: int

    @property
    def summary_search(self) -> str:
        return f"ph_hunt_summary_{self.source_index}"


TUNED = (
    IndexSpec(
        key="kyoushi",
        source_index="hb_kyoushi_s1",
        target_index="hb_kyoushi_s1_v2",
        root=CORPORA / "hunt_bed" / "kyoushi_s1" / "gather",
        receipt=CORPORA / "hunt_bed" / "kyoushi_s1_ingest" / "receipt.json",
        entity_field="acct",
        default_year=2021,
    ),
    IndexSpec(
        key="santos",
        source_index="hb_ait_santos",
        target_index="hb_ait_santos_v2",
        root=CORPORA / "ait_lds_v21" / "santos" / "gather",
        receipt=CORPORA / "ait_lds_v21" / "santos_ingest" / "receipt.json",
        entity_field="acct",
        default_year=2022,
    ),
    IndexSpec(
        key="russellmitchell",
        source_index="hb_ait_russellmitchell",
        target_index="hb_ait_russellmitchell_v2",
        root=CORPORA / "ait_lds_v21" / "russellmitchell" / "gather",
        receipt=CORPORA / "ait_lds_v21" / "russellmitchell_ingest" / "receipt.json",
        entity_field="acct",
        default_year=2022,
    ),
)

TUNED_BY_KEY = {spec.key: spec for spec in TUNED}
TUNED_BY_TARGET = {spec.target_index: spec for spec in TUNED}


@dataclass(frozen=True)
class Target:
    sourcetype: str
    index_time: str  # "json" | "regex" | ""
    cim_tags: tuple[str, ...] = ()
    note: str = ""


#: One sourcetype per data type: the normalised vocabulary (the doc's §5.1 mapping, measured).
TARGETS: dict[str, Target] = {
    "linux_secure": Target("linux_secure", "regex", ("authentication",), "sshd/sudo/pam auth"),
    "linux_audit": Target("linux_audit", "regex", ("authentication",), "auditd USER_*/SYSCALL"),
    "syslog": Target("syslog", "", (), "syslog + journald service/syslog lines"),
    "access_combined": Target("access_combined", "regex", ("web",), "Apache/nginx/horde access"),
    "apache:error": Target("apache:error", "", (), "Apache error log"),
    "suricata": Target("suricata", "json", (), "eve.json (TA-suricata-4 binds `suricata`)"),
    "suricata:fast": Target("suricata:fast", "regex", ("ids", "attack"), "Suricata fast.log"),
    "suricata:log": Target("suricata:log", "", (), "Suricata engine log"),
    "dnsmasq": Target("dnsmasq", "regex", ("network", "resolution"), "DNS queries/replies"),
    "postfix_syslog": Target("postfix_syslog", "", (), "exim/postfix mail log"),
    "openvpn": Target("openvpn", "", (), "OpenVPN connection log"),
    "shorewall": Target("shorewall", "", (), "firewall init log"),
    "redis": Target("redis", "", (), "redis server log"),
    "logstash": Target("logstash", "", (), "logstash server log"),
    "metricbeat:system": Target("metricbeat:system", "json", (), "system metrics (measurement)"),
}

#: Measurement sources: dropped from the tuned index unless --keep-metrics routes them in.
MEASUREMENT = frozenset({"suricata:stats", "metricbeat:system"})


@dataclass(frozen=True)
class Route:
    target: str | None = None
    kind: str = "log"  # "log" | "measurement" | "noise"
    note: str = ""

    @property
    def is_noise(self) -> bool:
        return self.target is None


_METRICBEAT_SYSTEM = re.compile(
    r"-system\.(cpu|diskio|filesystem|fsstat|load|memory|network|process|"
    r"process\.summary|socket\.summary|uptime)\.log$"
)
_DATED_AUTH = re.compile(r"-system\.auth\.log$")
_DATED_SYSLOG = re.compile(r"-system\.(syslog|service)\.log$")
_JOURNAL = re.compile(r"journal.*\.txt$")

#: (pattern, route). First match wins; the order is the specificity order.
RULES: tuple[tuple[re.Pattern[str], Route], ...] = (
    (re.compile(r"^stats\.log$"), Route(None, "noise", "suricata performance stats")),
    (_METRICBEAT_SYSTEM, Route("metricbeat:system", "measurement", "metricbeat system metrics")),
    (_DATED_AUTH, Route("linux_secure")),
    (_DATED_SYSLOG, Route("syslog")),
    (_JOURNAL, Route("syslog")),
    (re.compile(r"^eve\.json$"), Route("suricata")),
    (re.compile(r"^fast\.log$"), Route("suricata:fast")),
    (re.compile(r"^suricata(-start)?\.log$"), Route("suricata:log")),
    (re.compile(r"^dnsmasq\.log$"), Route("dnsmasq")),
    (re.compile(r"^audit\.log$"), Route("linux_audit")),
    (re.compile(r"^auth\.log$"), Route("linux_secure")),
    (re.compile(r"^(syslog|messages|kern\.log|user\.log)$"), Route("syslog")),
    (re.compile(r"access\.log$|access_combined"), Route("access_combined")),
    (re.compile(r"error\.log$|apache_error"), Route("apache:error")),
    (re.compile(r"^mainlog$|^mail\.(log|info|warn)$"), Route("postfix_syslog")),
    (re.compile(r"^openvpn\.log$"), Route("openvpn")),
    (re.compile(r"^shorewall-init\.log$"), Route("shorewall")),
    (re.compile(r"^redis(-server)?\.log$"), Route("redis")),
    (re.compile(r"^logstash-"), Route("logstash")),
)


def classify(sourcetype: str) -> Route:
    """Map an as-ingested sourcetype onto the normalised vocabulary."""
    for pattern, route in RULES:
        if pattern.search(sourcetype):
            return route
    return Route(None, "noise", "unmapped")


def target_index(spec: IndexSpec) -> str:
    """The index a normalised event lands in: always the new name, never the original."""
    return spec.target_index


#: CIM bindings as eventtypes: the tag names are the model constraints (CIM 8.x base searches).
EVENTTYPES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("ph_auth_linux_secure", 'sourcetype="linux_secure"', ("authentication",)),
    ("ph_auth_linux_audit", 'sourcetype="linux_audit" type=USER_*', ("authentication",)),
    (
        "ph_process_linux_audit",
        'sourcetype="linux_audit" type=SYSCALL',
        ("endpoint", "process", "report"),
    ),
    ("ph_web_access", 'sourcetype="access_combined"', ("web",)),
    ("ph_ids_suricata_alert", 'sourcetype="suricata" event_type=alert', ("ids", "attack")),
    ("ph_ids_suricata_fast", 'sourcetype="suricata:fast"', ("ids", "attack")),
    (
        "ph_traffic_suricata_flow",
        'sourcetype="suricata" event_type=flow',
        ("network", "communicate"),
    ),
    ("ph_dns_suricata", 'sourcetype="suricata" event_type=dns', ("network", "resolution")),
    ("ph_dns_dnsmasq", 'sourcetype="dnsmasq"', ("network", "resolution")),
    ("ph_web_suricata_http", 'sourcetype="suricata" event_type=http', ("web",)),
)

#: CIM index allowlist macros, scoped to the tuned indexes so botsv2 cannot be accelerated.
CIM_MACROS = (
    "cim_Authentication_indexes",
    "cim_Change_indexes",
    "cim_Endpoint_indexes",
    "cim_Intrusion_Detection_indexes",
    "cim_Network_Resolution_indexes",
    "cim_Network_Traffic_indexes",
    "cim_Web_indexes",
)

#: Accelerated models (the doc's six cheap ones); Change is opt-in and needs winregistry.
ACCELERATED = (
    "Authentication",
    "Endpoint",
    "Intrusion_Detection",
    "Network_Resolution",
    "Network_Traffic",
    "Web",
)
ACCELERATED_OPTIONAL = ("Change",)


@dataclass(frozen=True)
class PlanRow:
    host: str
    source: str
    sourcetype_in: str
    sourcetype_out: str | None
    index: str
    events: int
    note: str = ""


@dataclass
class ReindexPlan:
    spec: IndexSpec
    root: Path = Path()
    rows: list[PlanRow] = field(default_factory=list)
    source_total: int = 0
    kept_total: int = 0
    noise_total: int = 0
    by_target: dict[str, tuple[int, int]] = field(default_factory=dict)

    @property
    def sourcetypes_out(self) -> list[str]:
        return sorted({r.sourcetype_out for r in self.rows if r.sourcetype_out})


def build_reindex_plan(
    spec: IndexSpec, files: list[dict], *, keep_metrics: bool = False, root: Path | None = None
) -> ReindexPlan:
    """Route every file in an ingest receipt to its normalised sourcetype and target index."""
    plan = ReindexPlan(spec=spec, root=root or spec.root)
    for record in files:
        route = classify(str(record["sourcetype"]))
        events = int(record.get("sent", 0))
        keep = route.target is not None and (keep_metrics or route.kind != "measurement")
        plan.rows.append(
            PlanRow(
                host=str(record["host"]),
                source=str(record["source"]),
                sourcetype_in=str(record["sourcetype"]),
                sourcetype_out=route.target if keep else None,
                index=target_index(spec) if keep else "",
                events=events,
                note=route.note,
            )
        )
        plan.source_total += events
        if keep and route.target:
            plan.kept_total += events
            n_src, n_ev = plan.by_target.get(route.target, (0, 0))
            plan.by_target[route.target] = (n_src + 1, n_ev + events)
        else:
            plan.noise_total += events
    return plan


def load_inventory(path: Path | None = None) -> dict:
    return json.loads((path or Path(__file__).with_name("inventory.json")).read_text())


#: TAs the doc's stage 2 enables (aws is listed because its data is in the estate already).
APPS_ENABLE = (
    "Splunk_TA_windows",
    "TA-microsoft-sysmon",
    "TA-suricata-4",
    "Splunk_TA_nix",
    "Splunk_TA_apache",
    "Splunk_TA_paloalto",
    "Splunk_TA_aws",
)

#: Retention is measured from event time: these corpora are 2021/2022, so a 10-day setting
#: would freeze and delete the whole index during ingest. ~11.5 years keeps them readable.
INDEX_SETTINGS = {
    "maxTotalDataSizeMB": "20000",
    "frozenTimePeriodInSecs": "365000000",
    "maxHotBuckets": "10",
}


@dataclass(frozen=True)
class Probe:
    name: str
    spl: str
    expect: str


def verify_probes(spec: IndexSpec) -> tuple[Probe, ...]:
    """The stage 5 probes; unexpected results are what the runbook's `verify` reports."""
    return (
        Probe("events", f"| eventcount summarize=false index={spec.target_index}", "count > 0"),
        Probe(
            "sourcetypes",
            f"| tstats count where index={spec.target_index} by sourcetype",
            "<= 20 rows, no date-in-filename names",
        ),
        Probe(
            "entity_indexed",
            f"| tstats count where index={spec.target_index} by acct",
            "> 0 rows (index-time acct present)",
        ),
        Probe(
            "auth_model",
            "| tstats summariesonly=true count from datamodel=Authentication by Authentication.user",
            "> 0 rows (tags + acceleration)",
        ),
    )


CONTROL_PROBES = (
    Probe(
        "control_raw_name",
        '| tstats count where index=botsv2 sourcetype="WinEventLog" by host',
        "0 rows — the tsidx name is not the raw name",
    ),
    Probe(
        "control_tsidx_name",
        '| tstats count where index=botsv2 sourcetype="wineventlog:security" by host',
        "> 0 rows — this path still answers on the control",
    ),
    Probe(
        "control_no_summary",
        "| tstats summariesonly=true count from datamodel=Authentication by Authentication.user",
        "0 rows inside botsv2's range — the control is not accelerated",
    ),
)
