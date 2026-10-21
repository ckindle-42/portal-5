"""Build tests/wfe/suites/vision_production.jsonl and its images under
tests/fixtures/vision/, auto-vision's suite (WFE new-instruments brief, I-VISION).

The seat is qwen3-vl:32b (ctx 8192). Every image is generated here — matplotlib charts,
PIL-rendered tables, receipts, invoices, tickets and shape scenes — from fictional seeded
values, so the images are licence-clean (no third-party source, nothing to attribute) and
cannot be recalled from training. The gold is computed from the same spec that draws the
image and lives only in this generator and the jsonl, never in the PNG (no text chunks are
written; a test checks). Three kinds, 36 tasks, 12 in the screen tier (four per kind):

- chart-table (12)   a value read from a bar chart, a line chart or a table image;
- doc-fields (12)    a field read from a receipt, an invoice or an event ticket;
- natural (12)       counting shapes of one colour, naming a shape's colour, and reading
                     the text on a sign.

All tasks are `no_tools`; the answer contract is JSON {"answer": ...} with each answer
form defined in the instruction. The runner attaches each task's `images` as OpenAI
`image_url` parts (tests/wfe/runner.py `user_content`). Sources: none external — all
images and golds are original to this generator (2026-10-18), so contamination by
pre-2026 material is not a concern.

    uv run python tests/wfe/suites/build_vision_production.py
"""

from __future__ import annotations

import json
import random
import re
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from PIL import Image, ImageDraw, ImageFont  # noqa: E402

from tests.wfe.suites._publish import publish_text

REPO = Path(__file__).resolve().parents[3]
OUT = Path(__file__).with_name("vision_production.jsonl")
IMG_DIR = REPO / "tests/fixtures/vision"
COUNTS = {"chart-table": 12, "doc-fields": 12, "natural": 12}
SCREEN = {"chart-table": 4, "doc-fields": 4, "natural": 4}
LANE = "vision"
SEEDS = {"chart-table": 7100, "doc-fields": 7200, "natural": 7300}
FORMAT = 'Answer only as JSON {"answer": ...}.'

_CATEGORIES = [
    "Harbor",
    "Quarry",
    "Meadow",
    "Foundry",
    "Lantern",
    "Orchard",
    "Summit",
    "Delta",
    "Ember",
    "Glacier",
]
_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug"]
_VENDORS = [
    "Brindle & Oak Provisions",
    "Tallow Street Hardware",
    "Quillfeather Books",
    "Marrow Lane Bakery",
]
_ITEMS = ["Notebook", "Wire brush", "Lamp oil", "Rye loaf", "Twine", "Candle box", "Tea tin"]
_BILL_TO = ["Corvane Freight Ltd", "Ostrel Marine Co", "Pellwick Grain Works", "Hadrow Print Group"]
_EVENTS = ["Lantern Night Concert", "Foundry Open Day", "Harbor Regatta Final", "Orchard Film Hour"]
_COLOURS = {
    "red": (214, 40, 40),
    "green": (46, 160, 67),
    "blue": (35, 90, 200),
    "yellow": (240, 200, 20),
    "purple": (125, 60, 170),
    "orange": (240, 130, 20),
}
_SIGN_WORDS = ["HARBOR", "QUARRY", "FOUNDRY", "ORCHARD", "SUMMIT", "MEADOW", "LANTERN", "GLACIER"]
_MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    return ImageFont.load_default(size=size)


def _pattern(value: str) -> str:
    return rf'"answer"\s*:\s*"?{re.escape(value)}"?(?![\w.-])'


def _save(img: Image.Image, name: str) -> str:
    IMG_DIR.mkdir(parents=True, exist_ok=True)
    img.convert("P", palette=Image.Palette.ADAPTIVE, colors=64).save(
        IMG_DIR / name, format="PNG", optimize=True
    )
    return f"tests/fixtures/vision/{name}"


