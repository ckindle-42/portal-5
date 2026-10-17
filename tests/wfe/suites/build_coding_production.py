"""Build tests/wfe/suites/coding_production.jsonl and its hidden graded suites, auto-coding's
production suite: 36 tasks, 12 in the screen tier, in the harness's sandbox tool mode
(file_read / file_write / pytest_run), the one family that may run there.

Each task seeds a small repo in the row's sandbox. The gold is hidden tests the model never
sees (`hidden_pytest`, committed under tests/wfe/graded/cp_*), whose expected values are computed
here by running the reference solution, never written by hand. `immutable` protects the visible
test a fix or refactor task ships. Four kinds:

- implement (12)  a function with an exact spec and its edge cases written out;
- fix (10)        seeded code fails a visible test; fix it without touching the test;
- refactor (6)    restructure to a stated shape while the visible tests stay green; the hidden
                  tests include the new interface;
- read (8)        an exact question about seeded code (a return value, an exception type),
                  graded on the answer and on a file_read of that file.

The reference solutions live in this module only: no tool reaches them (a test holds the seeded
files and instructions free of every distinctive reference line).

    uv run python tests/wfe/suites/build_coding_production.py
"""

from __future__ import annotations

import hashlib
import json
import re
import textwrap
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "coding_production.jsonl"
GRADED = HERE.parent / "graded"
DONE = "TASK COMPLETE"
COUNTS = {"implement": 12, "fix": 10, "refactor": 6, "read": 8}
SCREEN = {"implement": 4, "fix": 3, "refactor": 2, "read": 3}
FORMAT = 'Answer only as JSON {"answer": ...}.'

#: task id -> {file: source} that passes the task's hidden tests (the attainability proof)
REFERENCES: dict[str, dict[str, str]] = {}


def d(src: str) -> str:
    return textwrap.dedent(src).lstrip("\n")


# --------------------------------------------------------------------------- implement

