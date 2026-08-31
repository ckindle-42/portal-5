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
    """Catalog headers explicitly marked DROPPED/RETIRED/NEEDS-GGUF-CONVERSION.

    Additive-only catalog discipline: nothing is deleted, retired models are
    labeled in place rather than purged. Such entries are expected to have no
    backends.yaml counterpart — that's the point of removal — so they're
    exempt from the orphan check below without exempting genuine drift.
    NEEDS-GGUF-CONVERSION marks a surveyed specialist that was never
    registered (conversion blocked or, per TASK_CAD_MODULE_OVERHAUL_V1,
    a broken upstream checkpoint) — same "no backends.yaml entry expected"
    shape as DROPPED/RETIRED.
    """
    text = CATALOG.read_text()
    return set(
        re.findall(
            r"^### `([^`]+)` — (?:DROPPED|RETIRED|NEEDS-GGUF-CONVERSION)\b",
            text,
            re.MULTILINE,
        )
    )


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


def _backends_alias_maps() -> list[tuple[str, dict[str, str]]]:
    """(backend_id, aliases) for every backend that declares an aliases: map."""
    raw = yaml.safe_load(BACKENDS.read_text()) or {}
    out = []
    for backend in raw.get("backends", []):
        aliases = backend.get("aliases") or {}
        if aliases:
            out.append((backend.get("id", "(unknown)"), dict(aliases)))
    return out


def test_omlx_alias_targets_have_catalog_entry() -> None:
    """Every oMLX alias *target* (the native MLX model name a GGUF hint maps to)
    must have its own MODEL_CATALOG.md section — otherwise a hint can resolve to a
    model with no catalog provenance, and the hollow-group check can't reason about it.
    """
    catalog_ids = _catalog_model_ids()
    missing: list[str] = []
    for bid, aliases in _backends_alias_maps():
        if "omlx" not in bid:
            continue
        for src, target in aliases.items():
            if target not in catalog_ids:
                missing.append(f"{bid}: {src!r} -> {target!r}")
    assert not missing, "oMLX alias target(s) with no MODEL_CATALOG entry:\n" + "\n".join(
        f"  {m}" for m in sorted(missing)
    )


def test_alias_source_keys_are_known_model_ids() -> None:
    """Every alias *key* (the GGUF hint operators/personas reference) must be a real
    backends.yaml model id — a typo'd key silently never matches and the alias is dead.
    """
    known = _backends_model_ids()
    dangling: list[str] = []
    for bid, aliases in _backends_alias_maps():
        for src in aliases:
            if src not in known:
                dangling.append(f"{bid}: {src!r}")
    assert not dangling, (
        "alias source key(s) not present as a backends.yaml model id:\n"
        + "\n".join(f"  {m}" for m in sorted(dangling))
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
    r"""Every model id in the relocation snapshot must still have a catalog section.

    The snapshot (`tests/fixtures/backends_notes_snapshot.json`) captured the notes
    that were relocated from backends.yaml into MODEL_CATALOG.md at M2. Its original
    form asserted the note *text* survived verbatim; that became a stale invariant
    once TASK_WIKI_ZERO_DEBT_V1 re-grounded the model-catalog units to
    `config/backends.yaml` and rewrote each body against the live config. What the
    snapshot still protects is id preservation: no relocated model may have lost its
    catalog entry. Every model in the snapshot must appear as a `### \`id\`` section.
    """
    import json
    import re

    snapshot_path = REPO / "tests" / "fixtures" / "backends_notes_snapshot.json"
    snap = json.loads(snapshot_path.read_text())
    catalog_ids = set(re.findall(r"^### `([^`]+)`", CATALOG.read_text(), re.MULTILINE))

    missing = [mid for mid in snap if mid not in catalog_ids]
    assert not missing, (
        f"{len(missing)} snapshot model id(s) missing from MODEL_CATALOG.md:\n"
        + "\n".join(f"  {m}" for m in sorted(missing))
    )