def _save_fig(fig, name: str) -> str:
    IMG_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(IMG_DIR / name, format="png", dpi=80, metadata={"Software": None})
    plt.close(fig)
    # Re-encode through PIL to a small palette PNG without text chunks.
    with Image.open(IMG_DIR / name) as im:
        im.load()
        return _save(im.convert("RGB"), name)


# ------------------------------------------------------------------ chart-table


def chart_task(n: int) -> tuple[str, str, str]:
    """(image path, question, gold) for chart-table task n; shape cycles bar/line/table."""
    r = random.Random(SEEDS["chart-table"] + n)
    shape = n % 3
    name = f"chart-table-{n:02d}.png"
    if shape == 0:  # bar chart, values on multiples of 5, gridline every 5
        cats = r.sample(_CATEGORIES, 5)
        vals = [r.randrange(10, 95, 5) for _ in cats]
        fig, ax = plt.subplots(figsize=(6, 4))
        ax.bar(cats, vals, color="#3b6fb6")
        ax.set_yticks(range(0, 101, 10))
        ax.set_yticks(range(0, 101, 5), minor=True)
        ax.grid(axis="y", which="both", alpha=0.35)
        ax.set_ylim(0, 100)
        ax.set_title(f"Units shipped by depot, week {r.randint(2, 40)}")
        ax.set_ylabel("Units")
        i = r.randrange(5)
        return (
            _save_fig(fig, name),
            f"What is the height of the {cats[i]} bar in the chart (read off the y axis)? "
            "Answer with the whole number.",
            str(vals[i]),
        )
    if shape == 1:  # line chart with markers
        months = _MONTHS[:6]
        vals = [r.randrange(10, 95, 5) for _ in months]
        fig, ax = plt.subplots(figsize=(6, 4))
        ax.plot(months, vals, marker="o", color="#b63b3b")
        ax.set_yticks(range(0, 101, 10))
        ax.set_yticks(range(0, 101, 5), minor=True)
        ax.grid(axis="y", which="both", alpha=0.35)
        ax.set_ylim(0, 100)
        ax.set_title(f"Pump readings, site {r.choice(_CATEGORIES)}")
        ax.set_ylabel("Reading")
        i = r.randrange(6)
        return (
            _save_fig(fig, name),
            f"What is the plotted value at {months[i]} (read off the y axis)? "
            "Answer with the whole number.",
            str(vals[i]),
        )
    rows = r.sample(_CATEGORIES, 5)  # table image
    cols = ["Q1", "Q2", "Q3"]
    cells = [[r.randint(100, 999) for _ in cols] for _ in rows]
    img = Image.new("RGB", (460, 300), "white")
    d = ImageDraw.Draw(img)
    f = _font(22)
    d.text((20, 12), f"Output by line, plant {r.randint(2, 9)}", fill="black", font=f)
    for ci, c in enumerate(["Line", *cols]):
        d.text((20 + ci * 105, 52), c, fill="black", font=f)
    d.line((15, 82, 445, 82), fill="black", width=2)
    for ri, row in enumerate(rows):
        y = 92 + ri * 40
        d.text((20, y), row, fill="black", font=f)
        for ci, v in enumerate(cells[ri]):
            d.text((125 + ci * 105, y), str(v), fill="black", font=f)
    ri, ci = r.randrange(5), r.randrange(3)
    return (
        _save(img, name),
        f"What value does the table show for {rows[ri]} in {cols[ci]}? Answer with the whole number.",
        str(cells[ri][ci]),
    )


# ------------------------------------------------------------------- doc-fields


def _date(r: random.Random) -> tuple[str, str]:
    """(printed form, ISO form) of a seeded 2026 date."""
    m, d = r.randint(1, 12), r.randint(1, 28)
    return f"{d:02d} {_MONTH_NAMES[m - 1]} 2026", f"2026-{m:02d}-{d:02d}"


