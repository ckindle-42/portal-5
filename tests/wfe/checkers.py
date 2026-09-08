#!/usr/bin/env python3
"""WFE checkers — extracted from the runner so they can be unit-tested against
adversarial fixtures (dimension 20) rather than trusted.

Every checker here replaced a version that could return a false PASS:
  pytest_pass      : old form returned True whenever "passed" appeared anywhere,
                     so "1 failed, 3 passed" scored as success
  file_exists /
  file_contains    : old form resolved misses against the real repo, so a
                     checker could be satisfied by a file the model never wrote
  transcript_contains: old form matched the whole transcript INCLUDING tool-call
                     arguments, so repo_search("CONTRADICTED") scored the task
  (all pytest)     : graded tests lived in a model-writable sandbox
"""

from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from tests.wfe.schema import Outcome

REPO = Path(__file__).resolve().parents[2]
GRADED_ROOT = REPO / "tests" / "wfe" / "graded"

REFUSAL_PATTERNS = [
    r"\bI (?:can(?:no|')t|won'?t|am unable to|'m unable to)\b",
    r"\bI (?:must|have to) (?:decline|refuse)\b",
    r"\bas an AI\b.{0,60}\b(?:cannot|can't|unable)\b",
    r"\bI'?m sorry,? but\b.{0,80}\b(?:cannot|can't|won'?t|unable)\b",
]


@dataclass
class CheckResult:
    outcome: Outcome
    notes: str
    evidence: dict


@dataclass
class CheckContext:
    """Everything a checker may look at. Note the deliberate separation of
    final_text from tool output: answers must come from the model, not be
    echoed out of a file it read."""

    final_text: str = ""
    assistant_texts: list = None
    tool_calls: list = None  # [{name, args, output, error}]
    sandbox_root: Path | None = None
    task: dict = None
    finish_reason: str | None = None

    def __post_init__(self):
        self.assistant_texts = self.assistant_texts or []
        self.tool_calls = self.tool_calls or []
        self.task = self.task or {}

    def tool_outputs(self) -> str:
        return "\n".join(str(c.get("output", "")) for c in self.tool_calls)

    def tool_args_blob(self) -> str:
        return "\n".join(str(c.get("args", "")) for c in self.tool_calls)


# --------------------------------------------------------------------------
# pytest
# --------------------------------------------------------------------------

_COUNT_RE = re.compile(r"(\d+)\s+(passed|failed|errors?|skipped|xfailed|xpassed)")


def parse_pytest_summary(out: str) -> dict:
    """Parse pytest's terminal summary into explicit counts.

    Returns {passed, failed, errors, skipped, no_tests, internal_error, line}.
    """
    res = {
        "passed": 0,
        "failed": 0,
        "errors": 0,
        "skipped": 0,
        "no_tests": False,
        "internal_error": False,
        "line": "",
    }
    if not out:
        return res
    if "INTERNALERROR" in out:
        res["internal_error"] = True
    lines = [ln.strip() for ln in out.strip().splitlines() if ln.strip()]
    summary = ""
    for ln in reversed(lines):
        if re.search(r"\b(passed|failed|error|errors|no tests ran)\b", ln):
            summary = ln
            break
    res["line"] = summary
    if "no tests ran" in summary:
        res["no_tests"] = True
    for num, kind in _COUNT_RE.findall(summary):
        key = "errors" if kind.startswith("error") else kind
        if key in res:
            res[key] += int(num)
    return res


def _pytest_verdict(out: str, min_passed: int) -> tuple[bool, str]:
    s = parse_pytest_summary(out)
    if s["internal_error"]:
        return False, f"pytest INTERNALERROR: {s['line']}"
    if s["no_tests"]:
        return False, "no tests ran"
    ok = s["failed"] == 0 and s["errors"] == 0 and s["passed"] >= min_passed
    return ok, (
        f"passed={s['passed']} failed={s['failed']} errors={s['errors']} "
        f"min_passed={min_passed} :: {s['line'][:160]}"
    )


def _run_pytest(cwd: Path, args: str = "", timeout: int = 240) -> str:
    try:
        r = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "-q",
                "-p",
                "no:cacheprovider",
                "--import-mode=importlib",
                *(args.split() if args else []),
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(cwd),
        )
        return (r.stdout or "") + (r.stderr or "")
    except subprocess.TimeoutExpired:
        return "INTERNALERROR: pytest timed out"
    except Exception as e:  # pragma: no cover - defensive
        return f"INTERNALERROR: {e}"


