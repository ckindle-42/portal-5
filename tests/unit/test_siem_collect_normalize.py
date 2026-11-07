"""`_normalize_windows_security_events` must carry the event's own clock.

Regression for a defect found live on 2026-11-07, not invented here: a real
kerberoast/credential-spray episode against the lab DC was collected and every
attack-relevant event (4625, 4768, 4769, 4662, 4688) arrived with no timestamp,
because the enriched pass emitted `EventCode=` plus its per-code fields only.
A consumer that needs event times had to drop exactly those events, leaving the
4624/4634/4672 logon noise — which comes from the timestamped compact pass — as
the only thing that survived into the review.

The `FORMAT_LIST_4769` fixture below is captured verbatim from the lab DC
(`Get-WinEvent ... | Select-Object Id,@{n='TimeCreatedUtc';...},Message |
Format-List`), with the SID's middle groups masked.

The pass-1 tests at the bottom cover the same defect's other half: the compact
pass used to emit `EventCode=` + `TimeCreated=` and nothing else (measured live
2026-11-07: 365 of 406 collected lines carried no identity at all), so entity
extraction had nothing to key on. The fixtures there are captured through the
pass-1 emitter's exact output shape, first line still carrying nxc's prefix.
"""

from __future__ import annotations

from unittest.mock import patch

from portal.modules.security.core.siem.collect import (
    _event_key,
    _logger,
    _merge_windows_events,
    _normalize_windows_security_events,
    _pass1_event_line,
    _pass1_identity_ps,
)

FORMAT_LIST_4769 = """

Id             : 4769
TimeCreatedUtc : 2026-11-07 20:12:12 UTC
Message        : A Kerberos service ticket was requested.

Account Information:
Account Name:       administrator@PORTAL.LAB
Account Domain:     PORTAL.LAB
Logon GUID:     {4bdfa421-7121-94f0-d723-2a10abed698a}
MSDS-SupportedEncryptionTypes:  N/A
Available Keys: N/A

Service Information:
Service Name:       svc_backup
Service ID:     S-1-5-21-0000000000-0000000000-0000000000-1111
MSDS-SupportedEncryptionTypes:  0x27 (DES, RC4, AES-Sk)
Available Keys: AES-SHA1, RC4
"""


def test_the_events_own_utc_clock_reaches_the_flat_line() -> None:
    lines = _normalize_windows_security_events(FORMAT_LIST_4769)
    assert len(lines) == 1
    assert "EventCode=4769" in lines[0]
    assert "TimeCreated=2026-11-07 20:12:12 UTC" in lines[0]


def test_the_stamp_follows_the_event_code_so_a_consumer_can_split_it() -> None:
    line = _normalize_windows_security_events(FORMAT_LIST_4769)[0]
    assert line.startswith("EventCode=4769 TimeCreated=")


def test_an_untimed_block_still_yields_its_line() -> None:
    """Best-effort is preserved: a block with no stamp is still evidence the
    event fired, it is simply untimed."""
    lines = _normalize_windows_security_events("\nId             : 4625\nMessage        : x\n")
    assert lines == ["EventCode=4625"]


def test_several_blocks_each_keep_their_own_stamp() -> None:
    doubled = FORMAT_LIST_4769 + FORMAT_LIST_4769.replace("20:12:12", "20:12:19").replace(
        "svc_backup", "svc_iis"
    )
    lines = _normalize_windows_security_events(doubled)
    assert len(lines) == 2
    assert "TimeCreated=2026-11-07 20:12:12 UTC" in lines[0]
    assert "TimeCreated=2026-11-07 20:12:19 UTC" in lines[1]


# ── pass 1: the compact line carries identity ────────────────────────────────
# Captured live 2026-11-07 through the pass-1 emitter's exact output shape
# (same Get-WinEvent window as FORMAT_LIST_4769); the first line still wears
# nxc's status-column prefix the way it arrives from the sandbox MCP.
PASS1_LINES = """\
WINRM   10.10.11.21   5985   WIN-MVQO0PT39IO  4624 2026-11-07 21:17:32 UTC Account=WIN-MVQO0PT39IO$ LogonId=0xc20239 LogonType=3 IpAddress=::1
4634 2026-11-07 21:17:32 UTC Account=WIN-MVQO0PT39IO$ LogonId=0xc1ff89 LogonType=3
4670 2026-11-07 21:17:40 UTC
4776 2026-11-07 21:12:53 UTC Account=administrator WorkstationName=WIN-MVQO0PT39IO
4799 2026-11-07 21:09:10 UTC Account=WIN-MVQO0PT39IO$ LogonId=0x3e7 Group=Backup Operators
"""


