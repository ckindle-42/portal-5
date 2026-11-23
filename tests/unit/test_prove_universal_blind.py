from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import duckdb
import pytest

from scripts.hunt_bed.prove_universal_blind import (
    PROOF_INDEXES,
    canonical_index,
    main,
    resolve_key_path,
    run_hunt,
    score_corpus,
    validate_blind_mode,
    write_receipt,
)
from scripts.hunt_bed.score_cases import _digest


def test_rejects_non_proof_index() -> None:
    with pytest.raises(ValueError, match="six Universal Hunt proof indexes"):
        canonical_index("hb_ait_fox")


def test_refuses_knowledge_store_argument_and_environment() -> None:
    with pytest.raises(ValueError, match="knowledge_store argument"):
        validate_blind_mode(knowledge_store=Path("known.duckdb"), environ={})
    with pytest.raises(ValueError, match="PORTAL_HUNT_KNOWLEDGE_STORE"):
        validate_blind_mode(environ={"PORTAL_HUNT_KNOWLEDGE_STORE": "/tmp/known.duckdb"})
    with pytest.raises(ValueError, match="PORTAL_HUNT_KNOWLEDGE_FAMILIES"):
        validate_blind_mode(environ={"PORTAL_HUNT_KNOWLEDGE_FAMILIES": "family-a"})
    with pytest.raises(ValueError, match="similar_to_known"):
        validate_blind_mode(enabled=("alerts", "similar_to_known"), environ={})


def test_refuses_stage4_verdict_feedback_in_blind_mode() -> None:
    with pytest.raises(ValueError, match="Stage 4 verdicts"):
        validate_blind_mode(environ={"PORTAL_HUNT_STAGE4_VERDICTS": "true"})


def test_resolves_key_paths_for_all_six_proof_corpora(tmp_path: Path) -> None:
    for index in PROOF_INDEXES:
        relative = {
            "hb_flaws_aws": "flaws_manifest/keys.jsonl",
            "hb_ait_wardbeck": "ait_wardbeck_key.json",
            "hb_ait_wilson": "ait_wilson_key.json",
            "hb_uwf_zeek24": "UWF-ZeekData24_key.json",
            "hb_lmd_2023": "LMD-2023_key.json",
            "hb_ics_pcap": "ICS-pcap_key.json",
        }[index]
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
        assert resolve_key_path(index, tmp_path) == path


