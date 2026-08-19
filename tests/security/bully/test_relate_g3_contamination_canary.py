"""G.3 -- held-out contamination canary + write-back freeze: a seeded
self-confirming loop is detected by the canary; the held-out set is
provably never written back."""

from __future__ import annotations

import pytest

from portal.modules.security.core.bully import canary, compounding
from portal.modules.security.core.bully import signatures as sig_mod
from portal.modules.security.core.bully.anchors import AnchorLibrary


def test_self_confirming_loop_is_detected():
    report = canary.check_contamination(
        library_accuracy_before=0.70,
        library_accuracy_after=0.90,  # in-library accuracy looks great...
        heldout_accuracy_before=0.65,
        heldout_accuracy_after=0.50,  # ...but the external world got worse
    )
    assert report.contaminated is True
    assert report.freeze_write_back is True


def test_genuine_improvement_is_not_flagged():
    report = canary.check_contamination(
        library_accuracy_before=0.70,
        library_accuracy_after=0.90,
        heldout_accuracy_before=0.65,
        heldout_accuracy_after=0.80,
    )
    assert report.contaminated is False
    assert report.freeze_write_back is False


def test_held_out_record_raises_before_write_back():
    protected = canary.CanarySet(protected_record_ids=frozenset({"heldout-1"}))
    with pytest.raises(canary.CanaryViolationError):
        canary.guard_write_back(protected, "heldout-1")
    canary.guard_write_back(protected, "not-protected")  # does not raise


def test_write_back_gate_never_writes_a_held_out_anchor():
    lib = AnchorLibrary()
    signature = sig_mod.build_signature(
        {"target_host": "held-out-host", "episode_id": "heldout-ep-1"}, {}
    )
    protected = canary.CanarySet(protected_record_ids=frozenset({signature.signature_id}))

    def _write(sig):
        return compounding.write_outcome_as_anchor(
            lib, sig, source_id="investigation", outcome="ESCALATE", analyst_confirmed=True
        )

    gate = canary.WriteBackGate(canary=protected, write_fn=_write)
    with pytest.raises(canary.CanaryViolationError):
        gate.write(signature.signature_id, signature)
    assert len(lib) == 0  # provably never written


def test_frozen_gate_refuses_every_write_regardless_of_canary():
    lib = AnchorLibrary()
    signature = sig_mod.build_signature({"target_host": "host1", "episode_id": "ep-1"}, {})
    empty_canary = canary.CanarySet(protected_record_ids=frozenset())

    def _write(sig):
        return compounding.write_outcome_as_anchor(
            lib, sig, source_id="investigation", outcome="ESCALATE", analyst_confirmed=True
        )

    gate = canary.WriteBackGate(canary=empty_canary, write_fn=_write)
    gate.freeze("contamination finding pending diagnosis")
    with pytest.raises(canary.WriteBackFrozenError):
        gate.write(signature.signature_id, signature)
    assert len(lib) == 0

    gate.unfreeze()
    gate.write(signature.signature_id, signature)
    assert len(lib) == 1
