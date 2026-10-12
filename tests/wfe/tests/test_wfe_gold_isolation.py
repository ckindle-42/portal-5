from __future__ import annotations

from pathlib import Path

from tests.wfe.runner import REPO, REPO_DENY_PREFIXES, Sandbox, _repo_denied

GOLD_FILE = "tests/wfe/suites/compliance_agentic.jsonl"


def test_denied_prefixes_cover_the_suite_and_probe_trees() -> None:
    assert _repo_denied(GOLD_FILE)
    assert _repo_denied("tests/compliance_probe/judgment_probe_v6.jsonl")
    assert not _repo_denied("portal/modules/compliance/data/nerc_cip_map.json")
    assert not _repo_denied("docs/SALUKI_27B_SPIKE_CLOSEOUT.md")


def test_file_read_refuses_the_suite_file(tmp_path: Path) -> None:
    sb = Sandbox(tmp_path, allow_repo_read=True)
    assert sb.file_read(GOLD_FILE).startswith("ERROR")


def test_repo_search_never_returns_gold_keys(tmp_path: Path) -> None:
    sb = Sandbox(tmp_path, allow_repo_read=True)
    out = sb.repo_search(pattern="gold_finding_type")
    for line in out.splitlines():
        path = line.split(":", 1)[0]
        assert not _repo_denied(path), f"answer-key path reachable: {line[:120]}"
    assert "compliance_agentic.jsonl" not in out


def test_repo_search_still_reads_the_rest_of_the_repo(tmp_path: Path) -> None:
    assert (REPO / "docs" / "SALUKI_27B_SPIKE_CLOSEOUT.md").exists()
    sb = Sandbox(tmp_path, allow_repo_read=True)
    assert "SALUKI" in sb.repo_search(pattern="Rule-5 attribution")
    assert REPO_DENY_PREFIXES
