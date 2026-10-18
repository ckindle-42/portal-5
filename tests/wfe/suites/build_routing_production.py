"""Build tests/wfe/suites/routing_production.jsonl, the `auto` router's single-arm
characterisation suite (WFE P3 triage §1 REVISED; master plan S8/O5).

The pipeline's `auto` routing is: harmful-intent gate -> Layer-1 LLM classifier ->
Layer-2 weighted keyword fallback (router/routing.py). The classifier model is the
LLM_ROUTER_MODEL env, not a request parameter, so there are no challenger arms: this
suite CHARACTERISES the production router. 36 tasks, 12 in the screen tier, four
kinds — the four workspaces Layer 2 can provably score (the O2 group sketch named
documents/data/media, but those workspaces have no keyword tables: a prompt routed
there is only decidable by the live LLM classifier, which the offline lane cannot
verify — so the kinds are the clear-cut set):

- auto-coding (9)     code intent, anchored on the table's strong terms;
- auto-compliance (9) NERC CIP / audit intent;
- auto-security (9)   defensive analysis of AUTHORIZED lab material (never trips the
                      harmful-intent gate — asserted at build time);
- auto-spl (9)        Splunk SPL intent.

Each task is a fictional user request that Layer 2, scored offline against the real
keyword tables (config/inference/routing_*_keywords.json via
router/routing.py:_detect_workspace), resolves to its gold workspace — the offline
proof that the prompt is clear-cut. The live row measures whether the production
router (Layer 1 first, Layer 2 as fallback) agrees; graded by the `routed_workspace`
checker on the row's own trace (served.options.workspace), never on the text: the
routed seat replies one word ("Reply with the single word OK.") to cap the seat-swap
cost. Every row is no_tools.

No-leak against the router's own few-shot prompt (config/routing_examples.json): a
task may share no five-word sequence with any example message, and no prompt may name
any workspace id — asserted at build time and by test, so the suite cannot teach the
router its own examples or its answer.

    uv run python tests/wfe/suites/build_routing_production.py
"""

from __future__ import annotations

import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
OUT = Path(__file__).with_name("routing_production.jsonl")
EXAMPLES = json.loads((REPO / "config" / "routing_examples.json").read_text())
LANE = "routing"
SCREEN = {"auto-coding": 3, "auto-compliance": 3, "auto-security": 3, "auto-spl": 3}
COUNTS = {"auto-coding": 9, "auto-compliance": 9, "auto-security": 9, "auto-spl": 9}
TAIL = "Reply with the single word OK."

#: (gold workspace, the fictional user request). Every request must survive the build
#: gate: Layer 2 resolves it to its gold offline, the harmful-intent gate stays cold,
#: and it shares no five-word sequence with any routing example.
PROMPTS: dict[str, list[str]] = {
    "auto-coding": [
        "Write a Python script that renames every file in a folder to lowercase and prints a summary of what it changed.",
        "Write a function that parses ISO 8601 timestamps from a log file and returns the five most recent ones.",
        "Can you review this code for a race condition? The worker threads share one dictionary without a lock and I think that is the bug.",
        "Debug this for me: my shell script exits 0 but never writes the output file when the directory name has spaces in it.",
        "Write a program that reads a CSV of fictional warehouse stock and prints every item whose count fell below its reorder level.",
        "Write code that turns a directory of JSON exports into one merged Parquet file, and add unit tests for the merge logic.",
        "This function returns the wrong column when the header row has trailing spaces — fix the bug and show me the diff.",
        "I need a code review of this pull request diff: it swaps a queue for a stack in the job scheduler and I think the retries now starve.",
        "Write a script that pings every host in a fictional subnet and appends the reachable ones to an inventory file with a timestamp.",
    ],
    "auto-compliance": [
        "Map our fictional substation maintenance policy to CIP-007 requirements and list every gap with remediation steps for audit preparation.",
        "For CIP-003, what does the standard require a registered entity to document in its cybersecurity governance policy, and where do our fictional procedures fall short?",
        "We are preparing an audit of CIP-004 access rights. Build the checklist of evidence the auditor will ask for.",
        "Which CIP-006 physical security controls apply to a fictional control center, and what would a gap analysis look like for them?",
        "Our fictional operator self-certified CIP-005 for the current quarter — what evidence must the compliance program keep to support that posting?",
        "Write the remediation plan outline for a fictional finding against CIP-008 incident reporting, with the standard's own vocabulary.",
        "For CIP-009 recovery plans, which parts must be exercised on a cycle, and what does the register text actually require?",
        "Draft the supply-chain risk assessment section for CIP-013 as it would apply to a fictional medium-impact fleet of inverters.",
        "Compare what CIP-010 requires for configuration change management against what our fictional change board already documents.",
    ],
    "auto-security": [
        "In our authorized lab, analyze this captured payload for a buffer overflow and write the defensive signature that detects it.",
        "For a threat-hunting exercise on our own network, suggest hunts for lateral movement using Windows event logs, and what a backdoor beacon would look like.",
        "Our fictional honeypot caught scanning traffic — write the incident response steps to contain and eradicate a suspected bind shell on a decoy host.",
        "Assess this fictional vulnerability report for a privilege escalation in a print service and recommend defensive mitigations for our fleet.",
        "Build the defensive detection rule for an asreproasting attempt against our fictional domain controller, and explain the tell-tale event ids.",
        "Write the incident response runbook for a suspected botnet callback from a fictional point-of-sale host, containment first.",
        "In our authorized malware analysis lab, walk through static analysis of this fictional dropper sample and list the indicators a defender can block.",
        "Map this fictional attack chain to mitre att&ck techniques and write the defensive detections our SOC should deploy at each stage.",
        "For a defensive review of our fictional fleet, which hardening steps blunt an attempt to pass the hash, and what would the detection look like?",
    ],
    "auto-spl": [
        "Write a Splunk SPL query using tstats to count authentication failures per host over the last 24 hours.",
        "Build a Splunk correlation search that fires a notable event when one source IP produces failed logins on five or more fictional workstations.",
        "Which SPL commands join a lookup of asset owners to authentication events — show an inputlookup and stats example I can adapt.",
        "Draft a detection search that alerts when a service account is used outside its documented maintenance window.",
        "Use makeresults and eventstats to build a fictional baseline of logins per user, then flag the outliers in the same Splunk search.",
        "Write the SPL for a mvexpand over a comma-separated list field so each fictional process name becomes its own row.",
        "Write a Splunk SPL query that pivots tstats by the data model's Authentication index and prints a per-user success and failure table.",
        "Build a Splunk correlation search for data model acceleration gaps: which fictional sourcetypes are falling out of the model?",
        "Write SPL that uses inputlookup to pull a fictional asset list, joins it to authentication events, and marks each row with the owner's site.",
    ],
}


