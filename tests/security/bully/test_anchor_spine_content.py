"""Content-derived behaviour spines classify the event rather than its log format."""

from __future__ import annotations

from pathlib import Path

import pytest

from portal.modules.security.core.bully import telemetry_behavior
from portal.modules.security.core.bully.anchors import AnchorLibrary, EmptySpineError
from scripts.corpus_ingest import (
    ManifestDataset,
    description_census,
    parse_description_steps,
)


def test_attack_episode_with_an_empty_spine_is_refused() -> None:
    lib = AnchorLibrary()
    with pytest.raises(EmptySpineError):
        lib.load_attack_episode(
            source_id="attack_data",
            record={"family": "opaque"},
            logs=[{"verb": "not-a-behaviour"}],
            action_of=lambda log: log["verb"],
        )
    assert len(lib) == 0


def test_anchor_without_logs_still_loads() -> None:
    """The pre-R.3c record-only path is unchanged: no series is claimed."""
    lib = AnchorLibrary()
    anchor = lib.load_attack_episode(source_id="attack_data", record={"family": "x"})
    assert anchor.behavioural_series is None


# ── content classification: same event, different log formats ──────────────


def test_sysmon_process_create_reads_the_command_not_the_sourcetype() -> None:
    record = {
        "EventID": "1",
        "Image": "C:\\Windows\\System32\\vssadmin.exe",
        "CommandLine": "vssadmin delete shadows /all /quiet",
    }
    for sourcetype in ("", "XmlWinEventLog", "xmlwineventlog:sysmon", "corpus:raw"):
        assert telemetry_behavior.classify_content(record, sourcetype) == "destroy"


def test_security_event_id_reads_from_raw_xml() -> None:
    xml = (
        "<Event><System><EventID>4624</EventID></System>"
        "<EventData><Data Name='TargetUserName'>alice</Data></EventData></Event>"
    )
    assert telemetry_behavior.classify_content({"_raw": xml}) == "auth"


def test_powershell_script_block_is_execution_until_its_content_says_otherwise() -> None:
    record = {
        "EventID": "4104",
        "Channel": "Microsoft-Windows-PowerShell/Operational",
        "ScriptBlockText": "$x = Get-ChildItem C:\\Users",
    }
    assert telemetry_behavior.classify_content(record) == "enumerate"


def test_auditd_proctitle_is_read_as_the_command() -> None:
    record = {
        "_raw": "type=PROCTITLE msg=audit(02/20/2025 13:07:46.504:118908) : proctitle=cat /etc/shadow"
    }
    assert telemetry_behavior.classify_content(record) == "collect"


def test_cloudtrail_event_name_is_the_content() -> None:
    assert telemetry_behavior.classify_content({"eventName": "CreatePolicyVersion"}) == "escalate"
    assert (
        telemetry_behavior.classify_content({"eventName": "DescribeInstances", "readOnly": True})
        == "enumerate"
    )


def test_o365_operation_is_the_content() -> None:
    assert telemetry_behavior.classify_content({"Operation": "New-InboxRule"}) == "persist"
    assert telemetry_behavior.classify_content({"Operation": "UserLoggedIn"}) == "auth"


def test_asa_message_id_is_the_content() -> None:
    line = (
        "Sep 23 18:08:27 18.144.133.67 :2025-09-23T18:08:27Z: %ASA-5-111010: "
        "User 'admin', running 'N/A' from IP 198.27.166.158, executed 'logging emblem'"
    )
    assert telemetry_behavior.classify_content({"_raw": line}) == "execute"


def test_record_with_nothing_usable_is_unclassified() -> None:
    assert telemetry_behavior.classify_content({"columns": []}) == ""
    assert telemetry_behavior.classify_content({"_raw": "GET /index.html 200 512"}) == ""


def test_manifest_steps_keep_order_and_stated_outcomes() -> None:
    description = (
        "Atomic Test Results: Successful Execution of test T1003.003-1 Copy credentials "
        "Return value unclear for test T1003.003-3 Dump credentials "
        "Failed Execution of test T1003.003-6 Remove evidence"
    )

    steps = parse_description_steps(description)

    assert [(step.step_index, step.step_id, step.text, step.outcome) for step in steps] == [
        (1, "T1003.003-1", "Copy credentials", "successful"),
        (3, "T1003.003-3", "Dump credentials", "unclear"),
        (6, "T1003.003-6", "Remove evidence", "other"),
    ]


def test_description_census_counts_all_unparsed_descriptions_once_per_manifest() -> None:
    parsed = "Atomic Test Results: Successful Execution of test T1003.003-1 Copy credentials"
    prose = "An operator used a remote tool to access the host."
    malformed = "Atomic Test Results: Successful Execution of test T1003.003 Copy credentials"

    def dataset(manifest: str, description: str | None) -> ManifestDataset:
        steps = parse_description_steps(description)
        return ManifestDataset(
            path=Path(f"{manifest}.log"),
            sourcetype=None,
            source=None,
            dataset_epoch=None,
            techniques=(),
            mapped_sourcetype="",
            manifest=Path(f"{manifest}.yml"),
            description=description,
            steps=steps,
        )

    census = description_census(
        (
            dataset("parsed", parsed),
            dataset("parsed", parsed),
            dataset("prose", prose),
            dataset("malformed", malformed),
            dataset("missing", None),
        )
    )

    assert census["manifests_observed"] == 4
    assert census["with_parseable_steps"] == 1
    assert census["with_description_unparsed"] == 2
    assert census["with_step_like_description_unparsed"] == 1
    assert census["with_prose_description"] == 1
    assert census["without_description"] == 1
    assert census["step_count_distribution"] == {"1": 1}
