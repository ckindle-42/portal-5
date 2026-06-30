"""Tests that backends.yaml model ids are 1:1 with MODEL_CATALOG.md sections.

Prevents backends.yaml and MODEL_CATALOG.md from drifting after M2.
Every model id in backends.yaml must have a catalog section, and vice versa.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent.parent
BACKENDS = REPO / "config" / "backends.yaml"
CATALOG = REPO / "config" / "MODEL_CATALOG.md"


def _backends_model_ids() -> set[str]:
    raw = yaml.safe_load(BACKENDS.read_text()) or {}
    ids = set()
    for backend in raw.get("backends", []):
        for model in backend.get("models", []):
            mid = model.get("id", "")
            if mid:
                ids.add(mid)
    return ids


def _catalog_model_ids() -> set[str]:
    text = CATALOG.read_text()
    # Catalog sections are: ### `model/id:tag`
    return set(re.findall(r"^### `([^`]+)`", text, re.MULTILINE))


def _catalog_retired_ids() -> set[str]:
    """Catalog headers explicitly marked DROPPED/RETIRED in the header line.

    Additive-only catalog discipline: nothing is deleted, retired models are
    labeled in place rather than purged. Such entries are expected to have no
    backends.yaml counterpart — that's the point of removal — so they're
    exempt from the orphan check below without exempting genuine drift.
    """
    text = CATALOG.read_text()
    return set(re.findall(r"^### `([^`]+)` — (?:DROPPED|RETIRED)\b", text, re.MULTILINE))


def test_all_backends_models_have_catalog_entry() -> None:
    """Every model id in backends.yaml must have a ### `id` section in MODEL_CATALOG.md."""
    backend_ids = _backends_model_ids()
    catalog_ids = _catalog_model_ids()
    missing = backend_ids - catalog_ids
    assert not missing, (
        f"{len(missing)} model(s) in backends.yaml with no MODEL_CATALOG entry:\n"
        + "\n".join(f"  {m}" for m in sorted(missing))
    )


def test_no_orphan_catalog_entries() -> None:
    """Every MODEL_CATALOG.md section must correspond to a model in backends.yaml,
    unless explicitly labeled DROPPED/RETIRED (additive-only catalog discipline)."""
    backend_ids = _backends_model_ids()
    catalog_ids = _catalog_model_ids()
    retired_ids = _catalog_retired_ids()
    orphans = catalog_ids - backend_ids - retired_ids
    assert not orphans, (
        f"{len(orphans)} MODEL_CATALOG section(s) with no matching backends.yaml entry "
        "and no DROPPED/RETIRED label:\n" + "\n".join(f"  {m}" for m in sorted(orphans))
    )


def test_backends_models_have_no_notes_field() -> None:
    """After M2, no model entry in backends.yaml may have a notes: field (prose lives in catalog)."""
    raw = yaml.safe_load(BACKENDS.read_text()) or {}
    models_with_notes = []
    for backend in raw.get("backends", []):
        for model in backend.get("models", []):
            if "notes" in model:
                models_with_notes.append(model.get("id", "(unknown)"))
    assert not models_with_notes, (
        "Model entries still contain notes: field — prose belongs in MODEL_CATALOG.md:\n"
        + "\n".join(f"  {m}" for m in models_with_notes)
    )


def test_catalog_lossless_from_snapshot() -> None:
    """Every note in the relocation snapshot must appear verbatim (first 40 chars) in catalog."""
    import json

    snapshot_path = REPO / "tests" / "fixtures" / "backends_notes_snapshot.json"
    snap = json.loads(snapshot_path.read_text())
    catalog_text = CATALOG.read_text()

    missing = []
    for mid, v in snap.items():
        notes = v.get("notes", "") if isinstance(v, dict) else v
        if notes and notes.strip()[:40] not in catalog_text:
            missing.append(mid)

    assert not missing, (
        f"{len(missing)} model note(s) not found in catalog (first 40 chars mismatch):\n"
        + "\n".join(f"  {m}" for m in sorted(missing))
    )
