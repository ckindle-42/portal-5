"""Reader tests: apache combined and syslog parsing, entities, failure accounting."""

from __future__ import annotations

from portal.modules.security.core.mawa.events import read_events

APACHE_LINE = (
    '192.0.2.10 - - [22/Aug/2026:13:30:00 +0700] "GET /dvwa/login.php HTTP/1.1" '
    '200 1286 "http://192.0.2.5/x" "Mozilla/5.0 TestUA"'
)
APACHE_LINE_NOREF = (
    '192.0.2.10 - - [22/Aug/2026:13:30:01 +0700] "GET /a.php?q=WyJ1bmFtZSJd HTTP/1.1" '
    '404 - "-" "python-requests/2.32"'
)
SYSLOG_PID = (
    "Aug 22 13:34:52 webserver sshd[1548]: pam_unix(sshd:session): session closed for user dvwa"
)
SYSLOG_NOPID = (
    "Aug 22 13:34:52 webserver sudo:     dvwa : TTY=pts/0 ; "
    "PWD=/var/www/html/dvwa/hackable/uploads ; USER=root ; COMMAND=/usr/bin/cat /etc/passwd"
)


def _read(tmp_path, *lines: str) -> tuple[list, list]:
    path = tmp_path / "in.log"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return read_events([str(path)], syslog_year=2026, syslog_tz_hours=7.0)


def test_apache_line_parses_fields_and_ts(tmp_path) -> None:
    events, reports = _read(tmp_path, APACHE_LINE)
    assert reports[0].events == 1 and not reports[0].failures
    ev = events[0]
    assert ev.kind == "apache_access"
    assert ev.fields["client"] == "192.0.2.10"
    assert ev.fields["code"] == "200"
    assert ev.ts > 0
    assert "path:/dvwa/login.php" in ev.entities
    assert "code:200" in ev.entities


def test_apache_entities_never_carry_client_or_user_agent(tmp_path) -> None:
    events, _ = _read(tmp_path, APACHE_LINE)
    joined = " ".join(sorted(events[0].entities))
    assert "192.0.2.10" not in joined
    assert "TestUA" not in joined
    assert "Mozilla" not in joined


def test_base64_query_decodes_to_command_tokens(tmp_path) -> None:
    events, _ = _read(tmp_path, APACHE_LINE_NOREF)
    ents = events[0].entities
    assert "cmd:uname" in ents
    assert "qval:WyJ1bmFtZSJd" in ents


def test_syslog_line_with_and_without_pid(tmp_path) -> None:
    events, _ = _read(tmp_path, SYSLOG_PID, SYSLOG_NOPID)
    sshd, sudo = events[0], events[1]
    assert sshd.tag == "sshd" and sshd.pid == "1548"
    assert sshd.message == "pam_unix(sshd:session): session closed for user dvwa"
    assert "user:dvwa" in sshd.entities
    assert sudo.tag == "sudo" and sudo.pid == ""
    assert sudo.message.startswith("dvwa : TTY=pts/0")
    assert "user:dvwa" in sudo.entities
    assert "path:/var/www/html/dvwa/hackable/uploads" in sudo.entities
    assert "cmd:/usr/bin/cat" in sudo.entities
    assert "cmd:/etc/passwd" in sudo.entities


def test_failures_and_empty_lines_are_accounted(tmp_path) -> None:
    events, reports = _read(
        tmp_path, APACHE_LINE, "", "garbage line that matches nothing", SYSLOG_PID
    )
    assert len(events) == 2
    report = reports[0]
    assert report.lines_read == 4
    assert report.empty_lines == 1
    assert report.events == 2
    assert len(report.failures) == 1
    assert report.failures[0].line_no == 3
    assert "no parser matched" in report.failures[0].reason