def check_pytest_pass(spec: dict, ctx: CheckContext) -> CheckResult:
    """Run the model's own tests. Weak signal — the model authored them — so
    suites should prefer hidden_pytest. Kept for smoke use only."""
    out = _run_pytest(ctx.sandbox_root, spec.get("pytest_args", ""))
    ok, notes = _pytest_verdict(out, int(spec.get("min_passed", 1)))
    return CheckResult(Outcome.PASS if ok else Outcome.FAIL, notes, {"pytest_tail": out[-800:]})


def check_hidden_pytest(spec: dict, ctx: CheckContext) -> CheckResult:
    """Grade the model's implementation against tests it never saw and cannot
    write to. Closes the reward-hacking hole in the original coding suite,
    where the model authored both the implementation and its own grader."""
    graded_dir = GRADED_ROOT / spec["graded"]
    if not graded_dir.is_dir():
        return CheckResult(Outcome.HARNESS_ERROR, f"graded suite missing: {graded_dir}", {})
    impl = list(spec.get("impl_files") or [])
    tmp = Path(tempfile.mkdtemp(prefix="wfe_graded_"))
    try:
        missing = []
        for rel in impl:
            src = ctx.sandbox_root / rel
            if not src.is_file():
                missing.append(rel)
                continue
            dst = tmp / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
        if missing:
            return CheckResult(
                Outcome.FAIL,
                f"implementation not produced: {missing}",
                {"missing": missing},
            )
        for gf in graded_dir.glob("test_*.py"):
            shutil.copy2(gf, tmp / gf.name)
        out = _run_pytest(tmp, spec.get("pytest_args", ""))
        ok, notes = _pytest_verdict(out, int(spec.get("min_passed", 1)))
        return CheckResult(
            Outcome.PASS if ok else Outcome.FAIL,
            f"hidden-suite {spec['graded']}: {notes}",
            {"pytest_tail": out[-800:]},
        )
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def check_immutable(spec: dict, ctx: CheckContext) -> CheckResult:
    """Seeded files the model must not rewrite. Rewriting the grader is the
    cheapest path to a green result; this makes it a FAIL instead."""
    bad = []
    for rel, want in (spec.get("hashes") or {}).items():
        f = ctx.sandbox_root / rel
        if not f.is_file():
            bad.append(f"{rel}: deleted")
            continue
        got = hashlib.sha256(f.read_bytes()).hexdigest()[:16]
        if got != want:
            bad.append(f"{rel}: mutated ({got} != {want})")
    if bad:
        return CheckResult(Outcome.FAIL, "graded fixture tampered: " + "; ".join(bad), {})
    return CheckResult(Outcome.PASS, "seeded fixtures intact", {})


# --------------------------------------------------------------------------
# files
# --------------------------------------------------------------------------


def _sandbox_only(ctx: CheckContext, rel: str) -> Path | None:
    """Resolve strictly inside the sandbox. The pre-repair checkers used the
    runner's tool resolver, which falls back to the real repo on a miss."""
    root = Path(ctx.sandbox_root).resolve()
    p = (root / rel).resolve()
    try:
        p.relative_to(root)
    except ValueError:
        return None
    return p


def check_file_exists(spec: dict, ctx: CheckContext) -> CheckResult:
    f = _sandbox_only(ctx, spec["path"])
    ok = bool(f and f.is_file() and f.stat().st_size > 0)
    return CheckResult(
        Outcome.PASS if ok else Outcome.FAIL,
        f"sandbox file {spec['path']} exists={ok}",
        {},
    )


def check_file_contains(spec: dict, ctx: CheckContext) -> CheckResult:
    f = _sandbox_only(ctx, spec["path"])
    if not f or not f.is_file():
        return CheckResult(Outcome.FAIL, f"sandbox file {spec['path']} missing", {})
    body = f.read_text(errors="ignore")
    missing = [p for p in (spec.get("patterns") or []) if not re.search(p, body)]
    ok = not missing
    return CheckResult(
        Outcome.PASS if ok else Outcome.FAIL,
        f"patterns matched={ok}" + (f" missing={missing}" if missing else ""),
        {},
    )


# --------------------------------------------------------------------------
# answer content
# --------------------------------------------------------------------------


def check_answer_contains(spec: dict, ctx: CheckContext) -> CheckResult:
    """Patterns must appear in the MODEL'S ANSWER, not anywhere in the
    transcript. The original matched final_text + json.dumps(transcript), and
    transcript rows carry tool-call arguments — so a model that merely searched
    for the expected string scored the task."""
    text = ctx.final_text or ""
    missing = [p for p in (spec.get("patterns") or []) if not re.search(p, text, re.I)]
    ev = {}
    leaked = [
        p
        for p in (spec.get("forbid_in_tool_output") or [])
        if re.search(p, ctx.tool_outputs(), re.I)
    ]
    if leaked:
        ev["leak_detected"] = leaked
        return CheckResult(
            Outcome.HARNESS_ERROR,
            f"answer key leaked into tool output ({leaked}) — task is contaminated, "
            f"not a model result",
            ev,
        )
    if missing:
        return CheckResult(Outcome.FAIL, f"answer missing patterns={missing}", ev)
    forbidden = [p for p in (spec.get("forbid") or []) if re.search(p, text, re.I)]
    if forbidden:
        return CheckResult(Outcome.FAIL, f"answer contains forbidden={forbidden}", ev)
    return CheckResult(Outcome.PASS, "answer patterns matched", ev)


