"""Unit tests for capability_lib scorers.

Covers extract_final_answer, run_python_against_tests, and parse_tcpdump_filter.
Includes regression fixtures from actual V10 result data.
"""

from __future__ import annotations

from tests.benchmarks.capability_lib import (
    extract_code_block,
    extract_final_answer,
    parse_tcpdump_filter,
    run_python_against_tests,
)

# ── Actual V10 excerpts (from v10_candidates_20260629T194541Z.json) ──────────

# AgentWorld P1_envsim — bare prose reasoning preamble
AGENTWORLD_P1_EXCERPT = """The user wants me to simulate the execution of the following command in a Linux terminal:
`find /var/log -name '*.log' -mtime -1 -size +10M 2>/dev/null | head -20`

This command finds files in `/var/log` that:
- have a name ending with `.log`
- were modified within the last day (`-mtime -1`)
- are larger than 10MB (`-size +10M`)
and then pipes the output to `head -20`.

Since this is a simulation and I don't have access to an actual filesystem, I'll provide a plausible output based on common log files found in `/var/log` on a Linux system. The output would be similar to what you'd see on a moderately active server:
```
/var/log/syslog
/var/log/auth.log
/var/log/kern.log
/var/log/apache2/access.log
/var/log/apache2/error.log
/var/log/mysql/error.log
/var/log/mail.log
/var/log/ufw.log
/var/log/dpkg.log
/var/log/apt/history.log
/var/log/journal/12345/user-1000.journal
/var/log/nginx/access.log
/var/log/nginx/error.log
/var/log/postgresql/postgresql-14-main.log
/var/log/auth.log.1
/var/log/kern.log.1
/var/log/syslog.1
```"""

# AgentWorld P6_swe_handoff — "Thinking Process:" bare prose preamble
AGENTWORLD_P6_EXCERPT = """Thinking Process:

1.  **Analyze the Request:**
    *   **Issue:** Intermittent HTTP 502 Bad Gateway errors from nginx -> uvicorn (Python FastAPI) backend during high load / request bursts. Not 100% of requests.
    *   **Goal:** Walk through the diagnosis from the terminal, then write a `tcpdump` filter to capture the most relevant traffic.
    *   **Output Format:**
        1.  Diagnostic plan first as a numbered list.
        2.  Then a single `tcpdump` command in a fenced bash code block.

2.  **Diagnostic Plan Formulation (nginx -> uvicorn / FastAPI):**
    *   HTTP 502 Bad Gateway from nginx means nginx received an invalid response from the upstream server. Common causes for FastAPI/uvicorn are: uvicorn crashing, timing out, or hitting worker limits during spikes.

**Diagnostic Plan:**

1.  Check uvicorn logs for worker timeouts or crashes: `journalctl -u fastapi -n 100`
2.  Check system resource usage during the incident (CPU, RAM, file descriptors): `top -bn1 | head -20 ; ulimit -n ; ss -s`
3.  Capture traffic between nginx and uvicorn using tcpdump to confirm what nginx is actually receiving back when the 502 occurs.

Now, the tcpdump filter to capture only HTTP traffic between nginx (e.g., 127.0.0.1) and uvicorn:

```bash
tcpdump -i lo -nn 'tcp port 8000 and (port 80 or port 443)' -w /tmp/nginx-uvicorn-502.pcap
```"""


# ── extract_final_answer tests ───────────────────────────────────────────────


class TestExtractFinalAnswer:
    def test_strips_think_tags(self):
        text = "<think>Let me think about this...</think>\nThe answer is 42."
        result = extract_final_answer(text)
        assert "answer is 42" in result
        assert "<think>" not in result

    def test_handles_unclosed_think(self):
        text = "<think>I'm reasoning...\nSome text but never closed."
        result = extract_final_answer(text)
        assert "I'm reasoning" not in result or result == ""

    def test_leaves_clean_text_unchanged(self):
        text = "Here is the answer: print('hello')"
        result = extract_final_answer(text)
        assert result == text

    def test_strips_thinking_process_preamble(self):
        """Regression: AgentWorld P6 starts with 'Thinking Process:' — must strip."""
        result = extract_final_answer(AGENTWORLD_P6_EXCERPT)
        # The answer should start with the diagnostic plan, not the preamble
        assert "Thinking Process" not in result
        assert "tcpdump" in result or "Diagnostic Plan" in result

    def test_strips_the_user_wants_preamble(self):
        """Regression: AgentWorld P1 starts with 'The user wants...' — must strip."""
        result = extract_final_answer(AGENTWORLD_P1_EXCERPT)
        assert "The user wants" not in result
        # The answer should start at the fenced block
        assert "```" in result

    def test_regression_agentworld_p6_sees_answer_not_preamble(self):
        """V10 P6 excerpt: after extraction, scorer sees answer body, not preamble."""
        result = extract_final_answer(AGENTWORLD_P6_EXCERPT)
        assert "tcpdump" in result.lower()
        assert "Thinking Process" not in result

    def test_handles_empty_text(self):
        assert extract_final_answer("") == ""
        assert extract_final_answer("  \n  ") == ""


# ── run_python_against_tests ─────────────────────────────────────────────────


