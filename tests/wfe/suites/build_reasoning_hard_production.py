"""Build tests/wfe/suites/reasoning_hard_production.jsonl — the hard-reasoning
suite for auto-reasoning (WFE_NEW_INSTRUMENTS_BRIEF_V1, package I-REASON).

The reasoning/math suite is at its ceiling (96–99 % for every arm), so this suite
raises the lane's floor. Three kinds × 12, 12 on screen (4 per kind), every task
`no_tools` with the same JSON answer contract as reasoning_math_production
(`{"answer": ...}`) and the same two checkers (answer_contains,
answer_after_reasoning — tests/wfe/checkers.py).

- competition-math (12)  real contest items with exact integer answers, all
                         published 2026-02 (post-2026-01): AIME I/II 2026 and
                         HMMT February 2026. Golds are the official answers,
                         cross-checked against the official keys/solutions, and
                         build() additionally asserts each COMPETITION_VERIFIERS
                         recomputation equals the gold before writing.
- grad-science (12)      graduate-level multiple choice written for this suite
                         (GPQA-Diamond style: a non-expert should guess ~25 %).
                         Each gold letter's option states a fact from a standard
                         reference, recorded in PROVENANCE.
- puzzle (12)            seeded multi-step logic (5 runners, five clue types, a
                         unique finishing order forced by brute force over the
                         5! permutations) and combinatorics (six shapes; each
                         gold is computed BOTH by closed formula and by brute
                         force, which must agree).

The instruction never states the gold (test-enforced), every enumerated answer
value is defined in its instruction ("the number only", "the letter only", "the
name only", a three-digit integer), and there are no tool arguments to name. The
hard output cap is the workspace's own predict_limit (16384, applied by the
harness, tests/wfe/runner.py:1278); every chain these tasks need fits far inside.

Contamination note: every competition item was published after 2026-01, so none
of them can be answered from pre-2026 training alone. Each item's source and
licence are recorded in PROVENANCE (the AIME items are © MAA and are reworded
here; the HMMT items are posted publicly at hmmt.org with official solutions;
the science and puzzle items are original to this suite).

    uv run python tests/wfe/suites/build_reasoning_hard_production.py
"""

from __future__ import annotations

import itertools
import json
import math
import random
import re
from collections.abc import Callable
from pathlib import Path

from tests.wfe.suites.build_research_production import Fact

# Item tables live in a data sidecar; a competition entry names its verifier function, which
# build_competition resolves from this module.
_ITEMS = json.loads((Path(__file__).parent / "data" / "reasoning_hard_items.json").read_text())
COMPETITION: list[list] = _ITEMS["COMPETITION"]
SCIENCE: list[list] = _ITEMS["SCIENCE"]
OUT = Path(__file__).with_name("reasoning_hard_production.jsonl")
FORMAT = 'Answer only as JSON {"answer": ...}.'
COUNTS = {"competition-math": 12, "grad-science": 12, "puzzle": 12}
SCREEN = {"competition-math": 4, "grad-science": 4, "puzzle": 4}
LANE = "reasoning"
#: AIME answers are integers 000–999; the suite asks for the padded form so the
#: checker can grade an exact string (the contest's own convention).
AIME_FMT = "a three-digit integer between 000 and 999 (pad with leading zeros, for example 007)"
ORDINALS = {1: "first", 2: "second", 3: "third", 4: "fourth", 5: "fifth"}

DECIDING_FACTS: dict[str, list[Fact]] = {}

#: Golds already used by a built task (reset by build()). Puzzle draws re-seed on
#: a collision; the curated kinds are fixed, so a collision there is an error.
_USED_GOLDS: set[str] = set()


def _pattern(gold: str) -> str:
    """The answer in its JSON field. A padded AIME gold ("062") also accepts the unpadded
    integer (62): the instruction still asks for padding, but the value is what is graded."""
    alt = f"(?:{gold}|{int(gold)})" if re.fullmatch(r"0\d\d", gold) else re.escape(gold)
    return rf'"answer"\s*:\s*"?{alt}"?(?![\w.-])'


def _answer(gold: str) -> str:
    return json.dumps({"answer": gold})