#: slug, module, function, spec sentence(s), reference source, cases (argument tuples)
IMPLEMENT = [
    (
        "runs",
        "runs",
        "squeeze_runs",
        "takes a string and returns a list of (character, count) tuples, one per run of identical "
        "consecutive characters, in order. An empty string gives an empty list. The comparison is "
        "case-sensitive.",
        """
        def squeeze_runs(text):
            out = []
            for ch in text:
                if out and out[-1][0] == ch:
                    out[-1] = (ch, out[-1][1] + 1)
                else:
                    out.append((ch, 1))
            return out
        """,
        [("",), ("aaabcc",), ("aAa",), ("z",), ("112211",)],
    ),
    (
        "spans",
        "spans",
        "join_spans",
        "takes a list of (start, end) integer pairs (start <= end, both ends inclusive) and merges "
        "spans that overlap or touch (a span ending at 4 and one starting at 5 touch). It returns "
        "the merged spans as a list of tuples sorted by start. An empty list gives an empty list. "
        "The input list must not be modified.",
        """
        def join_spans(spans):
            out = []
            for s, e in sorted(spans):
                if out and s <= out[-1][1] + 1:
                    out[-1] = (out[-1][0], max(out[-1][1], e))
                else:
                    out.append((s, e))
            return out
        """,
        [
            ([],),
            ([(1, 3), (2, 6), (8, 10), (15, 18)],),
            ([(1, 4), (5, 6)],),
            ([(5, 5), (1, 2), (3, 3)],),
            ([(1, 10), (2, 3)],),
        ],
    ),
    (
        "clock",
        "clock",
        "parse_span_text",
        "takes text such as '1h30m15s', '45m' or '90s' and returns the total number of seconds as "
        "an int. The units are h, m and s, in that order, each at most once, each preceded by a "
        "non-negative integer. It raises ValueError for an empty string, an unknown unit, units "
        "out of order, a repeated unit, or a number with no unit.",
        """
        import re

        def parse_span_text(text):
            m = re.fullmatch(r"(?:(\\d+)h)?(?:(\\d+)m)?(?:(\\d+)s)?", text)
            if not text or m is None:
                raise ValueError(text)
            h, mi, s = (int(g) if g else 0 for g in m.groups())
            return h * 3600 + mi * 60 + s
        """,
        [
            ("1h30m15s",),
            ("45m",),
            ("90s",),
            ("2h",),
            ("",),
            ("5x",),
            ("30m1h",),
            ("1h1h",),
            ("15",),
        ],
    ),
    (
        "grid",
        "grid",
        "spin_grid",
        "takes a rectangular list of equal-length lists and returns a new list of lists rotated 90 "
        "degrees clockwise. An empty list gives an empty list. The input must not be modified.",
        """
        def spin_grid(rows):
            return [list(r) for r in zip(*rows[::-1])]
        """,
        [([],), ([[1, 2, 3], [4, 5, 6]],), ([[1]],), ([[1, 2], [3, 4], [5, 6]],), ([["a", "b"]],)],
    ),
    (
        "fold",
        "fold",
        "fold_lines",
        "takes text and a width and packs the whitespace-separated words greedily into lines of at "
        "most width characters, joining the words on a line with a single space. A word longer than "
        "width gets a line of its own, unbroken. It returns the list of lines; text with no words "
        "gives an empty list.",
        """
        def fold_lines(text, width):
            lines, cur = [], ""
            for w in text.split():
                if not cur:
                    cur = w
                elif len(cur) + 1 + len(w) <= width:
                    cur += " " + w
                else:
                    lines.append(cur)
                    cur = w
            if cur:
                lines.append(cur)
            return lines
        """,
        [
            ("the quick brown fox jumps over", 10),
            ("", 5),
            ("extraordinarily long word", 8),
            ("a b c", 1),
            ("aa bb cc dd", 5),
            ("  spaced   out  ", 20),
        ],
    ),
    (
        "common",
        "common",
        "most_common",
        "takes a list of hashable items and an integer k and returns the k most frequent items, "
        "most frequent first. Items with equal counts keep the order in which they first appeared "
        "in the input. If k is larger than the number of distinct items, return them all; if k is "
        "zero or negative, return an empty list.",
        """
        def most_common(items, k):
            if k <= 0:
                return []
            counts, first = {}, {}
            for i, x in enumerate(items):
                counts[x] = counts.get(x, 0) + 1
                first.setdefault(x, i)
            return sorted(counts, key=lambda x: (-counts[x], first[x]))[:k]
        """,
        [
            (["b", "a", "b", "c", "a", "d"], 2),
            ([], 3),
            ([1, 1, 2, 2, 3], 5),
            (["x"], 0),
            (list("mississippi"), 3),
            (["q", "r"], -1),
        ],
    ),
    (
        "numeral",
        "numeral",
        "numeral_value",
        "takes an uppercase Roman numeral (I V X L C D M; subtractive forms IV IX XL XC CD CM only) "
        "and returns its value as an int, for values 1 to 3999. It raises ValueError for an empty "
        "string, lowercase letters, or any non-canonical numeral such as IIII, VX or IC.",
        """
        _VALS = [(1000, "M"), (900, "CM"), (500, "D"), (400, "CD"), (100, "C"), (90, "XC"),
                 (50, "L"), (40, "XL"), (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I")]

        def _encode(n):
            out = ""
            for v, sym in _VALS:
                while n >= v:
                    out += sym
                    n -= v
            return out

        def numeral_value(s):
            table = dict(I=1, V=5, X=10, L=50, C=100, D=500, M=1000)
            if not s or any(c not in table for c in s):
                raise ValueError(s)
            total = 0
            for i, c in enumerate(s):
                v = table[c]
                total += -v if i + 1 < len(s) and table[s[i + 1]] > v else v
            if not 1 <= total <= 3999 or _encode(total) != s:
                raise ValueError(s)
            return total
        """,
        [
            ("XIV",),
            ("MCMXCIV",),
            ("III",),
            ("IIII",),
            ("",),
            ("iv",),
            ("VX",),
            ("IC",),
            ("MMMCMXCIX",),
            ("MMMM",),
        ],
    ),
    (
        "nest",
        "nest",
        "nests_ok",
        "takes a string and returns True when every (), [] and {} bracket in it is closed by the "
        "matching kind in the right order, and False otherwise. Characters other than brackets are "
        "ignored. The empty string is True.",
        """
        def nests_ok(text):
            pairs, stack = {")": "(", "]": "[", "}": "{"}, []
            for ch in text:
                if ch in "([{":
                    stack.append(ch)
                elif ch in pairs:
                    if not stack or stack.pop() != pairs[ch]:
                        return False
            return not stack
        """,
        [("",), ("([]{})",), ("([)]",), ("((",), ("a(b)c]",), ("{[()]}x",), (")(",)],
    ),
    (
        "budget",
        "budget",
        "split_by_budget",
        "takes a list of numbers and a limit and splits the list into consecutive groups, order "
        "kept, so that each group's sum is at most limit. A new group starts only when adding the "
        "next number would push the current group's sum over the limit. A single number larger "
        "than the limit forms a group of its own. It returns a list of lists; an empty list gives "
        "an empty list.",
        """
        def split_by_budget(nums, limit):
            groups, cur, total = [], [], 0
            for n in nums:
                if cur and total + n > limit:
                    groups.append(cur)
                    cur, total = [], 0
                cur.append(n)
                total += n
            if cur:
                groups.append(cur)
            return groups
        """,
        [([], 5), ([1, 2, 3, 4, 5], 6), ([9, 1], 5), ([5, 5, 5], 5), ([2, 2, 2, 2], 4), ([1], 1)],
    ),
    (
        "latest",
        "latest",
        "keep_latest",
        "takes a list of dicts and a key name. For each distinct value of row[key] it keeps only the "
        "last row with that value. The result keeps the kept rows in their input order. Rows that "
        "do not contain the key are all kept.",
        """
        def keep_latest(rows, key):
            last = {}
            for i, r in enumerate(rows):
                if key in r:
                    last[r[key]] = i
            return [r for i, r in enumerate(rows) if key not in r or last[r[key]] == i]
        """,
        [
            ([], "id"),
            ([{"id": 1, "v": "a"}, {"id": 2, "v": "b"}, {"id": 1, "v": "c"}], "id"),
            ([{"v": 1}, {"v": 2}], "id"),
            ([{"id": 1}, {"x": 1}, {"id": 1}], "id"),
        ],
    ),
    (
        "rebase",
        "rebase",
        "convert_digits",
        "takes text (a non-negative integer written in base src, digits 0-9 then letters, either "
        "case), src and dst and returns the number written in base dst with uppercase letters and no "
        "leading zeros ('0' for zero). It raises ValueError if a base is outside 2..36, if the text "
        "is empty, or if the text has a digit that is not valid in base src.",
        """
        _D = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"

        def convert_digits(text, src, dst):
            if not (2 <= src <= 36 and 2 <= dst <= 36) or not text:
                raise ValueError(text)
            n = 0
            for c in text.upper():
                dg = _D.find(c)
                if dg < 0 or dg >= src:
                    raise ValueError(text)
                n = n * src + dg
            out = ""
            while n:
                n, r = divmod(n, dst)
                out = _D[r] + out
            return out or "0"
        """,
        [
            ("ff", 16, 2),
            ("0", 10, 2),
            ("zz", 36, 10),
            ("101", 2, 8),
            ("12", 2, 10),
            ("", 10, 2),
            ("9", 10, 37),
            ("00ff", 16, 10),
            ("1010", 2, 16),
        ],
    ),
    (
        "paths",
        "paths",
        "tidy_path",
        "does POSIX-style path normalisation with no filesystem access: it collapses repeated "
        "slashes, drops '.' parts and resolves '..' against the part before it. An absolute path "
        "(leading '/') never goes above '/'. A relative path keeps the leading '..' parts it cannot "
        "resolve. There is no trailing slash except for the root '/'. A relative path that "
        "normalises to nothing is '.'.",
        """
        def tidy_path(p):
            absolute = p.startswith("/")
            parts = []
            for part in p.split("/"):
                if part in ("", "."):
                    continue
                if part == "..":
                    if parts and parts[-1] != "..":
                        parts.pop()
                    elif not absolute:
                        parts.append("..")
                else:
                    parts.append(part)
            body = "/".join(parts)
            return "/" + body if absolute else (body or ".")
        """,
        [
            ("/a/b/../c//d/.",),
            ("a/./b/..",),
            ("../../x",),
            ("/..",),
            ("",),
            ("a/../..",),
            ("/",),
            ("a//b/",),
            ("./",),
        ],
    ),
]

