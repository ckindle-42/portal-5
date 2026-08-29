"""Adaptive UAT — catalog assembly (TASK_UAT_ADAPTIVE_OVERHAUL_V1).

Turns generated challenge suites into a list of runner-compatible test dicts
that ``tests.uat.cli._select_tests`` swaps in when ``--adaptive`` is set. The
challenges then execute through the *existing* OWUI browser runner unchanged —
real routing, real personas, real tool loops, real artifacts — which is what a
release sign-off must exercise.

Not-addressable spaces (designed but not reachable in OWUI) are excluded from
the default run and written to a manifest the review rollup surfaces as an
exposure-gap finding, rather than silently passing or failing.
"""

from __future__ import annotations

import json
from pathlib import Path

from tests.uat.adaptive.generate import build_all
from tests.uat.adaptive.introspect import introspect_spaces
from tests.uat.adaptive.rubric import build_rubric

_ROOT = Path(__file__).resolve().parents[3]
UNREACHABLE_MANIFEST = _ROOT / "tests" / "uat_adaptive" / "designed_unreachable.json"


def build_adaptive_catalog(args=None) -> list[dict]:
    """Return runner-ready adaptive test dicts.

    Honors these optional args attributes when present:
        adaptive_regenerate  -> re-author suites (default: replay frozen)
        adaptive_dry_run     -> template prompts, no author-model call
        adaptive_space       -> list[str] restrict to space id(s)
        adaptive_dimension   -> list[str] restrict to dimension(s)
        adaptive_author_model-> author model slug override
        adaptive_include_unreachable -> also emit not-OWUI-addressable spaces
        section              -> list[str] restrict to adaptive-<module> section(s)
    """
    regenerate = bool(getattr(args, "adaptive_regenerate", False))
    dry = bool(getattr(args, "adaptive_dry_run", False))
    space_filter = tuple(getattr(args, "adaptive_space", None) or ())
    dims = tuple(getattr(args, "adaptive_dimension", None) or ()) or None
    author_model = getattr(args, "adaptive_author_model", "") or ""
    include_unreachable = bool(getattr(args, "adaptive_include_unreachable", False))
    sections = set(getattr(args, "section", None) or [])

    spaces = {s.space_id: s for s in introspect_spaces()}
    # Run-time authoring (--adaptive-regenerate) is a convenience for dev/regression
    # runs only: it uses the template author, or the non-independent local model if
    # --adaptive-author-model is given — never empty skeletons, which cannot execute.
    # The release sign-off authors challenges with the Claude Code agent ahead of the
    # run (emit_worksheets -> agent fills -> ingest_worksheets -> frozen), which this
    # then loads with regenerate=False.
    author = "model" if author_model else "template"
    suites = build_all(
        dry=(author == "template"),
        regenerate=regenerate,
        author=author,
        author_model=author_model,
        space_filter=space_filter,
        dimensions=dims,
    )

    catalog: list[dict] = []
    unreachable: list[dict] = []
    for space_id, suite in suites.items():
        space = spaces.get(space_id)
        if space is None:
            continue
        if not space.owui_addressable and not include_unreachable:
            unreachable.append(
                {
                    "space_id": space_id,
                    "name": space.name,
                    "module": space.module,
                    "kind": space.kind,
                    "reason": "no OWUI workspace/ide_expose signal — not selectable in OWUI",
                    "design_refs": list(space.design_refs),
                }
            )
            continue
        for ch in suite:
            rub = build_rubric(space, ch.dimension, ch.rubric_id).to_dict()
            entry = ch.to_catalog_dict(space, rub)
            if sections and entry["section"] not in sections:
                continue
            catalog.append(entry)

    # Persist the exposure-gap finding for the review rollup.
    UNREACHABLE_MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    UNREACHABLE_MANIFEST.write_text(
        json.dumps(unreachable, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    # Cascade-friendly stable order (runner re-sorts, but keep it deterministic).
    catalog.sort(key=lambda t: (t["workspace_tier"], t["model_slug"], t["id"]))
    return catalog


if __name__ == "__main__":  # pragma: no cover
    import types

    cat = build_adaptive_catalog(types.SimpleNamespace(adaptive_dry_run=True))
    print(f"{len(cat)} adaptive catalog entries")
    print(f"unreachable manifest: {UNREACHABLE_MANIFEST}")
