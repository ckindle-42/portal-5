#!/usr/bin/env python3
"""READING_TRUTH_V1 P6R amendment 1 (A1) - the verbatim copy probe.

Seat-fidelity of a build or cache setting needs a measure that holds the
reading behaviour fixed. The probe embeds a passage sampled from the store in a
prompt padded with real store material to a target window pressure, asks the
model to reproduce the passage exactly, and scores the copy:

* ``errors_per_1000`` - character edit errors per 1,000 source characters;
* ``meaning_changed`` - a negation, number or modal differs from the source.

It changes no product setting: it posts through the same router and the same
``?model=`` pin as the arms, with no caller sampling by default (``product``) or
``temperature: 0`` (``t0``). Output is local only.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import random
import re
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from typing import Any

MIN_WORDS, MAX_WORDS = 40, 120
#: a rough, build-independent estimate; the arms' real pressure comes from serving metadata
CHARS_PER_TOKEN = 4

_NEGATIONS = frozenset({"not", "no", "never", "nor", "neither", "without", "cannot", "none"})
_MODALS = frozenset({"shall", "must", "should", "may", "might", "can", "could", "will", "would"})
_MEANING = re.compile(r"\d[\d.,]*|[a-z']+", re.I)


def meaning_tokens(text: str) -> Counter:
    """Numbers, negations and modals of ``text`` - the tokens whose change flips a requirement."""
    out: Counter = Counter()
    for raw in _MEANING.findall(text.lower()):
        word = raw.replace("can't", "cannot").replace("won't", "will not").strip("'")
        if word.endswith("n't"):
            word = "not"
        if word[:1].isdigit() or word in _NEGATIONS or word in _MODALS:
            out[word.rstrip(".,")] += 1
    return out


def _edits(a: str, b: str) -> int:
    from scripts.compliance.truth.quote_fidelity import levenshtein

    return levenshtein(a, b, max(len(a), len(b)))


def score_copy(source: str, copy: str) -> dict[str, Any]:
    """Score one reproduction. Whitespace is folded; case and punctuation are not."""
    source = " ".join(source.split())
    copy = " ".join(copy.split())
    edits = _edits(source, copy)
    return {
        "edits": edits,
        "errors_per_1000": round(1000 * edits / max(1, len(source)), 3),
        "meaning_changed": meaning_tokens(source) != meaning_tokens(copy),
        "exact": source == copy,
    }


def sample_passages(store: Any, n: int, seed: int) -> list[dict]:
    """``n`` passages of 40-120 words, alternating operator and regulatory sections."""
    from portal.modules.compliance.core.citation_by_quote import _folded_index
    from portal.modules.compliance.core.section_index import resolve_sections
    from scripts.compliance.truth.citation_integrity import _section_side

    rng = random.Random(seed)
    ids = sorted(_folded_index(store))
    texts = resolve_sections(store, ids)
    by_side: dict[str, list[tuple[str, list[str]]]] = {"operator": [], "regulatory": []}
    for sid in ids:
        words = str(texts.get(sid, {}).get("text", "")).split()
        side = _section_side(store, sid)
        if side in by_side and len(words) >= MIN_WORDS:
            by_side[side].append((sid, words))
    out: list[dict] = []
    sides = [s for s in ("operator", "regulatory") if by_side[s]]
    if not sides:
        return out
    # bullets and numbers first: they are where copy errors cost the most
    for side in sides:
        by_side[side].sort(key=lambda sw: -sum(1 for w in sw[1] if re.search(r"[0-9•]", w)))
    pools = {side: by_side[side][: max(1, len(by_side[side]) // 2)] for side in sides}
    i = 0
    while len(out) < n:
        side = sides[i % len(sides)]
        sid, words = rng.choice(pools[side])
        size = rng.randint(MIN_WORDS, min(MAX_WORDS, len(words)))
        start = rng.randint(0, len(words) - size)
        out.append({"section_id": sid, "side": side, "text": " ".join(words[start : start + size])})
        i += 1
    return out


def padding(store: Any, chars: int, exclude: str, seed: int) -> str:
    """Real store material, other sections than ``exclude``, up to ``chars`` characters."""
    from portal.modules.compliance.core.citation_by_quote import _folded_index
    from portal.modules.compliance.core.section_index import resolve_sections

    ids = [s for s in sorted(_folded_index(store)) if s != exclude]
    random.Random(seed).shuffle(ids)
    parts: list[str] = []
    total = 0
    for sid, entry in resolve_sections(store, ids[: max(50, chars // 200)]).items():
        text = " ".join(str(entry.get("text", "")).split())
        if text:
            parts.append(text)
            total += len(text)
        if total >= chars:
            break
    return "\n\n".join(parts)[:chars]


def build_prompt(passage: str, pad: str) -> str:
    """The passage sits in the middle of the padding; the ask names it by its first words."""
    half = len(pad) // 2
    lead = " ".join(passage.split()[:6])
    return (
        f"{pad[:half]}\n\n<<<BEGIN PASSAGE>>>\n{passage}\n<<<END PASSAGE>>>\n\n{pad[half:]}\n\n"
        f"Reproduce, exactly and with no other words, the text between <<<BEGIN PASSAGE>>> and "
        f"<<<END PASSAGE>>> (it starts with: {lead}). Do not correct, summarise or reword."
    )


def ask(
    session: Any, router: str, key: str, workspace: str, build: str, prompt: str, mode: str
) -> dict:
    import urllib.parse

    body: dict[str, Any] = {
        "model": workspace,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
    }
    if mode == "t0":
        body["temperature"] = 0
    query = f"?model={urllib.parse.quote(build, '')}" if build else ""
    started = time.monotonic()
    try:
        response = session.post(
            f"{router}/v1/chat/completions{query}",
            headers={"Authorization": f"Bearer {key}"},
            json=body,
            timeout=900,
        )
        response.raise_for_status()
        message = response.json()["choices"][0]["message"]
        return {
            "text": str(message.get("content") or ""),
            "route": response.headers.get("x-portal-route", ""),
            "wall_s": round(time.monotonic() - started, 2),
        }
    except Exception as exc:  # noqa: BLE001 - a failed probe item is recorded, not hidden
        return {"text": "", "error": str(exc)[:300], "route": ""}


def summarise(rows: list[dict]) -> dict:
    ok = [r for r in rows if not r.get("error")]
    chars = sum(len(" ".join(r["source"].split())) for r in ok)
    return {
        "n": len(rows),
        "n_scored": len(ok),
        "errors_per_1000": round(1000 * sum(r["edits"] for r in ok) / max(1, chars), 3),
        "meaning_changed": sum(bool(r["meaning_changed"]) for r in ok),
        "exact": sum(bool(r["exact"]) for r in ok),
    }


def run(
    store: Any,
    session: Any,
    *,
    router: str,
    key: str,
    workspace: str,
    build: str,
    mode: str,
    pressure: float,
    window: int,
    n: int,
    seed: int,
    concurrency: int,
) -> dict:
    passages = sample_passages(store, n, seed)
    target = int(pressure * window * CHARS_PER_TOKEN)

    # the store connection is not thread-safe: build every pad before the pool starts
    pads = [
        padding(store, max(0, target - len(p["text"])), p["section_id"], seed + i)
        for i, p in enumerate(passages)
    ]

    def one(item: tuple[int, dict]) -> dict:
        idx, passage = item
        pad = pads[idx]
        got = ask(session, router, key, workspace, build, build_prompt(passage["text"], pad), mode)
        reply = got["text"].strip()
        match = re.search(r"<<<BEGIN PASSAGE>>>\s*(.*?)\s*(?:<<<END PASSAGE>>>|$)", reply, re.S)
        copy = match.group(1) if match else reply
        row = {
            "section_id": passage["section_id"],
            "side": passage["side"],
            "source": passage["text"],
            "copy": copy,
            "route": got.get("route", ""),
            "wall_s": got.get("wall_s"),
        }
        if got.get("error"):
            row["error"] = got["error"]
        else:
            row.update(score_copy(passage["text"], copy))
        return row

    with ThreadPoolExecutor(max_workers=max(1, concurrency)) as pool:
        rows = list(pool.map(one, enumerate(passages)))
    return {
        "build": build,
        "mode": mode,
        "pressure": pressure,
        "window": window,
        "concurrency": concurrency,
        "summary": summarise(rows),
        "rows": rows,
    }


def main(argv: list[str] | None = None) -> int:
    from scripts.compliance.truth import _local

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--workspace", required=True)
    ap.add_argument("--build", required=True, help="the pinned model id, as the arms declare it")
    ap.add_argument("--window", type=int, required=True, help="served window, tokens")
    ap.add_argument("--pressures", required=True, help="e.g. 0.35,0.62 (B0' median and p90)")
    ap.add_argument("--modes", default="t0,product")
    ap.add_argument("--n", type=int, default=30)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--concurrency", type=int, default=1, help="1, then the alias's fan-out")
    ap.add_argument("--out", type=pathlib.Path, required=True, help="a .json file (local only)")
    args = ap.parse_args(argv)
    refused = _local.refusal(args.out, "the copy probe")
    if refused:
        print(refused, file=sys.stderr)
        return 2
    import httpx

    from portal.modules.compliance.core.repository import Repository
    from scripts.compliance_acceptance import _api_key, router_base_url

    repo = Repository()
    results = []
    try:
        with httpx.Client() as session:
            for pressure in (float(p) for p in args.pressures.split(",")):
                for mode in args.modes.split(","):
                    results.append(
                        run(
                            repo,
                            session,
                            router=router_base_url(),
                            key=_api_key(),
                            workspace=args.workspace,
                            build=args.build,
                            mode=mode,
                            pressure=pressure,
                            window=args.window,
                            n=args.n,
                            seed=args.seed,
                            concurrency=args.concurrency,
                        )
                    )
    finally:
        repo.close()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(results, indent=1, ensure_ascii=False))
    for r in results:
        print(f"{r['build']} {r['mode']} p={r['pressure']} c={r['concurrency']}: {r['summary']}")
    return 0


if __name__ == "__main__":
    if __package__ in (None, ""):
        sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))
    raise SystemExit(main())