# --------------------------------------------------------------------------- fix

#: slug, module, function, buggy source, fixed source, visible-test cases, extra hidden cases
FIX = [
    (
        "meantop",
        "stats",
        "mean_of_top",
        """
        def mean_of_top(values, n):
            if not values:
                return 0.0
            top = sorted(values)[:n]
            return sum(top) / len(top)
        """,
        """
        def mean_of_top(values, n):
            if not values:
                return 0.0
            top = sorted(values, reverse=True)[:n]
            return sum(top) / len(top)
        """,
        [([1, 5, 3, 9], 2), ([4, 8], 1)],
        [([], 3), ([2, 2, 2], 2), ([10, 0, 5, 7], 3), ([6], 4)],
    ),
    (
        "leap",
        "calendar_util",
        "is_leap_year",
        """
        def is_leap_year(y):
            return y % 4 == 0 and y % 100 != 0
        """,
        """
        def is_leap_year(y):
            return (y % 4 == 0 and y % 100 != 0) or y % 400 == 0
        """,
        [(2024,), (1900,), (2000,)],
        [(2100,), (1600,), (1999,), (2400,)],
    ),
    (
        "tags",
        "tagbag",
        "add_tag",
        """
        def add_tag(tag, tags=[]):
            tags.append(tag)
            return tags
        """,
        """
        def add_tag(tag, tags=None):
            tags = [] if tags is None else tags
            tags.append(tag)
            return tags
        """,
        [("a",), ("b",)],
        [("c", ["x"]), ("d",), ("e", []), ("f",)],
    ),
    (
        "pages",
        "pager",
        "paginate",
        """
        def paginate(items, page, size):
            start = page * size
            return items[start:start + size]
        """,
        """
        def paginate(items, page, size):
            start = (page - 1) * size
            return items[start:start + size]
        """,
        [(list(range(10)), 1, 3), (list(range(10)), 2, 3)],
        [(list(range(10)), 4, 3), (list(range(10)), 5, 3), ([], 1, 3), (list("abcde"), 3, 2)],
    ),
    (
        "pctchange",
        "growth",
        "percent_change",
        """
        def percent_change(old, new):
            if old == 0:
                return None
            return (new - old) * 100 // old
        """,
        """
        def percent_change(old, new):
            if old == 0:
                return None
            return round((new - old) / old * 100, 1)
        """,
        [(3, 4), (200, 250)],
        [(0, 5), (80, 60), (7, 7), (1000, 1)],
    ),
    (
        "prefix",
        "prefix",
        "common_prefix",
        """
        def common_prefix(words):
            if not words:
                return ""
            first = words[0]
            second = words[1] if len(words) > 1 else words[0]
            n = 0
            while n < min(len(first), len(second)) and first[n] == second[n]:
                n += 1
            return first[:n]
        """,
        """
        def common_prefix(words):
            if not words:
                return ""
            n = 0
            while all(n < len(w) for w in words) and len({w[n] for w in words}) == 1:
                n += 1
            return words[0][:n]
        """,
        [(["flower", "flow", "flight"],), (["same", "same"],)],
        [
            ([],),
            (["solo"],),
            (["abc", "abd", "xyz"],),
            (["", "a"],),
            (["interview", "internet", "internal"],),
        ],
    ),
    (
        "slug",
        "slugs",
        "slugify",
        """
        import re

        def slugify(title):
            return re.sub(r"[^a-z0-9]", "-", title.lower())
        """,
        """
        import re

        def slugify(title):
            return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
        """,
        [("Hello,  World!",), ("Plain",)],
        [("  lead and trail  ",), ("a--b",), ("!!!",), ("Rust 2021 Edition",), ("",)],
    ),
    (
        "wordcount",
        "wc",
        "count_words",
        """
        def count_words(text):
            counts = {}
            for w in text.split():
                counts[w] = counts.get(w, 0) + 1
            return counts
        """,
        """
        import re

        def count_words(text):
            counts = {}
            for w in re.findall(r"[a-z0-9']+", text.lower()):
                counts[w] = counts.get(w, 0) + 1
            return counts
        """,
        [("Go go, GO!",), ("one two one",)],
        [("",), ("It's it's, IT'S.",), ("a b a. b? c",), ("42 forty-two 42",)],
    ),
    (
        "due",
        "due",
        "due_in_days",
        """
        from datetime import datetime

        def due_in_days(today, due):
            a = datetime.strptime(today, "%Y-%d-%m")
            b = datetime.strptime(due, "%Y-%d-%m")
            return (b - a).days
        """,
        """
        from datetime import datetime

        def due_in_days(today, due):
            a = datetime.strptime(today, "%Y-%m-%d")
            b = datetime.strptime(due, "%Y-%m-%d")
            return (b - a).days
        """,
        [("2031-03-10", "2031-03-15"), ("2031-03-10", "2031-03-10")],
        [("2031-02-27", "2031-03-02"), ("2031-12-30", "2032-01-02"), ("2031-05-20", "2031-05-01")],
    ),
    (
        "flat",
        "flatten_util",
        "flatten",
        """
        def flatten(nested):
            out = []
            for x in nested:
                if isinstance(x, list):
                    out.extend(x)
                else:
                    out.append(x)
            return out
        """,
        """
        def flatten(nested):
            out = []
            for x in nested:
                if isinstance(x, list):
                    out.extend(flatten(x))
                else:
                    out.append(x)
            return out
        """,
        [([1, [2, [3, [4]]]],), ([[1], [2]],)],
        [([],), ([[], [[]]],), (["ab", ["cd", ["ef"]]],), ([1, [2, 3], 4],)],
    ),
]