def _phrase(imperative: bool, question: str, command: str) -> str:
    return command if imperative else question


# --------------------------------------------------------------- curated content
#
# Each entry's gold is the OFFICIAL answer (MAA answer key / HMMT official
# solutions); the verifier recomputes it independently and build() asserts
# equality, so a transcription error can never reach the suite.


def _verify_aime_i_p2() -> str:
    """Palindromes, base 10, no zero digit, digit sum 13 (DP over half strings)."""
    memo: dict[tuple[int, int], int] = {}

    def half(m: int, s: int) -> int:
        if (m, s) in memo:
            return memo[(m, s)]
        if m == 0:
            return 1 if s == 0 else 0
        if s <= 0:
            return 0
        memo[(m, s)] = sum(half(m - 1, s - d) for d in range(1, 10) if s - d >= 0)
        return memo[(m, s)]

    total = 0
    for c in range(1, 10):
        s, rem = divmod(13 - c, 2)
        if rem:
            continue  # an even-length palindrome has an even digit sum
        total += sum(half(m, s) for m in range(1, 7))
    return str(total)


def _verify_aime_i_p7() -> str:
    """Permutations of {1..6} whose sixth power is the identity (order | 6)."""
    count = 0
    for perm in itertools.permutations(range(6)):
        seen: set[int] = set()
        order = 1
        for i in range(6):
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
    return str(count)


def _verify_aime_i_p8() -> str:
    """Divisors of 17017^17 (17017 = 7·11·13·17) congruent to 5 mod 12, N mod 1000."""
    n = 0
    for a in range(18):
        for b in range(18):
            for c in range(18):
                for d in range(18):
                    v = pow(7, a, 12) * pow(11, b, 12) % 12
                    v = v * pow(13, c, 12) % 12
                    v = v * pow(17, d, 12) % 12
                    if v == 5:
                        n += 1
    return str(n % 1000)


