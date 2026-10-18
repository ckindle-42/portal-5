"""Build tests/wfe/suites/security_analysis_production.jsonl, the security
analysis production suite for auto-security (WFE new instruments 2026-10-18).

Three kinds, 36 tasks, 12 screen (four per kind), all no_tools:

- cve-cwe (12)          map a CVE published after 2026-01 to its NVD-assigned CWE id;
- severity (12)         report the CVSS v3.1/v4 base severity band from NVD;
- vulnerable-function (12) identify the CWE id of a seeded weakness in a short code snippet.

Every gold is checkable in code (exact CWE id or exact severity band) and sourced
from public data: CVE/CWE/severity records come from the U.S. National Vulnerability
Database (NVD), which is published by NIST and is in the public domain. The code
snippets are minimal original examples written for this suite for static analysis
only; none are executable exploit payloads.

    uv run python tests/wfe/suites/build_security_analysis_production.py
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from tests.wfe.suites.build_research_production import Fact

OUT = Path(__file__).with_name("security_analysis_production.jsonl")
FORMAT = 'Answer only as JSON {"answer": "..."}.'
COUNTS = {"cve-cwe": 12, "severity": 12, "vulnerable-function": 12}
SCREEN = {"cve-cwe": 4, "severity": 4, "vulnerable-function": 4}
LANE = "security"

DECIDING_FACTS: dict[str, list[Fact]] = {}

# CVE/CWE/severity data from the U.S. National Vulnerability Database (NVD,
# https://nvd.nist.gov/), a public-domain resource published by NIST. Values
# retrieved 2026-10-18 via the NVD REST API v2.0
# (https://services.nvd.nist.gov/rest/json/cves/2.0).
CVE_ITEMS: list[tuple[str, str, str, str]] = [
    ("CVE-2026-0001", "CWE-416", "MEDIUM", "2026-09-08"),
    ("CVE-2026-0005", "CWE-200", "MEDIUM", "2026-03-02"),
    ("CVE-2026-0006", "CWE-122", "CRITICAL", "2026-03-02"),
    ("CVE-2026-0007", "CWE-1021", "HIGH", "2026-03-02"),
    ("CVE-2026-0008", "CWE-441", "HIGH", "2026-03-02"),
    ("CVE-2026-0009", "CWE-269", "HIGH", "2026-06-01"),
    ("CVE-2026-0010", "CWE-787", "HIGH", "2026-03-02"),
    ("CVE-2026-0011", "CWE-693", "HIGH", "2026-03-02"),
    ("CVE-2026-0012", "CWE-284", "MEDIUM", "2026-03-02"),
    ("CVE-2026-0018", "CWE-20", "MEDIUM", "2026-06-01"),
    ("CVE-2026-0024", "CWE-862", "MEDIUM", "2026-03-02"),
    ("CVE-2026-0040", "CWE-190", "MEDIUM", "2026-06-01"),
]

# Minimal original code snippets for static analysis only. Each demonstrates one
# well-known weakness class; none are executable exploit payloads. License: the
# snippets are original to this suite and released under the same license as the
# repository (Apache-2.0).
VULN_SNIPPETS: list[tuple[str, str, str]] = [
    (
        "sql-injection",
        'def lookup_user(conn, username):\n    query = "SELECT * FROM users WHERE name = \'" + username + "\'"\n    return conn.execute(query)',
        "CWE-89",
    ),
    (
        "cross-site-scripting",
        'def render_comment(comment):\n    return f"<div>{comment}</div>"',
        "CWE-79",
    ),
    (
        "buffer-overflow",
        "void process(char *input) {\n    char buf[16];\n    strcpy(buf, input);\n}",
        "CWE-121",
    ),
    (
        "command-injection",
        'def ping(host):\n    return os.system("ping -c 1 " + host)',
        "CWE-78",
    ),
    (
        "path-traversal",
        'def read_file(base, path):\n    return open(base + "/" + path).read()',
        "CWE-22",
    ),
    (
        "insecure-deserialization",
        "def load_user(data):\n    return pickle.loads(data)",
        "CWE-502",
    ),
    (
        "hardcoded-credentials",
        'DB_PASSWORD = "supersecret123"\n\ndef connect():\n    return db.connect(password=DB_PASSWORD)',
        "CWE-798",
    ),
    (
        "weak-hash",
        "def hash_password(pwd):\n    return hashlib.md5(pwd.encode()).hexdigest()",
        "CWE-328",
    ),
    (
        "improper-access-control",
        'def delete_record(record_id):\n    # no ownership check\n    db.execute(f"DELETE FROM records WHERE id = {record_id}")',
        "CWE-284",
    ),
    (
        "missing-authorization",
        "def admin_panel(request):\n    # no role check\n    return render_admin(request)",
        "CWE-862",
    ),
    (
        "race-condition",
        "def increment(balance):\n    current = balance.read()\n    balance.write(current + 1)",
        "CWE-362",
    ),
    (
        "information-exposure",
        'def handle_error(e):\n    return f"Error: {repr(e)}\\nTrace: {traceback.format_exc()}"',
        "CWE-200",
    ),
]


def _pattern(gold: str) -> str:
    return rf'"answer"\s*:\s*"?{re.escape(gold)}"?(?![\w.-])'


def _answer(gold: str) -> str:
    return json.dumps({"answer": gold})


def _phrase(imperative: bool, question: str, command: str) -> str:
    return command if imperative else question


def _task(
    tid: str,
    kind: str,
    n: int,
    ins: str,
    gold: str,
    givens: list[tuple[str, str]],
    wrong: str,
) -> dict:
    DECIDING_FACTS[tid] = [Fact("", {}, re.escape(given), why) for given, why in givens]
    return {
        "id": tid,
        "kind": kind,
        "lane": LANE,
        "agentic": False,
        "screen": n < SCREEN[kind],
        "instruction": ins,
        "requires_tools": [],
        "checkers": [{"type": "answer_contains", "patterns": [_pattern(gold)]}],
        "controls": {
            "pass": [{"answer": _answer(gold), "tool_calls": []}],
            "fail": [{"answer": _answer(wrong), "tool_calls": []}],
        },
        "no_tools": True,
    }


def build_cve_cwe(n: int) -> dict:
    cve, cwe, severity, published = CVE_ITEMS[n]
    tid = f"sa-cve-cwe-{n:02d}"
    ins = _phrase(
        n % 3 == 0,
        f"What CWE id does NVD assign to {cve} (published {published})? {FORMAT}",
        f"Classify {cve} (published {published}) by its NVD CWE assignment. {FORMAT}",
    )
    return _task(
        tid,
        "cve-cwe",
        n,
        ins,
        cwe,
        [(cve, "the CVE identifier being classified")],
        "CWE-000",
    )


def build_severity(n: int) -> dict:
    cve, _cwe, severity, published = CVE_ITEMS[n]
    tid = f"sa-severity-{n:02d}"
    ins = _phrase(
        n % 3 == 0,
        (
            f"What is the CVSS base severity band for {cve} (published {published}) "
            f"as recorded by NVD? Answer with the exact band name. {FORMAT}"
        ),
        (
            f"Report the NVD CVSS base severity band for {cve} (published {published}). "
            f"Answer with the exact band name. {FORMAT}"
        ),
    )
    return _task(
        tid,
        "severity",
        n,
        ins,
        severity,
        [(cve, "the CVE identifier whose severity is asked")],
        "UNKNOWN",
    )


def build_vulnerable_function(n: int) -> dict:
    label, snippet, cwe = VULN_SNIPPETS[n]
    tid = f"sa-vulnerable-function-{n:02d}"
    body = f"```\n{snippet}\n```"
    ins = _phrase(
        n % 3 == 0,
        (
            f"What is the CWE id of the primary vulnerability in this code snippet?\n{body}\n"
            f"{FORMAT}"
        ),
        (f"Identify the CWE id of the primary vulnerability in this snippet:\n{body}\n{FORMAT}"),
    )
    # use a distinctive non-comment line as the deciding fact
    givens = [(snippet.splitlines()[0], f"the first line of the {label} snippet")]
    return _task(tid, "vulnerable-function", n, ins, cwe, givens, "CWE-000")


BUILDERS = {
    "cve-cwe": build_cve_cwe,
    "severity": build_severity,
    "vulnerable-function": build_vulnerable_function,
}


def _leaks(t: dict) -> str | None:
    """The gold must not appear in the instruction (CVE/CWE ids and severity bands)."""
    gold = json.loads(t["controls"]["pass"][0]["answer"])["answer"]
    if gold in t["instruction"]:
        return f"gold {gold!r} is stated in the instruction"
    return None


def build() -> list[dict]:
    DECIDING_FACTS.clear()
    tasks = [BUILDERS[k](n) for k, count in COUNTS.items() for n in range(count)]
    # Golds are not unique across kinds by design: severity bands repeat, and CWE
    # ids can appear in both cve-cwe mapping and vulnerable-function identification.
    for t in tasks:
        if leak := _leaks(t):
            raise RuntimeError(f"{t['id']}: {leak}")
    tasks.sort(key=lambda t: not t["screen"])
    return tasks


def main() -> None:
    tasks = build()
    OUT.write_text("".join(json.dumps(t) + "\n" for t in tasks))
    print(f"wrote {OUT.name}: {len(tasks)} tasks, {sum(t['screen'] for t in tasks)} screen")


if __name__ == "__main__":
    main()