# --------------------------------------------------------------------------- refactor

#: slug, module, original, refactored, instruction, visible cases, hidden extra snippets
REFACTOR = [
    (
        "invoice",
        "invoice",
        """
        def total(items, tax_rate, discount):
            \"\"\"items: list of (price_cents, qty). discount and tax_rate are whole percents.\"\"\"
            sub = 0
            for price, qty in items:
                sub += price * qty
            sub = sub - sub * discount // 100
            return sub + sub * tax_rate // 100
        """,
        """
        def subtotal(items):
            return sum(price * qty for price, qty in items)

        def total(items, tax_rate, discount):
            \"\"\"items: list of (price_cents, qty). discount and tax_rate are whole percents.\"\"\"
            sub = subtotal(items)
            sub = sub - sub * discount // 100
            return sub + sub * tax_rate // 100
        """,
        "extract the item-summing loop in total() into a function subtotal(items) that returns the "
        "sum of price * qty over the (price_cents, qty) pairs; total() must behave exactly as before",
        [
            "result = total([(250, 2), (100, 3)], 10, 5)",
            "result = total([], 20, 0)",
            "result = total([(999, 1)], 0, 100)",
        ],
        [
            "result = subtotal([(250, 2), (100, 3)])",
            "result = subtotal([])",
            "result = subtotal([(7, 0), (3, 3)])",
            "result = total([(1000, 2)], 7, 15)",
        ],
    ),
    (
        "money",
        "money",
        """
        def fmt_money(cents):
            sign = "-" if cents < 0 else ""
            cents = abs(cents)
            return f"{sign}${cents // 100}.{cents % 100:02d}"
        """,
        """
        def format_cents(cents):
            sign = "-" if cents < 0 else ""
            cents = abs(cents)
            return f"{sign}${cents // 100}.{cents % 100:02d}"

        def fmt_money(cents):
            return format_cents(cents)
        """,
        "rename fmt_money to format_cents, and keep fmt_money working as a function that returns "
        "exactly what format_cents returns",
        ["result = fmt_money(1234)", "result = fmt_money(-5)", "result = fmt_money(0)"],
        [
            "result = format_cents(1234)",
            "result = format_cents(-5)",
            "result = format_cents(100)",
            "result = fmt_money(99999) == format_cents(99999)",
        ],
    ),
    (
        "orders",
        "orders",
        """
        def process(order):
            errors = []
            if not order.get("id"):
                errors.append("missing id")
            if not order.get("items"):
                errors.append("no items")
            elif any(qty <= 0 for _, qty in order["items"]):
                errors.append("bad quantity")
            if errors:
                return {"ok": False, "errors": errors}
            return {"ok": True, "total": sum(p * q for p, q in order["items"])}
        """,
        """
        def validate_order(order):
            errors = []
            if not order.get("id"):
                errors.append("missing id")
            if not order.get("items"):
                errors.append("no items")
            elif any(qty <= 0 for _, qty in order["items"]):
                errors.append("bad quantity")
            return errors

        def process(order):
            errors = validate_order(order)
            if errors:
                return {"ok": False, "errors": errors}
            return {"ok": True, "total": sum(p * q for p, q in order["items"])}
        """,
        "extract the validation in process() into a function validate_order(order) that returns the "
        "list of error strings (empty when the order is valid); process() must return exactly what "
        "it returns now",
        [
            'result = process({"id": 1, "items": [(5, 2)]})',
            "result = process({})",
            'result = process({"id": 2, "items": [(5, 0)]})',
        ],
        [
            'result = validate_order({"id": 1, "items": [(5, 2)]})',
            "result = validate_order({})",
            'result = validate_order({"items": [(5, -1)]})',
            'result = process({"id": 3, "items": []})',
        ],
    ),
    (
        "ids",
        "ids",
        """
        _n = 0

        def next_id(prefix="id"):
            global _n
            _n += 1
            return f"{prefix}-{_n}"
        """,
        """
        class IdSource:
            def __init__(self, start=0):
                self._n = start

            def next(self, prefix="id"):
                self._n += 1
                return f"{prefix}-{self._n}"

        _default = IdSource()

        def next_id(prefix="id"):
            return _default.next(prefix)
        """,
        "turn the module-level counter into a class IdSource with __init__(self, start=0) and a "
        "method next(self, prefix='id') that returns the same strings next_id returns today, and "
        "keep the module-level next_id(prefix='id') working, backed by one default IdSource",
        ["result = next_id()", 'result = next_id("job")', "result = next_id()"],
        [
            "s = IdSource()\nresult = [s.next(), s.next('x')]",
            "t = IdSource(10)\nresult = t.next('t')",
            "result = next_id('z')",
        ],
    ),
    (
        "rows",
        "rows",
        """
        def parse_line(line):
            fields = [f.strip() for f in line.split(",")]
            if len(fields) != 3:
                raise ValueError(line)
            return {"name": fields[0], "qty": int(fields[1]), "price": float(fields[2])}
        """,
        """
        def split_fields(line):
            fields = [f.strip() for f in line.split(",")]
            if len(fields) != 3:
                raise ValueError(line)
            return fields

        def convert(fields):
            return {"name": fields[0], "qty": int(fields[1]), "price": float(fields[2])}

        def parse_line(line):
            return convert(split_fields(line))
        """,
        "split parse_line into split_fields(line), which returns the three stripped fields and raises "
        "ValueError unless there are exactly three, and convert(fields), which builds the dict; "
        "parse_line must behave exactly as before",
        ['result = parse_line("bolt, 4, 0.25")', 'result = parse_line(" nut ,10,1.5 ")'],
        [
            'result = split_fields(" a , b ,c")',
            'result = convert(["x", "2", "3.5"])',
            'result = parse_line("p,1,2")',
            'result = split_fields("a,b")',
        ],
    ),
    (
        "calc",
        "calc",
        """
        def apply(op, a, b):
            if op == "add":
                return a + b
            elif op == "sub":
                return a - b
            elif op == "mul":
                return a * b
            elif op == "div":
                return a / b
            raise ValueError(op)
        """,
        """
        OPERATIONS = {
            "add": lambda a, b: a + b,
            "sub": lambda a, b: a - b,
            "mul": lambda a, b: a * b,
            "div": lambda a, b: a / b,
        }

        def apply(op, a, b):
            if op not in OPERATIONS:
                raise ValueError(op)
            return OPERATIONS[op](a, b)
        """,
        "replace the if/elif chain in apply() with a module-level dict OPERATIONS that maps each "
        "operation name to a two-argument function; apply() looks the name up and still raises "
        "ValueError for an unknown name",
        [
            'result = apply("add", 2, 3)',
            'result = apply("div", 9, 2)',
            'result = apply("mul", 4, 5)',
        ],
        [
            "result = sorted(OPERATIONS)",
            "result = OPERATIONS['sub'](10, 4)",
            'result = apply("sub", 1, 5)',
            'result = apply("pow", 2, 3)',
            'result = apply("div", 1, 0)',
        ],
    ),
]

