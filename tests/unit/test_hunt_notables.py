from __future__ import annotations

import json

from portal.modules.security.core.hunt.notables.cards import (
    apply_answer,
    ask_model,
    cadence_facts,
    is_alert_event,
    is_alert_line,
    reconcile_kind,
    value_facts,
)
from portal.modules.security.core.hunt.notables.parse import (
    choose_partition,
    field_stats,
    parse_events,
    parse_json,
    parse_kv,
    parse_row,
    parse_sample,
    parse_xml,
    partition_groups,
    words,
)
from portal.modules.security.core.hunt.notables.run import _sample_source
from portal.modules.security.core.hunt.notables.sample import SourceFacts


def _facts() -> SourceFacts:
    return SourceFacts(
        index="ix",
        sourcetype="st",
        events=100,
        first=1000.0,
        last=1500.0,
        hosts=("h1",),
        host_count=1,
        sources=("s1",),
        source_count=1,
    )


def test_json_fields_keep_their_paths_and_flatten_scalars():
    fields = parse_json('{"a": {"b": 1}, "c": ["x", "y"], "d": [{"e": 2}]}')
    assert fields["a.b"] == "1"
    assert fields["c"] == "x,y"
    assert fields["d[0].e"] == "2"


def test_xml_fields_are_named_by_tag_and_distinguishing_attribute():
    fields = parse_xml(
        '<Event><Data Name="Image">cmd.exe</Data><Data Name="User">bob</Data><ID>5</ID></Event>'
    )
    assert fields["Data[Name=Image]"] == "cmd.exe"
    assert fields["Data[Name=User]"] == "bob"
    assert fields["ID"] == "5"


def test_a_multi_line_xml_event_is_read_whole():
    raw = """<Event xmlns="http://schemas.microsoft.com/win/2004/08/events/event">
  <EventData>
    <Data Name="Image">C:\\Windows\\System32\\cmd.exe</Data>
    <Data Name="User">bob</Data>
  </EventData>
</Event>"""
    parsed = parse_events([raw])
    assert parsed[0].fmt == "xml"
    assert parsed[0].fields["Data[Name=Image]"].endswith("cmd.exe")
    assert parsed[0].fields["Data[Name=User]"] == "bob"


def _mixed_rows() -> list[dict[str, object]]:
    rows = []
    for index in range(8):
        if index % 2 == 0:
            raw = json.dumps({"kind": "alert", "sig": f"s{index}", "src": "a"})
        else:
            raw = json.dumps({"kind": "flow", "src": "a", "dst": "b", "bytes": index})
        rows.append({"_raw": raw, "_time": 1000.0 + index, "host": "h1"})
    return rows


def test_kind_facts_measure_numeric_and_recurring_values():
    rows = [
        json.dumps({"n": str(index % 2), "who": "bob" if index % 2 else "amy"})
        for index in range(4)
    ]
    parsed = parse_events(rows)
    stats = field_stats(parsed)
    facts = value_facts(parsed, stats)
    assert facts == {"numeric_share": 0.5, "identity_share": 1.0}
    assert cadence_facts(
        SourceFacts(
            "ix",
            "st",
            10,
            0.0,
            1.0,
            (),
            0,
            (),
            0,
            active_periods=10,
            periods=20,
            count_cv=0.3,
        )
    ) == {"active_periods": 10, "periods": 20, "active_share": 0.5, "count_cv": 0.3}


def test_facts_overrule_a_non_numeric_measurement_and_record_other_conflicts():
    assert reconcile_kind("measurement", {"numeric_share": 0.1}) == (
        "activity",
        "facts_override:measurement_numeric_share=0.10",
    )
    assert reconcile_kind("measurement", {"numeric_share": 0.9}) == ("measurement", None)
    assert reconcile_kind("activity", {"numeric_share": 0.9}) == (
        "activity",
        "kind_conflict:activity_numeric_share=0.90",
    )
    assert reconcile_kind("alert", {"numeric_share": 0.9}) == ("alert", None)


