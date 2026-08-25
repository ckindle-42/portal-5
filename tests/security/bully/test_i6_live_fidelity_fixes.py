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


def test_run_search_survives_a_unicode_line_separator_inside_a_result(monkeypatch):
    """H.5 follow-up: a binary `_raw` payload (live-verified against a real
    botsv2 window -- an indexed binary event) decoded to text containing a
    U+2028 LINE SEPARATOR byte inside its JSON string value. That code
    point is perfectly legal JSON (only 0x00-0x1F need escaping) but
    `str.splitlines()` treats it as a line break, so the old
    `r.text.splitlines()` + per-line `json.loads` parser cut that one
    result across two lines, threw `Unterminated string` on the fragment,
    and silently dropped it -- surfacing later as `SampledWindowError`
    ("read N-1 of N known records") with no indication the loss was a
    parser bug rather than missing data. Incremental `raw_decode` over the
    whole body must recover both results regardless of the embedded
    separator."""

    class _FakeResponse:
        text = (
            '{"preview":false,"offset":0,"result":{"_time":"1.0","host":"h1"}}\n'
            '{"preview":false,"offset":1,"result":{"_time":"2.0","host":"line1\u2028line2"}}\n'
        )

        def raise_for_status(self):
            return None

    monkeypatch.setattr(spl_backend.httpx, "post", lambda url, **kwargs: _FakeResponse())
    backend = spl_backend.SplunkBackend()
    rows = backend._run_search("search index=botsv2", "0", "now")
    assert len(rows) == 2
    assert rows[0]["host"] == "h1"
    assert rows[1]["host"] == "line1 line2"


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


def test_dig_parses_json_raw_when_sourcetype_extraction_is_skipped():
    """Live-verified (I.6): an injected cousin's JSON body shipped under a
    real sourcetype whose OWN extraction rules expect a different wire
    format (wineventlog:security's classic-text rules) never gets HEC's
    automatic JSON field extraction -- the JSON sits in _raw untouched."""
    record = {
        "_raw": '{"action": "privilege_state_change", "cousin_id": "cz-T1558.004-REVOCABULARY-00"}'
    }
    assert tb._dig(record, "cousin_id") == "cz-T1558.004-REVOCABULARY-00"
