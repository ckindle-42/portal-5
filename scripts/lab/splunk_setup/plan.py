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
    "syslog": Target("syslog", "", (), "syslog/messages/kern user logs + user journals"),
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
#: filebeat's `system` module re-ships another host's auth/service/syslog as JSON, and the
#: host's journald export duplicates its own syslog/audit lines: one event family, two copies.
_SHIPPER_COPY = re.compile(r"-system\.(auth|service|syslog)\.log$")
_SYSTEM_JOURNAL = re.compile(r"(?:^|/)system\.journal.*\.txt$")
_JOURNAL = re.compile(r"journal.*\.txt$")

#: (pattern, route). First match wins; the order is the specificity order.
RULES: tuple[tuple[re.Pattern[str], Route], ...] = (
    (re.compile(r"^stats\.log$"), Route(None, "noise", "suricata performance stats")),
    (_METRICBEAT_SYSTEM, Route("metricbeat:system", "measurement", "metricbeat system metrics")),
    (_SHIPPER_COPY, Route(None, "noise", "filebeat copy of a host log: duplicate, JSON shape")),
    (_SYSTEM_JOURNAL, Route(None, "noise", "journald export duplicating syslog/audit")),
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
    (
        "ph_dns_suricata",
        'sourcetype="suricata" event_type=dns',
        ("network", "resolution", "dns"),
    ),
    ("ph_dns_dnsmasq", 'sourcetype="dnsmasq"', ("network", "resolution", "dns")),
    ("ph_web_suricata_http", 'sourcetype="suricata" event_type=http', ("web",)),
)

#: CIM index allowlist macros and the acceleration of every CIM model live in Splunk_SA_CIM,
#: whose own defaults win over any other app's copy, so both are written there.
CIM_APP = "Splunk_SA_CIM"
CIM_DEFAULT_DEFINITION = "()"

#: Hunt-bed indexes ingested outside stage 2. On the CIM allowlist, never created or reshipped here.
CIM_EXTRA_INDEXES = (
    "hb_ait_fox",
    "hb_ait_harrison",
    "hb_ait_shaw",
    "hb_ait_wardbeck",
    "hb_ait_wilson",
    "hb_flaws_aws",
    "hb_uwf_zeek24",
    "hb_lmd_2023",
    "hb_lmd_2023_v2",
    "hb_ics_pcap",
    "hb_otrf_apt3",
    "hb_cyber4ot",
    "hb_iec104",
    "hb_sherlock_grid",
    "hb_icssim",
    "hb_pdmfc_ot",
    "hb_robotdog_audit",
)

#: Files an earlier release shipped and this one does not; a tar install overwrites but never
#: deletes, so the installer removes them by name.
LEGACY_CONF_FILES = ("datamodels.conf",)

#: The CIM DNS object looks this file up; the app on the box ships it only as ``.default``.
CIM_DNS_LOOKUP_FILE = "cim_dns_reply_codes2.csv"

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


def accelerated_models(with_change: bool = False) -> tuple[str, ...]:
    """The data models stage 3 switches acceleration on for."""
    return ACCELERATED + (ACCELERATED_OPTIONAL if with_change else ())


def accel_settings() -> dict[str, str]:
    """The conf-datamodels keys that switch a model's acceleration on over the corpus span."""
    return {
        "acceleration": "true",
        "acceleration.earliest_time": ACCEL_WINDOW,
        "acceleration.cron_schedule": "*/10 * * * *",
        "acceleration.max_concurrent": "1",
    }


def cim_macros(with_change: bool = False) -> tuple[str, ...]:
    """The index-allowlist macros of every model acceleration is switched on for."""
    return tuple(f"cim_{model}_indexes" for model in accelerated_models(with_change))


def cim_allowlist_indexes() -> tuple[str, ...]:
    """Tuned `_v2` indexes plus the extended hunt-bed indexes. Never the control index."""
    names = tuple(spec.target_index for spec in TUNED) + CIM_EXTRA_INDEXES
    if CONTROL_INDEX in names or len(names) != len(set(names)):
        raise ValueError(f"CIM allowlist must be unique and exclude {CONTROL_INDEX}")
    return names


def cim_macro_definition() -> str:
    """Scope every accelerated model to the allowlist and keep botsv2 out of it."""
    return "(" + " OR ".join(f"index={name}" for name in cim_allowlist_indexes()) + ")"


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
    min_rows: int = 0
    max_rows: int | None = None


def entity_probe(spec: IndexSpec) -> Probe:
    """The property is rows from tstats: an indexed entity field must be answered by the tsidx."""
    return Probe(
        f"entity_indexed:{spec.target_index}",
        f"| tstats count where index={spec.target_index} by {spec.entity_field}",
        f"> 0 rows ({spec.entity_field} is in the tsidx)",
        min_rows=1,
    )


def verify_probes(spec: IndexSpec) -> tuple[Probe, ...]:
    """The stage 5 probes; unexpected results are what the runbook's `verify` reports."""
    return (
        Probe("events", f"| eventcount summarize=false index={spec.target_index}", "count > 0"),
        Probe(
            "sourcetypes",
            f"| tstats count where index={spec.target_index} by sourcetype",
            "<= 20 rows, no date-in-filename names",
        ),
        entity_probe(spec),
        Probe(
            "vhost_indexed",
            f"| tstats count where index={spec.target_index} by vhost",
            "> 0 rows (vhost is in the tsidx, not in c_ip)",
            min_rows=1,
        ),
        Probe(
            "service_log_absent",
            f"| tstats count where index={spec.target_index} "
            'source="*system.service.log" OR source="*system.auth.log" '
            'OR source="*system.syslog.log" OR source="*system.journal*" by source',
            "0 rows (a shipper copy or journal export was shipped: one family, one copy)",
            max_rows=0,
        ),
        Probe(
            "user_clean",
            f"| tstats count where index={spec.target_index} sourcetype=linux_secure by user "
            "| where length(user) > 64",
            "0 rows (index-time user is the username, not the rest of a JSON record)",
            max_rows=0,
        ),
        Probe(
            "auid_indexed",
            f"| tstats count where index={spec.target_index} sourcetype=linux_audit by auid",
            "> 0 rows (auid is in the tsidx)",
            min_rows=1,
        ),
        Probe(
            "auth_model",
            "| tstats summariesonly=true count from datamodel=Authentication by Authentication.user",
            "> 0 rows (tags + acceleration)",
            min_rows=1,
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
        min_rows=1,
    ),
    Probe(
        "control_model_scope",
        "| tstats summariesonly=false count from datamodel=Authentication by Authentication.user",
        "0 rows in 2017-08..2018-10 — botsv2 is outside the CIM index allowlist",
    ),
)