def test_a_low_variety_field_that_selects_the_field_set_splits_the_source():
    parsed = parse_events([str(row["_raw"]) for row in _mixed_rows()])
    partition = choose_partition(parsed)
    assert partition is not None
    assert partition.field == "kind"
    assert partition.values == ("alert", "flow")
    groups = partition_groups(parsed, _mixed_rows(), partition)
    assert [len(groups[value][0]) for value in partition.values] == [4, 4]


def test_is_alert_event_reads_the_event_type_property() -> None:
    assert is_alert_event({"_raw": json.dumps({"event_type": "alert", "src_ip": "a"})}) is True
    assert is_alert_event({"_raw": json.dumps({"event_type": "flow", "src_ip": "a"})}) is False
    assert is_alert_event({"_raw": "Mar 24 10:00:00 sshd: not json"}) is False


def test_a_sample_of_alert_lines_is_a_detection_stream_even_when_the_model_said_activity() -> None:
    from portal.modules.security.core.hunt.notables.cards import (
        ModelAnswer,
        assemble_cards,
        prepare_cards,
    )

    flows = [
        json.dumps({"event_type": "flow", "src_ip": "10.0.0.1", "dest_ip": "10.0.0.2"})
        for _ in range(6)
    ]
    alerts = [
        json.dumps({"event_type": "alert", "src_ip": f"10.0.1.{i}", "alert": {"signature": "s"}})
        for i in range(6)
    ]
    rows = [
        {"_raw": raw, "_time": float(index), "host": "h1"}
        for index, raw in enumerate(flows + alerts)
    ]
    facts = SourceFacts("ix", "eve.json", 12, 0.0, 100.0, ("h1",), 1, ("s1",), 1)
    prepared = prepare_cards(facts, rows, windows=1, model="test")
    answer = ModelAnswer(
        json.dumps({"kind": "activity", "actor": ["src_ip"], "basis": "network events"}),
        0.0,
        "",
        None,
        None,
    )
    cards = assemble_cards(
        prepared, {item.given.cache_key: (answer, 1, False) for item in prepared}
    )
    alert_card = next(card for card in cards if card.part_value == "alert")
    flow_card = next(card for card in cards if card.part_value == "flow")
    assert alert_card.kind == "alert"
    assert alert_card.kind_said == "activity"
    assert alert_card.kind_note is not None and alert_card.kind_note.startswith("alert_structure:")
    assert alert_card.kind_facts["alert_lines"] == 6
    assert flow_card.kind == "activity"


def test_sample_source_adds_probe_alerts_missed_by_the_general_sample() -> None:
    from portal.modules.security.core.hunt.executor import Read

    class _ProbeExecutor:
        def __init__(self, sample: list[dict[str, object]], probe: list[dict[str, object]]):
            self.sample = sample
            self.probe = probe
            self.kinds: list[str] = []

        def read(
            self, query: str, start: float, end: float, *, kind: str, row_cap: int | None = None
        ) -> Read:
            del query, start, end, row_cap
            self.kinds.append(kind)
            rows = self.probe if kind == "alert_probe" else self.sample
            return Read([dict(row) for row in rows], False, None)

    flow = {
        "_raw": json.dumps({"event_type": "flow", "src_ip": "a", "dest_ip": "b"}),
        "_time": 1000.0,
        "host": "h1",
    }
    alert = {
        "_raw": json.dumps(
            {"event_type": "alert", "alert": {"signature": "ET scan"}, "src_ip": "a"}
        ),
        "_time": 1001.0,
        "host": "h1",
    }

    executor = _ProbeExecutor([flow], [alert])
    _facts_value, read = _sample_source(executor, _facts())  # type: ignore[arg-type]
    assert "alert_probe" in executor.kinds
    assert any(is_alert_event(row) for row in read.rows)
    assert any(row["_raw"] == flow["_raw"] for row in read.rows)

    sampled_alerts = _ProbeExecutor([alert] * 6, [])
    _facts_value, read = _sample_source(sampled_alerts, _facts())  # type: ignore[arg-type]
    assert "alert_probe" not in sampled_alerts.kinds


