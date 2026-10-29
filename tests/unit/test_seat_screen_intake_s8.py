"""The s8 intake screen kit: entries parse, seats are real, plans and the bar match."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
import yaml

from portal.platform.inference.config import effective_workspace
from scripts.model_upstream import split_derived
from scripts.seat_screen.intake_s8 import sha_check
from tests.wfe import campaign, decision
from tests.wfe.eval_mode import mode_for
from tests.wfe.sweep_plan import servable, window_tokens

REPO = Path(__file__).resolve().parents[2]
QUEUE = REPO / "scripts/seat_screen/intake_s8/queue.yaml"
PLANS = REPO / "tests/wfe/plans"
SUITES = REPO / "tests/wfe/suites"
DOC = REPO / "docs/MODEL_INTAKE_FRESHNESS_20261029.md"

TAG_KEYS = ("tag", "omlx_twin")
TARGET_KEYS = ("workspace", "suite", "tool_mode", "context_limit", "think")
DISK_KEYS = (
    "screen_gb",
    "seat_gb_in",
    "seat_gb_out",
    "net_gb",
    "replaces_on_win",
    "delete_on_loss",
)


def _yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text())


def _queue() -> dict:
    return _yaml(QUEUE)


def _items(kind: str | None = None) -> list[dict]:
    items = _queue()["items"]
    return [item for item in items if kind is None or item["kind"] == kind]


def _backends() -> dict:
    return _yaml(REPO / "config/backends.yaml")


def _portal() -> dict:
    return _yaml(REPO / "config/portal.yaml")["workspaces"]


def _registered_tags(backends: dict) -> set[str]:
    tags: set[str] = set()
    for backend in backends["backends"]:
        for model in backend.get("models") or []:
            tags.add(str(model["id"] if isinstance(model, dict) else model))
        tags.update(backend.get("aliases") or {})
    return tags


def _suite(name: str) -> list[dict]:
    return [json.loads(line) for line in (SUITES / f"{name}.jsonl").read_text().splitlines()]


def test_queue_parses_and_every_item_is_complete():
    queue = _queue()
    assert queue["version"] == 1
    assert (REPO / queue["source"]).is_file()
    items = queue["items"]
    assert len({item["id"] for item in items}) == len(items)
    for position, item in enumerate(items, start=1):
        assert item["order"] == position
        assert {"id", "kind", "status", "role", "screen"} <= set(item)
        if item["kind"] != "bench":
            continue
        assert item["candidate"]["gguf_gb"] > 0
        assert item["candidate"]["intake_tag"].startswith("hf.co/")
        assert set(TAG_KEYS) <= set(item["incumbent"])
        assert item["targets"] and all(
            set(TARGET_KEYS) <= set(target) for target in item["targets"]
        )
        assert set(DISK_KEYS) <= set(item["disk"])


def test_repo_ids_and_sizes_come_from_the_freshness_doc():
    doc = DOC.read_text()
    for item in _items("bench"):
        candidate = item["candidate"]
        for repo in (
            candidate.get("weights_repo"),
            candidate["gguf_repo"],
            candidate.get("mlx_repo"),
        ):
            if repo:
                assert repo in doc, f"{item['id']}: {repo} is not in the freshness doc"
        tag_repo = candidate["intake_tag"].removeprefix("hf.co/").partition(":")[0]
        assert tag_repo == candidate["gguf_repo"], item["id"]
        quant = split_derived(candidate["intake_tag"])
        assert quant is not None and quant[1] * 1024 >= max(
            target["context_limit"] for target in item["targets"]
        ), item["id"]
    maintenance = _items("maintenance")
    assert len(maintenance) == 1
    assert maintenance[0]["maintenance"]["upstream_repo"] in doc


def test_incumbents_are_registered_and_are_the_seated_hint():
    backends, portal = _backends(), _portal()
    tags = _registered_tags(backends)
    for item in _items("bench"):
        incumbent = item["incumbent"]
        assert incumbent["tag"] in tags, f"{item['id']}: {incumbent['tag']} is not in backends.yaml"
        if incumbent.get("omlx_twin"):
            assert incumbent["omlx_twin"] in tags, item["id"]
        for target in item["targets"]:
            workspace = target["workspace"]
            assert incumbent["tag"] in servable(workspace, backends), (item["id"], workspace)
            assert effective_workspace(portal, workspace)["model_hint"] == incumbent["tag"], (
                item["id"],
                workspace,
            )


def test_maintenance_tags_are_registered_in_backends():
    tags = _registered_tags(_backends())
    for item in _items("maintenance"):
        for tag in item["maintenance"]["tags"]:
            assert tag in tags, f"{item['id']}: {tag} is not in backends.yaml"


def test_context_windows_cover_each_role():
    portal = _portal()
    for item in _items("bench"):
        candidate = item["candidate"]
        for target in item["targets"]:
            effective = effective_workspace(portal, target["workspace"])
            assert target["context_limit"] == effective["context_limit"], target["workspace"]
            assert window_tokens(candidate["intake_tag"]) >= target["context_limit"]
            native = candidate.get("native_context")
            if native is not None:
                assert native >= target["context_limit"], item["id"]


def test_plans_match_the_queue_and_expand():
    referenced: dict[str, str] = {}
    for item in _items("bench"):
        plan_name = item["screen"].get("plan")
        if plan_name is None:
            continue
        referenced[Path(plan_name).name] = item["id"]
        plan = _yaml(REPO / plan_name)["workloads"]
        targets = {target["workspace"]: target for target in item["targets"]}
        assert set(plan) == set(targets), item["id"]
        for workspace, workload in plan.items():
            target = targets[workspace]
            assert workload["home"] == target["suite"]
            assert workload["tool_mode"] == target["tool_mode"]
            assert workload["arms"]["incumbent"] == item["incumbent"]["tag"]
            assert workload["arms"]["challengers"] == [item["candidate"]["intake_tag"]]
        rows = campaign.expand_matrix(REPO / plan_name, 1, tier="screen")
        assert rows and {row["workspace"] for row in rows} == set(plan)
    on_disk = {path.name for path in PLANS.glob("s8_*.yaml")}
    assert on_disk == set(referenced), "every s8 plan is referenced once by the queue"


def test_unauthorized_production_modes_are_declared_as_prerequisites():
    for item in _items("bench"):
        for target in item["targets"]:
            if target["tool_mode"] != "production":
                continue
            try:
                mode_for(target["workspace"], "production")
            except ValueError:
                assert item["screen"]["plan"] is None, item["id"]
                prerequisites = item["screen"].get("prerequisites") or []
                assert any("tool_modes.yaml" in line for line in prerequisites), item["id"]


def test_pass_bar_matches_the_decision_module():
    bar = _queue()["defaults"]["pass_bar"]
    assert bar["screen"]["min_compared_tasks"] == decision.SCREEN_MIN_TASKS
    assert bar["screen"]["drop_if_losses_exceed_wins_by"] == decision.SCREEN_DROP_MARGIN
    assert bar["confirm"]["min_compared_tasks"] == decision.DECISION_FLOOR
    assert bar["confirm"]["alpha"] == decision.ALPHA
    assert bar["confirm"]["max_excluded_frac"] == decision.MAX_EXCLUDED_FRAC


def test_every_suite_carries_the_screen_and_confirm_floor():
    for item in _items("bench"):
        for target in item["targets"]:
            tasks = _suite(target["suite"])
            assert len(tasks) >= decision.DECISION_FLOOR, target["suite"]
            assert sum(bool(task.get("screen")) for task in tasks) >= decision.SCREEN_MIN_TASKS


@pytest.mark.parametrize("kind", ["bench", "maintenance"])
def test_disk_plan_arithmetic(kind):
    for item in _items(kind):
        disk = item["disk"]
        assert disk["net_gb"] == pytest.approx(disk["seat_gb_in"] - disk["seat_gb_out"], abs=0.01)
        if "net_gb_if_shared_kept" in disk:
            assert disk["net_gb_if_shared_kept"] >= disk["net_gb"]
        if kind == "bench":
            candidate = item["candidate"]
            assert disk["seat_gb_in"] == pytest.approx(
                candidate["gguf_gb"] + (candidate.get("mlx_gb") or 0.0), abs=0.01
            )
            assert disk["screen_gb"] > 0
            assert disk["replaces_on_win"] and disk["delete_on_loss"]
        else:
            assert disk["net_gb"] == 0
            assert not disk["replaces_on_win"] and not disk["delete_on_loss"]


def test_conditional_item_waits_for_a_queued_predecessor():
    items = {item["id"]: item for item in _items("bench")}
    conditional = [item for item in items.values() if item["status"] == "conditional"]
    assert conditional
    for item in conditional:
        predecessor = items[item["screen_after"]]
        assert predecessor["order"] < item["order"]
        assert predecessor["status"] == "queued"
    queued = [item for item in items.values() if item["status"] == "queued"]
    assert all("screen_after" not in item for item in queued)


def _write_manifest(models: Path, tag: str, digest: str, model_layer: bool = True) -> Path:
    name, _, qualifier = tag.partition(":")
    path = models / "manifests/registry.ollama.ai/library" / name / qualifier
    path.parent.mkdir(parents=True, exist_ok=True)
    layers: list[dict] = [{"mediaType": "other", "digest": "x"}]
    if model_layer:
        layers.insert(
            0, {"mediaType": "application/vnd.ollama.image.model", "digest": f"sha256:{digest}"}
        )
    path.write_text(json.dumps({"layers": layers}))
    return path


def _fetch(
    registry_blob: str = "", status: int = 200, hf: dict | None = None, manifest_sha: str = "m" * 64
):
    def fetch(method: str, url: str):
        if "huggingface.co" in url:
            return (200, {}, json.dumps(hf).encode()) if hf is not None else (500, {}, b"")
        if status != 200:
            return status, {}, b""
        layers = [
            {"mediaType": "application/vnd.ollama.image.model", "digest": f"sha256:{registry_blob}"}
        ]
        headers = {"ollama-content-digest": manifest_sha}
        return 200, headers, json.dumps({"layers": layers}).encode()

    return fetch


SEAT = "gemma4:26b-a4b-it-q4_K_M-ctx128k"
BASE = "gemma4:26b-a4b-it-q4_K_M"
DIGEST = "a" * 64


def _installed(tmp_path: Path) -> Path:
    models = tmp_path / "models"
    _write_manifest(models, BASE, DIGEST)
    _write_manifest(models, SEAT, DIGEST)
    return models


def test_sha_check_current_and_stale(tmp_path):
    models = _installed(tmp_path)
    current = sha_check.check_tag(SEAT, models, _fetch(DIGEST), None)
    assert current["verdict"] == "current"
    assert current["base"] == BASE
    assert current["installed_blob"] == DIGEST
    assert current["registry_blob"] == DIGEST
    stale = sha_check.check_tag(SEAT, models, _fetch("b" * 64), None)
    assert stale["verdict"] == "stale"
    assert stale["registry_blob"] == "b" * 64


def test_sha_check_falls_back_to_the_manifest_digest_without_a_model_layer(tmp_path):
    models = tmp_path / "models"
    path = _write_manifest(models, BASE, DIGEST, model_layer=False)
    local = hashlib.sha256(path.read_bytes()).hexdigest()
    report = sha_check.check_tag(BASE, models, _fetch(DIGEST, manifest_sha=local), None)
    assert report["verdict"] == "current"
    assert "manifest digest matches" in report["reason"]


def test_sha_check_unknown_when_not_installed_or_upstream_is_down(tmp_path):
    missing = sha_check.check_tag(SEAT, tmp_path / "models", _fetch(DIGEST), None)
    assert missing["verdict"] == "unknown"
    assert "not installed" in missing["reason"]
    models = _installed(tmp_path)
    down = sha_check.check_tag(SEAT, models, _fetch(status=500), None)
    assert down["verdict"] == "unknown"
    assert down["registry_status"] == 500


def test_sha_check_item_reports_upstream_and_the_worst_tag(tmp_path):
    models = _installed(tmp_path)
    item = {
        "id": "gemma4-26b-a4b-sha",
        "maintenance": {
            "tags": [SEAT],
            "upstream_repo": "google/gemma-4-26B-A4B-it",
            "omlx_twin_repo": "mlx-community/gemma-4-26b-a4b-it-4bit",
        },
    }
    hf = {"sha": "c" * 40, "lastModified": "2026-07-20T00:00:00.000Z"}
    report = sha_check.check_item(item, models, _fetch("b" * 64, hf=hf), None)
    assert report["verdict"] == "stale"
    assert report["upstream"]["last_modified"] == "2026-07-20T00:00:00.000Z"
    assert report["omlx_twin"]["repo"] == "mlx-community/gemma-4-26b-a4b-it-4bit"


def test_sha_check_cli_reads_the_real_queue_offline(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(sha_check.upstream, "default_fetch", _fetch(status=500))
    code = sha_check.main(["--json", "--no-ollama", "--models", str(tmp_path)])
    reports = json.loads(capsys.readouterr().out)
    assert code == 2
    assert [report["item"] for report in reports] == ["gemma4-26b-a4b-sha"]
    assert reports[0]["verdict"] == "unknown"
