"""The vision suite: sound under the controls gate, regenerates identically (jsonl and
images), every gold computed in the generator and absent from the instruction and the
image files, the runner attaching each task's images as image_url parts without counting
them as text, and the plan's arms served by auto-vision's groups at >= 8k windows."""

from __future__ import annotations

import base64
import hashlib
import json
import re
from pathlib import Path

import yaml
from PIL import Image

from tests.wfe import controls
from tests.wfe.checkers import CheckContext, apply_checkers
from tests.wfe.runner import _text_chars, user_content
from tests.wfe.schema import Outcome
from tests.wfe.suites import build_vision_production as gen

REPO = Path(__file__).resolve().parents[3]
SUITE = REPO / "tests/wfe/suites/vision_production.jsonl"
PLAN = REPO / "tests/wfe/plans/vision_decision_v1.yaml"
TASKS = {t["id"]: t for t in map(json.loads, SUITE.read_text().splitlines())}
KINDS = {"chart-table": 12, "doc-fields": 12, "natural": 12}


def _kind(kind: str) -> list[dict]:
    return [t for t in TASKS.values() if t["kind"] == kind]


def _gold(task: dict) -> str:
    return json.loads(task["controls"]["pass"][0]["answer"])["answer"]


def test_the_suite_is_sound_and_balanced():
    assert len(TASKS) == 36 and sum(t["screen"] for t in TASKS.values()) == 12
    for kind, n in KINDS.items():
        assert len(_kind(kind)) == n, kind
        assert sum(t["screen"] for t in _kind(kind)) == 4, kind
        assert all(t["id"].startswith(f"vis-{kind}-") for t in _kind(kind))
    assert controls.check_suite(SUITE) == []
    assert all(controls.schema_failures(t) == [] for t in TASKS.values())


def test_every_task_is_no_tools_and_answer_graded():
    for t in TASKS.values():
        assert t["no_tools"] is True and t["requires_tools"] == [] and t["agentic"] is False, t[
            "id"
        ]
        assert [c["type"] for c in t["checkers"]] == ["answer_contains"], t["id"]
        assert t["lane"] == "vision", t["id"]


def test_the_controls_pass_and_fail_where_they_must():
    def run(task, answer):
        return apply_checkers(task, CheckContext(task=task, final_text=answer)).outcome

    for t in TASKS.values():
        assert run(t, t["controls"]["pass"][0]["answer"]) == Outcome.PASS, t["id"]
        assert run(t, t["controls"]["fail"][0]["answer"]) == Outcome.FAIL, t["id"]
        assert run(t, "") == Outcome.FAIL, t["id"]


def test_the_gold_is_not_in_the_instruction():
    for t in TASKS.values():
        gold = _gold(t)
        assert not re.search(rf"(?<![\w.]){re.escape(gold)}(?![\w.])", t["instruction"]), t["id"]


def test_every_task_has_one_small_clean_unique_image():
    seen = set()
    for t in TASKS.values():
        assert len(t["images"]) == 1, t["id"]
        path = REPO / t["images"][0]
        assert path.parent == REPO / "tests/fixtures/vision" and path.stat().st_size < 50_000
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        assert digest not in seen, t["id"]
        seen.add(digest)
        with Image.open(path) as im:
            assert im.format == "PNG" and not im.text, t["id"]  # no metadata, so no gold in it


def test_the_suite_regenerates_identically_with_identical_images():
    def digests() -> dict[str, str]:
        return {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted((REPO / "tests/fixtures/vision").glob("*.png"))
        }

    before = digests()
    built = "".join(json.dumps(t) + "\n" for t in gen.build())
    assert built == SUITE.read_text()
    assert digests() == before


def test_the_runner_attaches_images_as_image_url_parts_and_not_as_text():
    task = TASKS["vis-chart-table-00"]
    content = user_content(task)
    assert [p["type"] for p in content] == ["text", "image_url"]
    assert content[0]["text"] == task["instruction"]
    url = content[1]["image_url"]["url"]
    assert url.startswith("data:image/png;base64,")
    assert base64.b64decode(url.split(",", 1)[1]) == (REPO / task["images"][0]).read_bytes()
    assert _text_chars(content) == len(task["instruction"])
    assert user_content({"instruction": "hi"}) == "hi"  # an imageless task is unchanged


def test_the_native_adapter_carries_the_image_to_ollama():
    from portal.platform.inference.ollama_native import to_native_request

    content = user_content(TASKS["vis-natural-02"])
    native = to_native_request(
        {"model": "m", "messages": [{"role": "user", "content": content}]}, False
    )
    assert any(m.get("images") for m in native["messages"])


def test_the_plan_arms_are_served_by_the_workspaces_groups_and_fit_its_window():
    plan = yaml.safe_load(PLAN.read_text())["workloads"]["auto-vision"]
    portal = yaml.safe_load((REPO / "config/portal.yaml").read_text())["workspaces"]["auto-vision"]
    backends = yaml.safe_load((REPO / "config/backends.yaml").read_text())
    groups = set(backends["workspace_routing"]["auto-vision"])
    served = {
        m["id"] for b in backends["backends"] if b["group"] in groups for m in b.get("models") or []
    }
    arms = plan["arms"]
    assert portal["model_hint"] in [arms["incumbent"], *arms["challengers"]]
    assert plan["home"] == "vision_production"
    assert plan["discovery"] == [] and "tool_mode" not in plan
    assert len(arms["challengers"]) == 3
    for tag in [arms["incumbent"], *arms["challengers"]]:
        assert tag in served, tag
        window = int(re.search(r"ctx(\d+)k", tag).group(1)) * 1024
        assert window >= portal["context_limit"], (tag, window)
