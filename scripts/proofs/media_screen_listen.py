#!/usr/bin/env python3
"""Blind A/B audio listener: the media screen's judge step for music rows.

Pairs every candidate clip in a screen run against the incumbent clip for the same fixed
prompt, draws the A/B order blind from a seed, and asks an audio-capable model for the
document's five 1-5 dimensions, the words it actually heard and the elements it can pick out.
The answer is unblinded into `listen_<listener>_music_<date>.md` beside the judge sheet, with
one receipt per pair in `listen_rows.jsonl`.

    uv run python scripts/proofs/media_screen_listen.py --run-dir <screens/music-...> \
        [--listener mimo-v2.6-pro] [--base-url https://api.xiaomimimo.com/v1] [--dry-run]

Exit codes: 0 step completed (an unparsed answer is recorded, not fatal), 2 setup error.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import httpx
import yaml

REPO = Path(__file__).resolve().parents[2]
CATALOG_PATH = Path(__file__).resolve().parent / "media_screen_catalog.yaml"
AUTH_PATH = Path.home() / ".local/share/opencode/auth.json"
DEFAULT_LISTENER = "mimo-v2.6-pro"
DEFAULT_BASE_URL = "https://api.xiaomimimo.com/v1"
DEFAULT_SEED = 20261120
DIMENSIONS = ("adherence", "musicality", "instruments", "cleanliness", "vocals")
SCORE_WORDS = "1-5"
LISTEN_TIMEOUT_S = 240
MAX_TOKENS = 2000


@dataclass
class Pair:
    """One candidate/incumbent receipt pair for the same fixed prompt."""

    candidate: dict
    incumbent: dict

    @property
    def prompt_index(self) -> int:
        return int(self.candidate["prompt_index"])

    @property
    def key(self) -> str:
        return f"{self.candidate['row']}-p{self.prompt_index}"


def load_catalog(path: Path = CATALOG_PATH) -> dict:
    """Load the screen catalog (prompts and canvas) the run was made from."""
    return yaml.safe_load(path.read_text())


def load_receipts(run_dir: Path) -> list[dict]:
    """Screen receipts with at least one output file; the run-header line is skipped."""
    path = run_dir / "rows.jsonl"
    receipts = []
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        if record.get("kind") == "run" or not record.get("outputs"):
            continue
        receipts.append(record)
    return receipts


def pair_runs(receipts: list[dict]) -> list[Pair]:
    """Candidate receipts paired with the incumbent receipt of the same prompt index."""
    incumbent = {int(r["prompt_index"]): r for r in receipts if r.get("role") == "incumbent"}
    pairs = []
    for receipt in receipts:
        if receipt.get("role") != "candidate":
            continue
        index = int(receipt["prompt_index"])
        if index in incumbent:
            pairs.append(Pair(receipt, incumbent[index]))
    return sorted(pairs, key=lambda pair: (pair.candidate.get("rank") or 99, pair.prompt_index))


def draw_order(seed: int, key: str) -> str:
    """'AB' when the candidate takes slot A, 'BA' when it takes B — blind and reproducible."""
    digest = hashlib.sha256(f"{seed}:{key}".encode()).digest()
    return "AB" if digest[0] % 2 == 0 else "BA"


def _prompt_requirements(catalog: dict, index: int) -> str:
    entry = catalog["media"]["music"]["prompts"][index - 1]
    lines = [f"caption: {entry['caption']}"]
    if entry.get("lyrics"):
        lines.append("required lyrics to sing:\n" + entry["lyrics"].strip())
    if entry.get("instrumental"):
        lines.append("instrumental: no vocals, no singing, no humming")
    return "\n".join(lines)


def judge_question(catalog: dict, index: int) -> str:
    """The fixed judging question: the screen's criteria, five dimensions, JSON only."""
    return (
        "You are an independent listener judging two 30-second music clips, A and B, from a "
        "text-to-music screen. You do not know which system made which clip. The row prompt was:\n"
        f"{_prompt_requirements(catalog, index)}\n\n"
        "Score each clip 1-5 on: adherence (does it follow the caption and sing the required "
        "words), musicality, instruments (are the named instruments there and nothing forbidden), "
        "cleanliness (5 = intact audio, no artefacts, no dropouts) and vocals (5 = intelligible and "
        "correct; score 5 when the prompt forbids vocals and there are none).\n"
        'Reply with ONE json object and nothing else: {"A": {"adherence": n, "musicality": n, '
        '"instruments": n, "cleanliness": n, "vocals": n, "lyrics": "<words you actually heard or '
        'NONE>", "elements": ["<instruments you can pick out>"], "notes": "<=20 words"}, "B": {...}, '
        '"winner": "A|B|tie", "why": "<=20 words"}. '
        "If you cannot hear the audio at all, reply exactly CANNOT_PERCEIVE."
    )