_SYSLOG = [
    "Mar 24 10:00:00 web01 sshd[123]: Accepted password for bob from 10.0.0.5 port 22 ssh2",
    "Mar 24 10:00:05 web02 sshd[124]: Accepted password for amy from 10.0.0.6 port 22 ssh2",
    "Mar 24 10:01:00 web01 sshd[125]: Accepted password for bob from 10.0.0.5 port 22 ssh2",
    "Mar 24 10:02:00 web02 sshd[126]: Failed password for root from 10.0.0.7 port 22 ssh2",
    "Mar 25 11:00:00 web01 sshd[127]: Accepted password for amy from 10.0.0.6 port 22 ssh2",
    "Mar 25 11:01:00 web02 sshd[128]: Accepted password for bob from 10.0.0.5 port 22 ssh2",
]


def test_a_line_oriented_log_is_mined_into_a_header_and_templates():
    parsed, model = parse_sample(_SYSLOG)
    assert model is not None
    assert (model.header_tokens, model.program_position) == (5, 4)
    assert {item.fmt for item in parsed} == {"template"}
    assert model.states["existed"] == 1
    assert model.states["kept"] == 1
    assert model.states["explained"] == 6
    assert parsed[0].fields["program"] == "sshd"
    assert parsed[0].fields["template"] == "* password for * from * port 22 ssh2"
    assert parsed[0].fields["v1"] == "Accepted"
    assert parsed[0].fields["v2"] == "bob"
    assert parsed[0].fields["v3"] == "10.0.0.5"
    assert parsed[3].fields["v1"] == "Failed"


def test_template_events_read_with_the_learned_model_after_the_sample():
    _parsed, model = parse_sample(_SYSLOG)
    assert model is not None
    row = parse_row(_SYSLOG[5], "template", template=model)
    assert row.fields["program"] == "sshd"
    assert row.fields["v2"] == "bob"
    assert parse_row(_SYSLOG[5], "template", template=None).fields == {}


def test_is_alert_line_reads_a_suricata_fast_log_line() -> None:
    assert is_alert_line(
        "01/24/2022-03:56:58.599059  [**] [1:2220006:1] SURICATA SMTP no server welcome "
        "message [**] [Classification: Generic Protocol Command Decode] [Priority: 3] {TCP} "
        "172.19.130.4:587 -> 192.168.230.122:49954"
    )
    assert is_alert_line(json.dumps({"event_type": "alert", "src_ip": "a"}))
    assert is_alert_line("Mar 24 10:00:00 sshd: not json") is False
    assert is_alert_line(json.dumps({"event_type": "flow"})) is False


def test_a_time_ordered_discriminator_never_splits_a_source():
    rows = []
    for day in (1, 2, 3):
        for _index in range(4):
            fields = {"day": str(day), "a": "x"}
            for extra in "bcd"[:day]:
                fields[extra] = extra
            rows.append(json.dumps(fields))
    parsed = parse_events(rows)
    assert choose_partition(parsed) is None


def test_words_keep_a_bracketed_stamp_and_a_quoted_phrase_whole():
    line = '1.2.3.4 - - [01/Jan/2020:00:00:00 +0000] "GET /a b HTTP/1.1" 200 12'
    positions = words(line)
    assert positions[3] == "[01/Jan/2020:00:00:00 +0000]"
    assert positions[4] == "GET /a b HTTP/1.1"
    assert positions[5:] == ["200", "12"]


def test_a_web_access_line_keeps_the_quoted_request_whole_and_names_no_tool():
    lines = [
        '1.2.3.4 - - [01/Jan/2020:00:00:00 +0000] "GET /a HTTP/1.1" 200 12 "-" "Firefox/86.0"',
        '1.2.3.5 - - [01/Jan/2020:00:00:01 +0000] "GET /b HTTP/1.1" 200 34 "-" "Firefox/86.0"',
        '1.2.3.6 - - [01/Jan/2020:00:00:02 +0000] "POST /c HTTP/1.1" 404 56 "-" "Firefox/86.0"',
        '1.2.3.4 - - [01/Jan/2020:00:00:03 +0000] "GET /a HTTP/1.1" 200 12 "-" "Firefox/86.0"',
    ]
    parsed, model = parse_sample(lines)
    assert model is not None
    assert model.header_tokens == 0
    assert parsed[0].fields["v1"] == "1.2.3.4"
    assert parsed[0].fields["v3"] == "GET /a HTTP/1.1"
    assert parsed[2].fields["v3"] == "POST /c HTTP/1.1"
    assert "HTTP/1.1" not in parsed[0].fields["template"]
    assert "Firefox" not in parsed[0].fields["template"]