def _shingles(text: str, k: int = 5) -> set[str]:
    words = re.sub(r"[^a-z0-9 ]", " ", text.lower()).split()
    return {" ".join(words[i : i + k]) for i in range(len(words) - k + 1)}


def _example_shingles() -> set[str]:
    out: set[str] = set()
    for ex in EXAMPLES.get("examples", []):
        out |= _shingles(str(ex.get("message", "")))
    return out


def build() -> list[dict]:
    from portal.platform.inference.router import routing as rt

    example_shingles = _example_shingles()
    tasks = []
    for ws, prompts in PROMPTS.items():
        if len(prompts) != COUNTS[ws]:
            raise RuntimeError(f"{ws}: {len(prompts)} prompts for a {COUNTS[ws]}-task kind")
        for n, body in enumerate(prompts):
            instruction = f"{body} {TAIL}"
            # the clear-cut proof: the real Layer 2 resolves this prompt to its gold
            got = rt._detect_workspace([{"role": "user", "content": instruction}])
            if got != ws:
                raise RuntimeError(
                    f"{ws}-{n:02d}: Layer 2 resolves the prompt to {got!r}, not {ws!r}"
                )
            # the harmful-intent gate must stay cold: a trip would reroute to auto-daily
            if rt.detect_harmful_intent([{"role": "user", "content": instruction}]):
                raise RuntimeError(f"{ws}-{n:02d}: the prompt trips the harmful-intent gate")
            # no-leak vs the router's own few-shot examples, and no workspace id named
            if _shingles(instruction) & example_shingles:
                raise RuntimeError(
                    f"{ws}-{n:02d}: the prompt shares a five-word sequence with routing_examples.json"
                )
            for other in PROMPTS:
                if re.search(rf"\b{re.escape(other)}\b", instruction):
                    raise RuntimeError(f"{ws}-{n:02d}: the prompt names a workspace id")
            if re.search(r"(?:^|[.\n]\s*)In [A-Z0-9][A-Z0-9._-]*\s*[,\u2014]", instruction):
                raise RuntimeError(f"{ws}-{n:02d}: instruction opens a sentence with 'In <file>,'")
            tasks.append(
                {
                    "id": f"route-{ws.removeprefix('auto-')}-{n:02d}",
                    "kind": ws,
                    "lane": LANE,
                    "agentic": False,
                    "screen": n < SCREEN[ws],
                    "instruction": instruction,
                    "requires_tools": [],
                    "checkers": [{"type": "routed_workspace", "workspace": ws}],
                    "controls": {
                        "pass": [
                            {
                                "answer": "OK",
                                "tool_calls": [],
                                "served": {"options": {"workspace": ws}},
                            }
                        ],
                        "fail": [
                            {
                                "answer": "OK",
                                "tool_calls": [],
                                "served": {"options": {"workspace": "auto-daily"}},
                            }
                        ],
                    },
                    "no_tools": True,
                }
            )
    tasks.sort(key=lambda t: not t["screen"])
    return tasks


def main() -> None:
    tasks = build()
    OUT.write_text("".join(json.dumps(t) + "\n" for t in tasks))
    print(f"wrote {OUT.name}: {len(tasks)} tasks, {sum(t['screen'] for t in tasks)} screen")


if __name__ == "__main__":
    main()