# --------------------------------------------------------------------------- read

#: slug, module, source, expression, wording of the call, what it asks
READ = [
    (
        "drift",
        "drift",
        """
        def drift(n):
            total = 0
            for i in range(n):
                if i % 3 == 0:
                    total += i * 2
                else:
                    total -= 1
            return total
        """,
        "drift(10)",
        "the value of drift(10)",
        "value",
    ),
    (
        "bump",
        "bump",
        """
        def make(step):
            count = 0

            def bump():
                nonlocal count
                count += step
                return count

            return bump
        """,
        "(lambda b: [b(), b(), b()][-1])(make(3))",
        "the value returned by the third call b(), where b = make(3) and b() is called three times in a row",
        "value",
    ),
    (
        "stash",
        "stash",
        """
        def stash(x, bag=[]):
            bag.append(x)
            return len(bag)
        """,
        "[stash('p'), stash('q'), stash('r')][-1]",
        "the value of stash('r') when it is called third, after stash('p') and stash('q') were "
        "called in that order in a fresh interpreter",
        "value",
    ),
    (
        "peel",
        "peel",
        """
        def peel(s):
            return s[1:-1][::-1].upper()
        """,
        "peel('portal5')",
        "the value of peel('portal5')",
        "value",
    ),
    (
        "rank",
        "rank",
        """
        def rank(words):
            return sorted(words, key=len)[0]
        """,
        "len(rank(['pear', 'fig', 'plum', 'kiwi', 'date']))",
        "the value of len(rank(['pear', 'fig', 'plum', 'kiwi', 'date']))",
        "value",
    ),
    (
        "depth",
        "depth",
        """
        def depth(n):
            return 0 if n <= 0 else 1 + depth(n // 2)
        """,
        "depth(1000)",
        "the value of depth(1000)",
        "value",
    ),
    (
        "invert",
        "invert",
        """
        def invert(d):
            return {v: k for k, v in d.items()}
        """,
        "len(invert({'a': 10, 'b': 20, 'c': 10}))",
        "the value of len(invert({'a': 10, 'b': 20, 'c': 10}))",
        "value",
    ),
    (
        "ratio",
        "ratio",
        """
        def ratio(a, b):
            return a / (b - 3)
        """,
        "ratio(5, 3)",
        "the exception type that ratio(5, 3) raises (the class name)",
        "exception",
    ),
]


