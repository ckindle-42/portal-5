"""Unit tests for universal hunt corpora index gating and out-of-band AIT-LDS2 scorer keys."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from portal.modules.security.core.hunt.notables import knowledge, stage2
from portal.modules.security.core.hunt.notables.knowledge import (
    PROOF_INDEXES,
    TRAINING_INDEXES,
    KnowledgeError,
    KnowledgeItem,
    build_store,
)
from portal.modules.security.core.hunt.notables.manifest import parse_source
from portal.modules.security.core.hunt.notables.relate import relatable_index
from scripts.hunt_bed import keys_ait

REPO = Path(__file__).resolve().parents[2]


class _FakeEmbedder:
    model = "fake-embed"

    def embed(self, texts):
        return [[1.0, 0.0, 0.0] for _ in texts]


def _item(index: str, family: str = "ait") -> KnowledgeItem:
    return KnowledgeItem(
        statement="actor=attacker did execute to shell",
        label="step",
        label_kind="known_bad",
        label_basis="attack_step",
        family=family,
        split="build",
        index=index,
        source_kind="activity",
        query=f'search index="{index}" | head 5',
    )


@pytest.mark.parametrize("index_name", ["hb_flaws_aws", "hb_ait_wardbeck", "hb_ait_wilson"])
def test_new_proof_indexes_are_rejected_from_knowledge_store(
    tmp_path: Path, index_name: str
) -> None:
    assert index_name in PROOF_INDEXES
    assert index_name not in TRAINING_INDEXES
    item = _item(index_name)
    with pytest.raises(KnowledgeError, match="proof index"):
        item.validate()
    with pytest.raises(KnowledgeError, match="proof index"):
        build_store([item], _FakeEmbedder(), tmp_path / "knowledge.duckdb")
    with pytest.raises(ValueError, match="proof index"):
        parse_source(
            f"name=proof,index={index_name},kind=window,cards={tmp_path},good_window=0:100"
        )
    with pytest.raises(ValueError, match="proof index"):
        relatable_index(index_name)


@pytest.mark.parametrize("index_name", ["hb_ait_fox", "hb_ait_harrison", "hb_ait_shaw"])
def test_new_training_indexes_are_accepted_and_not_proof(tmp_path: Path, index_name: str) -> None:
    assert index_name in TRAINING_INDEXES
    assert index_name in knowledge.TRAINING_INDEXES
    assert index_name in stage2.TRAINING_INDEXES
    assert index_name not in PROOF_INDEXES
    receipt = build_store([_item(index_name)], _FakeEmbedder(), tmp_path / "knowledge.duckdb")
    assert receipt["items"] == 1
    spec = parse_source(
        f"name=ait,index={index_name},kind=window,cards={tmp_path},good_window=0:100"
    )
    assert spec.index == index_name


def test_keys_ait_never_referenced_by_portal() -> None:
    hits = [
        p.relative_to(REPO).as_posix()
        for p in (REPO / "portal").rglob("*.py")
        if "keys_ait" in p.read_text(errors="replace")
    ]
    assert hits == []


def _write_synthetic_ait_tree(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "dataset.yaml").write_text(
        "name: processed_fox_scenario\nstart: '2022-01-15T00:00:00'\nend: '2022-01-20T00:00:00'\n",
        encoding="utf-8",
    )
    vpn_log = root / "gather" / "vpn" / "logs" / "openvpn.log"
    vpn_log.parent.mkdir(parents=True, exist_ok=True)
    vpn_log.write_text(
        "\n".join(
            [
                "2022-01-15 00:41:37 benign-line-1",
                "2022-01-15 01:00:00 SECRET_RAW_VPN_LINE_1",
                "2022-01-15 01:05:00 SECRET_RAW_VPN_LINE_2",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    vpn_labels = root / "labels" / "vpn" / "logs" / "openvpn.log"
    vpn_labels.parent.mkdir(parents=True, exist_ok=True)
    vpn_labels.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "line": 2,
                        "labels": ["attacker_vpn", "foothold"],
                        "rules": {
                            "attacker_vpn": ["attacker.foothold.vpn.ip"],
                            "foothold": ["attacker.foothold.vpn.ip"],
                        },
                    }
                ),
                json.dumps(
                    {
                        "line": 2,
                        "labels": ["attacker_vpn"],
                        "rules": {"attacker_vpn": ["attacker.foothold.vpn.ip.dup"]},
                    }
                ),
                json.dumps(
                    {
                        "line": 3,
                        "labels": ["attacker_vpn", "foothold"],
                        "rules": {
                            "attacker_vpn": ["attacker.foothold.vpn.ip"],
                            "foothold": ["attacker.foothold.vpn.ip"],
                        },
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    auth_log = root / "gather" / "intranet_server" / "logs" / "auth.log"
    auth_log.parent.mkdir(parents=True, exist_ok=True)
    auth_log.write_text(
        "\n".join(
            [
                "Jan 16 06:25:50 intranet-server CRON[1]: pam_unix routine",
                "Jan 16 07:10:00 intranet-server su: SECRET_RAW_SU_LINE",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    auth_labels = root / "labels" / "intranet_server" / "logs" / "auth.log"
    auth_labels.parent.mkdir(parents=True, exist_ok=True)
    auth_labels.write_text(
        json.dumps(
            {
                "line": 2,
                "labels": ["attacker_change_user", "escalate"],
                "rules": {
                    "attacker_change_user": ["attacker.escalate.su.login"],
                    "escalate": ["attacker.escalate.su.login"],
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )


def _zip_tree(src_root: Path, zip_path: Path) -> None:
    with zipfile.ZipFile(zip_path, "w") as zf:
        for file_path in sorted(src_root.rglob("*")):
            if file_path.is_file():
                zf.write(file_path, arcname=file_path.relative_to(src_root).as_posix())


def test_keys_ait_parses_zip_and_dir_and_emits_dedup_summary(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    corpus = tmp_path / "fox_corpus"
    _write_synthetic_ait_tree(corpus)
    zip_path = tmp_path / "fox.zip"
    _zip_tree(corpus, zip_path)

    zip_out = tmp_path / "out" / "fox_zip.json"
    dir_out = tmp_path / "out" / "fox_dir.json"
    rc_zip = keys_ait.main(
        ["--archive", str(zip_path), "--dataset", "fox", "--out", str(zip_out), "--summary"]
    )
    summary_out = capsys.readouterr().out
    assert rc_zip == 0

    rc_dir = keys_ait.main(
        ["--labels-dir", str(corpus / "labels"), "--dataset", "fox", "--out", str(dir_out)]
    )
    _ = capsys.readouterr().out
    assert rc_dir == 0

    zip_key = json.loads(zip_out.read_text(encoding="utf-8"))
    dir_key = json.loads(dir_out.read_text(encoding="utf-8"))

    # Zip and directory modes must yield identical aggregated truth (except source path string)
    zip_norm = {**zip_key, "source": ""}
    dir_norm = {**dir_key, "source": ""}
    assert zip_norm == dir_norm

    assert zip_key["dataset"] == "fox"
    assert zip_key["index"] == "hb_ait_fox"
    assert zip_key["split"] == "build"
    assert zip_key["total_labelled_lines"] == 3  # line 2 deduplicated across duplicate rows
    assert zip_key["affected_hosts"] == ["intranet_server", "vpn"]
    assert zip_key["step_counts"] == {
        "attacker_change_user": 1,
        "attacker_vpn": 2,
        "escalate": 1,
        "foothold": 2,
    }
    assert zip_key["time_window"]["start"] == "2022-01-15T01:00:00Z"
    assert zip_key["time_window"]["end"] == "2022-01-16T07:10:00Z"

    vpn_step = next(s for s in zip_key["attack_steps"] if s["step"] == "attacker_vpn")
    assert vpn_step["rules"] == ["attacker.foothold.vpn.ip", "attacker.foothold.vpn.ip.dup"]
    assert vpn_step["log_paths"] == ["/openvpn.log"]
    assert vpn_step["sources"][0]["line_ranges"] == [[2, 3]]

    # Zero raw log duplication in emitted JSON or --summary stdout
    raw_json_text = zip_out.read_text(encoding="utf-8")
    assert "SECRET_RAW_" not in raw_json_text
    assert "SECRET_RAW_" not in summary_out
    assert "dataset=fox index=hb_ait_fox split=build" in summary_out
    assert "attacker_vpn: count=2" in summary_out
    assert "attacker_change_user: count=1" in summary_out


def test_keys_ait_proof_dataset_split_and_labels_only_dir(tmp_path: Path) -> None:
    labels_only = tmp_path / "wardbeck_labels"
    p = labels_only / "inet-firewall" / "logs" / "dnsmasq.log"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        json.dumps(
            {
                "line": 10,
                "labels": ["dnsteal"],
                "rules": {"dnsteal": ["dnsteal.domain.match"]},
                "timestamp": "2022-02-01T10:00:00Z",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    out_path = tmp_path / "wardbeck.json"
    rc = keys_ait.main(
        ["--labels-dir", str(labels_only), "--dataset", "wardbeck", "--out", str(out_path)]
    )
    assert rc == 0
    key = json.loads(out_path.read_text(encoding="utf-8"))
    assert key["index"] == "hb_ait_wardbeck"
    assert key["split"] == "proof"
    assert key["affected_hosts"] == ["inet-firewall"]
    assert key["step_counts"] == {"dnsteal": 1}
    assert key["time_window"]["start"] == "2022-02-01T10:00:00Z"
