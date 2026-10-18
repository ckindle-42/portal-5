"""Build tests/wfe/suites/audio_production.jsonl and its clips under tests/fixtures/audio/,
auto-audio's suite (WFE new-instruments brief, I-AUDIO).

The workspace's seat (gemma4:12b-it-qat) never hears the audio: Open WebUI stores the upload,
and the seat calls transcribe_audio / transcribe_with_speakers (portal-mlx-transcribe, Parakeet
ASR + Sortformer diarization) and answers from the returned transcript. The suite therefore
measures tool use plus reading the transcript, in production tool mode: the clip is staged in
the row's `in/` (task `fixtures`, tests/wfe/eval_mode.py) and the MCP resolves it as it would an
upload (scripts/mlx-transcribe.py, under the eval scope). Each task carries two checkers: the
answer, and `tool_grounded` — a successful transcription call whose output shows the fact.

Clips are synthesised locally with macOS `say` (16 kHz mono WAV) from fictional seeded text;
speaker clips use two different voices. Three kinds, 36 tasks, 12 in the screen tier:

- fact (12)       a fact stated in a one-voice briefing (weekday, room, month, contact name);
- who-said (12)   which of two speakers, each introducing themselves by first name, said they
                  would bring a named item — the answer is that first name;
- number (12)     a count or total spoken in a one-voice stock check (a counted number, or the
                  sum of two counted numbers; sums stay under 100).

Golds are computed here. ASR may write a number as digits or words, so the answer patterns
accept both, and the evidence patterns accept the transcript in either form. `say` voices and
ASR output are not verified offline: the clips' transcripts have to be checked once with the
real service (see the plan's TODO) before a campaign, as no live model is run while building.
Sources: none external; all text and audio are original to this generator (2026-10-18).

    uv run python tests/wfe/suites/build_audio_production.py          # jsonl + clips (macOS)
    uv run python tests/wfe/suites/build_audio_production.py --no-audio   # jsonl only
"""

from __future__ import annotations

import json
import random
import re
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
OUT = Path(__file__).with_name("audio_production.jsonl")
AUDIO_DIR = REPO / "tests/fixtures/audio"
COUNTS = {"fact": 12, "who-said": 12, "number": 12}
SCREEN = {"fact": 4, "who-said": 4, "number": 4}
LANE = "audio"
SEEDS = {"fact": 6100, "who-said": 6200, "number": 6300}
FORMAT = 'Answer only as JSON {"answer": ...}.'
RATE = 16000
GAP_S = 0.45
TOOLS = ["transcribe_audio", "transcribe_with_speakers"]

_WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
_ROOMS = ["Harbor", "Quarry", "Orchard", "Foundry", "Meadow", "Lantern", "Summit", "Glacier"]
_MONTHS = ["January", "March", "April", "June", "July", "September", "October", "December"]
_NAMES = ["Anna", "Ben", "Carla", "David", "Elena", "Frank", "Grace", "Henry", "Irene", "Jack"]
_ITEMS = ["sandwiches", "lanterns", "blankets", "speakers", "chairs", "cooler", "maps", "drinks"]
_EVENTS = ["picnic", "hike", "street fair", "market stall"]
_DEPOTS = ["Harbor", "Quarry", "Orchard", "Foundry", "Meadow", "Summit"]
_VOICE_PAIRS = [("Samantha", "Daniel"), ("Karen", "Rishi"), ("Moira", "Fred"), ("Tessa", "Daniel")]

_UNITS = [
    "zero",
    "one",
    "two",
    "three",
    "four",
    "five",
    "six",
    "seven",
    "eight",
    "nine",
    "ten",
    "eleven",
    "twelve",
    "thirteen",
    "fourteen",
    "fifteen",
    "sixteen",
    "seventeen",
    "eighteen",
    "nineteen",
]
_TENS = ["_", "_", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]


def spoken(n: int) -> str:
    """English words for 0 <= n < 100, hyphenated tens ('forty-two')."""
    if n < 20:
        return _UNITS[n]
    t, u = divmod(n, 10)
    return _TENS[t] + (f"-{_UNITS[u]}" if u else "")


def number_alt(n: int) -> str:
    """Regex alternatives for a number as the ASR may write it: digits or words."""
    w = re.escape(spoken(n)).replace(r"\-", "[- ]")
    return rf"(?:{n}|{w})"


def _pattern(alt: str) -> str:
    return rf'"answer"\s*:\s*"?{alt}"?(?![\w.-])'


def _word(value: str) -> str:
    return rf"\b{re.escape(value)}\b"


# ------------------------------------------------------------------------ specs


def fact_spec(n: int) -> dict:
    r = random.Random(SEEDS["fact"] + n)
    day, room, month = r.choice(_WEEKDAYS), r.choice(_ROOMS), r.choice(_MONTHS)
    contact = r.choice(_NAMES)
    text = (
        f"Briefing note for the site team. The review meeting is on {day} in the {room} room. "
        f"The report is due in {month}. Please ask {contact} for the key."
    )
    q, gold = [
        ("On which day of the week is the review meeting?", day),
        ("What is the name of the room where the review meeting is held?", room),
        ("In which month is the report due?", month),
        ("Who should be asked for the key? Answer with the first name.", contact),
    ][n % 4]
    return {
        "turns": [(0, text)],
        "voices": ("Samantha",) if n % 2 else ("Daniel",),
        "question": q,
        "alt": re.escape(gold),
        "gold": gold,
        "wrong": "nobody",
        "evidence": [_word(gold)],
    }


