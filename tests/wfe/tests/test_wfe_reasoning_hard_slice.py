"""The hard-reasoning production suite: sound under the controls gate, regenerates
identically, every gold recomputable from the instruction text alone (an oracle
that does not share the generator's code path), no gold stated, every deciding
fact declared and stated, and the auto-reasoning plan served by its backends.yaml
groups at windows that hold the reasoning chain and the hard output cap.

The oracle differs per kind, matching how each gold is checkable in code:

- competition-math: an independent re-derivation (brute force / DP) of the answer
  from the numbers the instruction states, asserted equal to the committed gold
  (which was also cross-checked against the official MAA answer key / HMMT
  solutions at authoring time — recorded in the generator's PROVENANCE);
- grad-science: the gold is a letter; the test asserts the option at that letter
  states exactly the reference fact re-listed here (the fact itself is recorded
  against its standard reference in PROVENANCE — factual MCQs cannot be
  recomputed from their own text, which is the one place this suite's oracle
  deviates from the math suite's);
- puzzle: logic puzzles are re-solved by brute force over all 5! finishing orders
  from the parsed clues; combinatorics puzzles are re-computed by formula and
  (where cheap) brute force from the numbers the instruction states.
"""

from __future__ import annotations

import itertools
import json
import math
import re
from pathlib import Path

import pytest
import yaml

from tests.wfe import controls
from tests.wfe.checkers import CheckContext, apply_checkers
from tests.wfe.schema import Outcome
from tests.wfe.suites import build_reasoning_hard_production as gen