# --------------------------------------------------------------------------- helpers


def run_snippet(namespace: dict, code: str):
    """(value, None) of `result` after exec, or (None, exception type name)."""
    ns = dict(namespace)
    try:
        exec(code, ns)  # noqa: S102 - generator-controlled reference code
    except Exception as e:  # noqa: BLE001
        return None, type(e).__name__
    return ns["result"], None


def snippet(fn: str, args: tuple) -> str:
    return f"result = {fn}({', '.join(map(repr, args))})"


def expected_for(src: str, codes: list[str]) -> list:
    """Run `codes` in order against the reference module; the expected value or a raises marker."""
    ns: dict = {}
    exec(d(src), ns)  # noqa: S102
    out = []
    for code in codes:
        # the snippet runs in a copy, but the functions' globals are `ns`: module-level state
        # (a counter, a mutable default) carries from case to case, as it does in the hidden test
        val, exc = run_snippet(ns, code)
        out.append(("__raises__", exc) if exc else val)
    return out


def hidden_test(tid: str, module: str, src: str, codes: list[str]) -> tuple[str, int]:
    exp = expected_for(src, codes)
    cases = ",\n".join(f"    ({c!r}, {e!r})" for c, e in zip(codes, exp, strict=True))
    text = (
        f'"""Hidden graded suite for {tid}. The model never sees this file and cannot write to the\n'
        f'directory it runs in. Expected values are computed from the reference solution."""\n\n'
        f"import builtins\n\nimport pytest\n\nimport {module} as mod\n\n"
        f"CASES = [\n{cases},\n]\n\n\n"
        f'@pytest.mark.parametrize("code,expected", CASES)\n'
        f"def test_case(code, expected):\n"
        f"    ns = dict(vars(mod))\n"
        f'    if isinstance(expected, tuple) and expected[:1] == ("__raises__",):\n'
        f"        with pytest.raises(getattr(builtins, expected[1])):\n"
        f"            exec(code, ns)\n"
        f"    else:\n"
        f"        exec(code, ns)\n"
        f'        assert ns["result"] == expected\n'
    )
    return text, len(codes)