_BROWSER_SAMPLE = [
    '192.168.104.81 - - [17/Jan/2022:10:49:17 +0000] "GET / HTTP/1.1" 200 6137 "-" '
    '"Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:86.0) Gecko/20100101 Firefox/86.0"',
    "192.168.104.155 - - [17/Jan/2022:10:49:18 +0000] "
    '"GET /wp-includes/js/jquery/jquery.js HTTP/1.1" 200 19870 "-" '
    '"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) '
    'HeadlessChrome/95.0.4638.69 Safari/537.36"',
    "192.168.104.81 - - [17/Jan/2022:10:49:20 +0000] "
    '"GET /wp-content/themes/go/style.css HTTP/1.1" 200 9202 "-" '
    '"Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:86.0) Gecko/20100101 Firefox/86.0"',
    '192.168.104.155 - - [17/Jan/2022:10:49:22 +0000] "POST /xmlrpc.php HTTP/1.1" 200 411 "-" '
    '"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) '
    'HeadlessChrome/95.0.4638.69 Safari/537.36"',
    "192.168.104.82 - - [17/Jan/2022:10:49:25 +0000] "
    '"GET /wp-content/uploads/2022/01/note.txt HTTP/1.1" 404 146 "-" '
    '"Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:86.0) Gecko/20100101 Firefox/86.0"',
    "192.168.104.155 - - [17/Jan/2022:10:49:27 +0000] "
    '"GET /wp-content/plugins/akismet/akismet.js HTTP/1.1" 200 10207 "-" '
    '"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) '
    'HeadlessChrome/95.0.4638.69 Safari/537.36"',
]

# Real attack-hour lines the stored round-3 runs read and then dropped as fields == {}
# (provenance: coding_task/FINDING_HUNT_TEMPLATE_PARSE.md; stored runs under
# /Volumes/data01/portal5_hunt/hunt_proof_r3_<family>/v3/<family>)
_ATTACK_LINES = [
    # santos: the WPScan burst line E2 read from Splunk
    '172.21.128.119 - - [17/Jan/2022:11:22:42 +0000] "HEAD /.wp-config.swp HTTP/1.1" 404 146 '
    '"https://intranet.smith.santos.com" '
    '"WPScan v3.8.20 (https://wpscan.com/wordpress-security-scanner)"',
    # santos: python-requests webshell fetch from the same burst
    '172.21.128.119 - - [17/Jan/2022:11:22:57 +0000] "GET /?p=5 HTTP/1.1" 200 32311 "-" '
    '"python-requests/2.27.1"',
    # russell: the 24/Jan 03:00 python-requests burst (2,499 such lines dropped in round 3)
    '172.19.131.174 - - [24/Jan/2022:03:58:20 +0000] "GET / HTTP/1.1" 200 9291 "-" '
    '"python-requests/2.27.1"',
    # kyoushi: graded intranet file line dropped by the horde-sampled template model
    "172.16.0.27 - - [24/Mar/2021:10:30:49 +0000] "
    '"GET /wp-login.php?action=logout&_wpnonce=2d01559b52 HTTP/1.1" 302 2543 "-" '
    '"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) '
    'HeadlessChrome/89.0.4389.82 Safari/537.36"',
    # a plain single-word tool agent
    '10.0.0.9 - - [01/Jan/2020:00:00:09 +0000] "GET /a HTTP/1.1" 200 12 "-" "curl/7.81.0"',
]


def test_a_novel_user_agent_or_quoted_payload_still_parses():
    _parsed, model = parse_sample(_BROWSER_SAMPLE)
    assert model is not None
    for line in _ATTACK_LINES:
        fields = parse_row(line, "template", template=model).fields
        assert fields, f"dropped: {line}"
    literals = {token for template in model.templates for token in template.tokens if token}
    tools = {
        "WPScan",
        "python-requests/2.27.1",
        "curl/7.81.0",
        "Firefox/86.0",
        "HeadlessChrome/95.0.4638.69",
        "Mozilla/5.0",
    }
    assert not literals & tools