REPO = Path(__file__).resolve().parents[3]
SUITE = REPO / "tests/wfe/suites/reasoning_hard_production.jsonl"
PLAN = REPO / "tests/wfe/plans/reasoning_hard_screen.yaml"
TASKS = {t["id"]: t for t in map(json.loads, SUITE.read_text().splitlines())}
KINDS = {"competition-math": 12, "grad-science": 12, "puzzle": 12}
WORKSPACES = ("auto-reasoning",)
ORD = {"first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5}
IMPERATIVE = {"Work", "Solve", "Count", "Determine"}

#: Challengers named in the brief; the last two need ctx64k tags that do not exist
#: yet (TODO operator: create + register them), so their served/window checks are
#: skipped until registration (test below).
REGISTERED_CHALLENGERS = [
    "hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M-ctx96k",
    "glm-4.7-flash:Q4_K_M-ctx64k",
]
PENDING_CHALLENGERS = [
    "hf.co/bartowski/K2-Horizon-MoVA-36B-A4B-GGUF:Q4_K_M-ctx64k",
    "hf.co/ibm-granite/granite-4.2-30b-GGUF:Q4_K_M-ctx64k",
]

#: The correct-option string each grad-science task's gold letter must point at,
#: re-listed here independently of the generator (the fact each states is recorded
#: against its standard reference in the generator's PROVENANCE).
SCIENCE_FACTS = {
    "rh-grad-science-00": "(C) 3",
    "rh-grad-science-01": "(D) 15.6 μs",
    "rh-grad-science-02": "(C) p → e⁺ + π⁰",
    "rh-grad-science-03": "(C) 3R/2",
    "rh-grad-science-04": "(A) 0",
    "rh-grad-science-05": "(B) 4.76",
    "rh-grad-science-06": "(D) Ar",
    "rh-grad-science-07": "(A) CH₃Br",
    "rh-grad-science-08": "(B) N-formylmethionyl-tRNA",
    "rh-grad-science-09": "(A) allolactose",
    "rh-grad-science-10": "(C) 1.98%",
    "rh-grad-science-11": "(C) a ketone",
}


def _kind(kind: str) -> list[dict]:
    return [t for t in TASKS.values() if t["kind"] == kind]


def _gold(task: dict) -> str:
    return json.loads(task["controls"]["pass"][0]["answer"])["answer"]


# --------------------------------------------------------------- the oracle: competition


def _palindromes(ins: str) -> str:
    """Positive base-10 palindromes, no zero digit, stated digit sum (DP)."""
    s = int(re.search(r"add up to (\d+)", ins).group(1))
    memo: dict[tuple[int, int], int] = {}

    def half(m: int, left: int) -> int:
        if (m, left) in memo:
            return memo[(m, left)]
        if m == 0:
            return 1 if left == 0 else 0
        if left <= 0:
            return 0
        memo[(m, left)] = sum(half(m - 1, left - d) for d in range(1, 10) if left - d >= 0)
        return memo[(m, left)]

    total = 0
    for c in range(1, 10):
        if (s - c) % 2:
            continue
        total += sum(half(m, (s - c) // 2) for m in range(1, s))
    return f"{total:03d}"


def _pi6(ins: str) -> str:
    n = int(re.search(r"set \{([\d, ]+)\}", ins).group(1).count(",")) + 1
    count = 0
    for perm in itertools.permutations(range(n)):
        seen: set[int] = set()
        order = 1
        for i in range(n):
            if i in seen:
                continue
            j, length = i, 0
            while j not in seen:
                seen.add(j)
                j = perm[j]
                length += 1
            order = order * length // math.gcd(order, length)
        if 6 % order == 0:
            count += 1
    return f"{count:03d}"


def _divisors_mod12(ins: str) -> str:
    exp = int(re.search(r"(\d+)\^(\d+)", ins).group(2))
    primes = [int(x) for x in re.search(r"equals ([\d ·]+)", ins).group(1).split("·")]
    residue = int(re.search(r"remainder of (\d+) when divided by (\d+)", ins).group(1))
    mod = int(re.search(r"remainder of (\d+) when divided by (\d+)", ins).group(2))
    n = 0
    for exps in itertools.product(range(exp + 1), repeat=len(primes)):
        v = 1
        for p, e in zip(primes, exps, strict=True):
            v = v * pow(p, e, mod) % mod
        if v == residue:
            n += 1
    return f"{n % 1000:03d}"


def _die_stickers(ins: str) -> str:
    num = den = 0
    for rolls in itertools.product(range(6), repeat=6):
        top = [0] * 6
        for i, f in enumerate(rolls, start=1):
            top[f] = i
        if not all(top[rolls[e - 1]] == e for e in (2, 4, 6)):
            continue
        den += 1
        if sum(1 for s in top if s == 0) == 1:
            num += 1
    g = math.gcd(num, den)
    return f"{num // g + den // g:03d}"


def _tenth_terms(ins: str) -> str:
    first = int(re.search(r"first term (\d+)", ins).group(1))
    a, b = (int(x) for x in re.search(r"includes both (\d+) and (\d+)", ins).groups())
    total = sum(
        first + 9 * d for d in range(1, 11) if (a - first) % d == 0 and (b - first) % d == 0
    )
    return f"{total:03d}"


def _rebased(ins: str) -> str:
    limit = int(re.search(r"less than (\d+)", ins).group(1))

    def f(n: int) -> int:
        s = str(n)
        b = max(int(ch) for ch in s) + 1
        return sum(int(ch) * b**i for i, ch in enumerate(reversed(s)))

    return f"{sum(1 for n in range(1, limit) if f(n) == n):03d}"


def _urn(ins: str) -> str:
    red = int(re.search(r"exactly (\d+) of them", ins).group(1))
    ns = []
    for n in range(14, 500):
        for r in range(7, n - 6):  # at least 7 marbles of each color
            if math.comb(r, red) * math.comb(n - r, 7 - red) == math.comb(r, red + 1) * math.comb(
                n - r, 7 - red - 1
            ):
                ns.append(n)
                break
    return f"{sum(ns[:5]):03d}"


def _seven_tuples(ins: str) -> str:
    count = 0
    for t in itertools.product((1, 2, 3), repeat=7):
        if sum(t) % 3:
            continue
        s = (
            t[0] * t[1] * t[3]
            + t[1] * t[2] * t[4]
            + t[2] * t[3] * t[5]
            + t[3] * t[4] * t[6]
            + t[4] * t[5] * t[0]
            + t[5] * t[6] * t[1]
            + t[6] * t[0] * t[2]
        )
        if s % 3 == 0:
            count += 1
    return f"{count:03d}"


def _contains_block(ins: str) -> str:
    divisor = int(re.search(r"divisible by (\d+)", ins).group(1))
    block = re.search(r"contains (\d+) as a consecutive block", ins).group(1)
    found = []
    for n in range(divisor, 2_000_000, divisor):
        if block in str(n):
            found.append(n)
            if len(found) == 2:
                break
    return str(found[1])


def _factorial_power(ins: str) -> str:
    k = int(re.search(r"divides S\(n\) \+ (\d+)", ins).group(1))
    candidates = {n for n in range(1, k + 1) if k % n == 0}
    for p in (11, 41):  # primes dividing 451 = 450 + 1
        for d in range(1, p):
            if k % d == 0:
                candidates.add(d * p)
    best = 0
    for n in sorted(candidates):
        base = math.factorial(math.isqrt(n)) % n
        if pow(base, math.factorial(n), n) == (-k) % n:
            best = max(best, n)
    for n in range(1, 3001):
        base = math.factorial(math.isqrt(n)) % n
        assert pow(base, math.factorial(n), n) != (-k) % n or n <= best, n
    return str(best)


def _binomial_pair(ins: str) -> str:
    sols = []
    for m in range(2, 160):
        for n in range(2, m + 1):
            p = m * n
            if not 1000 <= p <= 9999:
                continue
            sp = str(p)
            if len(set(sp)) < 4 or "0" in sp:
                continue
            b = math.comb(m, n)
            if 1000 <= b <= 9999 and str(b) == sp[2:] + sp[:2]:
                sols.append(m + n)
    assert len(sols) == 1, sols
    return str(sols[0])


def _divisor_counts(ins: str) -> str:
    a, b = (int(x) for x in re.search(r"τ\(n\) = (\d+) and τ\(n \+ 1\) = (\d+)", ins).groups())
    lim = 10**6
    tau = [0] * (lim + 1)
    for i in range(1, lim + 1):
        for j in range(i, lim + 1, i):
            tau[j] += 1
    return str(next(n for n in range(1, lim) if tau[n] == a and tau[n + 1] == b))


_COMPETITION_ORACLE = {
    "rh-competition-math-00": _palindromes,
    "rh-competition-math-01": _pi6,
    "rh-competition-math-02": _divisors_mod12,
    "rh-competition-math-03": _die_stickers,
    "rh-competition-math-04": _tenth_terms,
    "rh-competition-math-05": _rebased,
    "rh-competition-math-06": _urn,
    "rh-competition-math-07": _seven_tuples,
    "rh-competition-math-08": _contains_block,
    "rh-competition-math-09": _factorial_power,
    "rh-competition-math-10": _binomial_pair,
    "rh-competition-math-11": _divisor_counts,
}


# --------------------------------------------------------------- the oracle: puzzle


def _parse_clues(ins: str) -> list[tuple]:
    """Every clue bullet, classified by type (the bullet list is the instruction's
    own structure, so parsing it whole cannot miss a clue)."""
    out = []
    for bullet in re.findall(r"^- (.+?)$", ins, re.M):
        if m := re.fullmatch(r"(\w+) finished immediately before (\w+)\.", bullet):
            out.append(("before", m.group(1), m.group(2)))
        elif m := re.fullmatch(r"(\w+) finished somewhere ahead of (\w+)\.", bullet):
            out.append(("ahead", m.group(1), m.group(2)))
        elif m := re.fullmatch(r"(\w+) finished exactly two positions ahead of (\w+)\.", bullet):
            out.append(("two", m.group(1), m.group(2)))
        elif m := re.fullmatch(r"(\w+) and (\w+) finished in adjacent positions\.", bullet):
            out.append(("adjacent", m.group(1), m.group(2)))
        elif m := re.fullmatch(r"(\w+) did not finish (first|second|third|fourth|fifth)\.", bullet):
            out.append(("not", m.group(1), ORD[m.group(2)]))
        else:
            raise AssertionError(f"unparseable clue: {bullet!r}")
    return out


def _order_fits(clues: list[tuple], pos: dict[str, int]) -> bool:
    for kind, a, b in clues:
        if kind == "not" and pos[a] == b:
            return False
        if kind == "before" and pos[a] + 1 != pos[b]:
            return False
        if kind == "ahead" and pos[a] >= pos[b]:
            return False
        if kind == "two" and pos[a] != pos[b] + 2:
            return False
        if kind == "adjacent" and abs(pos[a] - pos[b]) != 1:
            return False
    return True


def _recompute_logic(ins: str) -> str:
    """Brute-force all 5! finishing orders against every parsed clue; the gold is the
    asked position's runner in the UNIQUE order the clues admit."""
    roster = re.search(r"runners \u2014 ([A-Za-z, ]+?) \u2014", ins).group(1)
    names = sorted(w.strip() for w in roster.replace(" and ", ",").split(","))
    asked = ORD[re.search(r"finished (\w+)[.?]", ins).group(1)]
    clues = _parse_clues(ins)
    assert len(clues) == len(re.findall(r"^- ", ins, re.M)), "a clue bullet went unparsed"
    sols = [
        {nm: i + 1 for i, nm in enumerate(perm)}
        for perm in itertools.permutations(names)
        if _order_fits(clues, {nm: i + 1 for i, nm in enumerate(perm)})
    ]
    assert len(sols) == 1, len(sols)
    return next(nm for nm, p in sols[0].items() if p == asked)


def _phi(x: int) -> int:
    return sum(1 for k in range(1, x + 1) if math.gcd(k, x) == 1)


def _recompute_combinatorics(ins: str) -> str:
    if "round table" in ins:
        seats, k = (
            int(x) for x in re.search(r"(\d+) people.*?(\d+) seats be chosen", ins).groups()
        )
        formula = seats * math.comb(seats - k, k) // (seats - k)
        brute = sum(
            1
            for c in itertools.combinations(range(seats), k)
            if all((y - x) % seats not in (1, seats - 1) for x, y in itertools.combinations(c, 2))
        )
        assert formula == brute
        return str(formula)
    if "A row has" in ins:
        seats, k = (
            int(x)
            for x in re.search(r"A row has (\d+) seats.*?(\d+) seats be chosen", ins).groups()
        )
        return str(math.comb(seats - k + 1, k))
    if "quadruples" in ins:
        s, b = (int(x) for x in re.search(r"= (\d+) and 1 ≤ xi ≤ (\d+)", ins).groups())
        return str(
            sum(
                (-1) ** j * math.comb(4, j) * math.comb(s - 1 - j * b, 3)
                for j in range(5)
                if s - 1 - j * b >= 3
            )
        )
    if "letters are addressed" in ins:
        n = int(re.search(r"(\d+) letters are addressed", ins).group(1))
        d0, d1 = 1, 0
        for i in range(2, n + 1):
            d0, d1 = d1, (i - 1) * (d0 + d1)
        assert d1 == sum(
            1 for p in itertools.permutations(range(n)) if all(p[i] != i for i in range(n))
        )
        return str(d1)
    if "north-west" in ins:
        w, d, bx, by = (
            int(x)
            for x in re.search(
                r"(\d+) units wide and (\d+) units tall.*?(\d+) units east and (\d+) units south",
                ins,
            ).groups()
        )
        return str(
            math.comb(w + d, w) - math.comb(bx + by, bx) * math.comb(w + d - bx - by, w - bx)
        )
    n = int(re.search(r"necklaces with (\d+) beads", ins).group(1))
    return str(sum(_phi(div) * 2 ** (n // div) for div in range(1, n + 1) if n % div == 0) // n)


def _recompute(task: dict) -> str:
    """The gold, recomputed from the instruction text ALONE — no generator code
    beyond the shared _leaks/gold accessors."""
    ins, kind = task["instruction"], task["kind"]
    if kind == "competition-math":
        return _COMPETITION_ORACLE[task["id"]](ins)
    if kind == "puzzle":
        if re.search(r"runners \u2014", ins):
            return _recompute_logic(ins)
        return _recompute_combinatorics(ins)
    # grad-science: factual MCQ — the gold letter is checked against SCIENCE_FACTS
    # and the option list below; nothing can be recomputed from the text.
    return _gold(task)


# --------------------------------------------------------------- suite gates


def test_the_suite_is_sound_and_balanced():
    assert len(TASKS) == 36 and sum(t["screen"] for t in TASKS.values()) == 12
    for kind, n in KINDS.items():
        assert len(_kind(kind)) == n, kind
        assert all(t["id"].startswith(f"rh-{kind}-") for t in _kind(kind))
    assert controls.check_suite(SUITE) == []
    assert all(controls.schema_failures(t) == [] for t in TASKS.values())


def test_every_task_is_no_tools_and_graded_on_answer_and_reasoning():
    for t in TASKS.values():
        assert t["no_tools"] is True and t["requires_tools"] == [] and t["agentic"] is False, t[
            "id"
        ]
        kinds = [c["type"] for c in t["checkers"]]
        assert kinds == ["answer_contains", "answer_after_reasoning"], t["id"]
        assert t["checkers"][0]["patterns"] == t["checkers"][1]["patterns"], t["id"]
        assert t["lane"] == "reasoning", t["id"]


def test_the_controls_pass_and_fail_where_they_must():
    def run(task, answer):
        ctx = CheckContext(task=task, final_text=answer)
        return apply_checkers(task, ctx).outcome

    for t in TASKS.values():
        good = t["controls"]["pass"][0]["answer"]
        assert run(t, good) == Outcome.PASS, t["id"]
        assert run(t, t["controls"]["fail"][0]["answer"]) == Outcome.FAIL, t["id"]
        think_only = t["controls"]["fail"][1]["answer"]
        assert _gold(t) in think_only, t["id"]
        assert run(t, think_only) == Outcome.FAIL, t["id"]


def test_the_instruction_never_states_the_gold():
    for t in TASKS.values():
        assert gen._leaks(t) is None, t["id"]
        gold = _gold(t)
        if re.fullmatch(r"\d+", gold):
            assert not re.search(rf"(?<!\d){gold}(?!\d)", t["instruction"]), t["id"]
            if re.fullmatch(r"0\d\d", gold):
                assert not re.search(rf"(?<!\d){int(gold)}(?!\d)", t["instruction"]), t["id"]


def test_every_gold_is_recomputed_from_the_instruction_alone():
    for t in TASKS.values():
        assert _recompute(t) == _gold(t), t["id"]


def test_every_science_option_and_gold_letter_matches_the_recorded_fact():
    for t in _kind("grad-science"):
        options = re.findall(r"^\(([A-D])\) (.+?)$", t["instruction"], re.M)
        assert [o[0] for o in options] == ["A", "B", "C", "D"], t["id"]
        assert len({o[1] for o in options}) == 4, t["id"]
        gold = _gold(t)
        assert gold in "ABCD", t["id"]
        chosen = dict(options)[gold]
        assert f"({gold}) {chosen}" == SCIENCE_FACTS[t["id"]], t["id"]


def test_a_third_of_each_kind_is_imperative():
    for kind in KINDS:
        starts = [t["instruction"].split()[0] for t in _kind(kind)]
        imperative = sum(w in IMPERATIVE for w in starts)
        assert imperative * 3 >= len(starts) - 1, (kind, starts)


def test_deciding_facts_are_declared_and_stated():
    gen.build()
    for t in TASKS.values():
        facts = gen.DECIDING_FACTS[t["id"]]
        assert facts, t["id"]
        for f in facts:
            assert f.tool == "" and not f.args, (
                t["id"],
                f.why,
            )  # no tools: the prompt is the source
            assert re.search(f.pattern, t["instruction"]), (t["id"], f.why)


def test_the_golds_are_unique_across_the_suite():
    # Numbers and runner names must be unique; grad-science letter answers repeat
    # by design (only four letters exist).
    golds = [_gold(t) for t in TASKS.values() if t["kind"] != "grad-science"]
    assert len(golds) == len(set(golds))


def test_provenance_is_recorded_for_every_task():
    gen.build()
    for t in TASKS.values():
        p = gen.PROVENANCE[t["id"]]
        assert p.get("source") and p.get("licence"), t["id"]
    # contamination note: every competition item was published after 2026-01
    for t in _kind("competition-math"):
        assert "2026" in gen.PROVENANCE[t["id"]]["source"], t["id"]


def test_the_suite_regenerates_identically():
    built = "".join(json.dumps(t) + "\n" for t in gen.build())
    assert built == SUITE.read_text()


def test_the_chain_fits_the_window_under_the_hard_output_cap():
    """prompt (chars/4) + predict_limit <= context_limit, per seat, per task."""
    portal = yaml.safe_load((REPO / "config/portal.yaml").read_text())["workspaces"]
    for ws in WORKSPACES:
        w = portal[ws]
        limit, cap = w["context_limit"], w["predict_limit"]
        assert cap and limit, ws
        for t in TASKS.values():
            prompt = (len(w.get("owui_system_prompt") or "") + len(t["instruction"])) / 4
            assert prompt + cap <= limit, (ws, t["id"], prompt + cap)


# --------------------------------------------------------------- the plan


def _served(ws: str, backends: dict) -> set[str]:
    groups = set(backends["workspace_routing"][ws])
    return {
        m["id"] for b in backends["backends"] if b["group"] in groups for m in b.get("models") or []
    }


def _window(tag: str) -> int:
    return int(re.search(r"ctx(\d+)k", tag).group(1)) * 1024


def test_the_plan_arms_are_served_by_the_workspaces_groups_and_fit_its_window():
    plan = yaml.safe_load(PLAN.read_text())["workloads"]
    portal = yaml.safe_load((REPO / "config/portal.yaml").read_text())["workspaces"]
    backends = yaml.safe_load((REPO / "config/backends.yaml").read_text())
    assert sorted(plan) == ["auto-reasoning"]
    wl = plan["auto-reasoning"]
    assert wl["home"] == "reasoning_hard_production" and wl["discovery"] == []
    # every task is no_tools, so the workload declares no tool mode at all
    assert "tool_mode" not in wl, "auto-reasoning"
    arms = wl["arms"]
    assert arms["incumbent"] == portal["auto-reasoning"]["model_hint"]
    assert arms["challengers"] == REGISTERED_CHALLENGERS + PENDING_CHALLENGERS
    served = _served("auto-reasoning", backends)
    limit = portal["auto-reasoning"]["context_limit"]
    for tag in [arms["incumbent"], *REGISTERED_CHALLENGERS]:
        assert tag in served, tag
        assert _window(tag) >= limit, (tag, _window(tag), limit)


def test_the_pending_challenger_tags_are_skipped_until_registered():
    """The K2-Horizon-MoVA and Granite-4.2-30B ctx64k tags do not exist yet:
    TODO(operator) create + register them in backends.yaml (brief I-REASON). Their
    served/window checks are skipped until then, and apply once they exist."""
    backends = yaml.safe_load((REPO / "config/backends.yaml").read_text())
    served = _served("auto-reasoning", backends)
    limit = yaml.safe_load((REPO / "config/portal.yaml").read_text())["workspaces"][
        "auto-reasoning"
    ]["context_limit"]
    missing = [tag for tag in PENDING_CHALLENGERS if tag not in served]
    if missing:
        pytest.skip(
            f"pending challenger tag(s) not yet registered in backends.yaml: {missing} — "
            "TODO operator (WFE_NEW_INSTRUMENTS_BRIEF_V1 I-REASON)"
        )
    for tag in PENDING_CHALLENGERS:
        assert tag in served, tag
        assert _window(tag) >= limit, (tag, _window(tag), limit)


# --------------------------------------------------------------- attainability


def test_attainability_flags_a_missing_given_a_stated_gold_and_gold_drift():
    from tests.wfe.e2e import reasoning_hard_attainability as att

    gen.build()
    portal = yaml.safe_load((REPO / "config/portal.yaml").read_text())["workspaces"]
    built = {t["id"]: _gold(t) for t in TASKS.values()}
    assert all(att.check_task(t, portal, built) == [] for t in TASKS.values())

    truncated = json.loads(json.dumps(TASKS["rh-competition-math-00"]))
    truncated["instruction"] = "How many palindromes? Give the number only."
    assert any("given not stated" in f for f in att.check_task(truncated, portal, built))

    leaked = json.loads(json.dumps(TASKS["rh-competition-math-00"]))
    gold = _gold(leaked)
    leaked["instruction"] += f' The count is JSON {{"answer": "{gold}"}}.'
    assert any("gold not private" in f for f in att.check_task(leaked, portal, built))

    drifted = dict.fromkeys(built, built["rh-competition-math-00"])
    assert any(
        "gold drift" in f for f in att.check_task(TASKS["rh-competition-math-01"], portal, drifted)
    )
