"""HK - public reports are outcome summaries only; everything else stays local."""

from __future__ import annotations

import json
import subprocess

from scripts.validation import compliance_public_text as hk


def _repo(tmp_path, files: dict[str, str]):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    for rel, body in files.items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body)
    subprocess.run(["git", "-C", str(tmp_path), "add", "-A"], check=True)
    return tmp_path


def test_everything_but_top_level_summaries_fails(tmp_path):
    root = _repo(
        tmp_path,
        {
            "reports/compliance/READING_TRUTH_V1.md": "# outcome summary",
            "reports/compliance/run/receipt.json": "{}",
            "reports/compliance/data.json": "{}",
            "reports/compliance/run/NOTES.md": "a narrative in a run dir",
            "reports/other/transcripts/q1.json": "{}",
            "reports/other/receipt.json": json.dumps({"rows": [{"answer": "x" * 300}]}),
            "reports/other/summary.json": json.dumps(
                {"rows": [{"answer_chars": 300, "verdict": "PASS"}]}
            ),
            "docs/notes.md": "design notes are not reports",
            "tests/benchmarks/results/persona_matrix_auto-compliance_20260503.json": "{}",
            "tests/benchmarks/results/_archive/judgment_probe_v6_20260906.json": "{}",
            "tests/benchmarks/results/persona_matrix_auto-coding_20260503.json": "{}",
            "results/sec_bench_archive/ABLATION_POC_COUNCIL.raw.jsonl": "{}",
        },
    )
    status, _, findings = hk.audit(root, content=False)
    assert status == "FAIL"
    assert {f["path"] for f in findings} == {
        "reports/compliance/run/receipt.json",
        "reports/compliance/data.json",
        "reports/compliance/run/NOTES.md",
        "reports/other/transcripts/q1.json",
        "reports/other/receipt.json",
        "tests/benchmarks/results/persona_matrix_auto-compliance_20260503.json",
        "tests/benchmarks/results/_archive/judgment_probe_v6_20260906.json",
    }


def test_summaries_pass_and_the_content_scan_says_it_did_not_run(tmp_path):
    root = _repo(
        tmp_path,
        {
            "reports/compliance/README.md": "public reports are outcome summaries",
            "reports/other/summary.json": json.dumps({"n": 3, "answer": "short"}),
        },
    )
    status, detail, findings = hk.audit(root, content=False)
    assert status == "PASS" and findings == []
    assert "NOT RUN" in detail


def test_untracked_local_files_are_not_public(tmp_path):
    root = _repo(tmp_path, {"reports/compliance/README.md": "policy"})
    local = root / "reports" / "compliance" / "later" / "transcripts"
    local.mkdir(parents=True)
    (local / "q.json").write_text("{}")
    assert hk.audit(root, content=False)[0] == "PASS"


def test_a_tracked_compliance_row_with_answer_text_fails_by_content(tmp_path):
    """N-11: matched on content. A planted compliance row under a neutral name is refused;
    a non-compliance row with text, and a compliance row without text, are not."""
    compliance_row = {
        "suite": "compliance_production",
        "workspace": "auto-compliance",
        "final_text_head": "The control requires review every 35 days.",
    }
    root = _repo(
        tmp_path,
        {
            "tests/wfe/results/campaigns/x/rows/abc.json": json.dumps(compliance_row),
            "tests/wfe/results/campaigns/x/rows/def.json": json.dumps(
                {"suite": "coding", "workspace": "auto-coding", "final_text_head": "print(1)"}
            ),
            "tests/wfe/results/campaigns/x/rows/ghi.json": json.dumps(
                {
                    "suite": "compliance_production",
                    "workspace": "auto-compliance",
                    "transcript": [{"turn": 0, "content": ""}],
                }
            ),
        },
    )
    status, _, findings = hk.audit(root, content=False)
    assert status == "FAIL"
    assert [f["path"] for f in findings] == ["tests/wfe/results/campaigns/x/rows/abc.json"]
