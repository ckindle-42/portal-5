#!/usr/bin/env python3
"""Acquire corpus sources for the analyst corpus (TASK_BULLY_SA5.1).

The missing acquisition layer from SA4: fetch every dossier-approved source
into ``PORTAL5_HUNT_DIR/corpora/<source>/`` and record URL, retrieval
timestamp, byte size, checksum, and license into an **acquisition manifest**.
A source that fails to fetch is a **recorded finding**, never a silent skip
(A2). A license-incompatible source (OTRF GPL-3.0) is **never fetched**.

Usage::

    python3 scripts/corpus_acquire.py                      # all admissible sources
    python3 scripts/corpus_acquire.py --source flaws_cloud_cloudtrail
    python3 scripts/corpus_acquire.py --manifest-only      # no network, re-emit manifest

The manifest is append-only per source: re-running overwrites the artifact
under a source's staging root but updates the manifest row (new timestamp /
bytes / checksum). Every row carries the source's dossier license call, so the
record is self-validating against ``license_is_compatible``.

Sources with a ``git`` fetch kind are cloned shallowly; sources with a
``download`` fetch kind are streamed to disk with a retry. Both record the
same fields.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from portal.modules.security.core.bully.analyst_corpus import (  # noqa: E402
    CANDIDATE_SOURCE_DOSSIERS,
    SourceDossier,
    license_is_compatible,
)

ACQUISITION_MANIFEST_SCHEMA = "CORPUS_ACQUISITION_MANIFEST_V1"


def corpora_root() -> Path:
    """``PORTAL5_HUNT_DIR/corpora`` (optional override; default under the
    hunt dir, outside the repo)."""
    base = Path(os.environ.get("PORTAL5_HUNT_DIR", "/Volumes/data01/portal5_hunt/"))
    return base / "corpora"


@dataclass(frozen=True)
class SourceFetchSpec:
    """How one dossier-approved source is acquired: its manifest identity and
    a fetch ``kind`` of ``download`` (stream a file) or ``git`` (shallow
    clone). ``url`` is the primary endpoint; ``archive_members`` lists paths
    worth noting in the manifest for download kinds that unpack to a tree."""

    source_id: str
    name: str
    license: str
    fetch_kind: str  # download | git
    url: str
    git_ref: str = "HEAD"
    notes: str = ""

    @classmethod
    def from_dossier(
        cls, dossier: SourceDossier, *, url: str, fetch_kind: str, notes: str = ""
    ) -> SourceFetchSpec:
        return cls(
            source_id=dossier.source_id,
            name=dossier.name,
            license=dossier.license,
            fetch_kind=fetch_kind,
            url=url,
            notes=notes,
        )


# Each admissible source's fetch spec. The license is carried from the dossier
# so the manifest stays self-validating; a license-incompatible source has no
# spec here (it is never fetched -- the loader asserts that).
SOURCE_FETCH_SPECS: tuple[SourceFetchSpec, ...] = (
    SourceFetchSpec.from_dossier(
        next(d for d in CANDIDATE_SOURCE_DOSSIERS if d.source_id == "flaws_cloud_cloudtrail"),
        url="https://summitroute.com/downloads/flaws_cloudtrail_logs.tar",
        fetch_kind="download",
    ),
    SourceFetchSpec.from_dossier(
        next(d for d in CANDIDATE_SOURCE_DOSSIERS if d.source_id == "invictus_ir_aws_dataset"),
        url="https://github.com/invictus-ir/aws_dataset",
        fetch_kind="git",
    ),
    SourceFetchSpec.from_dossier(
        next(d for d in CANDIDATE_SOURCE_DOSSIERS if d.source_id == "cloudtrail_attack_research"),
        url="https://github.com/amitsec-ai/CloudtrailAPIs-MITRE",
        fetch_kind="git",
        notes="CloudTrail API names observed in honeypots/attacks mapped to MITRE tactics "
        "(small, precise; 9 tactic columns)",
    ),
    SourceFetchSpec.from_dossier(
        next(d for d in CANDIDATE_SOURCE_DOSSIERS if d.source_id == "darpa_optc_tc3"),
        url="https://github.com/FiveDirections/OpTC-data",
        fetch_kind="git",
        notes="Ground-truth manifest only; the ~1TB bulk eCAR/Bro captures are hosted on "
        "Google Drive (not scriptable without an API quota) -- recorded as a partial finding",
    ),
)


def load_fetch_specs() -> dict[str, SourceFetchSpec]:
    """Index fetch specs by source_id, asserting license compatibility.

    A license-incompatible source must have no spec: ``corpus_acquire`` never
    fetches it. The assertion is structural, not prose (SA4.1 policy)."""
    specs = {spec.source_id: spec for spec in SOURCE_FETCH_SPECS}
    dossier_by_id = {d.source_id: d for d in CANDIDATE_SOURCE_DOSSIERS}
    for source_id, spec in specs.items():
        dossier = dossier_by_id[source_id]
        if not license_is_compatible(spec.license):
            raise RuntimeError(
                f"fetch spec for license-blocked source {source_id!r} ({spec.license}) -- "
                "an incompatible license must never be fetched"
            )
        if not license_is_compatible(dossier.license):
            raise RuntimeError(f"dossier license for {source_id!r} changed to incompatible")
    return specs


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _download(url: str, dest: Path) -> int:
    """Stream ``url`` to ``dest``, returning bytes written. Retries once on
    transport error; raises the underlying error so it is a recorded finding."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    last_exc: Exception | None = None
    for attempt in (1, 2):
        try:
            with urllib.request.urlopen(url, timeout=600) as resp, dest.open("wb") as out:
                written = 0
                while True:
                    chunk = resp.read(1 << 20)
                    if not chunk:
                        break
                    out.write(chunk)
                    written += len(chunk)
            return written
        except Exception as exc:  # noqa: BLE001 -- transport/parse errors become findings
            last_exc = exc
            time.sleep(2)
    assert last_exc is not None
    raise last_exc