def test_an_apostrophe_does_not_swallow_the_rest_of_a_line():
    assert words("a b don't stop c d") == ["a", "b", "don't", "stop", "c", "d"]


def test_key_value_needs_two_pairs_and_delimited_uses_its_header():
    assert parse_kv("user=bob action=login") == {"user": "bob", "action": "login"}
    assert parse_kv("just one=thing") == {}
    parsed = parse_events(["time,user,action", "1,bob,login", "2,amy,run"])
    assert [item.fmt for item in parsed] == ["header", "delimited", "delimited"]
    assert parsed[1].fields == {"time": "1", "user": "bob", "action": "login"}


# Real botsv2 wineventlog:security shape: a KV header then a colon-labelled detail body.
_SECURITY_4720 = (
    "08/23/2017 09:18:55 PM\nLogName=Security\n"
    "SourceName=Microsoft Windows security auditing.\nEventCode=4720\nEventType=0\n"
    "Type=Information\nComputerName=mercury.frothly.local\nTaskCategory=User Account Management\n"
    "OpCode=Info\nRecordNumber=1700527\nKeywords=Audit Success\nMessage=A user account was created.\n"
    "\nSubject:\n\tSecurity ID:\t\tFROTHLY\\service3\n\tAccount Name:\t\tservice3\n"
    "\tAccount Domain:\t\tFROTHLY\n\tLogon ID:\t\t0x927DF4B\n"
    "\nNew Account:\n\tSecurity ID:\t\tFROTHLY\\svcvnc\n\tAccount Name:\t\tsvcvnc\n"
    "\nAttributes:\n\tSAM Account Name:\tsvcvnc\n\tDisplay Name:\t\t<value not set>\n"
)
_SECURITY_4688 = (
    "08/23/2017 09:16:40 PM\nLogName=Security\nEventCode=4688\n"
    "ComputerName=mercury.frothly.local\nTaskCategory=Process Creation\n"
    "Message=A new process has been created.\n\nSubject:\n\tAccount Name:\t\tservice3\n"
    "\nProcess Information:\n\tNew Process ID:\t\t0x16e4\n"
    "\tNew Process Name:\tC:\\Windows\\System32\\ftp.exe\n"
    '\tProcess Command Line:\t"C:\\Windows\\System32\\ftp.exe" -s:C:\\Users\\public\\ftpscript.txt\n'
)


def test_kv_reads_the_colon_labelled_body_of_a_rendered_security_event():
    fields = parse_kv(_SECURITY_4720)
    assert fields["EventCode"] == "4720"
    assert fields["SAM Account Name"] == "svcvnc"
    assert fields["ComputerName"] == "mercury.frothly.local"
    process = parse_kv(_SECURITY_4688)
    assert process["New Process Name"] == "C:\\Windows\\System32\\ftp.exe"
    assert process["Account Name"] == "service3"
    # a detail value may itself contain '=' (a command line); the label still keys it
    assert "ftpscript.txt" in process["Process Command Line"]


def test_kv_colon_body_does_not_change_auditd_or_dovecot_lines():
    from portal.modules.security.core.hunt.notables.parse import _KV

    audit = (
        "type=USER_ACCT msg=audit(1616458141.526:150): pid=1899 uid=0 auid=4294967295 "
        'ses=4294967295 msg=\'op=PAM:accounting acct="root" exe="/usr/sbin/cron" res=success\''
    )
    mail = (
        "Mar 23 08:06:26 mail dovecot: imap-login: Login: user=<konstantin.braun>, "
        "method=PLAIN, rip=172.16.100.30, lip=172.16.100.30, mpid=4044, TLS, session=<x>"
    )
    journal = (
        "2021-03-22T20:21:49+00:00 ubuntu kernel: Command line: "
        "BOOT_IMAGE=/boot/vmlinuz root=LABEL=cloudimg-rootfs ro console=tty1"
    )
    for line in (audit, mail, journal):
        kv_keys = {m.group(1) for m in _KV.finditer(line)}
        # the colon-label rule adds no field these single-line KV logs do not already carry
        assert set(parse_kv(line)) == kv_keys


