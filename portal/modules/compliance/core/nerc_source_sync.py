"""Official NERC source synchronization (END_TO_END Phase 2 / foundation P2).

Acquires the authoritative NERC material for a standard family from official
sources, fingerprinted and immutable:

* the **One-Stop Shop** workbook — NERC's own lifecycle registry (status,
  adoption/filing/FERC-order dates, effective and retirement dates, docket,
  project page, and the hyperlinks to implementation plans/technical
  rationale/RSAWs);
* the **official standard PDFs**;
* the **implementation plans** (and technical rationale, when linked) that the
  standards themselves defer to for effective dates.

Guarantees this module owns (foundation §P2):

- every acquisition records URL, retrieval time, media type, byte hash, size,
  and local path in an append-friendly manifest under the private artifact
  hierarchy — never in Git;
- bytes are written once and never mutated; a refresh that sees identical
  bytes is ``UNCHANGED`` (no rewrite, no new store revision), and changed bytes
  create a NEW ``document_revisions`` row while the old one still resolves;
- a network failure preserves the last verified snapshot and returns a dated
  currency warning — it never deletes, never marks stale material current;
- lifecycle facts are parsed from the workbook, not hand-entered, and carry
  the workbook's own hash as their provenance.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx

_DATA = Path(__file__).resolve().parent.parent / "data"
OFFICIAL_DIR = _DATA / "private" / "nerc_official"
MANIFEST_NAME = "acquisition_manifest.json"

ONE_STOP_SHOP_URL = "https://www.nerc.com/globalassets/align-reports/one-stop-shop.xlsx"
_STANDARD_PDF_URL = (
    "https://www.nerc.com/globalassets/standards/reliability-standards/cip/{slug}.pdf"
)

#: workbook column names we depend on (One Stop Shop sheet, header row 1).
_LIFECYCLE_COLUMNS = (
    "Status",
    "Standard Number",
    "Standard Title",
    "Board Adopted Date",
    "Filing Date of Standard",
    "FERC Orders (Issued Date)",
    "Regulatory Order Effective Date",
    "Effective Date of Standard",
    "Phased-in Implementation",
    "Inactive Date of Standard",
    "Implementation Plan",
    "Public Notes",
    "Project Page",
    "Technical Rationale",
    "RSAW",
)


@dataclass
class Artifact:
    """One acquired official artifact and its fingerprint."""

    name: str
    url: str
    media_type: str = ""
    sha256: str = ""
    size: int = 0
    retrieved_at: str = ""
    path: str = ""
    status: str = ""  # ACQUIRED | UNCHANGED | FAILED
    role: str = ""  # registry | standard | implementation_plan | technical_rationale
    warning: str = ""

    def fingerprint(self) -> str:
        return hashlib.sha256(f"{self.url}|{self.sha256}|{self.retrieved_at}".encode()).hexdigest()


@dataclass
class LifecycleFacts:
    """Sourced lifecycle facts for one standard revision, parsed from the
    One-Stop Shop workbook. Dates are ISO ``YYYY-MM-DD`` or ``''`` when the
    registry cell is empty — an absent date is never guessed."""

    standard: str
    status: str = ""
    title: str = ""
    board_adopted: str = ""
    filed: str = ""
    ferc_order: str = ""
    regulatory_order_effective: str = ""
    effective: str = ""
    phased_implementation: bool = False
    inactive: str = ""
    implementation_plan_url: str = ""
    project_page_url: str = ""
    technical_rationale_url: str = ""
    rsaw_url: str = ""
    public_notes: str = ""
    docket: str = ""
    registry_sha256: str = ""  # provenance: the workbook these facts came from

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SyncReport:
    """The result of one synchronization run."""

    ran_at: str = ""
    family: str = ""
    artifacts: list[Artifact] = field(default_factory=list)
    lifecycle: dict[str, dict[str, Any]] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    store_revisions: dict[str, str] = field(default_factory=dict)  # name -> revision_id

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


# ── acquisition ──────────────────────────────────────────────────────────────


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def fetch_bytes(url: str, *, timeout: float = 90.0) -> bytes:
    """Fetch official bytes. Raises on any transport/HTTP failure — the caller
    decides how to preserve the last verified snapshot."""
    response = httpx.get(
        url,
        timeout=timeout,
        follow_redirects=True,
        headers={
            "User-Agent": "portal-5 compliance source synchronizer",
        },
    )
    response.raise_for_status()
    return response.content


def _media_type(url: str, payload: bytes) -> str:
    if url.endswith(".pdf") or payload[:5] == b"%PDF-":
        return "application/pdf"
    if url.endswith(".xlsx") or payload[:2] == b"PK":
        return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    if url.endswith(".docx"):
        return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    if payload[:15].lstrip().lower().startswith((b"<!doctype html", b"<html")):
        return "text/html"
    return "application/octet-stream"


def _acquire(
    name: str,
    url: str,
    *,
    role: str,
    directory: Path,
    fetch: Any = fetch_bytes,
) -> Artifact:
    """Fetch, fingerprint, and durably store one artifact.

    Failure semantics: if the fetch raises AND a previous copy exists on disk,
    the previous copy is preserved and reported ``UNCHANGED``-with-warning —
    the artifact is stale but retained, never silently current. If no previous
    copy exists the artifact is ``FAILED`` and the warning says so.
    """
    dest = directory / name
    try:
        payload = fetch(url)
    except Exception as exc:  # noqa: BLE001 - any transport failure preserves state
        if dest.exists():
            old = dest.read_bytes()
            return Artifact(
                name=name,
                url=url,
                media_type=_media_type(url, old),
                sha256=hashlib.sha256(old).hexdigest(),
                size=len(old),
                retrieved_at="",
                path=str(dest),
                status="UNCHANGED",
                role=role,
                warning=f"refresh failed ({exc}); last verified snapshot retained",
            )
        return Artifact(
            name=name,
            url=url,
            status="FAILED",
            role=role,
            warning=f"acquisition failed and no prior snapshot exists: {exc}",
        )
    digest = hashlib.sha256(payload).hexdigest()
    artifact = Artifact(
        name=name,
        url=url,
        media_type=_media_type(url, payload),
        sha256=digest,
        size=len(payload),
        retrieved_at=_now_iso(),
        path=str(dest),
        status="ACQUIRED",
        role=role,
    )
    if dest.exists() and hashlib.sha256(dest.read_bytes()).hexdigest() == digest:
        artifact.status = "UNCHANGED"  # fingerprint-aware: identical bytes, no rewrite
        artifact.retrieved_at = _now_iso()
        return artifact
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    tmp.write_bytes(payload)
    tmp.replace(dest)  # atomic within the directory; bytes never mutated in place
    return artifact


# ── lifecycle parsing ───────────────────────────────────────────────────────


def _iso(value: Any) -> str:
    """Workbook date cell → ISO date. An absent cell is '', never guessed."""
    if value is None or value == "":
        return ""
    text = str(value)[:10]
    return text if len(text) == 10 and text[4] in ("-", "/") else str(value)[:10]


def _link(cell: Any) -> str:
    target = getattr(cell, "hyperlink", None)
    if target is not None and getattr(target, "target", None):
        return str(target.target)
    value = getattr(cell, "value", None)
    return str(value) if value and str(value).startswith("http") else ""


def parse_lifecycle(xlsx_bytes: bytes, *, registry_sha256: str = "") -> dict[str, LifecycleFacts]:
    """Parse the One-Stop Shop workbook into lifecycle facts keyed by standard
    number (e.g. ``CIP-007-6``)."""
    import io
    import warnings

    from openpyxl import load_workbook

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        wb = load_workbook(io.BytesIO(xlsx_bytes), data_only=True)
    ws = wb["One Stop Shop"]
    rows = list(ws.iter_rows())
    # stripped: the workbook's own header cells carry padding (" RSAW "), and a
    # column lost to whitespace is a component nobody knows is missing
    header = [str(c.value or "").strip() for c in rows[0]]
    idx = {name: header.index(name) for name in _LIFECYCLE_COLUMNS if name in header}

    facts: dict[str, LifecycleFacts] = {}
    for row in rows[1:]:
        standard = str(row[idx["Standard Number"]].value or "")
        if not standard:
            continue
        notes = str(row[idx["Public Notes"]].value or "") if "Public Notes" in idx else ""
        docket = ""
        for line in notes.splitlines():
            if "Docket" in line:
                docket = line.strip()
                break
        facts[standard] = LifecycleFacts(
            standard=standard,
            status=str(row[idx["Status"]].value or ""),
            title=str(row[idx["Standard Title"]].value or ""),
            board_adopted=_iso(row[idx["Board Adopted Date"]].value),
            filed=_iso(row[idx["Filing Date of Standard"]].value),
            ferc_order=_iso(row[idx["FERC Orders (Issued Date)"]].value),
            regulatory_order_effective=_iso(row[idx["Regulatory Order Effective Date"]].value),
            effective=_iso(row[idx["Effective Date of Standard"]].value),
            phased_implementation=bool(row[idx["Phased-in Implementation"]].value),
            inactive=_iso(row[idx["Inactive Date of Standard"]].value),
            implementation_plan_url=_link(row[idx["Implementation Plan"]]),
            project_page_url=_link(row[idx["Project Page"]]),
            technical_rationale_url=_link(row[idx["Technical Rationale"]]),
            rsaw_url=_link(row[idx["RSAW"]]),
            public_notes=notes,
            docket=docket,
            registry_sha256=registry_sha256,
        )
    return facts


# ── the bundle synchronizer ─────────────────────────────────────────────────


#: artifact role -> (source_kind, logical-id suffix). The logical id is the
#: STANDARD's stable identity plus the component, never the filename: two
#: acquisitions of the same standard are two revisions of one document, and a
#: filename change must not fork the identity (BILATERAL_CORPUS_V1 P3).
_ROLE_IDENTITY: dict[str, tuple[str, str]] = {
    "standard": ("regulatory_standard", ""),
    "implementation_plan": ("implementation_plan", " implementation plan"),
    "technical_rationale": ("technical_rationale", " technical rationale"),
    "rsaw": ("rsaw", " RSAW"),
    "registry": ("lifecycle_registry", ""),
}

# the standard id at the head of an artifact name, read off the name's stem so a
# version dot is never confused with a file extension: cip-007-6.pdf ->
# CIP-007-6, cip-002-5.1a.pdf -> CIP-002-5.1A,
# cip-007-6-implementation-plan.pdf -> CIP-007-6.
_ARTIFACT_EXT_RE = re.compile(r"\.(pdf|xlsx|html|htm|docx)$", re.I)
_ARTIFACT_STANDARD_RE = re.compile(r"^(cip-\d{3}-[\d.]+[a-z]?)(?:$|-)", re.I)


def canonical_identity(artifact: Artifact) -> tuple[str, str, str]:
    """``(logical_id, source_kind, title)`` for one acquired artifact.

    Derived from the artifact's ROLE and the standard id its name carries, so
    ``cip-007-6.pdf`` and a later ``cip-007-6-clean.pdf`` are two revisions of
    ``NERC/CIP-007-6`` rather than two documents. An artifact whose name carries
    no standard id keeps its own name as its identity — honest, and visible.
    """
    kind, suffix = _ROLE_IDENTITY.get(artifact.role, ("official_standard_material", ""))
    if artifact.role == "registry":
        return "NERC/one-stop-shop", kind, "NERC One-Stop Shop lifecycle registry"
    m = _ARTIFACT_STANDARD_RE.match(_ARTIFACT_EXT_RE.sub("", artifact.name))
    if not m:
        return f"NERC/{artifact.name}", kind, artifact.name
    family, number, version = m.group(1).split("-", 2)
    # the family is upper-cased, the version kept exactly as published: the
    # register spells it CIP-002-5.1a, and 5.1A is a different string.
    standard = f"{family.upper()}-{number}-{version}"
    return f"NERC/{standard}{suffix}", kind, f"{standard}{suffix}".strip()


def apply_lifecycle_only(repo: Any, standard: str, entry: LifecycleFacts) -> dict[str, Any]:
    """Record a moved effective date without re-capturing the document.

    A lifecycle change is a fact about a revision's *effectivity*, not its
    *text*. There was no path to record one without re-capturing the whole
    document, which is what wedged the NERC autosync: re-capturing an
    UNCHANGED revision deleted sections that citations, spans and requirement
    joins reference. This writes the effectivity change against the existing
    revision and touches no section.
    """
    row = repo._conn.execute(
        """SELECT r.revision_id FROM document_revisions r
           JOIN source_documents d ON d.logical_id = r.logical_id
           WHERE d.source_kind = 'regulatory_standard' AND d.logical_id LIKE ?
           ORDER BY r.retrieved_at DESC LIMIT 1""",
        (f"%/{standard}",),
    ).fetchone()
    if row is None:
        return {
            "standard": standard,
            "action": "no_existing_revision",
            "reason": f"no stored revision for {standard} — cannot apply lifecycle-only",
        }
    revision_id = str(row[0])
    repo.set_regulatory_lifecycle(
        revision_id,
        effective_date=str(entry.effective or ""),
        inactive_date=str(entry.inactive or ""),
        approved_date=str(entry.board_adopted or ""),
        authored_date=str(entry.filed or ""),
        lifecycle_status=str(entry.status or ""),
    )
    return {
        "standard": standard,
        "revision_id": revision_id,
        "action": "lifecycle_only",
        "effective_date": entry.effective,
        "inactive_date": entry.inactive,
        "lifecycle_status": entry.status,
    }


def _register_in_store(
    logical_id: str, title: str, alias_path: str, payload: bytes, source_kind: str
) -> str:
    """Record the artifact in the canonical store as an immutable revision.

    Idempotent on identical bytes (content hash). New bytes at the same alias
    create a new revision; the old revision still resolves. Returns the
    revision id (sha256 of the bytes)."""
    from portal.modules.compliance.core.models import SourceDocument
    from portal.modules.compliance.core.repository import Repository

    repo = Repository()
    try:
        repo.upsert_source_document(
            SourceDocument(
                logical_id=logical_id,
                title=title,
                issuer="NERC",
                source_kind=source_kind,
                jurisdiction="US",
            )
        )
        rev = repo.add_document_revision(
            logical_id,
            alias_path,
            payload,
            binding_effect="regulatory",
        )
        return rev.revision_id
    finally:
        repo.close()


def _register_glossary(payload: bytes, artifact: Artifact) -> str:
    """Register the Glossary as a resolvable term corpus: one section per term,
    with the effectivity sidecar beside the acquired bytes."""
    from portal.modules.compliance.core.glossary import (
        parse_glossary,
        register_glossary,
        write_term_dates,
    )
    from portal.modules.compliance.core.repository import Repository

    repo = Repository()
    try:
        write_term_dates(Path(artifact.path).parent, parse_glossary(payload))
        report = register_glossary(repo, payload, artifact.path)
        return str(report["revision_id"])
    finally:
        repo.close()


def _register_artifacts(report: SyncReport) -> None:
    """Register every acquired/unchanged artifact in the canonical store. A
    store failure is a warning on the report, never data loss — the bytes and
    the manifest are already durable."""
    for artifact in report.artifacts:
        if artifact.status == "FAILED":
            continue
        payload = Path(artifact.path).read_bytes()
        if artifact.role == "glossary":
            try:
                report.store_revisions[artifact.name] = _register_glossary(payload, artifact)
            except Exception as exc:  # noqa: BLE001 - a parse failure is reported, not fatal
                report.warnings.append(
                    f"{artifact.name}: Glossary registration failed ({exc}); "
                    "bytes and manifest retained, defined terms will not resolve"
                )
            continue
        logical_id, source_kind, title = canonical_identity(artifact)
        try:
            revision_id = _register_in_store(
                logical_id=logical_id,
                title=title,
                alias_path=artifact.path,
                payload=payload,
                source_kind=source_kind,
            )
            report.store_revisions[artifact.name] = revision_id
        except Exception as exc:  # noqa: BLE001 - store failure is a warning, not data loss
            report.warnings.append(
                f"{artifact.name}: canonical-store registration failed ({exc}); "
                "bytes and manifest retained"
            )


def sync_official_bundle(
    family: str = "CIP-007",
    versions: tuple[str, ...] = ("6", "7.1"),
    *,
    directory: Path | None = None,
    fetch: Any = fetch_bytes,
    register_store: bool = True,
) -> SyncReport:
    """Synchronize the official bundle for one family. Idempotent for
    unchanged bytes; failure-preserving for network errors."""
    directory = directory or OFFICIAL_DIR
    directory.mkdir(parents=True, exist_ok=True)
    report = SyncReport(ran_at=_now_iso(), family=family)

    # 1. the lifecycle registry — everything else's provenance
    registry = _acquire(
        "one-stop-shop.xlsx",
        ONE_STOP_SHOP_URL,
        role="registry",
        directory=directory,
        fetch=fetch,
    )
    report.artifacts.append(registry)
    if registry.status == "FAILED":
        report.warnings.append(
            f"lifecycle registry unavailable: {registry.warning}; lifecycle facts not refreshed"
        )
        _write_manifest(report, directory)
        return report
    if registry.warning:
        # refresh failed but the last verified workbook is on disk: facts stay
        # usable, with an explicit dated currency warning — never "current".
        report.warnings.append(
            f"{_now_iso()}: lifecycle registry not refreshed ({registry.warning});"
            " lifecycle facts come from the last verified snapshot and must not"
            " be treated as current"
        )

    registry_bytes = (directory / "one-stop-shop.xlsx").read_bytes()
    facts = parse_lifecycle(registry_bytes, registry_sha256=registry.sha256)
    slug_family = family.lower()  # CIP-007 -> cip-007

    # 1b. the Glossary of Terms — every CIP standard that carries no definitions
    # section defers to it, so it is a component of the bundle, not an extra.
    from portal.modules.compliance.core.glossary import GLOSSARY_ARTIFACT, GLOSSARY_URL

    glossary = _acquire(
        GLOSSARY_ARTIFACT,
        GLOSSARY_URL,
        role="glossary",
        directory=directory,
        fetch=fetch,
    )
    report.artifacts.append(glossary)
    if glossary.status == "FAILED":
        report.warnings.append(
            f"NERC Glossary unavailable: {glossary.warning}; defined terms will not resolve"
        )

    # 2. standard PDFs + linked implementation plans / technical rationale
    for version in versions:
        standard = f"{family}-{version}"
        entry = facts.get(standard)
        if entry is None:
            report.warnings.append(
                f"{standard} is absent from the lifecycle registry; no lifecycle facts recorded"
            )
            continue
        report.lifecycle[standard] = entry.as_dict()

        pdf = _acquire(
            f"{standard.lower()}.pdf",
            _STANDARD_PDF_URL.format(slug=f"{slug_family}-{version.lower()}"),
            role="standard",
            directory=directory,
            fetch=fetch,
        )
        report.artifacts.append(pdf)

        plan_name = f"{standard.lower()}-implementation-plan.pdf"
        if entry.implementation_plan_url:
            plan = _acquire(
                plan_name,
                quote(entry.implementation_plan_url, safe=":/%"),
                role="implementation_plan",
                directory=directory,
                fetch=fetch,
            )
            report.artifacts.append(plan)
        else:
            report.warnings.append(f"{standard} has no implementation-plan link in the registry")

        if entry.technical_rationale_url:
            report.artifacts.append(
                _acquire(
                    f"{standard.lower()}-technical-rationale.pdf",
                    quote(entry.technical_rationale_url, safe=":/%"),
                    role="technical_rationale",
                    directory=directory,
                    fetch=fetch,
                )
            )

        # the RSAW — the compliance auditor's own question sheet per requirement
        # (MODULE_COMPLETE_V1 §P0.5: acquired + captured; placement stays open —
        # the guidance is keyed by bare table-cell R<n> markers, not by
        # requirement-named headings, so the heading route cannot place it)
        if entry.rsaw_url:
            rsaw_suffix = ".docx" if entry.rsaw_url.lower().endswith(".docx") else ".pdf"
            report.artifacts.append(
                _acquire(
                    f"{standard.lower()}-rsaw{rsaw_suffix}",
                    quote(entry.rsaw_url, safe=":/%"),
                    role="rsaw",
                    directory=directory,
                    fetch=fetch,
                )
            )
        else:
            report.warnings.append(f"{standard} has no RSAW link in the registry")

    report.warnings.extend(
        f"{a.name}: {a.warning}" for a in report.artifacts if a.warning and a.status != "FAILED"
    )

    # 3. register acquired/unchanged artifacts in the canonical store
    if register_store:
        _register_artifacts(report)

    _write_manifest(report, directory)
    return report


def _write_manifest(report: SyncReport, directory: Path) -> None:
    manifest = {
        "ran_at": report.ran_at,
        "family": report.family,
        "artifacts": [asdict(a) for a in report.artifacts],
        "lifecycle": report.lifecycle,
        "warnings": report.warnings,
        "store_revisions": report.store_revisions,
    }
    target = directory / MANIFEST_NAME
    tmp = target.with_suffix(".tmp")
    tmp.write_text(json.dumps(manifest, indent=2, default=str))
    tmp.replace(target)


def load_manifest(directory: Path | None = None) -> dict[str, Any]:
    """The retained acquisition manifest (last run)."""
    target = (directory or OFFICIAL_DIR) / MANIFEST_NAME
    return json.loads(target.read_text()) if target.exists() else {}


def lifecycle_for(standard: str, directory: Path | None = None) -> dict[str, Any]:
    """Sourced lifecycle facts for one standard revision, from the retained
    manifest. Empty dict when never synchronized."""
    return dict(load_manifest(directory).get("lifecycle", {}).get(standard, {}))