def _pass1_flat() -> list[str]:
    return [
        flat for line in PASS1_LINES.splitlines() if (flat := _pass1_event_line(line)) is not None
    ]


def test_a_logon_events_flat_line_carries_its_account() -> None:
    flat = _pass1_flat()
    assert flat[0].startswith("EventCode=4624 TimeCreated=2026-11-07 21:17:32 UTC ")
    assert "Account=WIN-MVQO0PT39IO$" in flat[0]
    assert "LogonId=0xc20239" in flat[0]
    assert "IpAddress=::1" in flat[0]
    # The identity tail follows the clock, never precedes it.
    assert flat[0].index("UTC") < flat[0].index("Account=")


def test_an_event_without_identity_still_ships_exactly_as_before() -> None:
    # 4670 (removable storage) is unmapped: code + clock, nothing invented.
    assert (
        _pass1_event_line("4670 2026-11-07 21:17:40 UTC")
        == "EventCode=4670 TimeCreated=2026-11-07 21:17:40 UTC"
    )


def test_renamed_fields_keep_the_detection_vocabulary_and_skip_absent_ones() -> None:
    # 4776's XML names its workstation field `Workstation`; the emitted name is
    # the WorkstationName the SPL detections filter on. It carries no logon id,
    # and none is invented.
    line = _pass1_flat()[3]
    assert line.startswith("EventCode=4776")
    assert "Account=administrator" in line
    assert "WorkstationName=WIN-MVQO0PT39IO" in line
    assert "LogonId" not in line


def test_a_value_with_spaces_stays_one_pair_on_the_line() -> None:
    line = _pass1_flat()[4]
    assert line.startswith("EventCode=4799")
    assert "Account=WIN-MVQO0PT39IO$" in line
    assert "Group=Backup Operators" in line


def test_a_digits_first_line_that_lost_its_stamp_still_ships_code_and_clock() -> None:
    assert (
        _pass1_event_line("123 some non-stamp text")
        == "EventCode=123 TimeCreated=some non-stamp text"
    )
    assert _pass1_event_line("[*] Initializing WMI protocol database") is None


def test_the_identity_map_never_claims_a_code_pass_2_owns() -> None:
    """A compact identity line for a pass-2 code would survive the merge's
    `"Account=" not in e` guard and duplicate that code's detailed lines, so
    the pass-1 field set must stay disjoint from _attack_ids
    (4769/4768/4662/4698/4625/4771/4688/4702/4770/5140)."""
    script = _pass1_identity_ps()
    for code in ("4625", "4688", "4768", "4769", "4662", "4698", "4771", "4770", "4702", "5140"):
        assert f"'{code}'=@" not in script
    assert "'4624'=@('Account=TargetUserName'" in script
    assert "'WorkstationName=Workstation'" in script


# ── merge: per-event identity, not per-code sweep ───────────────────────────
# Regression for a defect found live on 2026-11-07: 67 compact 4688 events
# were read by pass 1, only 15 shipped because the old merge dropped every
# compact line for a code once pass 2 returned any event for that code.
# The fix matches on (EventCode, TimeCreated) so surplus compact lines survive.


def test_surplus_compact_events_survive_the_merge() -> None:
    """A code whose pass-1 had more compact lines than pass-2 returned must
    not silently lose the surplus. Found live 2026-11-07: 67 compact 4688,
    15 shipped."""
    pass1 = [
        "EventCode=4688 TimeCreated=2026-11-07 20:00:00 UTC",
        "EventCode=4688 TimeCreated=2026-11-07 20:00:01 UTC",
        "EventCode=4688 TimeCreated=2026-11-07 20:00:02 UTC",
        "EventCode=4688 TimeCreated=2026-11-07 20:00:03 UTC",
        "EventCode=4688 TimeCreated=2026-11-07 20:00:04 UTC",
    ]
    # Pass 2 returned only two of the five timestamps (simulating its cap).
    pass2 = [
        "EventCode=4688 TimeCreated=2026-11-07 20:00:01 UTC Account=victim",
        "EventCode=4688 TimeCreated=2026-11-07 20:00:03 UTC Account=admin",
    ]

    merged, dropped = _merge_windows_events(pass1, pass2)

    # Two drops for the exact matches.
    assert dropped == 2
    # Five total: three surviving compact + two detailed.
    assert len(merged) == 5
    assert "EventCode=4688 TimeCreated=2026-11-07 20:00:00 UTC" in merged
    assert "EventCode=4688 TimeCreated=2026-11-07 20:00:02 UTC" in merged
    assert "EventCode=4688 TimeCreated=2026-11-07 20:00:04 UTC" in merged
    assert any("Account=victim" in e for e in merged)
    assert any("Account=admin" in e for e in merged)