def test_free_text_stays_text_and_field_stats_count_repeats():
    parsed = parse_events(["x"] * 4)
    assert {item.fmt for item in parsed} == {"text"}
    assert not field_stats(parsed)
    stats = field_stats(parse_events([json.dumps({"a": index % 2}) for index in range(6)]))
    assert stats[0].present == 6
    assert stats[0].distinct == 2
    assert stats[0].repeats is True


def test_delimited_row_reads_with_the_columns_the_sample_established():
    parsed = parse_row("3,carl,stop", "delimited", ("time", "user", "action"))
    assert parsed.fields == {"time": "3", "user": "carl", "action": "stop"}
    assert parse_row("3,carl,stop", "delimited", ()) == parse_row("3,carl,stop", "text", ())


def test_quoted_delimited_records_keep_their_real_columns():
    lines = [
        '"time","user","action"',
        '"2020-01-01 00:00:00",bob,"login, ok"',
        "host,[01/Jan/2020:00:00:00,123],logout",
    ]
    parsed = parse_events(lines)
    assert {item.fmt for item in parsed} == {"header", "delimited"}
    assert parsed[1].fields == {
        "time": "2020-01-01 00:00:00",
        "user": "bob",
        "action": "login, ok",
    }
    assert parsed[2].fields == {
        "time": "host",
        "user": "[01/Jan/2020:00:00:00,123]",
        "action": "logout",
    }


def test_one_field_in_several_core_roles_is_rejected():
    answer = apply_answer(
        json.dumps({"kind": "activity", "actor": ["c1"], "action": ["c1"], "object": ["c1"]}),
        ["c1", "c2", "c3"],
    )
    assert answer.error == "ambiguous_roles:c1"
    assert answer.roles == {}


def test_model_answer_is_rejected_when_it_names_a_field_the_sample_lacks():
    answer = apply_answer(
        json.dumps({"kind": "activity", "actor": ["user", "invented"], "action": ["image"]}),
        ["user", "image"],
    )
    assert answer.error is None
    assert answer.roles == {"actor": ("user",), "action": ("image",)}
    assert answer.rejected == ("invented",)
    assert apply_answer("no json at all", ["user"]).error == "unparseable_answer"
    assert apply_answer('{"kind": "nonsense"}', ["user"]).error == "invalid_kind"


def test_a_no_answer_response_records_tokens_and_finish_reason():
    class _Full:
        def complete(self, **request: object) -> dict[str, object]:
            del request
            return {
                "model": "seat",
                "usage": {"prompt_tokens": 5, "completion_tokens": 84},
                "choices": [{"finish_reason": "stop", "message": {"content": "retry"}}],
            }

    answer = ask_model(_Full(), "seat", "prompt")
    assert answer.error == "no_answer"
    assert answer.completion_tokens == 84
    assert answer.finish_reason == "stop"
    assert answer.prompt_tokens == 5


def test_template_mining_generalizes_glog_dates_pids_and_clock_times():
    sample = [
        "W0815 09:03:50.228999 264929280 virtual_table.cpp:515] The browser_plugins table returns data",
        "W0815 09:19:50.733101 264929280 virtual_table.cpp:515] The chrome_extensions table returns data",
        "W0815 09:35:50.111222 264929280 virtual_table.cpp:515] The browser_plugins table returns data",
        "W0815 09:51:50.333444 264929280 virtual_table.cpp:515] The chrome_extensions table returns data",
    ]
    _parsed, model = parse_sample(sample)
    assert model is not None
    # A line from another day and PID still matches the mined template
    other_day = (
        "W0811 14:48:02.307137 62255104 virtual_table.cpp:515] The shell_history table returns data"
    )
    assert parse_row(other_day, "template", template=model).fields
    # A genuinely different error message remains out of structure (misfit)
    anomaly = "W0811 14:50:40.060264 61181952 filesystem.cpp:114] Cannot read file that exceeds size limit: /tmp/a.crypt"
    assert parse_row(anomaly, "template", template=model).fields == {}