def test_dry_run_resolves_key_without_creating_search(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    key_path = tmp_path / "flaws_aws_key.jsonl"
    key_path.touch()
    monkeypatch.delenv("PORTAL_HUNT_KNOWLEDGE_STORE", raising=False)
    monkeypatch.delenv("PORTAL_HUNT_KNOWLEDGE_FAMILIES", raising=False)
    monkeypatch.setenv("PORTAL_HUNT_STAGE4_VERDICTS", "0")

    import scripts.hunt_bed.prove_universal_blind as proof_runner

    monkeypatch.setattr(proof_runner, "default_search", lambda: pytest.fail("dry run made search"))
    assert main(["--index", "hb_flaws_aws", "--keys-dir", str(tmp_path), "--dry-run"]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "dry_run_ok"
    assert output["splunk_contacted"] is False
    assert output["keys"]["hb_flaws_aws"] == str(key_path)


def test_run_hunt_uses_blind_discovery_stages_only(tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def stage_runner(argv: list[str], *, search: Any) -> int:
        calls.append(argv)
        return 0

    run_hunt("hb_ait_wardbeck", tmp_path, object(), stage_runner=stage_runner)
    assert len(calls) == 4
    assert [argv[argv.index("--stage") + 1] for argv in calls] == [
        "cards",
        "behaviours",
        "notables",
        "relate",
    ]
    assert all("--knowledge-store" not in argv for argv in calls)
    assert all("similar_to_known" not in argv[argv.index("--generators") + 1] for argv in calls)
    assert "--allow-proof" in calls[-1]


def _write_flaws_proof(root: Path) -> tuple[Path, Path, Path]:
    raw = '{"eventName":"GetCallerIdentity"}'
    host, source = "host-a", "/aws/cloudtrail.json"
    key_path = root / "flaws_aws_key.jsonl"
    key_path.write_text(
        json.dumps(
            {
                "digest": _digest(host, source, raw),
                "host": host,
                "source": source,
                "scenario": "flaws_chain",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    event = {"host": host, "source": source, "line": raw, "earliest": 100, "latest": 101}
    run_dir = root / "flaws_run"
    run_dir.mkdir()
    (run_dir / "notables.jsonl").write_text(json.dumps({"evidence": [event]}) + "\n")
    (run_dir / "cases.json").write_text(json.dumps({"cases": [{"evidence": [event]}]}))
    return key_path, run_dir, root / "flaws_manifest"


def _write_window_proof(root: Path, index: str, step: str) -> tuple[Path, Path]:
    key_path = root / f"{index}_key.json"
    key_path.write_text(
        json.dumps(
            {
                "attack_steps": [
                    {
                        "step": step,
                        "affected_hosts": ["host-b"],
                        "sources": [
                            {
                                "host": "host-b",
                                "log_path": "/logs/auth.json",
                                "time_window": {"start_epoch": 100, "end_epoch": 200},
                            }
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    run_dir = root / f"{index}_run"
    run_dir.mkdir()
    event = {
        "host": "host-b",
        "source": "/logs/auth.json",
        "line": "attack event",
        "earliest": 145,
        "latest": 155,
    }
    (run_dir / "notables.jsonl").write_text(json.dumps({"evidence": [event]}) + "\n")
    (run_dir / "cases.json").write_text(json.dumps({"cases": [{"evidence": [event]}]}))
    return key_path, run_dir


def _add_event_store(run_dir: Path) -> None:
    connection = duckdb.connect(str(run_dir / "behaviours.duckdb"))
    try:
        connection.execute("CREATE TABLE events (raw VARCHAR)")
        connection.execute("INSERT INTO events VALUES ('event-a'), ('event-b')")
    finally:
        connection.close()


def test_scores_synthetic_flaws_ait_and_next_wave_and_writes_receipts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("PORTAL_HUNT_KNOWLEDGE_STORE", raising=False)
    monkeypatch.delenv("PORTAL_HUNT_KNOWLEDGE_FAMILIES", raising=False)
    monkeypatch.setenv("PORTAL_HUNT_STAGE4_VERDICTS", "0")
    key_path, run_dir, _ = _write_flaws_proof(tmp_path)
    _add_event_store(run_dir)
    flaws = score_corpus("hb_flaws_aws", key_path, run_dir, 1.25)
    assert flaws["events"] == 2
    assert flaws["notables_score"]["keyed_units"]["recall"] == 1.0
    assert flaws["cases_score"]["attack_steps"]["recall"] == 1.0

    corpora = [flaws]
    for index, step in (
        ("hb_ait_wardbeck", "Privilege Escalation"),
        ("hb_lmd_2023", "Execution"),
    ):
        window_key, window_run = _write_window_proof(tmp_path, index, step)
        _add_event_store(window_run)
        scored = score_corpus(index, window_key, window_run, 2.5)
        assert scored["notables_score"]["keyed_units"]["recall"] == 1.0
        assert scored["cases_score"]["entities"]["recall"] == 1.0
        corpora.append(scored)

    from scripts.hunt_bed.prove_universal_blind import build_receipt

    receipt = build_receipt(corpora)
    write_receipt(tmp_path / "receipt", receipt)
    parsed = json.loads((tmp_path / "receipt" / "proof_receipt.json").read_text())
    markdown = (tmp_path / "receipt" / "PROOF_RECEIPT.md").read_text()
    assert len(parsed["corpora"]) == 3
    assert parsed["zero_knowledge"] is True
    assert parsed["stage4_verdicts_enabled"] is False
    assert "Universal Hunt zero-knowledge proof receipt" in markdown
    assert "hb_ait_wardbeck" in markdown
    assert "hb_lmd_2023" in markdown
