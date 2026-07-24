"""Regression guard: the red-only --all-scenarios CLI loop must actually
start/stop episode-scoped packet capture and pass it through to telemetry
collection.

Found live 2026-07-24: the entire red-only --all-scenarios path (cli.py's
main()) never called start_network_capture/stop_network_capture at all --
only blue.py's separate --purple orchestration function did. Every red-only
capture (including a full 89-scenario run) fell back entirely to the old
lossy post-hoc scrape (collect_and_ship_scenario_telemetry's docker/access-
log read after the fact), which docs/SECURITY_BENCH_EXEC.md already
documents as the root cause of red evidence never reaching blue -- 52 of 68
full-depth scenario completions in that run showed zero ground-truth
coverage despite the attack genuinely executing. collect_and_ship_
scenario_telemetry already accepts episode_id/network_telemetry/pcap_path
as optional kwargs (built for blue.py's purple path); this was simply never
wired into the red-only path.

A full live integration test would need to mock through gate resolution,
run_chain_tests, DinD tcpdump, and Splunk shipping -- this is a structural
source-inspection check instead (same technique used by
test_toolcall_reliability.py's role="user" nudge-wiring test), verifying the
call sites exist and are connected, not the runtime behavior of a live
capture.
"""

from __future__ import annotations

import inspect


def _main_source() -> str:
    from portal.modules.security.core import cli

    return inspect.getsource(cli.main)


def test_all_scenarios_loop_starts_and_stops_network_capture():
    src = _main_source()
    assert "start_network_capture(episode_id" in src
    assert "stop_network_capture(network_capture)" in src


def test_all_scenarios_loop_uses_new_episode_id():
    src = _main_source()
    assert "new_episode_id(sc[" in src


def test_collect_and_ship_receives_episode_and_pcap_evidence():
    """The telemetry-collection call in the red-only loop must actually pass
    through what start_network_capture produced -- having the capture start/
    stop without wiring its output into collection would be the same class
    of gap wearing a disguise."""
    src = _main_source()
    call_start = src.index("collect_and_ship_scenario_telemetry(\n")
    # Slice a generous window after the call site to capture its kwargs.
    call_region = src[call_start : call_start + 500]
    assert "episode_id=episode_id" in call_region
    assert "network_telemetry=" in call_region
    assert "pcap_path=" in call_region