def _verify_aime_i_p9() -> str:
    """Die stickers: P(exactly one blank face | stickers 2, 4, 6 all visible),
    m + n for p = m/n. Exact enumeration of the 6^6 roll sequences."""
    num = den = 0
    for rolls in itertools.product(range(6), repeat=6):
        top = [0] * 6  # face f -> highest sticker index covering it (1-based)
        for i, f in enumerate(rolls, start=1):
            top[f] = i
        if not all(top[rolls[e - 1]] == e for e in (2, 4, 6)):
            continue
        den += 1
        if sum(1 for s in top if s == 0) == 1:
            num += 1
    g = math.gcd(num, den)
    return str(num // g + den // g)


def _verify_aime_ii_p1() -> str:
    """Arithmetic sequences, first term 4, containing 24 and 34: d | gcd(20, 30)."""
    return str(sum(4 + 9 * d for d in (1, 2, 5, 10)))


def _verify_aime_ii_p4() -> str:
    """n < 1000 reinterpreted in base (greatest digit + 1) equals itself."""

    def f(n: int) -> int:
        s = str(n)
        b = max(int(ch) for ch in s) + 1
        return sum(int(ch) * b**i for i, ch in enumerate(reversed(s)))

    return str(sum(1 for n in range(1, 1000) if f(n) == n))


def _verify_aime_ii_p5() -> str:
    """Urn: P(4 red of 7) == P(5 red of 7); sum of the five least n."""
    ns = []
    for n in range(14, 500):
        for r in range(7, n - 6):
            if math.comb(r, 4) * math.comb(n - r, 3) == math.comb(r, 5) * math.comb(n - r, 2):
                ns.append(n)
                break
    return str(sum(ns[:5]))


def _verify_aime_ii_p15() -> str:
    """7-tuples over {1,2,3}: both the sum and the cyclic triple-sum ≡ 0 mod 3."""
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
    return str(count)


def _verify_hmmt_algnt2() -> str:
    """Second smallest multiple of 101 whose decimal form contains 2026."""
    found = []
    for n in range(101, 2_000_000, 101):
        if "2026" in str(n):
            found.append(n)
            if len(found) == 2:
                break
    return str(found[1])


def _verify_hmmt_algnt5() -> str:
    """Largest n dividing (⌊√n⌋)!^(n!) + 450. Candidate set per the official
    solution's characterisation: n | 450, or n = d·p with d | 450 and p a prime
    divisor of 451 = 11·41 with d < p. Each candidate is checked directly."""
    k = 450
    candidates = {n for n in range(1, k + 1) if k % n == 0}
    for p in (11, 41):
        for d in range(1, p):
            if k % d == 0:
                candidates.add(d * p)
    best = 0
    for n in sorted(candidates):
        base = math.factorial(math.isqrt(n)) % n
        if pow(base, math.factorial(n), n) == (-k) % n:
            best = max(best, n)
    # completeness sweep: no n past the candidate set can win
    for n in range(1, 3001):
        base = math.factorial(math.isqrt(n)) % n
        assert pow(base, math.factorial(n), n) != (-k) % n or n <= best, n
    return str(best)


def _verify_hmmt_guts14() -> str:
    """Exactly one pair (m, n) > 1 with m·n = ABCD and C(m, n) = CDAB,
    A, B, C, D distinct nonzero digits; answer m + n."""
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


def _verify_hmmt_guts19() -> str:
    """Smallest n with exactly 10 divisors and n + 1 with exactly 9 divisors."""
    lim = 10**6
    tau = [0] * (lim + 1)
    for i in range(1, lim + 1):
        for j in range(i, lim + 1, i):
            tau[j] += 1
    return str(next(n for n in range(1, lim) if tau[n] == 10 and tau[n + 1] == 9))


#: id -> (question, format phrase, gold, verifier, provenance). The verifier
#: recomputes the gold independently of the official answer; build() asserts
#: str(verifier()) == gold.


def _v_well_mean_x() -> str:
    """<x> for (phi1 + phi2)/sqrt(2): L/2 + <phi1|x|phi2> (cross term −16/(9π²))."""
    return f"{0.5 - 16 / (9 * math.pi**2):.3f} L"


def _v_schottky() -> str:
    best = max(
        x * x * math.exp(x) / (1 + math.exp(x)) ** 2 for x in (i / 1000 for i in range(1, 8000))
    )
    return f"{best:.3f}"


def _v_threshold() -> str:
    mp, mpi = 938.27, 134.98
    return f"{2 * mpi + mpi**2 / (2 * mp):.1f} MeV"


def _v_xlinked() -> str:
    prior, like_c, like_n = 0.5, 0.5**3, 1.0
    return f"{100 * prior * like_c / (prior * like_c + (1 - prior) * like_n):.1f}%"


def _v_compton() -> str:
    lam, lam_c, hc = 0.0711, 2.4263e-3, 1239.84
    return f"{(hc / lam - hc / (lam + lam_c)) / 1000:.3f} keV"


def _v_bateman() -> str:
    l1, l2 = math.log(2) / 10.0, math.log(2) / 2.0
    return f"{math.log(l2 / l1) / (l2 - l1):.2f} h"


def _v_competitive() -> str:
    vmax, km, s, i, ki = 100.0, 2.0, 4.0, 10.0, 5.0
    return f"{vmax * s / (km * (1 + i / ki) + s):.1f} μmol/min"


def _v_pentanetriol() -> str:
    """Orbits of the eight Fischer labelings (a, b, c) under the 180° rotation
    (a, b, c) -> (-c, -b, -a)."""
    seen: set[tuple[int, int, int]] = set()
    orbits = 0
    for a, b, c in itertools.product((1, -1), repeat=3):
        if (a, b, c) in seen:
            continue
        orbits += 1
        seen |= {(a, b, c), (-c, -b, -a)}
    return str(orbits)


def _v_bond_length() -> str:
    h, c, u = 6.62607e-34, 2.99792e10, 1.66054e-27
    mu = 12.000 * 15.995 / (12.000 + 15.995) * u
    b = 3.845 / 2
    return f"{math.sqrt(h / (8 * math.pi**2 * c * mu * b)) * 1e10:.2f} Å"


def _v_d2_terms() -> str:
    """Peel LS terms off the 45 microstates of two equivalent d electrons."""
    orbitals = [(ml, ms) for ml in range(-2, 3) for ms in (1, -1)]
    table: dict[tuple[int, int], int] = {}
    for (m1, s1), (m2, s2) in itertools.combinations(orbitals, 2):
        key = ((m1 + m2), (s1 + s2) // 2)  # M_L, M_S (M_S in units of 1/2 -> integers 1, 0, -1)
        table[key] = table.get(key, 0) + 1
    terms = 0
    while any(table.values()):
        ml_top = max(ml for (ml, ms), n in table.items() if n)
        ms_top = max(ms for (ml, ms), n in table.items() if n and ml == ml_top)
        terms += 1
        for ml in range(-ml_top, ml_top + 1):
            for ms in range(-ms_top, ms_top + 1):
                table[(ml, ms)] -= 1
    return str(terms)


def _v_delta_shift() -> str:
    """First-order shift of the n = 2 well state under V0 δ(x − L/2), in units of V0/L."""
    shift = 2 * math.sin(2 * math.pi * 0.5) ** 2
    return "0" if abs(shift) < 1e-12 else f"{shift:g}V₀/L"


def _v_boyle() -> str:
    return f"{27 / 8 * 150.0:.0f} K"


#: id -> the correct option string, computed (never typed): build() asserts the option at the
#: gold letter equals it, so a mislettered or mistyped gold cannot reach the suite.
SCIENCE_VERIFY: dict[str, Callable[[], str]] = {
    "rh-grad-science-00": _v_well_mean_x,
    "rh-grad-science-01": _v_schottky,
    "rh-grad-science-02": _v_threshold,
    "rh-grad-science-03": _v_xlinked,
    "rh-grad-science-04": _v_compton,
    "rh-grad-science-05": _v_bateman,
    "rh-grad-science-06": _v_competitive,
    "rh-grad-science-07": _v_pentanetriol,
    "rh-grad-science-08": _v_bond_length,
    "rh-grad-science-09": _v_d2_terms,
    "rh-grad-science-10": _v_delta_shift,
    "rh-grad-science-11": _v_boyle,
}

PROVENANCE: dict[str, dict] = {tid: p for tid, *_rest, p in COMPETITION}
PROVENANCE.update({tid: p for tid, *_rest, p in SCIENCE})
for n in range(COUNTS["puzzle"]):
    PROVENANCE[f"rh-puzzle-{n:02d}"] = {
        "source": "generated by this suite's builder from seeded values (multi-step logic or "
        "combinatorics puzzle)",
        "licence": "original (Portal 5)",
    }


# ---------------------------------------------------------------- puzzle: logic


_LOGIC_NAMES = [
    "Vellisa",
    "Ondrey",
    "Sarait",
    "Mireau",
    "Kestrel",
    "Tobren",
    "Ilsabet",
    "Corvane",
    "Halvard",
    "Otteline",
    "Perrine",
    "Quillan",
    "Roderic",
    "Serafina",
    "Brannoch",
    "Fenwick",
]
ASKED_POSITION = (2, 3, 4, 1, 5)  # cycled across the six logic puzzles


Clue = tuple[str, Callable[[dict[str, int]], bool]]


def _immediately_before(a: str, b: str) -> Clue:
    return (f"{a} finished immediately before {b}.", lambda p, a=a, b=b: p[a] + 1 == p[b])


def _somewhere_ahead(a: str, b: str) -> Clue:
    return (f"{a} finished somewhere ahead of {b}.", lambda p, a=a, b=b: p[a] < p[b])


def _exactly_two_ahead(a: str, b: str) -> Clue:
    return (
        f"{a} finished exactly two positions ahead of {b}.",
        lambda p, a=a, b=b: p[a] == p[b] - 2,  # position 1 is first: "ahead" is smaller
    )


def _adjacent(a: str, b: str) -> Clue:
    return (
        f"{a} and {b} finished in adjacent positions.",
        lambda p, a=a, b=b: abs(p[a] - p[b]) == 1,
    )


def _not_position(a: str, p: int) -> Clue:
    return (f"{a} did not finish {ORDINALS[p]}.", lambda q, a=a, p=p: q[a] != p)


def _solutions(names: list[str], clues: list[Clue]) -> list[dict[str, int]]:
    """Every finishing order that satisfies every clue (5! = 120 candidates)."""
    out = []
    for perm in itertools.permutations(names):
        pos = {n: i + 1 for i, n in enumerate(perm)}
        if all(keep(pos) for _, keep in clues):
            out.append(pos)
    return out


def logic_case(n: int) -> tuple[list[str], list[str], int, str]:
    """(names, clue sentences, asked position, gold name) with a UNIQUE solution and
    a gold name no earlier task has taken (the drawer re-seeds under the fixed task
    seed until both hold, so the build stays deterministic)."""
    r = random.Random(7300 + n)
    asked = ASKED_POSITION[n % len(ASKED_POSITION)]
    while True:
        names = sorted(r.sample(_LOGIC_NAMES, 5))
        order = r.sample(names, 5)
        truth = {name: i + 1 for i, name in enumerate(order)}
        gold = next(name for name, p in truth.items() if p == asked)
        if gold not in _USED_GOLDS:
            break
    _USED_GOLDS.add(gold)
    pool: list[Clue] = []
    for a, b in itertools.permutations(names, 2):
        pool.append(_immediately_before(a, b))
        pool.append(_somewhere_ahead(a, b))
        pool.append(_exactly_two_ahead(a, b))
    for a, b in itertools.combinations(names, 2):
        pool.append(_adjacent(a, b))
    for a in names:
        for p in range(1, 6):
            if truth[a] != p:
                pool.append(_not_position(a, p))
    # Only clues that are TRUE of the generated order may be told; a false clue
    # would exclude the very order the gold was computed from.
    pool = [c for c in pool if c[1](truth)]
    r.shuffle(pool)
    clues: list[Clue] = []
    best: list[dict[str, int]] = _solutions(names, clues)
    for clue in pool:
        if len(best) == 1:
            break
        smaller = _solutions(names, clues + [clue])
        if len(smaller) < len(best):
            clues.append(clue)
            best = smaller
    if len(best) != 1 or best[0] != truth:
        raise RuntimeError(f"rh-puzzle-{n:02d}: clues admit {len(best)} solutions")
    return names, [text for text, _ in clues], asked, gold


# ---------------------------------------------------------------- puzzle: combinatorics


def _phi(x: int) -> int:
    return sum(1 for k in range(1, x + 1) if math.gcd(k, x) == 1)


def _combo_circular(r: random.Random) -> tuple[str, str, str]:
    """k of n round-table seats, no two adjacent (formula vs brute force)."""
    seats, k = r.randint(7, 10), r.randint(2, 3)
    formula = seats * math.comb(seats - k, k) // (seats - k)
    brute = sum(
        1
        for c in itertools.combinations(range(seats), k)
        if all((y - x) % seats not in (1, seats - 1) for x, y in itertools.combinations(c, 2))
    )
    assert formula == brute, (seats, k, formula, brute)
    question = (
        f"{seats} people sit at a round table with {seats} seats. How many ways can {k} seats "
        f"be chosen so that no two chosen seats are adjacent around the table?"
    )
    return question, "the number only", str(formula)


def _combo_row(r: random.Random) -> tuple[str, str, str]:
    """k of n row seats, no two adjacent (formula vs brute force)."""
    seats, k = r.randint(8, 12), r.randint(2, 4)
    formula = math.comb(seats - k + 1, k)
    brute = sum(
        1
        for c in itertools.combinations(range(seats), k)
        if all(b - a != 1 for a, b in zip(c, c[1:], strict=False))
    )
    assert formula == brute, (seats, k, formula, brute)
    question = (
        f"A row has {seats} seats. How many ways can {k} seats be chosen so that no two chosen "
        f"seats are adjacent?"
    )
    return question, "the number only", str(formula)


def _combo_quadruples(r: random.Random) -> tuple[str, str, str]:
    """Bounded positive integer solutions x1+x2+x3+x4 = s, 1 <= xi <= b
    (inclusion-exclusion vs brute force)."""
    s, b = r.randint(10, 16), r.randint(5, 7)
    formula = sum(
        (-1) ** j * math.comb(4, j) * math.comb(s - 1 - j * b, 3)
        for j in range(5)
        if s - 1 - j * b >= 3
    )
    brute = sum(1 for xs in itertools.product(range(1, b + 1), repeat=4) if sum(xs) == s)
    assert formula == brute, (s, b, formula, brute)
    question = (
        f"How many quadruples (x1, x2, x3, x4) of integers satisfy x1 + x2 + x3 + x4 = {s} "
        f"and 1 ≤ xi ≤ {b} for each i?"
    )
    return question, "the number only", str(formula)


def _combo_derangements(r: random.Random) -> tuple[str, str, str]:
    """Derangements of n letters (recurrence vs brute force)."""
    n = r.randint(5, 7)
    d0, d1 = 1, 0
    for i in range(2, n + 1):
        d0, d1 = d1, (i - 1) * (d0 + d1)
    formula = d1 if n else d0
    brute = sum(
        1 for perm in itertools.permutations(range(n)) if all(perm[i] != i for i in range(n))
    )
    assert formula == brute, (n, formula, brute)
    question = (
        f"{n} letters are addressed to {n} different envelopes. In how many ways can the "
        f"letters be placed one per envelope so that no letter ends up in its own envelope?"
    )
    return question, "the number only", str(formula)


def _combo_grid(r: random.Random) -> tuple[str, str, str]:
    """East/south lattice paths on a w x d grid avoiding one interior point
    (complement count vs a walk DP)."""
    w, d = r.randint(4, 6), r.randint(4, 6)
    bx, by = r.randint(1, w - 1), r.randint(1, d - 1)
    total = math.comb(w + d, w)
    through = math.comb(bx + by, bx) * math.comb(w + d - bx - by, w - bx)
    formula = total - through
    grid = [[0] * (w + 1) for _ in range(d + 1)]
    grid[0][0] = 1
    for i in range(d + 1):
        for j in range(w + 1):
            if (i, j) == (0, 0) or (i == by and j == bx):
                continue
            grid[i][j] = (grid[i - 1][j] if i else 0) + (grid[i][j - 1] if j else 0)
    assert formula == grid[d][w], (w, d, bx, by, formula, grid[d][w])
    question = (
        f"A grid is {w} units wide and {d} units tall. A walker starts at the north-west "
        f"corner and takes unit steps, only east or south, toward the south-east corner. How "
        f"many such paths avoid the interior point {bx} units east and {by} units south of the "
        f"start?"
    )
    return question, "the number only", str(formula)


def _combo_necklaces(r: random.Random) -> tuple[str, str, str]:
    """Binary necklaces of n beads counted up to rotation (Burnside vs orbits)."""
    n = r.randint(5, 9)
    formula = sum(_phi(div) * 2 ** (n // div) for div in range(1, n + 1) if n % div == 0) // n
    seen: set[str] = set()
    brute = 0
    for bits in itertools.product("RB", repeat=n):
        s = "".join(bits)
        if s in seen:
            continue
        brute += 1
        for k in range(n):
            seen.add(s[k:] + s[:k])
    assert formula == brute, (n, formula, brute)
    question = (
        f"How many different necklaces with {n} beads can be strung from red and blue beads, "
        f"where two necklaces count as the same if one is a rotation of the other?"
    )
    return question, "the number only", str(formula)


_COMBO_SHAPES = (
    _combo_circular,
    _combo_row,
    _combo_quadruples,
    _combo_derangements,
    _combo_grid,
    _combo_necklaces,
)


def combinatorics_case(n: int) -> tuple[str, str, str]:
    """(question, format phrase, gold) for puzzle task n (the shape cycles with the
    index). Every gold is computed BOTH by closed formula and by brute-force
    enumeration, which must agree — an exact count, never a hand-written value."""
    return _COMBO_SHAPES[n % len(_COMBO_SHAPES)](random.Random(7400 + n))


# ---------------------------------------------------------------- assembly


def _givens(tid: str, facts: list[tuple[str, str]]) -> list[Fact]:
    """One deciding fact per stated given; `tool` is empty because the instruction
    itself is the only source a no_tools task has (the attainability check reads
    them from the instruction, not from a tool output)."""
    out = [Fact("", {}, re.escape(given), why) for given, why in facts]
    DECIDING_FACTS[tid] = out
    return out


def _task(tid: str, kind: str, n: int, ins: str, gold: str, givens: list[tuple[str, str]]) -> dict:
    checkers = [
        {"type": "answer_contains", "patterns": [_pattern(gold)]},
        {"type": "answer_after_reasoning", "patterns": [_pattern(gold)]},
    ]
    t = {
        "id": tid,
        "kind": kind,
        "lane": LANE,
        "agentic": False,
        "screen": n < SCREEN[kind],
        "instruction": ins,
        "requires_tools": [],
        "checkers": checkers,
        "controls": {
            "pass": [{"answer": _answer(gold), "tool_calls": []}],
            # A no_tools task has no trace to withhold, so the failing controls are a
            # wrong answer — and the right answer buried inside the reasoning block,
            # which answer_after_reasoning exists to fail.
            "fail": [
                {"answer": _answer("wrong-value"), "tool_calls": []},
                {"answer": f"<think>{_answer(gold)}</think>", "tool_calls": []},
            ],
        },
        "no_tools": True,
    }
    _givens(tid, givens)
    return t


def build_competition(entry: list, n: int) -> dict:
    tid, question, fmt, gold, verifier_name, provenance = entry
    computed = globals()[verifier_name]()
    if int(computed) != int(gold):
        raise RuntimeError(f"{tid}: verifier computed {computed}, table says {gold}")
    if gold in _USED_GOLDS:
        raise RuntimeError(f"{tid}: gold {gold} already used")
    _USED_GOLDS.add(gold)
    ins = _phrase(
        n % 3 == 0,
        f"{question} Give {fmt}. {FORMAT}",
        f"Work this out: {question} Give {fmt}. {FORMAT}",
    )
    numbers = re.findall(r"\d+", question)
    givens = [(v, f"given {i + 1} of the problem statement") for i, v in enumerate(numbers)]
    return _task(tid, "competition-math", n, ins, gold, givens)


def build_science(entry: list, n: int) -> dict:
    tid, question, options, gold, provenance = entry
    if gold not in "ABCD" or len(options) != 4 or len(set(options)) != 4:
        raise RuntimeError(f"{tid}: malformed options or gold letter {gold!r}")
    computed = SCIENCE_VERIFY[tid]()
    if options["ABCD".index(gold)] != computed:
        raise RuntimeError(
            f"{tid}: option {gold} is {options['ABCD'.index(gold)]!r}, computed {computed!r}"
        )
    letters = "ABCD"
    body = "\n".join(f"({letter}) {text}" for letter, text in zip(letters, options, strict=True))
    ins = _phrase(
        n % 3 == 0,
        (
            f"{question}\nThe options are:\n{body}\nAnswer with the letter of the correct option "
            f"only. {FORMAT}"
        ),
        (
            f"Solve it: {question}\nThe options are:\n{body}\nAnswer with the letter of the "
            f"correct option only. {FORMAT}"
        ),
    )
    givens = [
        (f"({letter}) {text}", f"option {letter}")
        for letter, text in zip(letters, options, strict=True)
    ]
    givens.append((question, "the question's premise"))
    return _task(tid, "grad-science", n, ins, gold, givens)


def build_logic(n: int) -> dict:
    names, clues, asked, gold = logic_case(n)
    tid = f"rh-puzzle-{n:02d}"
    roster = f"{', '.join(names[:-1])} and {names[-1]}"
    body = "\n".join(f"- {c}" for c in clues)
    ins = _phrase(
        n % 3 == 0,
        (
            f"Five runners — {roster} — finished a race with no ties, in positions 1 (first) to "
            f"5 (fifth). The clues are:\n{body}\nWho finished {ORDINALS[asked]}? Give the name "
            f"only. {FORMAT}"
        ),
        (
            f"Determine the finishing order of five runners — {roster} — from the clues, positions "
            f"1 (first) to 5 (fifth), no ties:\n{body}\nThen state who finished {ORDINALS[asked]}. "
            f"Give the name only. {FORMAT}"
        ),
    )
    givens = [(c, f"clue: {c}") for c in clues]
    givens.append((roster, "the five runners named"))
    return _task(tid, "puzzle", n, ins, gold, givens)


def build_combinatorics(n: int) -> dict:
    for attempt in range(1000):
        question, fmt, gold = combinatorics_case(n + attempt * 1000)
        if gold not in _USED_GOLDS:
            break
    else:
        raise RuntimeError(f"rh-puzzle-{n:02d}: no unique gold found")
    _USED_GOLDS.add(gold)
    tid = f"rh-puzzle-{n:02d}"
    numbers = re.findall(r"\d+", question)
    givens = [(v, f"given {i + 1} of the puzzle") for i, v in enumerate(numbers)]
    ins = _phrase(
        n % 3 == 0,
        f"{question} Give {fmt}. {FORMAT}",
        f"Count it out: {question} Give {fmt}. {FORMAT}",
    )
    return _task(tid, "puzzle", n, ins, gold, givens)


def build() -> list[dict]:
    DECIDING_FACTS.clear()
    _USED_GOLDS.clear()
    tasks: list[dict] = []
    for n, entry in enumerate(COMPETITION):
        tasks.append(build_competition(entry, n))
    for n, entry in enumerate(SCIENCE):
        tasks.append(build_science(entry, n))
    for n in range(12):
        tasks.append(build_logic(n) if n < 6 else build_combinatorics(n))
    # golds: numbers and names must be unique across the suite; the grad-science
    # letter answers repeat by design (only four letters exist).
    scored = [
        json.loads(t["controls"]["pass"][0]["answer"])["answer"]
        for t in tasks
        if t["kind"] != "grad-science"
    ]
    if len(scored) != len(set(scored)):
        dupes = sorted({g for g in scored if scored.count(g) > 1})
        raise RuntimeError(f"duplicate gold answers across the suite: {dupes}")
    for t in tasks:
        if leak := _leaks(t):
            raise RuntimeError(f"{t['id']}: {leak}")
        if (
            t["id"] not in PROVENANCE
            or not PROVENANCE[t["id"]].get("source")
            or not PROVENANCE[t["id"]].get("licence")
        ):
            raise RuntimeError(f"{t['id']}: provenance (source + licence) missing")
    tasks.sort(key=lambda t: not t["screen"])
    return tasks


def _leaks(t: dict) -> str | None:
    """How the instruction states the gold, if it does. A computed integer must not
    appear at all (padded AIME golds are checked in both forms); a letter must never
    be bound to correctness; a logic-grid runner's NAME must appear (the roster
    names all five), so the leak to forbid there is the direct binding — the asked
    position stated with the gold's name in one sentence."""
    gold = json.loads(t["controls"]["pass"][0]["answer"])["answer"]
    ins = t["instruction"]
    if re.fullmatch(r"\d+", gold):
        if re.search(rf"(?<!\d){gold}(?!\d)", ins):
            return f"the gold {gold!r} is stated in the instruction"
        if re.fullmatch(r"0\d\d", gold) and re.search(rf"(?<!\d){int(gold)}(?!\d)", ins):
            return f"the gold {int(gold)} is stated in the instruction"
        return None
    if gold in "ABCD":
        for binding in (
            f"answer is {gold}",
            f"answer: {gold}",
            f"{gold} is correct",
            f"correct answer is {gold}",
            f"option {gold} is correct",
            f"the correct option is {gold}",
        ):
            if re.search(re.escape(binding), ins, re.I):
                return f"the binding {binding!r} is stated"
        return None
    asked = ASKED_POSITION[int(t["id"].rsplit("-", 1)[1]) % len(ASKED_POSITION)]
    binding = f"{gold} finished {ORDINALS[asked]}"
    return f"the binding {binding!r} is stated" if binding in ins else None


def main() -> None:
    tasks = build()
    OUT.write_text("".join(json.dumps(t) + "\n" for t in tasks))
    print(f"wrote {OUT.name}: {len(tasks)} tasks, {sum(t['screen'] for t in tasks)} screen")


if __name__ == "__main__":
    main()