def build_request(model: str, question: str, clip_a: Path, clip_b: Path) -> dict:
    """An OpenAI-compatible chat request carrying both clips as input_audio parts."""
    content: list[dict] = [{"type": "text", "text": question}]
    for path in (clip_a, clip_b):
        content.append(
            {
                "type": "input_audio",
                "input_audio": {
                    "data": _b64(path),
                    "format": path.suffix.lstrip(".").lower() or "wav",
                },
            }
        )
    return {
        "model": model,
        "max_tokens": MAX_TOKENS,
        "messages": [{"role": "user", "content": content}],
    }


def _b64(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode()


def parse_answer(content: str) -> dict | None:
    """The JSON object in the reply, fences and prose stripped; None if it is not a usable score."""
    text = (content or "").strip()
    if not text or text.upper().startswith("CANNOT_PERCEIVE"):
        return None
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        answer = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None
    for slot in ("A", "B"):
        scores = answer.get(slot)
        if not isinstance(scores, dict):
            return None
        for dimension in DIMENSIONS:
            value = scores.get(dimension)
            if not isinstance(value, int) or not 1 <= value <= 5:
                return None
    return answer


class Listener:
    """POST the judge question to an OpenAI-compatible audio endpoint."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        transport: httpx.BaseTransport | None = None,
        timeout_s: float = LISTEN_TIMEOUT_S,
    ) -> None:
        self.endpoint = base_url.rstrip("/") + "/chat/completions"
        self.api_key = api_key
        self.transport = transport
        self.timeout_s = timeout_s

    def ask(self, payload: dict) -> dict:
        """Return {"content", "audio_tokens", "error"}; an HTTP failure is a recorded error."""
        started = time.monotonic()
        try:
            with httpx.Client(transport=self.transport, timeout=self.timeout_s) as client:
                response = client.post(
                    self.endpoint,
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json=payload,
                )
                response.raise_for_status()
                body = response.json()
        except (httpx.HTTPError, json.JSONDecodeError) as exc:
            return {"content": "", "audio_tokens": None, "error": f"{type(exc).__name__}: {exc}"}
        choice = (body.get("choices") or [{}])[0]
        usage = body.get("usage") or {}
        details = usage.get("prompt_tokens_details") or {}
        return {
            "content": (choice.get("message") or {}).get("content") or "",
            "audio_tokens": details.get("audio_tokens"),
            "finish_reason": choice.get("finish_reason"),
            "error": None,
            "wall_s": round(time.monotonic() - started, 1),
        }


def score_pair(listener: Listener, model: str, catalog: dict, pair: Pair, seed: int) -> dict:
    """Ask for one blind A/B judgement and unblind it into candidate/incumbent scores."""
    order = draw_order(seed, pair.key)
    cand_path = Path(pair.candidate["outputs"][0])
    inc_path = Path(pair.incumbent["outputs"][0])
    clip_a, clip_b = (cand_path, inc_path) if order == "AB" else (inc_path, cand_path)
    asked = listener.ask(
        build_request(model, judge_question(catalog, pair.prompt_index), clip_a, clip_b)
    )
    answer = parse_answer(asked["content"])
    receipt = {
        "ts": datetime.now(UTC).isoformat(timespec="seconds"),
        "listener": model,
        "row": pair.candidate["row"],
        "role": pair.candidate.get("role"),
        "rank": pair.candidate.get("rank"),
        "prompt_index": pair.prompt_index,
        "prompt": pair.candidate.get("prompt"),
        "order": order,
        "candidate_slot": "A" if order == "AB" else "B",
        "clips": {"A": str(clip_a), "B": str(clip_b)},
        "audio_tokens": asked.get("audio_tokens"),
        "wall_s": asked.get("wall_s"),
        "error": asked.get("error"),
        "status": "ok" if answer else "unparsed",
        "raw": (asked["content"] or "")[:2000],
    }
    if answer:
        cand_slot = receipt["candidate_slot"]
        inc_slot = "B" if cand_slot == "A" else "A"
        receipt["candidate_scores"] = answer[cand_slot]
        receipt["incumbent_scores"] = answer[inc_slot]
        winner = str(answer.get("winner", "tie")).strip().upper()
        receipt["winner"] = (
            "candidate" if winner == cand_slot else "incumbent" if winner == inc_slot else "tie"
        )
        receipt["why"] = answer.get("why")
    return receipt


def render_sheet(receipts: list[dict], listener: str, run_dir: Path, seed: int) -> str:
    """The unblinded second-lineage sheet, in the document's own score-column shape."""
    lines = [
        f"# Listen sheet — music — {datetime.now(UTC):%Y-%m-%d}",
        "",
        f"run: {run_dir}",
        f"listener: {listener} (non-Google lineage; the Gemini listener stays lineage 1)",
        f"method: blind A/B, order drawn with seed {seed}; scores 1-5 "
        f"adherence/musicality/instruments/cleanliness/vocals",
        "",
        "| pair | candidate | incumbent | winner |",
        "|---|---|---|---|",
    ]
    for r in receipts:
        cand = _scores(r.get("candidate_scores")) or r["status"]
        inc = _scores(r.get("incumbent_scores")) or "-"
        lines.append(
            f"| {r['row']} p{r['prompt_index']} | {cand} | {inc} | {r.get('winner', r['status'])} |"
        )
    lines += ["", "## Heard lyrics and notes", ""]
    for r in receipts:
        lines.append(f"### {r['row']} p{r['prompt_index']}")
        lines.append(f"- order: candidate in slot {r['candidate_slot']} (seed {seed})")
        for slot, label in (("candidate_scores", "candidate"), ("incumbent_scores", "incumbent")):
            scores = r.get(slot) or {}
            if scores:
                lines.append(
                    f"- {label}: lyrics={scores.get('lyrics', '-')!r}; "
                    f"elements={', '.join(scores.get('elements') or []) or '-'}; {scores.get('notes', '')}"
                )
        if r.get("why"):
            lines.append(f"- winner: {r['winner']} — {r['why']}")
        if r["status"] != "ok":
            lines.append(f"- {r['status']}: {r.get('error') or r.get('raw', '')[:300]}")
        lines.append("")
    return "\n".join(lines) + "\n"


def _scores(scores: dict | None) -> str:
    if not scores:
        return ""
    return "/".join(str(scores.get(dimension)) for dimension in DIMENSIONS)


def resolve_api_key(env_name: str, base_url: str, auth_path: Path = AUTH_PATH) -> str:
    """Env var first, then the provider key opencode already stores for this endpoint."""
    key = os.environ.get(env_name, "").strip()
    if key:
        return key
    provider = "openrouter" if "openrouter" in base_url else "xiaomi"
    try:
        stored = json.loads(auth_path.read_text()).get(provider) or {}
    except (OSError, json.JSONDecodeError):
        stored = {}
    key = str(stored.get("key") or "").strip()
    if not key:
        raise ValueError(
            f"no API key for {base_url}: set ${env_name} or {auth_path}[{provider!r}]['key']"
        )
    return key


def listen_run(
    run_dir: Path,
    *,
    listener: str = DEFAULT_LISTENER,
    base_url: str = DEFAULT_BASE_URL,
    api_key: str,
    seed: int = DEFAULT_SEED,
    prompt_index: int | None = None,
    transport: httpx.BaseTransport | None = None,
) -> tuple[Path | None, Path | None]:
    """Run the whole step over one screen run directory; returns (sheet, receipts) paths."""
    catalog = load_catalog()
    pairs = pair_runs(load_receipts(run_dir))
    if prompt_index is not None:
        pairs = [pair for pair in pairs if pair.prompt_index == prompt_index]
    if not pairs:
        return None, None
    client = Listener(base_url, api_key, transport=transport)
    receipts = [score_pair(client, listener, catalog, pair, seed) for pair in pairs]
    sheet = run_dir / f"listen_{_slug(listener)}_music_{datetime.now(UTC):%Y-%m-%d}.md"
    sheet.write_text(render_sheet(receipts, listener, run_dir, seed))
    receipt_path = run_dir / "listen_rows.jsonl"
    with receipt_path.open("a") as stream:
        for receipt in receipts:
            stream.write(json.dumps(receipt, sort_keys=True, default=str) + "\n")
    return sheet, receipt_path


def _slug(model: str) -> str:
    return "".join(char if char.isalnum() else "-" for char in model).strip("-")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--run-dir", type=Path, required=True, help="a screens/music-<stamp> dir")
    parser.add_argument("--listener", default=DEFAULT_LISTENER, help="the judging model id")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="OpenAI-compatible base URL")
    parser.add_argument(
        "--api-key-env", default="XIAOMIMIMO_API_KEY", help="env var holding the key"
    )
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED, help="A/B order seed")
    parser.add_argument("--prompt-index", type=int, default=None, help="judge one fixed prompt")
    parser.add_argument(
        "--dry-run", action="store_true", help="print pairs and orders; ask nothing"
    )
    args = parser.parse_args(argv)
    try:
        if args.dry_run:
            pairs = pair_runs(load_receipts(args.run_dir))
            if not pairs:
                print(f"no candidate/incumbent pairs in {args.run_dir}", file=sys.stderr)
                return 2
            for pair in pairs:
                print(f"{pair.key}: candidate slot {draw_order(args.seed, pair.key)[0]}")
            return 0
        sheet, receipts = listen_run(
            args.run_dir,
            listener=args.listener,
            base_url=args.base_url,
            api_key=resolve_api_key(args.api_key_env, args.base_url),
            seed=args.seed,
            prompt_index=args.prompt_index,
        )
    except (ValueError, OSError) as exc:
        print(f"media_screen_listen: {exc}", file=sys.stderr)
        return 2
    if sheet is None:
        print(f"no candidate/incumbent pairs in {args.run_dir}", file=sys.stderr)
        return 0
    print(sheet.read_text())
    print(f"sheet: {sheet}\nreceipts: {receipts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