def doc_task(n: int) -> tuple[str, str, str]:
    r = random.Random(SEEDS["doc-fields"] + n)
    shape, variant = n % 3, n // 3
    name = f"doc-fields-{n:02d}.png"
    img = Image.new("RGB", (420, 420), "white")
    d = ImageDraw.Draw(img)
    f, fb = _font(20), _font(26)
    printed, iso = _date(r)
    if shape == 0:  # receipt
        vendor = r.choice(_VENDORS)
        items = [(it, r.randint(150, 1800)) for it in r.sample(_ITEMS, 4)]
        total = sum(p for _, p in items)
        card = f"{r.randint(0, 9999):04d}"
        d.text((20, 16), vendor, fill="black", font=fb)
        d.text((20, 54), f"Receipt {printed}", fill="black", font=f)
        for i, (it, p) in enumerate(items):
            d.text((20, 100 + i * 34), it, fill="black", font=f)
            d.text((300, 100 + i * 34), f"{p // 100}.{p % 100:02d}", fill="black", font=f)
        d.line((20, 250, 400, 250), fill="black", width=2)
        d.text((20, 266), "TOTAL", fill="black", font=fb)
        d.text((290, 266), f"{total // 100}.{total % 100:02d}", fill="black", font=fb)
        d.text((20, 330), f"Card ending {card}", fill="black", font=f)
        qa = [
            (
                "What is the total on the receipt? Answer in the form 12.34.",
                f"{total // 100}.{total % 100:02d}",
            ),
            ("What is the receipt date? Answer as YYYY-MM-DD.", iso),
            ("What is the vendor name printed at the top? Answer with the name exactly.", vendor),
            ("What are the last four digits of the card? Answer with the four digits.", card),
        ][variant % 4]
    elif shape == 1:  # invoice
        inv = f"INV-{r.randint(10000, 99999)}"
        bill = r.choice(_BILL_TO)
        amount = r.randint(20000, 990000)
        due_printed, due_iso = _date(r)
        d.text((20, 16), "INVOICE", fill="black", font=fb)
        d.text((20, 70), f"Invoice no: {inv}", fill="black", font=f)
        d.text((20, 110), f"Bill to: {bill}", fill="black", font=f)
        d.text((20, 150), f"Issued: {printed}", fill="black", font=f)
        d.text((20, 190), f"Due: {due_printed}", fill="black", font=f)
        d.line((20, 240, 400, 240), fill="black", width=2)
        d.text((20, 262), f"Amount due: {amount // 100}.{amount % 100:02d}", fill="black", font=fb)
        qa = [
            ("What is the invoice number? Answer with the number exactly.", inv),
            ("What is the due date? Answer as YYYY-MM-DD.", due_iso),
            (
                "What is the amount due? Answer in the form 1234.56.",
                f"{amount // 100}.{amount % 100:02d}",
            ),
            ("Who is the invoice billed to? Answer with the name exactly.", bill),
        ][variant % 4]
    else:  # event ticket
        event = r.choice(_EVENTS)
        seat = f"{r.choice('ABCDEFGH')}{r.randint(1, 30)}"
        gate = str(r.randint(1, 9))
        d.rectangle((10, 10, 410, 300), outline="black", width=3)
        d.text((24, 24), event, fill="black", font=fb)
        d.text((24, 84), f"Date: {printed}", fill="black", font=f)
        d.text((24, 124), f"Gate: {gate}", fill="black", font=f)
        d.text((24, 164), f"Seat: {seat}", fill="black", font=fb)
        qa = [
            ("What seat is printed on the ticket? Answer with the seat exactly.", seat),
            ("What gate is printed on the ticket? Answer with the digit.", gate),
            ("What date is the event? Answer as YYYY-MM-DD.", iso),
            ("What is the event name? Answer with the name exactly.", event),
        ][variant % 4]
    return _save(img, name), qa[0], qa[1]


# --------------------------------------------------------------------- natural


def _draw_shape(d: ImageDraw.ImageDraw, kind: str, cx: int, cy: int, rad: int, fill) -> None:
    if kind == "circle":
        d.ellipse((cx - rad, cy - rad, cx + rad, cy + rad), fill=fill)
    elif kind == "square":
        d.rectangle((cx - rad, cy - rad, cx + rad, cy + rad), fill=fill)
    else:
        d.polygon([(cx, cy - rad), (cx - rad, cy + rad), (cx + rad, cy + rad)], fill=fill)


