"""V4A sibling-discriminator gate regression tests."""

from __future__ import annotations

import inspect

from portal.modules.security.core.blue import (
    _discriminator_contradicts,
    _parent_collapse_precision_note,
)


def test_asrep_claimed_as_kerberoasting_is_contradicted():
    contradicted, siblings = _discriminator_contradicts(
        "T1558.003", "EventCode=4768 PreAuthType=0 Account=svc-web"
    )
    assert contradicted is True
    assert siblings == ["T1558.004"]


def test_correct_asrep_claim_not_contradicted():
    assert _discriminator_contradicts(
        "T1558.004", "EventCode=4768 PreAuthType=0 Account=svc-web"
    ) == (False, [])


def test_both_discriminators_present_not_contradicted():
    telemetry = (
        "EventCode=4769 TicketEncryptionType=0x17 ServiceName=HTTP/web "
        "EventCode=4768 PreAuthType=0 Account=svc-web"
    )
    assert _discriminator_contradicts("T1558.003", telemetry) == (False, [])


def test_neither_discriminator_present_not_contradicted():
    assert _discriminator_contradicts(
        "T1558.003", "EventCode=4624 LogonType=3 Account=svc-web"
    ) == (False, [])


def test_technique_without_distinguishing_features_passes_through():
    assert _discriminator_contradicts("T1190", 'sourcetype="web:access" status=500') == (False, [])


def test_gate_is_label_blind_no_ground_truth_param():
    params = inspect.signature(_discriminator_contradicts).parameters
    forbidden = ("ground_truth", "episode", "expected", "answer")
    assert not [name for name in params if any(word in name.lower() for word in forbidden)]


def test_dcsync_claimed_as_ntds_is_contradicted():
    contradicted, siblings = _discriminator_contradicts(
        "T1003.003",
        "EventCode=4662 Properties=*Replication* Account=svc-sync",
    )
    assert contradicted is True
    assert siblings == ["T1003.006"]


def test_parent_collapse_is_not_contradicted_but_gets_precision_note():
    telemetry = (
        r"EventCode=4688 NewProcessName=C:\Windows\System32\ntdsutil.exe "
        "CommandLine=ntdsutil"
    )
    assert _discriminator_contradicts("T1003", telemetry) == (False, [])
    note = _parent_collapse_precision_note(["T1003"], telemetry)
    assert "T1003 could be refined to T1003.003" in note
    assert "retained" in note
