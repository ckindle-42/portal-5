"""Doc-voice-family check: the README voice-restoration guard (HF).

`AW` proves a generated block equals its unit body, `BR` that new code is
cited, `BS` that declared claims still hold. None of them notices that a
document has stopped being readable — `README.md` reached 91% machine-
rendered with zero human-owned lines while all three stayed green. `HF`
guards the four structural properties the voice restoration
(`TASK_README_VOICE_V1`) had to repair, so a future migration pass cannot
silently undo them.
"""

from __future__ import annotations

import re

from ._shared import REPO_ROOT
from .registry import register

_ATX = re.compile(r"^(#{1,6})\s+(\S.*)$")
_FENCE = re.compile(r"^\s*(?:`{3,}|~{3,})")
_GEN = re.compile(r"<!-- WIKI:GENERATED unit=([\w.-]+) -->(.*?)<!-- /WIKI:GENERATED -->", re.DOTALL)
_HUMAN = re.compile(
    r'<!-- WIKI:HUMAN-OWNED reason="([^"]*)" -->(.*?)<!-- /WIKI:HUMAN-OWNED -->', re.DOTALL
)
_REASON = re.compile(r'reason="([^"]*)"')

# Editorial device headings belong to README alone — one editorial surface.
_EDITORIAL_HEADINGS = {
    "what this is for",
    "why you'd choose this",
    "what portal 5 is not",
    "how much of this you get",
    "what it does on this hardware",
    "which path is yours",
    "you know it worked when",
    "what to do next",
    "why this exists",
}


def _headings(text: str) -> list[tuple[int, int, str]]:
    out: list[tuple[int, int, str]] = []
    in_fence = False
    for i, line in enumerate(text.splitlines(), 1):
        if _FENCE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        m = _ATX.match(line)
        if m:
            out.append((i, len(m.group(1)), m.group(2).strip()))
    return out


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()


# Scoped to README.md: this guard ships with TASK_README_VOICE_V1, which
# repaired README only. The other Tier-1 docs still carry the pre-migration
# `## Why` inversions and stray H1s (~317 at last count) that T2 / T5–T10 of
# BUILD_PROGRAM_PORTAL5_VOICE_V1 clear; widen `_guarded_docs` to the full
# TIER1_DOCS set once they do, rather than shipping a gate that is red on
# arrival.
_GUARDED_DOCS = ("README.md",)


def _guarded_docs() -> list:
    return [REPO_ROOT / rel for rel in _GUARDED_DOCS]


def _inversions(rel: str, heads: list[tuple[int, int, str]]) -> list[str]:
    """A `## Why` shallower than the section it explains — the migration defect
    where a hardcoded H2 body heading was pasted verbatim under an `### ` host."""
    out: list[str] = []
    last: tuple[int, int, str] | None = None
    for line, level, title in heads:
        if title.lower() == "why":
            if last and last[1] > level:
                out.append(
                    f"{rel}:{line}: `{'#' * level} Why` outranks "
                    f"`{'#' * last[1]} {last[2]}` above it"
                )
        else:
            last = (line, level, title)
    return out


def _duplications(rel: str, text: str) -> list[str]:
    """A `WIKI:HUMAN-OWNED` fence that restates a generated block in the same
    doc — the fence adds nothing the reader did not already get from the unit."""
    gens = [g for g in (_norm(b) for _, b in _GEN.findall(text)) if g]
    out: list[str] = []
    for reason, body in _HUMAN.findall(text):
        nb = _norm(body)
        if nb and any(nb in g or g in nb for g in gens):
            out.append(f"{rel}: human fence ({reason!r}) restates a generated block")
    return out


def _doc_failures(rel: str, text: str) -> list[str]:
    heads = _headings(text)
    fails: list[str] = []

    # structure — exactly one H1. An H1 count, not a scan for headings inside
    # fences: the first version of this check scanned for fenced headings and
    # read clean on a README with 14 stray H1s, because the comments were never
    # inside the fences. Being outside them was the defect.
    h1 = [t for _, lvl, t in heads if lvl == 1]
    if len(h1) > 1:
        fails.append(f"{rel}: {len(h1)} H1 headings (a comment escaped its fence)")

    fails += _inversions(rel, heads)
    fails += _duplications(rel, text)

    # editorial — device headings outside README (one editorial surface)
    if rel != "README.md":
        stray = [t for _, _, t in heads if t.lower() in _EDITORIAL_HEADINGS]
        if stray:
            fails.append(f"{rel}: editorial device heading(s) outside README: {', '.join(stray)}")

    # reasons — no reason string reused more than twice
    counts: dict[str, int] = {}
    for r in _REASON.findall(text):
        counts[r] = counts.get(r, 0) + 1
    over = {r: n for r, n in counts.items() if n > 2}
    if over:
        fails.append(f"{rel}: reason string(s) reused >2x: {over}")

    return fails


def _ratio_sub(rel: str, text: str) -> dict | None:
    from portal.platform.wiki import migration

    try:
        human = migration.fenced_human_lines(text)
        total = migration.total_substantive_lines(text)
    except Exception:  # noqa: BLE001 — ratio is informational only
        return None
    ratio = round(human / total, 3) if total else 0.0
    klass = "editorial" if rel == "README.md" else "operational/other"
    return {
        "name": f"{rel} human-fence ratio ({klass})",
        "status": "PASS",
        "detail": f"{human}/{total} = {ratio} (reported, not enforced)",
    }


@register("doc_voice_guard", "HF. doc voice + structure integrity", order=79)
def check_doc_voice() -> tuple[str, str, list[dict]]:
    """HF. Five hard-fail axes on `README.md` (widen to all Tier-1 once T2/T5–T10
    clear the pre-migration debt in the other docs).

    - **inversion**: no rendered heading outranks its host section.
    - **duplication**: no `WIKI:HUMAN-OWNED` fence restates a generated block in
      the same doc.
    - **structure**: exactly one H1 per doc — a second is a shell comment that
      escaped its fence.
    - **editorial**: the editorial device headings appear only in `README.md`.
    - **reasons**: no `reason` string reused more than twice in one doc.

    Human-fence ratios are reported per doc with its class, never enforced: a
    floor is met by padding within one pass, and it would be actively wrong on
    operational docs, which are supposed to sit at 0.000.
    """
    subs: list[dict] = []
    failures: list[str] = []
    for path in _guarded_docs():
        if not path.exists():
            continue
        rel = str(path.relative_to(REPO_ROOT))
        text = path.read_text(encoding="utf-8")
        failures += _doc_failures(rel, text)
        sub = _ratio_sub(rel, text)
        if sub is not None:
            subs.append(sub)

    if failures:
        return (
            "FAIL",
            f"{len(failures)} doc-voice violation(s)",
            [{"name": "doc voice + structure", "status": "FAIL", "detail": v} for v in failures]
            + subs,
        )
    return (
        "PASS",
        "README.md: one H1, no rendered inversion, no fence restates a block",
        [{"name": "doc voice + structure", "status": "PASS", "detail": "clean"}] + subs,
    )