def _git_clone(url: str, dest: Path, ref: str = "HEAD") -> None:
    """Shallow-clone ``url`` into ``dest``. Raises on failure (recorded finding)."""
    dest.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "clone", "--depth", "1", "--branch", ref, url, str(dest)],
        check=True,
        capture_output=True,
        text=True,
    )


def _staged_bytes(root: Path) -> int:
    """Total bytes under a source's staging root (excluding .git plumbing)."""
    total = 0
    for path in root.rglob("*"):
        if path.is_file() and ".git" not in path.parts:
            total += path.stat().st_size
    return total


def _staged_checksum(root: Path) -> str:
    """SHA-256 over staged files in deterministic (sorted-path) order. For a
    download artifact the artifact file dominates; for a git tree the whole
    staged tree is hashed so the manifest fingerprints what is staged."""
    digest = hashlib.sha256()
    for path in sorted(p for p in root.rglob("*") if p.is_file() and ".git" not in p.parts):
        digest.update(str(path.relative_to(root)).encode("utf-8"))
        digest.update(b"\0")
        digest.update(_sha256_file(path).encode("utf-8"))
        digest.update(b"\0")
    return digest.hexdigest()


def acquire_one(
    spec: SourceFetchSpec,
    root: Path,
    *,
    fetch: bool = True,
) -> dict[str, Any]:
    """Fetch one source (or re-stage metadata only when ``fetch=False``).

    Returns a manifest row: fetched / failed / license-blocked. A failed fetch
    records the reason in the row -- it is a finding, never a silent skip."""
    source_root = root / spec.source_id
    manifest_path = root / "manifest.json"
    manifest = load_manifest(root)

    if not license_is_compatible(spec.license):
        return _record(
            manifest_path,
            manifest,
            _row(
                spec,
                status="license_blocked",
                reason=f"license {spec.license} incompatible",
                root=root,
            ),
        )

    if not fetch:
        if not source_root.exists():
            return _record(
                manifest_path,
                manifest,
                _row(spec, status="failed", reason="not staged (manifest-only run)", root=root),
            )
        return _record(
            manifest_path,
            manifest,
            _row(spec, status="fetched", root=root),
        )

    try:
        if spec.fetch_kind == "download":
            dest = source_root / Path(spec.url).name
            if dest.exists():
                dest.unlink()
            _download(spec.url, dest)
        elif spec.fetch_kind == "git":
            _git_clone(spec.url, source_root, spec.git_ref)
        else:  # pragma: no cover -- guarded by construction
            raise ValueError(f"unknown fetch kind {spec.fetch_kind!r}")
    except Exception as exc:  # noqa: BLE001 -- any failure becomes a recorded finding
        return _record(
            manifest_path,
            manifest,
            _row(spec, status="failed", reason=f"{type(exc).__name__}: {exc}", root=root),
        )
    return _record(
        manifest_path,
        manifest,
        _row(spec, status="fetched", root=root),
    )


