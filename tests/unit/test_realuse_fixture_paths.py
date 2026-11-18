"""Realuse fixtures are readable at the path the prompt names, in both tool modes."""

from __future__ import annotations

from tests.wfe.realuse_paths import named_paths
from tests.wfe.runner import REPO, load_suite

SUITE = REPO / "tests/wfe/suites/realuse_v1.jsonl"

UPLOAD = "/workspace/uploads/realuse_v1/ru-v1-010/report.txt"


def _task(task_id: str) -> dict:
    return next(task for task in load_suite(SUITE) if task["id"] == task_id)


def test_named_paths_cover_upload_and_repo_fixtures():
    upload = named_paths(_task("ru-v1-010"))
    repo = named_paths(_task("ru-v1-012"))
    assert UPLOAD in upload
    assert "fixtures/realuse_v1/ru-v1-012/app.py" in repo
    assert all(not item.startswith("/workspace/") for item in repo)