class TestRunPythonAgainstTests:
    def test_correct_code_passes(self):
        source = "def add(a, b):\n    return a + b\n"
        test = "from solution import add\n\ndef test_add():\n    assert add(1, 2) == 3\n"
        passed, output = run_python_against_tests(source, test)
        assert passed is True

    def test_wrong_code_fails(self):
        source = "def add(a, b):\n    return a - b\n"
        test = "from solution import add\n\ndef test_add():\n    assert add(1, 2) == 3\n"
        passed, output = run_python_against_tests(source, test)
        assert passed is False

    def test_syntax_error_fails(self):
        source = "def add(a, b)\n    return a + b\n"  # missing colon
        test = "from solution import add\n\ndef test_add():\n    assert add(1, 2) == 3\n"
        passed, output = run_python_against_tests(source, test)
        assert passed is False
        assert "SyntaxError" in output or "Error" in output


# ── extract_code_block tests ─────────────────────────────────────────────────


class TestExtractCodeBlock:
    def test_extracts_python_block(self):
        text = "Here's the code:\n```python\ndef foo():\n    pass\n```\nDone."
        code = extract_code_block(text, "python")
        assert "def foo()" in code

    def test_extracts_untagged_block(self):
        text = "Here:\n```\ndef bar():\n    pass\n```\n"
        code = extract_code_block(text, "python")
        assert "def bar()" in code

    def test_returns_empty_when_no_block(self):
        text = "No code block here."
        code = extract_code_block(text, "python")
        assert code == ""


# ── parse_tcpdump_filter tests ───────────────────────────────────────────────


class TestParseTcpdumpFilter:
    def test_good_tcpdump_scores_high(self):
        cmd = "tcpdump -i eth0 -nn 'tcp port 80 or port 443' -w capture.pcap"
        facts = parse_tcpdump_filter(cmd)
        assert facts["is_tcpdump"] is True
        assert facts["has_bpf_primitive"] is True
        assert facts["targets_http_ports"] is True
        assert facts["capability_score"] == 1.0

    def test_non_tcpdump_scores_zero(self):
        cmd = "cat /var/log/syslog"
        facts = parse_tcpdump_filter(cmd)
        assert facts["is_tcpdump"] is False
        assert facts["capability_score"] == 0.0

    def test_partial_tcpdump_scores_partial(self):
        cmd = "tcpdump -i any port 22"
        facts = parse_tcpdump_filter(cmd)
        assert facts["is_tcpdump"] is True
        assert facts["has_bpf_primitive"] is True
        assert facts["targets_http_ports"] is False  # port 22 is not HTTP
        assert 0.33 <= facts["capability_score"] <= 0.67


# ── Phase 4 (V11 fleet mode) — numeric_answer_matches, reasoning_aware_max_tokens, stamp_result_meta ──


class TestNumericAnswerMatches:
    def test_exact_match(self):
        from tests.benchmarks.capability_lib import numeric_answer_matches

        assert numeric_answer_matches("The answer is 42", 42.0) is True

    def test_wrong_value(self):
        from tests.benchmarks.capability_lib import numeric_answer_matches

        assert numeric_answer_matches("The answer is 99", 42.0) is False

    def test_within_tolerance(self):
        from tests.benchmarks.capability_lib import numeric_answer_matches

        assert numeric_answer_matches("Value: 2.30", 2.29, tol=0.1) is True

    def test_takes_last_number_ignoring_preamble(self):
        """Regression: preamble contains a decoy '12' but final answer is 2.29."""
        from tests.benchmarks.capability_lib import numeric_answer_matches

        text = (
            "Thinking Process:\n"
            "1. The arrival rate is 30, beds are 12, wait is long.\n"
            "2. Bottleneck capacity is 8/3.5 = 2.29 patients/hr.\n"
            "## Answer\n"
            "The bottleneck capacity is 2.29."
        )
        # Last number should be 2.29 (after preamble stripping)
        assert numeric_answer_matches(text, 2.29, tol=0.1) is True

    def test_no_numbers_returns_false(self):
        from tests.benchmarks.capability_lib import numeric_answer_matches

        assert numeric_answer_matches("no numbers here", 1.0) is False


class TestReasoningAwareMaxTokens:
    def test_emits_reasoning_workspace_returns_8192(self):
        from tests.benchmarks.capability_lib import reasoning_aware_max_tokens

        result = reasoning_aware_max_tokens("auto-agentic-lite")
        assert result == 8192

    def test_unknown_workspace_returns_4096(self):
        from tests.benchmarks.capability_lib import reasoning_aware_max_tokens

        result = reasoning_aware_max_tokens("nonexistent-workspace-xyz")
        assert result == 4096


class TestStampResultMeta:
    def test_adds_methodology_version(self):
        from tests.benchmarks.capability_lib import stamp_result_meta

        payload = {"task_id": "test"}
        result = stamp_result_meta(payload)
        assert result["methodology_version"] == "v2-capability"

    def test_adds_scored_at(self):
        from tests.benchmarks.capability_lib import stamp_result_meta

        payload = {}
        result = stamp_result_meta(payload)
        assert "scored_at" in result
