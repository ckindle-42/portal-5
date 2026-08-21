"""TASK_BULLY_INVESTIGATION_V1 (I.6): two live-fidelity bugs the run
against real BOTS uncovered, fixed at the root:

1. `SplunkBackend._run_search` fell back to `time.time()` ("now") for any
   `_time` value that wasn't a bare epoch number -- this lab's Splunk
   renders `_time` as a locale string ("2018-08-20 15:17:58.000 GMT") by
   default, so EVERY real captured record's client-side `_time` was
   silently "now". Requesting `time_format=%s` fixes it at the source.
2. This lab surfaces a field in exported JSON only when the search itself
   referenced it (live-verified: `EventCode` is absent unless the search
   filters on it) -- so `telemetry_behavior.classify_record` could not
   read `EventCode`/`ComputerName`/etc. from an ordinary capture at all.
   `_dig` now falls back to parsing `_raw`'s line-oriented `key=value`
   text when the field isn't already present on the record.
"""

from __future__ import annotations

from portal.modules.security.core.bully import telemetry_behavior as tb
from portal.modules.security.core.siem import spl_backend


def test_run_search_requests_epoch_time_format(monkeypatch):
    captured = {}

    class _FakeResponse:
        text = ""

        def raise_for_status(self):
            return None

    def _fake_post(url, **kwargs):
        captured.update(kwargs.get("data", {}))
        return _FakeResponse()

    monkeypatch.setattr(spl_backend.httpx, "post", _fake_post)
    backend = spl_backend.SplunkBackend()
    backend._run_search("search index=botsv3", "0", "now")
    assert captured.get("time_format") == "%s"


def test_dig_falls_back_to_parsing_raw_kv_text():
    record = {
        "_raw": "08/20/2018 03:17:58 AM\nLogName=Security\nEventCode=4689\nComputerName=BSTOLL-L.froth.ly\n"
    }
    assert tb._dig(record, "EventCode") == "4689"
    assert tb._dig(record, "ComputerName") == "BSTOLL-L.froth.ly"


def test_dig_prefers_already_present_field_over_raw_parsing():
    record = {"EventCode": "9999", "_raw": "EventCode=4689\n"}
    assert tb._dig(record, "EventCode") == "9999"


def test_classify_record_reads_real_windows_security_event_from_raw_only():
    record = {"_raw": "08/20/2018 03:17:58 AM\nLogName=Security\nEventCode=4689\n"}
    assert tb.classify_record(record, "WinEventLog") == "execute"
