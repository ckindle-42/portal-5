from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.hunt_bed import lab_vulhub_fleet_sweep as sweep


def test_discovery_parses_and_deduplicates_hundreds_of_compose_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = [f"nginx/CVE-2024-{number:04d}/docker-compose.yml" for number in range(250)]
    output = "\n".join(
        [
            *(f"/root/vulhub/{path}" for path in paths),
            *(f"/opt/vulhub/{path}" for path in paths),
            "/root/vulhub/redis/CVE-2025-0001/docker-compose.yml",
        ]
    )
    commands: list[str] = []

    def host_exec(command: str) -> dict[str, object]:
        commands.append(command)
        return {"ok": True, "output": output}

    monkeypatch.setattr(sweep.lab_host, "_host_exec_lxc", host_exec)

    targets = sweep.discover_targets()

    assert len(targets) == 251
    assert targets[0] == sweep.VulhubTarget("nginx", "CVE-2024-0000", paths[0].rsplit("/", 1)[0])
    assert targets[-1].host_root == "/root/vulhub"
    assert "/root/vulhub" in commands[0]
    assert "/opt/vulhub" in commands[0]
    assert "-maxdepth 3" in commands[0]


def test_round_robin_selection_maximizes_family_diversity() -> None:
    targets = [
        sweep.VulhubTarget(family, f"CVE-{family}-{number}", f"{family}/{number}")
        for family, count in (("php", 12), ("nginx", 3), ("redis", 2), ("tomcat", 1))
        for number in range(count)
    ]

    selected = sweep.select_targets(targets, limit=4)

    assert [target.service_family for target in selected] == ["nginx", "php", "redis", "tomcat"]


@pytest.mark.parametrize(
    ("family", "cve_slug", "expected"),
    [
        ("Nginx", "CVE-2017-7529", "hb_lab_nginx_cve_2017_7529"),
        ("Struts 2", "S2-045/variant", "hb_lab_struts_2_s2_045_variant"),
        ("BotsV2", "CVE-1", "hb_lab_botsv2_cve_1"),
    ],
)
def test_index_names_are_sanitized_and_use_lab_prefix(
    family: str, cve_slug: str, expected: str
) -> None:
    index = sweep.splunk_index(family, cve_slug)

    assert index == expected
    assert index.startswith("hb_lab_")
    assert all(
        character.islower() or character.isdigit() or character == "_" for character in index
    )
    assert index != "botsv2"


def test_resume_skips_completed_targets_and_runs_unfinished_target(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    first = sweep.VulhubTarget("nginx", "CVE-1", "nginx/CVE-1")
    second = sweep.VulhubTarget("tomcat", "CVE-2", "tomcat/CVE-2", "/root/vulhub")
    state_file = tmp_path / "state.json"
    state_file.write_text(
        json.dumps(
            {
                "version": 1,
                "targets": {
                    first.rel_path: {
                        "status": "completed",
                        "index": "hb_lab_nginx_cve_1",
                        "events_captured": 9,
                        "answer_key_path": "/Volumes/data01/hunt_keys/nginx_key.json",
                    }
                },
            }
        )
    )
    calls: list[list[str]] = []
    environments: list[dict[str, str]] = []

    def run(command: list[str], **kwargs: object) -> SimpleNamespace:
        calls.append(command)
        environments.append(kwargs["env"])
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps(
                {
                    "status": "complete",
                    "events_captured": 14,
                    "answer_key_path": "/Volumes/data01/hunt_keys/tomcat_key.json",
                }
            ),
            stderr="",
        )

    monkeypatch.setattr(sweep, "check_clock_sync", lambda: 0.0)
    monkeypatch.setattr(sweep.subprocess, "run", run)

    rows = sweep.run_sweep(
        [first, second],
        limit=2,
        families=None,
        benign_requests=150,
        resume=True,
        state_file=state_file,
        dry_run=False,
    )

    assert len(calls) == 1
    assert calls[0][calls[0].index("--target") + 1] == second.rel_path
    assert environments[0]["LAB_VULHUB_HOST_ROOT"] == "/root/vulhub"
    assert rows[0]["status"] == "completed"
    assert rows[1]["events_captured"] == 14
    saved = json.loads(state_file.read_text())
    assert saved["targets"][second.rel_path]["status"] == "completed"


def test_failed_capture_is_recorded_for_a_later_resume(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    target = sweep.VulhubTarget("redis", "CVE-3", "redis/CVE-3")
    state_file = tmp_path / "state.json"
    monkeypatch.setattr(sweep, "check_clock_sync", lambda: 0.0)
    monkeypatch.setattr(
        sweep.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(
            returncode=1, stdout='{"status":"error"}', stderr="capture failed"
        ),
    )

    rows = sweep.run_sweep(
        [target],
        limit=1,
        families=None,
        benign_requests=150,
        resume=False,
        state_file=state_file,
        dry_run=False,
    )

    assert rows[0]["status"] == "failed"
    assert "capture exited 1" in rows[0]["error"]
    saved = json.loads(state_file.read_text())
    assert saved["targets"][target.rel_path]["status"] == "failed"


@pytest.mark.parametrize("remote_epoch", [90, 110])
def test_clock_sync_preflight_rejects_drift_of_ten_seconds_or_more(
    monkeypatch: pytest.MonkeyPatch, remote_epoch: int
) -> None:
    monkeypatch.setattr(
        sweep.lab_host,
        "_host_exec_lxc",
        lambda _command: {"ok": True, "output": f"{remote_epoch}\n"},
    )
    monkeypatch.setattr(sweep.time, "time", lambda: 100.0)

    with pytest.raises(RuntimeError, match="drift"):
        sweep.check_clock_sync()