def _row(
    spec: SourceFetchSpec, *, status: str, reason: str = "", root: Path | None = None
) -> dict[str, Any]:
    source_root = (root or corpora_root()) / spec.source_id
    staged_bytes = _staged_bytes(source_root) if source_root.exists() else 0
    checksum = (
        _staged_checksum(source_root) if (source_root.exists() and status == "fetched") else ""
    )
    return {
        "source_id": spec.source_id,
        "name": spec.name,
        "license": spec.license,
        "license_compatible": license_is_compatible(spec.license),
        "url": spec.url,
        "fetch_kind": spec.fetch_kind,
        "status": status,
        "reason": reason,
        "fetched_at": time.time(),
        "staged_root": str(source_root),
        "bytes": staged_bytes,
        "checksum": checksum,
        "notes": spec.notes,
    }


def _record(manifest_path: Path, manifest: dict[str, Any], row: dict[str, Any]) -> dict[str, Any]:
    by_id = {entry["source_id"]: entry for entry in manifest.get("sources", [])}
    by_id[row["source_id"]] = row
    manifest["sources"] = [by_id[key] for key in sorted(by_id)]
    manifest["reconciled"] = True
    manifest_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    manifest_path.chmod(0o600)
    return row


def load_manifest(root: Path) -> dict[str, Any]:
    path = root / "manifest.json"
    if not path.exists():
        return {"schema": ACQUISITION_MANIFEST_SCHEMA, "sources": []}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema") != ACQUISITION_MANIFEST_SCHEMA:
        raise ValueError(f"unknown acquisition manifest schema: {payload.get('schema')!r}")
    return payload


def _manifest_summary(manifest: dict[str, Any]) -> dict[str, Any]:
    counts: dict[str, int] = {}
    total_bytes = 0
    for entry in manifest.get("sources", []):
        counts[entry.get("status", "unknown")] = counts.get(entry.get("status", "unknown"), 0) + 1
        total_bytes += int(entry.get("bytes") or 0)
    return {
        "schema": ACQUISITION_MANIFEST_SCHEMA,
        "source_count": len(manifest.get("sources", [])),
        "status_counts": counts,
        "total_staged_bytes": total_bytes,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", help="fetch only this source_id (default: all admissible)")
    ap.add_argument(
        "--manifest-only", action="store_true", help="re-emit manifest metadata without network"
    )
    ap.add_argument(
        "--root", type=Path, default=None, help="corpora root (default: $PORTAL5_HUNT_DIR/corpora)"
    )
    args = ap.parse_args(argv)

    root = args.root or corpora_root()
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    specs = load_fetch_specs()
    if args.source:
        if args.source not in specs:
            print(f"[FAIL] unknown source {args.source!r}; known: {sorted(specs)}", file=sys.stderr)
            return 2
        selected = [specs[args.source]]
    else:
        selected = list(specs.values())

    for spec in selected:
        row = acquire_one(spec, root, fetch=not args.manifest_only)
        print(
            f"[{row['status']:>14}] {row['source_id']:<28} "
            f"{row['bytes']} bytes  sha256={row['checksum'][:12]}"
            + (f"  {row['reason']}" if row.get("reason") else "")
        )
    summary = _manifest_summary(load_manifest(root))
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