def test_dropped_count_is_returned() -> None:
    """The caller must be able to see how many compact events were replaced."""
    pass1 = [
        "EventCode=4688 TimeCreated=2026-11-07 20:00:00 UTC",
        "EventCode=4688 TimeCreated=2026-11-07 20:00:01 UTC",
    ]
    pass2 = [
        "EventCode=4688 TimeCreated=2026-11-07 20:00:00 UTC Account=victim",
    ]

    merged, dropped = _merge_windows_events(pass1, pass2)
    assert dropped == 1
    assert len(merged) == 2  # 1 surviving compact + 1 detailed


def test_no_drop_when_detail_covrage_misses_all_timestamps() -> None:
    """When pass 2 returned zero exact matches, nothing is dropped — the
    compact line survives even for attack codes."""
    pass1 = [
        "EventCode=4688 TimeCreated=2026-11-07 20:00:00 UTC",
    ]
    pass2 = [
        "EventCode=4688 TimeCreated=2026-11-07 20:00:01 UTC Account=victim",
    ]

    merged, dropped = _merge_windows_events(pass1, pass2)
    assert dropped == 0
    assert len(merged) == 2


def test_an_event_without_timestamp_is_never_dropped() -> None:
    """Best-effort: a line without TimeCreated is never matched to a detailed
    event, because we can't establish identity. It always ships through."""
    pass1 = ["EventCode=4769"]
    pass2 = ["EventCode=4769 TimeCreated=2026-11-07 20:00:00 UTC ServiceName=svc"]

    merged, dropped = _merge_windows_events(pass1, pass2)
    assert dropped == 0
    assert "EventCode=4769" in merged


def test_different_codes_dont_merge_across() -> None:
    """A compact line for code A must never be dropped by a detailed event
    for code B, even if their timestamps match."""
    pass1 = [
        "EventCode=4625 TimeCreated=2026-11-07 20:00:00 UTC",
    ]
    pass2 = [
        "EventCode=4769 TimeCreated=2026-11-07 20:00:00 UTC ServiceName=svc",
    ]

    merged, dropped = _merge_windows_events(pass1, pass2)
    assert dropped == 0
    assert "EventCode=4625 TimeCreated=2026-11-07 20:00:00 UTC" in merged


def test_event_key_parses_untimed_lines_as_none() -> None:
    """A line without TimeCreated returns None, so it is never matched."""
    assert _event_key("EventCode=4769") is None
    assert _event_key("[*] nxc banner") is None
    assert _event_key("") is None


def test_event_key_parses_stamped_lines() -> None:
    trailing_id = "EventCode=4688 TimeCreated=2026-11-07 20:00:00 UTC Account=victim"
    assert _event_key(trailing_id) == ("4688", "2026-11-07 20:00:00 UTC")


def test_warning_logs_when_dropped_is_positive() -> None:
    """The dropped count must be surfaced; a dropped=0 run must not log a warning."""

    # Suppress noisy upstream logging; capture only this module's output.
    with (
        patch.object(_logger, "warning") as mock_warn,
        patch("portal.modules.security.core.siem.collect._logger", _logger),
    ):
        # Non-zero drop triggers a warning.
        _merge_windows_events(
            ["EventCode=4688 TimeCreated=2026-11-07 20:00:00 UTC"],
            ["EventCode=4688 TimeCreated=2026-11-07 20:00:00 UTC Account=v"],
        )
        assert mock_warn.called

    mock_warn.reset_mock()
    # Zero drop must not log.
    _merge_windows_events(
        ["EventCode=4688 TimeCreated=2026-11-07 20:00:00 UTC"],
        ["EventCode=4688 TimeCreated=2026-11-07 20:00:01 UTC Account=v"],
    )
    assert not mock_warn.called
