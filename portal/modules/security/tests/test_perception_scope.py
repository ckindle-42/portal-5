"""Slice 1 gate: lab-scope guard (invariant I1) — testable without the lab up."""

import pytest

from portal.modules.security.core.perception import (
    LabPerception,
    OutOfScopeError,
    assert_in_lab,
    in_lab,
)


def test_lab_target_allowed():
    assert_in_lab("10.10.11.42")
    assert in_lab("10.10.11.1") is True


@pytest.mark.parametrize("bad", ["10.10.12.5", "192.168.1.1", "8.8.8.8", "not-an-ip"])
def test_non_lab_rejected(bad):
    assert in_lab(bad) is False
    with pytest.raises(OutOfScopeError):
        assert_in_lab(bad)


def test_enumerate_rejects_non_lab_before_probe():
    calls = []
    p = LabPerception(prober=lambda hosts: calls.append(hosts) or {})
    with pytest.raises(OutOfScopeError):
        p.enumerate(["10.10.11.5", "10.10.12.9"])
    assert calls == []  # guard fires before any probe leaves the box


def test_delta_source_is_live_never_prior():
    p = LabPerception(
        prober=lambda hosts: {"services": [{"host": hosts[0], "up": True}], "state": {hosts[0]: 1}}
    )
    d = p.enumerate(["10.10.11.5"])
    assert d.to_observation()["_source"] == "live_perception"
