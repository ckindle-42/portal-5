"""Unit tests for capability_lib scorers.

Covers extract_final_answer, run_python_against_tests, and parse_tcpdump_filter.
Includes regression fixtures from actual V10 result data.
"""

from __future__ import annotations

from tests.benchmarks.capability_lib import (
    extract_final_answer,
)

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