def who_said_spec(n: int) -> dict:
    r = random.Random(SEEDS["who-said"] + n)
    a, b = r.sample(_NAMES, 2)
    item_a, item_b = r.sample(_ITEMS, 2)
    event = r.choice(_EVENTS)
    turns = [
        (0, f"Hi, I'm {a}."),
        (1, f"And I'm {b}. Let's plan the {event}."),
        (0, f"I will bring the {item_a}."),
        (1, f"Then I will take care of the {item_b}."),
    ]
    asked, gold, other = (item_a, a, b) if n % 2 == 0 else (item_b, b, a)
    return {
        "turns": turns,
        "voices": _VOICE_PAIRS[n % len(_VOICE_PAIRS)],
        "question": (
            f"Who said they would bring or take care of the {asked}? Answer with that "
            "speaker's first name."
        ),
        "alt": re.escape(gold),
        "gold": gold,
        "wrong": other,
        "evidence": [rf"\b{asked[:5]}", _word(gold)],
    }


def number_spec(n: int) -> dict:
    r = random.Random(SEEDS["number"] + n)
    depot = r.choice(_DEPOTS)
    vals = r.sample([v for v in range(21, 49) if v % 10], 3)
    crates, pallets, drums = vals
    text = (
        f"Stock check for the {depot} depot. We counted {spoken(crates)} crates, "
        f"{spoken(pallets)} pallets and {spoken(drums)} drums."
    )
    q, gold, ev = [
        ("How many crates were counted? Answer with the number.", crates, [crates]),
        ("How many pallets were counted? Answer with the number.", pallets, [pallets]),
        ("How many drums were counted? Answer with the number.", drums, [drums]),
        (
            "What is the total of crates and pallets counted? Answer with the number.",
            crates + pallets,
            [crates, pallets],
        ),
    ][n % 4]
    return {
        "turns": [(0, text)],
        "voices": ("Karen",) if n % 2 else ("Daniel",),
        "question": q,
        "alt": number_alt(gold),
        "gold": gold,
        "wrong": gold + 1,
        "evidence": [number_alt(v) for v in ev],
    }


SPECS = {"fact": fact_spec, "who-said": who_said_spec, "number": number_spec}


# ------------------------------------------------------------------------ audio


def render(spec: dict, path: Path) -> None:
    """Synthesise each turn with its voice (`say`) and join them with short silences."""
    path.parent.mkdir(parents=True, exist_ok=True)
    pcm = bytearray()
    silence = b"\x00\x00" * int(RATE * GAP_S)
    with tempfile.TemporaryDirectory() as td:
        for i, (who, text) in enumerate(spec["turns"]):
            tmp = Path(td) / f"t{i}.wav"
            subprocess.run(
                [
                    "say",
                    "-v",
                    spec["voices"][who],
                    "-o",
                    str(tmp),
                    f"--data-format=LEI16@{RATE}",
                    text,
                ],
                check=True,
            )
            with wave.open(str(tmp)) as w:
                if (w.getnchannels(), w.getsampwidth(), w.getframerate()) != (1, 2, RATE):
                    raise RuntimeError(f"unexpected `say` format for {tmp.name}")
                pcm += w.readframes(w.getnframes()) + silence
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(RATE)
        out.writeframes(bytes(pcm))


# ------------------------------------------------------------------------ tasks


def build_task(kind: str, n: int) -> tuple[dict, dict]:
    spec = SPECS[kind](n)
    tid = f"aud-{kind}-{n:02d}"
    fname = f"{tid}.wav"
    trace = [
        {
            "name": "transcribe_with_speakers" if kind == "who-said" else "transcribe_audio",
            "args": {"file": fname},
            "output": json.dumps({"markdown": " ".join(t for _, t in spec["turns"])}),
            "error": None,
        }
    ]
    task = {
        "id": tid,
        "kind": kind,
        "lane": LANE,
        "agentic": True,
        "screen": n < SCREEN[kind],
        "instruction": f"I uploaded a recording, {fname}. {spec['question']} {FORMAT}",
        "fixtures": [f"tests/fixtures/audio/{fname}"],
        "requires_tools": TOOLS,
        "checkers": [
            {"type": "answer_contains", "patterns": [_pattern(spec["alt"])]},
            {"type": "tool_grounded", "tools": TOOLS, "evidence": spec["evidence"]},
        ],
        "controls": {
            "pass": [{"answer": json.dumps({"answer": spec["gold"]}), "tool_calls": trace}],
            "fail": [
                json.dumps({"answer": spec["gold"]}),  # right answer, no transcription call
                {"answer": json.dumps({"answer": spec["wrong"]}), "tool_calls": trace},
            ],
        },
    }
    return task, spec


def build(write_audio: bool = False) -> list[dict]:
    tasks = []
    for kind, count in COUNTS.items():
        for n in range(count):
            task, spec = build_task(kind, n)
            if write_audio:
                render(spec, REPO / task["fixtures"][0])
            tasks.append(task)
    for t in tasks:
        gold = json.loads(t["controls"]["pass"][0]["answer"])["answer"]
        if re.search(rf"\b{re.escape(str(gold))}\b", t["instruction"]):
            raise RuntimeError(f"{t['id']}: the instruction states the gold")
    tasks.sort(key=lambda t: not t["screen"])
    return tasks


def main() -> None:
    tasks = build(write_audio="--no-audio" not in sys.argv)
    OUT.write_text("".join(json.dumps(t) + "\n" for t in tasks))
    print(f"wrote {OUT.name}: {len(tasks)} tasks, {sum(t['screen'] for t in tasks)} screen")


if __name__ == "__main__":
    main()