def formatted(text: str) -> str:
    """The text as `ruff` (import order, then format) leaves it, so a committed hidden test is
    byte-stable under the repo's tooling (generated reprs use single quotes and long lines)."""
    import subprocess
    import sys

    for args in (
        ["check", "--select", "I", "--fix", "--quiet", "--stdin-filename", "t.py", "-"],
        ["format", "-"],
    ):
        run = subprocess.run(
            [sys.executable, "-m", "ruff", *args], input=text, capture_output=True, text=True
        )
        if run.stdout:
            text = run.stdout
    return text


def write_graded(name: str, module: str, text: str) -> None:
    d_ = GRADED / name
    d_.mkdir(parents=True, exist_ok=True)
    (d_ / f"test_{module}.py").write_text(formatted(text))


def sha16(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def visible_test(module: str, fn: str, codes: list[str], src: str) -> str:
    """The visible test a fix/refactor task ships: plain asserts on values from the reference."""
    exp = expected_for(src, codes)
    lines = [f"from {module} import *  # noqa: F403\n\n"]
    for i, (c, e) in enumerate(zip(codes, exp, strict=True)):
        body = c.replace("\n", "\n    ")
        lines.append(f"def test_case_{i}():\n    {body}\n    assert result == {e!r}\n\n")
    return "".join(lines).rstrip() + "\n"


def task(tid, kind, n, ins, checkers, seed=None, requires=("file_write", "pytest_run")) -> dict:
    t = {
        "id": tid,
        "kind": kind,
        "lane": "coding",
        "agentic": True,
        "screen": n < SCREEN[kind],
        "instruction": ins,
        "completion_signal": DONE,
        "repo_read": False,
        "requires_tools": sorted(requires),
        "checkers": checkers,
    }
    if seed:
        t["seed"] = seed
    return t


# --------------------------------------------------------------------------- builders


def build_implement(n: int) -> dict:
    slug, module, fn, spec, src, cases = IMPLEMENT[n]
    tid = f"code-implement-{n:02d}"
    codes = [snippet(fn, c) for c in cases]
    text, count = hidden_test(tid, module, src, codes)
    write_graded(f"cp_implement_{n:02d}", module, text)
    REFERENCES[tid] = {f"{module}.py": d(src)}
    ins = (
        f"Create {module}.py in the working directory with a function {fn}(...) that {spec} "
        f"Write your own test_{module}.py and run pytest_run until it passes. Finish with: {DONE}"
    )
    return task(
        tid,
        "implement",
        n,
        ins,
        [
            {
                "type": "hidden_pytest",
                "graded": f"cp_implement_{n:02d}",
                "impl_files": [f"{module}.py"],
                "min_passed": count,
            }
        ],
    )


def build_fix(n: int) -> dict:
    slug, module, fn, buggy, fixed, vis, hid = FIX[n]
    tid = f"code-fix-{n:02d}"
    vis_codes = [snippet(fn, c) for c in vis]
    hid_codes = vis_codes + [snippet(fn, c) for c in hid]
    vtest = visible_test(module, fn, vis_codes, fixed)
    text, count = hidden_test(tid, module, fixed, hid_codes)
    write_graded(f"cp_fix_{n:02d}", module, text)
    REFERENCES[tid] = {f"{module}.py": d(fixed)}
    seed = {f"{module}.py": d(buggy), f"test_{module}.py": vtest}
    ins = (
        f"{module}.py in your working directory is broken: test_{module}.py fails. Read both files, "
        f"then fix {module}.py IN PLACE with file_write so the tests pass. Do not modify "
        f"test_{module}.py. Verify with pytest_run. Finish with: {DONE}"
    )
    return task(
        tid,
        "fix",
        n,
        ins,
        [
            {"type": "immutable", "hashes": {f"test_{module}.py": sha16(vtest)}},
            {
                "type": "hidden_pytest",
                "graded": f"cp_fix_{n:02d}",
                "impl_files": [f"{module}.py"],
                "min_passed": count,
            },
        ],
        seed,
        ("file_read", "file_write", "pytest_run"),
    )


def build_refactor(n: int) -> dict:
    slug, module, orig, refactored, shape, vis_codes, hid_extra = REFACTOR[n]
    tid = f"code-refactor-{n:02d}"
    vtest = visible_test(module, "", vis_codes, refactored)
    text, count = hidden_test(tid, module, refactored, vis_codes + hid_extra)
    write_graded(f"cp_refactor_{n:02d}", module, text)
    REFERENCES[tid] = {f"{module}.py": d(refactored)}
    seed = {f"{module}.py": d(orig), f"test_{module}.py": vtest}
    ins = (
        f"Refactor {module}.py in your working directory: {shape}. test_{module}.py passes today and "
        f"must stay green and unchanged. Use file_write to edit {module}.py in place and verify with "
        f"pytest_run. Finish with: {DONE}"
    )
    return task(
        tid,
        "refactor",
        n,
        ins,
        [
            {"type": "immutable", "hashes": {f"test_{module}.py": sha16(vtest)}},
            {
                "type": "hidden_pytest",
                "graded": f"cp_refactor_{n:02d}",
                "impl_files": [f"{module}.py"],
                "min_passed": count,
            },
        ],
        seed,
        ("file_read", "file_write", "pytest_run"),
    )


def build_read(n: int) -> dict:
    slug, module, src, expr, wording, what = READ[n]
    tid = f"code-read-{n:02d}"
    source = d(src)
    ns: dict = {}
    exec(source, ns)  # noqa: S102
    val, exc = run_snippet(ns, f"result = {expr}")
    gold = exc if what == "exception" else str(val)
    fname = re.search(r"def (\w+)", source).group(1)
    ins = (
        f"Read {module}.py and tell me {wording}. {FORMAT}"
        if n % 3 == 0
        else f"In {module}.py, what is {wording}? {FORMAT}"
    )
    pattern = rf'"answer"\s*:\s*"?{re.escape(gold)}"?(?![\w.-])'
    trace = [
        {"name": "file_read", "args": {"path": f"{module}.py"}, "output": source, "error": None}
    ]
    t = task(
        tid,
        "read",
        n,
        ins,
        [
            {"type": "answer_contains", "patterns": [pattern]},
            {"type": "tool_grounded", "tools": ["file_read"], "evidence": [rf"def {fname}\b"]},
        ],
        {f"{module}.py": source},
        ("file_read",),
    )
    del t["completion_signal"]  # a read task answers; it does not signal completion
    t["controls"] = {
        "pass": [{"answer": json.dumps({"answer": gold}), "tool_calls": trace}],
        "fail": [
            json.dumps({"answer": gold}),
            {"answer": json.dumps({"answer": "not-the-value"}), "tool_calls": trace},
        ],
    }
    REFERENCES[tid] = {}
    return t


def build() -> list[dict]:
    REFERENCES.clear()
    tasks = [build_implement(n) for n in range(COUNTS["implement"])]
    tasks += [build_fix(n) for n in range(COUNTS["fix"])]
    tasks += [build_refactor(n) for n in range(COUNTS["refactor"])]
    tasks += [build_read(n) for n in range(COUNTS["read"])]
    tasks.sort(key=lambda t: not t["screen"])
    return tasks


def main() -> None:
    tasks = build()
    OUT.write_text("".join(json.dumps(t) + "\n" for t in tasks))
    print(f"wrote {OUT.name}: {len(tasks)} tasks, {sum(t['screen'] for t in tasks)} screen")


if __name__ == "__main__":
    main()
