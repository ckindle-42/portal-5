"""Unit coverage for `scripts/fleet_consolidate.py` — the dry-run keep/remove table.

Fake config in `tmp_path`, fake Ollama tags and fake `ollama show` output: the
report's decisions are pure functions of those inputs, so no live engine, network
or repo state is involved (except the read-only real-config invariant at the end).
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
import yaml

from scripts import fleet_consolidate as fc

REPO_ROOT = Path(__file__).resolve().parents[2]
_MODEL_LAYER = "application/vnd.ollama.image.model"


def _omlx(models: list, aliases: dict | None = None) -> dict:
    return {
        "group": "general",
        "id": "omlx-general",
        "models": models,
        "priority": 10,
        "aliases": aliases or {},
        "type": "omlx",
        "url": "http://omlx",
    }


def _ollama(models: list) -> dict:
    return {
        "group": "general",
        "id": "ollama-general",
        "models": models,
        "type": "ollama",
        "url": "http://ollama",
    }


def _repo(
    tmp_path: Path,
    backends: list[dict],
    portal: str | None = None,
    bench: str | None = None,
) -> Path:
    (tmp_path / "config" / "personas").mkdir(parents=True)
    (tmp_path / "config" / "backends.yaml").write_text(
        yaml.dump({"backends": backends}), encoding="utf-8"
    )
    if portal is not None:
        (tmp_path / "config" / "portal.yaml").write_text(portal, encoding="utf-8")
    if bench is not None:
        (tmp_path / "config" / "bench_workspaces.yaml").write_text(bench, encoding="utf-8")
    return tmp_path


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


def _actions(report: dict) -> dict[str, str]:
    return {v["id"]: v["action"] for fam in report["families"] for v in fam["variants"]}


def _variant(report: dict, variant_id: str) -> dict:
    for fam in report["families"]:
        for variant in fam["variants"]:
            if variant["id"] == variant_id:
                return variant
    raise AssertionError(f"{variant_id} not in report")


# ── family decisions ─────────────────────────────────────────────────────────
def test_primary_seat_and_its_gguf_fallback_are_kept(tmp_path):
    root = _repo(
        tmp_path,
        [
            _ollama([{"id": "fam:q4_K_M-ctx32k"}, {"id": "fam:q8_0-ctx32k"}]),
            _omlx(
                [{"id": "Fam-4bit"}, {"id": "Fam-oQ4e-mtp"}],
                {"fam:q4_K_M-ctx32k": "Fam-4bit", "fam:q8_0-ctx32k": "Fam-oQ4e-mtp"},
            ),
        ],
        portal="workspaces:\n  auto:\n    model_hint: fam:q4_K_M-ctx32k\n",
    )
    report = fc.build_report(root, _facts())
    actions = _actions(report)
    assert actions["Fam-4bit"] == "KEEP"
    assert actions["fam:q4_K_M-ctx32k"] == "KEEP"
    assert actions["Fam-oQ4e-mtp"] == "REMOVE-CANDIDATE"
    assert actions["fam:q8_0-ctx32k"] == "REMOVE-CANDIDATE"


def test_repoints_name_the_config_line_and_its_target(tmp_path):
    root = _repo(
        tmp_path,
        [
            _ollama([{"id": "fam:q4_K_M-ctx32k"}, {"id": "fam:q8_0-ctx64k"}]),
            _omlx(
                [{"id": "Fam-4bit"}, {"id": "Fam-oQ4e-mtp"}],
                {"fam:q4_K_M-ctx32k": "Fam-4bit", "fam:q8_0-ctx64k": "Fam-oQ4e-mtp"},
            ),
        ],
        portal=(
            "workspaces:\n"
            "  auto:\n"
            "    model_hint: fam:q4_K_M-ctx32k\n"
            "  second:\n"
            "    model_hint: Fam-4bit\n"
            "  third:\n"
            "    model_hint: fam:q8_0-ctx64k\n"
            "  fourth:\n"
            "    model_hint: Fam-oQ4e-mtp\n"
        ),
    )
    # A third site on the Fam-4bit pair breaks the 2-2 tie between the two groups.
    (root / "config" / "personas" / "pin.yaml").write_text(
        "model_pin: Fam-4bit\n", encoding="utf-8"
    )
    report = fc.build_report(root, _facts())
    removed = _variant(report, "Fam-oQ4e-mtp")
    assert removed["action"] == "REMOVE-CANDIDATE"
    repoints = {(r["file"], r["line"]): r for r in removed["repoints"]}
    # A workspace naming the removed checkpoint moves to the family's kept GGUF tag.
    assert repoints[("config/portal.yaml", 9)]["to"] == "fam:q4_K_M-ctx32k"
    # The removed tag's own consumers move to the fallback, and lose their 64k window.
    tag_repoints = {
        (r["file"], r["line"]): r for r in _variant(report, "fam:q8_0-ctx64k")["repoints"]
    }
    assert tag_repoints[("config/portal.yaml", 7)]["to"] == "fam:q4_K_M-ctx32k"
    assert tag_repoints[("config/portal.yaml", 7)]["window_lost"] is True
    assert tag_repoints[("config/portal.yaml", 7)]["from_ctx"] == "64k"


def test_alias_line_is_repointed_to_the_kept_checkpoint(tmp_path):
    """A kept hint whose checkpoint goes is repointed at the surviving seat."""
    root = _repo(
        tmp_path,
        [
            _ollama([{"id": "fam:q4_K_M-ctx32k"}]),
            _omlx(
                [{"id": "Fam-4bit"}, {"id": "Fam-oQ4e-mtp"}],
                {"fam:q4_K_M-ctx32k": "Fam-oQ4e-mtp"},
            ),
        ],
        portal="workspaces:\n  auto:\n    model_hint: Fam-4bit\n",
    )
    report = fc.build_report(root, _facts())
    removed = _variant(report, "Fam-oQ4e-mtp")
    assert removed["action"] == "REMOVE-CANDIDATE"
    alias = [r for r in removed["repoints"] if r["how"] == "repoint-alias"]
    assert alias and alias[0]["to"] == "Fam-4bit"
    assert _variant(report, "fam:q4_K_M-ctx32k")["action"] == "KEEP"


def test_alias_entry_is_deleted_when_its_hint_is_removed_too(tmp_path):
    """No dangling `aliases:` key pointing a deleted GGUF tag at a live seat."""
    root = _repo(
        tmp_path,
        [
            _ollama([{"id": "fam:q4_K_M-ctx32k"}, {"id": "fam:q8_0-ctx32k"}]),
            _omlx(
                [{"id": "Fam-4bit"}, {"id": "Fam-oQ4e-mtp"}],
                {"fam:q4_K_M-ctx32k": "Fam-4bit", "fam:q8_0-ctx32k": "Fam-oQ4e-mtp"},
            ),
        ],
        portal="workspaces:\n  auto:\n    model_hint: Fam-4bit\n",
    )
    report = fc.build_report(root, _facts())
    alias = [r for r in _variant(report, "Fam-oQ4e-mtp")["repoints"] if "alias" in r["how"]]
    assert [r["how"] for r in alias] == ["delete-alias"]


def test_only_referenced_variant_is_never_removed():
    """The rule itself, isolated from group scoring."""
    referenced = fc.Variant("omlx", "Only-4bit", refs=[fc.Ref("f", 1, "m", "v", "reference", "id")])
    other = fc.Variant("omlx", "Other-4bit")
    action, reason = fc._decision(referenced, other, None, False, {})
    assert action == "KEEP"
    assert reason == "only config-referenced variant in the family"


def test_a_second_variant_is_removable_when_another_is_referenced():
    primary = fc.Variant("omlx", "Keep-4bit", refs=[fc.Ref("f", 1, "m", "v", "reference", "id")])
    second = fc.Variant("omlx", "Drop-4bit", refs=[fc.Ref("f", 2, "m", "v", "reference", "id")])
    action, _reason = fc._decision(second, primary, None, True, {})
    assert action == "REMOVE-CANDIDATE"


def test_draft_helper_is_kept(tmp_path):
    """A draft sits in its sibling's lineage, so it must survive the family's clean-up."""
    root = _repo(
        tmp_path,
        [
            _ollama([{"id": "fam:q4_K_M"}]),
            _omlx(
                [{"id": "Fam-4bit"}, {"id": "Fam-4bit-draft"}],
                {"fam:q4_K_M": "Fam-4bit"},
            ),
        ],
    )
    report = fc.build_report(root, _facts())
    assert _variant(report, "Fam-4bit-draft")["action"] == "KEEP"
    assert "draft" in _variant(report, "Fam-4bit-draft")["reason"]


def test_keep_reason_entry_is_kept_but_family_still_warns(tmp_path):
    root = _repo(
        tmp_path,
        [
            _ollama(
                [
                    {"id": "fam:q4_K_M"},
                    {"id": "fam:q5_K_M"},
                    {"id": "fam:q8_0", "keep_reason": "A/B lane needs Q8"},
                ]
            ),
            _omlx([{"id": "Fam-4bit"}], {"fam:q4_K_M": "Fam-4bit"}),
        ],
    )
    report = fc.build_report(root, _facts())
    kept = _variant(report, "fam:q8_0")
    assert kept["action"] == "KEEP"
    assert "A/B lane needs Q8" in kept["reason"]
    assert _actions(report)["fam:q5_K_M"] == "REMOVE-CANDIDATE"


def test_no_family_loses_every_variant(tmp_path):
    root = _repo(
        tmp_path,
        [
            _ollama([{"id": "fam:q4_K_M"}, {"id": "fam:q8_0"}, {"id": "fam:q5_K_M"}]),
            _omlx([{"id": "Fam-4bit"}, {"id": "Fam-oQ4e-mtp"}], {"fam:q4_K_M": "Fam-4bit"}),
        ],
    )
    report = fc.build_report(root, _facts())
    for fam in report["families"]:
        assert any(v["action"] == "KEEP" for v in fam["variants"])


def test_clean_family_is_not_in_the_table(tmp_path):
    root = _repo(
        tmp_path,
        [
            _ollama([{"id": "fam:q4_K_M"}]),
            _omlx([{"id": "Fam-4bit"}], {"fam:q4_K_M": "Fam-4bit"}),
        ],
    )
    report = fc.build_report(root, _facts())
    assert report["families"] == []
    assert report["totals"]["reclaimable_bytes"] == 0


# ── install state, sizes, config debt ────────────────────────────────────────
def test_ctx_twins_collapse_into_one_weights_variant(tmp_path):
    root = _repo(
        tmp_path,
        [
            _ollama([{"id": "fam:q4_K_M"}, {"id": "fam:q4_K_M-ctx32k"}, {"id": "fam:q8_0"}]),
            _omlx([{"id": "Fam-4bit"}], {"fam:q4_K_M": "Fam-4bit"}),
        ],
    )
    facts = _facts({"fam:q4_K_M-ctx32k": {"a": 10}, "fam:q4_K_M": {"a": 10}, "fam:q8_0": {"b": 20}})
    report = fc.build_report(root, facts)
    weights = _variant(report, "fam:q4_K_M")
    assert weights["tags"] == ["fam:q4_K_M", "fam:q4_K_M-ctx32k"]
    assert weights["installed"] is True
    assert weights["unique_bytes"] == 10


def test_unique_bytes_exclude_blobs_another_kept_tag_holds(tmp_path):
    root = _repo(
        tmp_path,
        [
            _ollama([{"id": "fam:q4_K_M"}, {"id": "fam:q8_0"}]),
            _omlx([{"id": "Fam-4bit"}], {"fam:q4_K_M": "Fam-4bit"}),
        ],
    )
    facts = _facts({"fam:q4_K_M": {"shared": 100}, "fam:q8_0": {"shared": 100}})
    report = fc.build_report(root, facts)
    assert _variant(report, "fam:q8_0")["unique_bytes"] == 0
    assert report["totals"]["reclaimable_bytes"] == 0


def test_reclaimable_is_the_union_not_the_sum(tmp_path):
    root = _repo(
        tmp_path,
        [
            _ollama([{"id": "fam:q4_K_M"}, {"id": "fam:q8_0"}, {"id": "fam:q5_K_M"}]),
            _omlx([{"id": "Fam-4bit"}], {"fam:q4_K_M": "Fam-4bit"}),
        ],
    )
    facts = _facts(
        {
            "fam:q4_K_M": {"kept": 1},
            "fam:q8_0": {"kept": 1, "dup": 50},
            "fam:q5_K_M": {"kept": 1, "dup": 50},
        }
    )
    report = fc.build_report(root, facts)
    assert report["totals"]["reclaimable_bytes"] == 50


def test_configured_not_installed_is_config_debt(tmp_path):
    root = _repo(
        tmp_path,
        [
            _ollama([{"id": "fam:q4_K_M"}, {"id": "fam:q8_0"}]),
            _omlx([{"id": "Fam-4bit"}], {"fam:q4_K_M": "Fam-4bit"}),
        ],
    )
    facts = _facts({"fam:q4_K_M": {"a": 1}}, {"Fam-4bit": {(1, 1): 1}})
    report = fc.build_report(root, facts)
    assert _variant(report, "fam:q4_K_M")["installed"] is True
    assert _variant(report, "fam:q8_0")["installed"] is False
    assert [v["id"] for v in report["config_debt"]] == ["fam:q8_0"]
    assert report["totals"]["config_only"] == 1


def test_omlx_dir_presence_marks_the_checkpoint_installed(tmp_path):
    root = _repo(
        tmp_path,
        [
            _ollama([{"id": "fam:q4_K_M"}, {"id": "fam:q8_0"}]),
            _omlx([{"id": "Fam-4bit"}, {"id": "Fam-oQ4e-mtp"}], {"fam:q4_K_M": "Fam-4bit"}),
        ],
    )
    report = fc.build_report(root, _facts(dirs={"Fam-4bit": {(1, 2): 2**30}}))
    assert _variant(report, "Fam-4bit")["installed"] is True
    assert _variant(report, "Fam-4bit")["unique_bytes"] == 2**30
    assert _variant(report, "Fam-oQ4e-mtp")["installed"] is False


def test_hardlinked_omlx_files_are_not_double_counted(tmp_path):
    root = _repo(
        tmp_path,
        [
            _ollama([{"id": "fam:q4_K_M"}]),
            _omlx([{"id": "Fam-4bit"}, {"id": "Fam-oQ4e-mtp"}], {"fam:q4_K_M": "Fam-4bit"}),
        ],
    )
    report = fc.build_report(
        root,
        _facts(dirs={"Fam-4bit": {(9, 9): 500}, "Fam-oQ4e-mtp": {(9, 9): 500}}),
    )
    assert _variant(report, "Fam-oQ4e-mtp")["unique_bytes"] == 0


# ── live-fact readers ────────────────────────────────────────────────────────
def _runner(stdout: str, returncode: int = 0):
    def run(argv: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(argv, returncode, stdout=stdout, stderr="")

    return run


def test_tag_blobs_come_from_ollama_show(tmp_path):
    models = tmp_path / "models"
    blob = models / "blobs" / f"sha256-{'a' * 64}"
    blob.parent.mkdir(parents=True)
    blob.write_bytes(b"x" * 32)
    out = fc.tag_blobs("fam:tag", models, _runner(f"FROM /blobs/sha256-{'a' * 64}\n"), "ollama")
    assert out == {"a" * 64: 32}


def test_tag_blobs_fall_back_to_the_manifest(tmp_path):
    models = tmp_path / "models"
    manifest = models / "manifests" / "registry.ollama.ai" / "library" / "fam" / "tag"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(
        json.dumps(
            {"layers": [{"mediaType": _MODEL_LAYER, "digest": f"sha256:{'b' * 64}", "size": 4096}]}
        ),
        encoding="utf-8",
    )
    out = fc.tag_blobs("fam:tag", models, _runner("", returncode=1), "ollama")
    assert out == {"b" * 64: 4096}


def test_unresolvable_tag_has_no_blobs(tmp_path):
    assert fc.tag_blobs("fam:tag", tmp_path, _runner("", returncode=1), "ollama") == {}


def test_omlx_model_dirs_come_from_settings(tmp_path):
    models = tmp_path / "mlx"
    (models / "Fam-4bit").mkdir(parents=True)
    (models / "Fam-4bit" / "weights.safetensors").write_bytes(b"y" * 16)
    settings = tmp_path / "settings.json"
    settings.write_text(
        json.dumps({"model": {"model_dir": str(models), "model_dirs": [str(models)]}}),
        encoding="utf-8",
    )
    dirs = fc.omlx_model_dirs(settings)
    assert list(dirs) == ["Fam-4bit"]
    assert sum(fc.dir_files(dirs["Fam-4bit"]).values()) == 16


def test_missing_settings_file_yields_no_dirs(tmp_path):
    assert fc.omlx_model_dirs(tmp_path / "absent.json") == {}


# ── config scanning ──────────────────────────────────────────────────────────
def test_block_scalar_prose_is_not_a_reference(tmp_path):
    portal = (
        "workspaces:\n"
        "  auto:\n"
        "    description: |-\n"
        "      - model_hint: fam:q8_0\n"
        "    model_hint: fam:q4_K_M\n"
    )
    root = _repo(
        tmp_path,
        [
            _ollama([{"id": "fam:q4_K_M"}, {"id": "fam:q8_0"}]),
            _omlx([{"id": "Fam-4bit"}], {"fam:q4_K_M": "Fam-4bit"}),
        ],
        portal=portal,
    )
    rows = fc.scan_config(root)
    assert ("config/portal.yaml", 5, "model_hint", "fam:q4_K_M") in rows
    assert not [row for row in rows if row[1] == 4]


def test_inline_flow_map_values_are_read(tmp_path):
    portal = "orchestration:\n  seats:\n    shadow: {model: 'fam:q8_0', timeout_seconds: 90}\n"
    root = _repo(
        tmp_path,
        [
            _ollama([{"id": "fam:q4_K_M"}, {"id": "fam:q8_0"}]),
            _omlx([{"id": "Fam-4bit"}], {"fam:q4_K_M": "Fam-4bit"}),
        ],
        portal=portal,
    )
    assert ("config/portal.yaml", 3, "model", "fam:q8_0") in fc.scan_config(root)


def test_persona_preferred_models_are_references(tmp_path):
    root = _repo(
        tmp_path,
        [
            _ollama([{"id": "fam:q4_K_M"}, {"id": "fam:q8_0"}]),
            _omlx([{"id": "Fam-4bit"}], {"fam:q4_K_M": "Fam-4bit"}),
        ],
    )
    persona = root / "config" / "personas" / "one.yaml"
    persona.write_text("preferred_models:\n  - fam:q8_0\n", encoding="utf-8")
    report = fc.build_report(root, _facts())
    refs = {(r["file"], r["line"]) for r in _variant(report, "fam:q8_0")["refs"]}
    assert ("config/personas/one.yaml", 2) in refs


# ── rendering ────────────────────────────────────────────────────────────────
def test_markdown_carries_the_table_refs_and_totals(tmp_path):
    root = _repo(
        tmp_path,
        [
            _ollama([{"id": "fam:q4_K_M"}, {"id": "fam:q8_0"}]),
            _omlx([{"id": "Fam-4bit"}], {"fam:q4_K_M": "Fam-4bit"}),
        ],
        portal=(
            "workspaces:\n"
            "  auto:\n"
            "    model_hint: fam:q4_K_M\n"
            "  second:\n"
            "    model_hint: fam:q8_0\n"
        ),
    )
    report = fc.build_report(
        root,
        _facts({"fam:q4_K_M": {"a": 2**30}, "fam:q8_0": {"b": 2**30}}),
        {"status": "WARN", "detail": "1 finding(s)", "findings": []},
    )
    text = fc.render_markdown(report)
    assert "| **REMOVE-CANDIDATE** | Ollama | `fam:q8_0` | yes | 1.0 |" in text
    assert "config/portal.yaml:5" in text
    assert "1.0 GiB reclaimable" in text
    assert "validate_system HY — WARN" in text


def test_json_report_is_plain_data(tmp_path):
    root = _repo(
        tmp_path,
        [
            _ollama([{"id": "fam:q4_K_M"}, {"id": "fam:q8_0"}]),
            _omlx([{"id": "Fam-4bit"}], {"fam:q4_K_M": "Fam-4bit"}),
        ],
    )
    report = fc.build_report(root, _facts())
    assert json.loads(json.dumps(report))["totals"]["families"] == 1


def test_main_json_prints_a_report(tmp_path, capsys):
    root = _repo(
        tmp_path,
        [
            _ollama([{"id": "fam:q4_K_M"}, {"id": "fam:q8_0"}]),
            _omlx([{"id": "Fam-4bit"}], {"fam:q4_K_M": "Fam-4bit"}),
        ],
    )
    facts = _facts()
    assert fc.main.__module__ == "scripts.fleet_consolidate"
    report = fc.build_report(root, facts)
    assert report["families"][0]["key"] == "Fam-4bit"
    capsys.readouterr()


# ── invariants ───────────────────────────────────────────────────────────────
def test_the_script_cannot_delete_or_edit_anything():
    source = (REPO_ROOT / "scripts" / "fleet_consolidate.py").read_text(encoding="utf-8")
    for token in ("unlink", "rmtree", "write_text", "write_bytes", "remove(", "os.rename"):
        assert token not in source, f"dry-run script must not call {token}"


def test_real_config_keeps_one_variant_per_warn_family():
    """Read-only: every WARN family on the live config keeps at least one variant."""
    report = fc.build_report(REPO_ROOT, _facts())
    assert report["families"]
    for fam in report["families"]:
        assert any(v["action"] == "KEEP" for v in fam["variants"]), fam["key"]


def test_real_config_marks_every_remove_candidate_with_a_reason():
    report = fc.build_report(REPO_ROOT, _facts())
    for fam in report["families"]:
        for variant in fam["variants"]:
            assert variant["reason"]
            if variant["action"] == "REMOVE-CANDIDATE":
                assert variant["repoints"] is not None


@pytest.mark.parametrize("engine", ["omlx", "ollama"])
def test_variant_payload_is_serialisable(engine):
    variant = fc.Variant(engine, "X-4bit")
    assert json.loads(json.dumps(variant.as_dict()))["engine"] == engine