def _place(r: random.Random, count: int, w: int, h: int, rad: int) -> list[tuple[int, int]]:
    pts: list[tuple[int, int]] = []
    while len(pts) < count:
        p = (r.randint(rad + 8, w - rad - 8), r.randint(rad + 8, h - rad - 8))
        if all((p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2 > (3 * rad) ** 2 for q in pts):
            pts.append(p)
    return pts


def natural_task(n: int) -> tuple[str, str, str]:
    r = random.Random(SEEDS["natural"] + n)
    shape = n % 3
    name = f"natural-{n:02d}.png"
    w, h, rad = 480, 320, 26
    img = Image.new("RGB", (w, h), (236, 236, 228))
    d = ImageDraw.Draw(img)
    kinds = ["circle", "square", "triangle"]
    if shape == 0:  # count shapes of one colour among distractors
        target = r.choice(list(_COLOURS))
        others = [c for c in _COLOURS if c != target]
        k, distract = r.randint(2, 8), r.randint(4, 6)
        pts = _place(r, k + distract, w, h, rad)
        for i, (x, y) in enumerate(pts):
            colour = target if i < k else r.choice(others)
            _draw_shape(d, r.choice(kinds), x, y, rad, _COLOURS[colour])
        return (
            _save(img, name),
            f"How many {target} shapes are in the image? Answer with the whole number.",
            str(k),
        )
    if shape == 1:  # colour of one named shape type; each type appears once
        colours = r.sample(list(_COLOURS), 3)
        pts = _place(r, 3, w, h, rad + 8)
        for kind, colour, (x, y) in zip(kinds, colours, pts, strict=True):
            _draw_shape(d, kind, x, y, rad + 8, _COLOURS[colour])
        i = r.randrange(3)
        return (
            _save(img, name),
            f"What colour is the {kinds[i]} in the image? Answer with one colour word in lower case.",
            colours[i],
        )
    word, num = r.choice(_SIGN_WORDS), r.randint(100, 999)  # sign with text
    d.rectangle((0, 0, w, h), fill=(70, 120, 70))
    d.rectangle((60, 90, 420, 230), fill="white", outline="black", width=4)
    d.text((90, 108), word, fill="black", font=_font(48))
    d.text((90, 168), f"RD {num}", fill="black", font=_font(40))
    return (
        _save(img, name),
        "What word is printed in large letters on the sign? Answer in capital letters.",
        word,
    )


BUILDERS = {"chart-table": chart_task, "doc-fields": doc_task, "natural": natural_task}


def build_task(kind: str, n: int) -> dict:
    image, question, gold = BUILDERS[kind](n)
    wrong = "wrong-value" if not gold.isdigit() else str(int(gold) + 1)
    return {
        "id": f"vis-{kind}-{n:02d}",
        "kind": kind,
        "lane": LANE,
        "agentic": False,
        "screen": n < SCREEN[kind],
        "instruction": f"{question} {FORMAT}",
        "images": [image],
        "requires_tools": [],
        "checkers": [{"type": "answer_contains", "patterns": [_pattern(gold)]}],
        "controls": {
            "pass": [{"answer": json.dumps({"answer": gold})}],
            "fail": [{"answer": json.dumps({"answer": wrong})}],
        },
        "no_tools": True,
    }


def build() -> list[dict]:
    tasks = [build_task(k, n) for k, count in COUNTS.items() for n in range(count)]
    for t in tasks:
        if t["controls"]["pass"][0]["answer"] in t["instruction"]:
            raise RuntimeError(f"{t['id']}: the instruction states the gold")
    tasks.sort(key=lambda t: not t["screen"])
    return tasks


def main() -> None:
    tasks = build()
    publish_text(OUT, "".join(json.dumps(t) + "\n" for t in tasks))
    print(f"wrote {OUT.name}: {len(tasks)} tasks, {sum(t['screen'] for t in tasks)} screen")


if __name__ == "__main__":
    main()
