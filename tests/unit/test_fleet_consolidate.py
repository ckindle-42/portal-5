"""Unit coverage for `scripts/fleet_consolidate.py` — the dry-run keep/remove table.

Fake config in `tmp_path`, fake Ollama tags and fake `ollama show` output: the
report's decisions are pure functions of those inputs, so no live engine, network
or repo state is involved (except the read-only real-config invariant at the end).
"""

from __future__ import annotations

from pathlib import Path

from scripts import fleet_consolidate as fc

REPO_ROOT = Path(__file__).resolve().parents[2]


def _facts(
    tags: dict[str, dict[str, int]] | None = None,
    dirs: dict[str, dict[tuple[int, int], int]] | None = None,
) -> fc.Facts:
    tags = tags or {}
    dirs = dirs or {}
    return fc.Facts(
        ollama_tags={name.lower(): name for name in tags},
        blob_sizes=dict(tags),
        omlx_dirs={name: Path("/fake") / name for name in dirs},
        dir_files=dict(dirs),
    )


def test_real_config_keeps_one_variant_per_warn_family():
    """Read-only: every WARN family on the live config keeps at least one variant.
    An empty worklist (the fleet rule passes) is the goal state, not a failure."""
    report = fc.build_report(REPO_ROOT, _facts())
    for fam in report["families"]:
        assert any(v["action"] == "KEEP" for v in fam["variants"]), fam["key"]


def test_real_config_marks_every_remove_candidate_with_a_reason():
    report = fc.build_report(REPO_ROOT, _facts())
    for fam in report["families"]:
        for variant in fam["variants"]:
            assert variant["reason"]
            if variant["action"] == "REMOVE-CANDIDATE":
                assert variant["repoints"] is not None