def test_xml_empty_text_attributes_use_dotted_names_instead_of_value_keys():
    raw = (
        "<Event><System><EventID>3</EventID>"
        '<TimeCreated SystemTime="2017-08-19T00:59:06.435Z"/>'
        '<Execution ProcessID="860" ThreadID="1020"/></System>'
        '<EventData><Data Name="Image">cmd.exe</Data></EventData></Event>'
    )
    fields = parse_xml(raw)
    assert fields["TimeCreated.SystemTime"] == "2017-08-19T00:59:06.435Z"
    assert fields["Execution.ProcessID"] == "860"
    assert fields["Data[Name=Image]"] == "cmd.exe"
    assert not any("2017-08-19" in key for key in fields)


def test_field_stats_surfaces_varying_non_numeric_fields_on_wide_json():
    rows = []
    for index in range(6):
        obj: dict[str, object] = {f"a_counter_{n:02d}": index * n for n in range(45)}
        obj["sender_mail_from"] = f"user{index % 2}@example.com"
        obj["receiver_rcpt_to"] = f"dest{index % 3}@remote.org"
        obj["subject"] = f"msg {index}"
        rows.append(json.dumps(obj))
    stats = field_stats(parse_events(rows))
    names = {stat.name for stat in stats}
    assert "sender_mail_from" in names
    assert "receiver_rcpt_to" in names
    assert "subject" in names


def test_choose_partition_prefers_true_schema_discriminator_over_host_or_header():
    rows = []
    for idx in range(24):
        host = f"host-{idx % 2}"
        kind = idx % 3
        if kind == 0:
            rec = {
                "Computer": host,
                "EventID": "1",
                "Image": "a.exe",
                "CommandLine": "run",
                "User": "u",
            }
        elif kind == 1:
            rec = {
                "Computer": host,
                "EventID": "3",
                "SourceIp": "10.0.0.1",
                "DestIp": "1.2.3.4",
                "DestPort": "443",
            }
        else:
            rec = {
                "Computer": host,
                "EventID": "11",
                "TargetFilename": "x.doc",
                "CreationUtcTime": "t",
                "ProcessGuid": "g",
            }
        rows.append(json.dumps(rec))
    partition = choose_partition(parse_events(rows))
    assert partition is not None
    assert partition.field == "EventID"
    assert partition.values == ("1", "11", "3")

    # Optional field varying independently of a header must not trigger a bogus partition
    uniform = [
        json.dumps(
            {
                "accept": f"type/{idx % 2}",
                "src_ip": f"10.0.0.{idx % 3}",
                "uri": f"/p{idx}",
                **({"ref": "/r"} if idx % 3 == 0 else {}),
            }
        )
        for idx in range(12)
    ]
    assert choose_partition(parse_events(uniform)) is None


def test_choose_partition_keeps_grouped_categorical_discriminator_not_time_ordered():
    # Reproduces osquery_results: long consecutive runs of the same pack name,
    # with both forward and backward transitions when the pack changes.
    rows = []
    packs = [
        ("pack_b", {"columns.mem": "10", "columns.wall": "1"}),
        ("pack_a", {"columns.path": "/tmp/a", "columns.pid": "42"}),
        ("pack_c", {"columns.port": "443", "columns.proto": "6"}),
        ("pack_a", {"columns.path": "/tmp/b", "columns.pid": "43"}),
        ("pack_b", {"columns.mem": "12", "columns.wall": "2"}),
    ]
    for pack_name, extra in packs:
        for _ in range(15):
            rows.append(json.dumps({"name": pack_name, "host": "h1", **extra}))
    partition = choose_partition(parse_events(rows))
    assert partition is not None
    assert partition.field == "name"
    assert partition.values == ("pack_a", "pack_b", "pack_c")


def test_template_card_classifies_numeric_metric_streams_as_measurement():
    from portal.modules.security.core.hunt.notables.cards import assemble_cards, prepare_cards
    from portal.modules.security.core.hunt.notables.sample import SourceFacts

    metric_rows = [
        {"_raw": f"mem {1000 + i} {2000 + i} {3000 + i} {40 + (i % 5)}.5 {50 + (i % 5)}.2"}
        for i in range(20)
    ]
    facts = SourceFacts("ix", "vmstat", 20, 0.0, 100.0, ("h1",), 1, ("s1",), 1)
    prepared = prepare_cards(facts, metric_rows, windows=1, model="test")
    cards = assemble_cards(prepared, {})
    assert len(cards) == 1
    assert cards[0].fmt == "template"
    assert cards[0].kind == "measurement"
