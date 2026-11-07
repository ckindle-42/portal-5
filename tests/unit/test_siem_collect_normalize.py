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
"""

from __future__ import annotations

from portal.modules.security.core.siem.collect import _normalize_windows_security_events

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