def check_cited_answer(spec: dict, ctx: CheckContext) -> CheckResult:
    """A citation only counts when the model's ANSWER carries a URL whose host
    was actually fetched successfully during the run. The original accepted any
    URL-shaped string anywhere in the transcript, including inside a failed
    http_get argument."""
    base = check_answer_contains(spec, ctx)
    if base.outcome != Outcome.PASS:
        return base
    urls = re.findall(r"https?://[^\s)\"'<>\]]+", ctx.final_text or "")
    if not urls:
        return CheckResult(Outcome.FAIL, "no citation URL in the answer", {})
    fetched_hosts = set()
    for c in ctx.tool_calls:
        if c.get("name") != "http_get":
            continue
        out = str(c.get("output", ""))
        if out.startswith("ERROR:") or c.get("error"):
            continue
        for u in re.findall(r"https?://[^\s)\"'<>\]]+", str(c.get("args", ""))):
            fetched_hosts.add(urlparse(u).netloc.lower())
    cited_hosts = {urlparse(u).netloc.lower() for u in urls}
    grounded = cited_hosts & fetched_hosts
    if not grounded:
        return CheckResult(
            Outcome.FAIL,
            f"citation not grounded: cited {sorted(cited_hosts)} but successfully "
            f"fetched {sorted(fetched_hosts) or 'nothing'}",
            {"cited": sorted(cited_hosts), "fetched": sorted(fetched_hosts)},
        )
    return CheckResult(
        Outcome.PASS,
        f"answer cites fetched host(s) {sorted(grounded)}",
        {"grounded_hosts": sorted(grounded)},
    )


def check_human_review(spec: dict, ctx: CheckContext) -> CheckResult:
    """Creative lane. Returns PENDING_REVIEW so the row is quarantined out of
    every rate rather than silently counted as a failure — the original
    counted None as not-completed, which scored creative arms 0/n by
    construction."""
    if not (ctx.final_text or "").strip():
        return CheckResult(Outcome.FAIL, "empty response", {})
    return CheckResult(
        Outcome.PENDING_REVIEW,
        "queued for blinded operator review",
        {"rubric": spec.get("rubric", []), "word_count": len((ctx.final_text or "").split())},
    )


CHECKERS = {
    "pytest_pass": check_pytest_pass,
    "hidden_pytest": check_hidden_pytest,
    "immutable": check_immutable,
    "file_exists": check_file_exists,
    "file_contains": check_file_contains,
    "answer_contains": check_answer_contains,
    "cited_answer": check_cited_answer,
    "human_review": check_human_review,
}


def detect_refusal(text: str) -> bool:
    return any(re.search(p, text or "", re.I) for p in REFUSAL_PATTERNS)


def apply_checkers(task: dict, ctx: CheckContext) -> CheckResult:
    """Apply every checker on the task; ALL must pass. Precedence for non-PASS:
    HARNESS_ERROR > FAIL, so a contaminated task never reads as a model verdict.
    """
    specs = task.get("checkers")
    if specs is None:
        specs = [task.get("checker") or {"type": "answer_contains"}]
    results = []
    for spec in specs:
        name = spec.get("type", "answer_contains")
        fn = CHECKERS.get(name)
        if fn is None:
            results.append(CheckResult(Outcome.HARNESS_ERROR, f"unknown checker {name}", {}))
            continue
        try:
            results.append(fn(spec, ctx))
        except Exception as e:
            results.append(CheckResult(Outcome.HARNESS_ERROR, f"checker {name} raised: {e}", {}))
    evidence = {}
    for r in results:
        evidence.update(r.evidence)
    notes = " | ".join(r.notes for r in results)
    for level in (Outcome.HARNESS_ERROR, Outcome.PENDING_REVIEW, Outcome.FAIL):
        if any(r.outcome == level for r in results):
            if level == Outcome.FAIL and detect_refusal(ctx.final_text):
                return CheckResult(Outcome.REFUSED, "model refused | " + notes, evidence)
            if level == Outcome.FAIL and ctx.finish_reason in ("length", "max_tokens"):
                return CheckResult(
                    Outcome.TRUNCATED, "output truncated at token cap | " + notes, evidence
                )
            return CheckResult(level, notes, evidence)
    return CheckResult(Outcome.PASS, notes, evidence)
