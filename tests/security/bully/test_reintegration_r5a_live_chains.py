"""R.5a -- real-tooling attack generator: >=8 families across >=3 vocabularies,
injected artifacts artifact-level labelled, benign-only fit window excludes them."""

from __future__ import annotations

from portal.modules.security.core.bully import inject_plane as ip


def _vocabulary(command: str) -> str:
    first_token = command.split()[0]
    if first_token == "nxc":
        return "netexec"
    if first_token.startswith("impacket-"):
        return "impacket"
    if first_token == "nmap":
        return "nmap"
    return first_token


def test_at_least_eight_families_across_at_least_three_vocabularies() -> None:
    families = {chain["family"] for chain in ip._LIVE_CHAINS}
    assert len(families) >= 8

    vocabularies = set()
    for chain in ip._LIVE_CHAINS:
        for step in chain["steps"]:
            vocabularies.add(_vocabulary(step))
    assert len(vocabularies) >= 3
    assert vocabularies >= {"netexec", "impacket", "nmap"}


def test_every_chain_has_a_technique_and_at_least_one_step() -> None:
    for chain in ip._LIVE_CHAINS:
        assert chain["technique"]
        assert chain["family"]
        assert chain["chain_id"]
        assert chain["steps"]


def test_generated_steps_are_artifact_level_labelled(monkeypatch) -> None:
    monkeypatch.setattr(ip, "lab_available", lambda: (True, ""))

    def _fake_dispatch(tool_name: str, arguments: dict) -> dict:
        return {"ok": True, "output": "fake lab output", "elapsed_s": 0.1}

    from portal.modules.security.core import lab as lab_module

    monkeypatch.setattr(lab_module, "dispatch_lab_tool", _fake_dispatch)

    report = ip.generate_labelled_activity()
    assert report.plane == "live"
    total_steps = sum(len(chain["steps"]) for chain in ip._LIVE_CHAINS)
    assert len(report.steps) == total_steps
    for step in report.steps:
        # every generated step carries its own family/technique/chain_id --
        # artifact-level labelling, not a coarse per-run label.
        assert step.family
        assert step.technique
        assert step.chain_id
        assert step.step_idx >= 0


def test_benign_only_fit_window_contains_no_injected_artifact(tmp_path, monkeypatch) -> None:
    """A baseline/fit window built by excluding sealed-ledger fingerprints
    from a captured pool must contain none of the injected chain steps --
    the same guard N-series prior tasks established for baseline poisoning,
    exercised here against the expanded 8-chain generator."""
    monkeypatch.setattr(ip, "lab_available", lambda: (True, ""))

    def _fake_dispatch(tool_name: str, arguments: dict) -> dict:
        return {"ok": True, "output": "fake lab output", "elapsed_s": 0.1}

    from portal.modules.security.core import lab as lab_module

    monkeypatch.setattr(lab_module, "dispatch_lab_tool", _fake_dispatch)

    generate_report = ip.generate_labelled_activity()
    assert generate_report.succeeded

    # Simulate a captured pool: one record per injected step (so every
    # generated command DOES have a matching captured record, exercising
    # the fingerprint-join path), plus benign noise records that never
    # appear in the sealed ledger.
    captured = tuple(
        {"event": {"cmd": step.command}, "note": "captured"} for step in generate_report.steps
    ) + ({"event": {"cmd": "benign background noise"}, "note": "benign"},)

    sealed_count = ip.seal_ground_truth(generate_report, captured, root=tmp_path)
    assert sealed_count == len(generate_report.steps)

    ledger = ip.specimen_ledger.SpecimenLedger(tmp_path)
    injected_fingerprints = {
        r["provenance"].get("matched_fingerprint")
        for r in ledger.records()
        if r["provenance"].get("injected")
    }
    injected_fingerprints.discard(None)

    def _fp(record):
        return ip._fingerprint(record)

    benign_fit_window = [r for r in captured if _fp(r) not in injected_fingerprints]

    assert len(benign_fit_window) == 1
    assert benign_fit_window[0]["note"] == "benign"
    for record in benign_fit_window:
        assert _fp(record) not in injected_fingerprints
