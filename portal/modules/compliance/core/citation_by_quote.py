"""Citation by quote (CITE_AND_SCOPE_V1 P1) — the inverse of the verbatim check.

``record_determination`` already proves a quoted sentence is IN a section:
``_norm_for_verbatim`` folds the typography a quotation picks up in transit
(dashes, quote marks, whitespace runs, case) and the check asks whether the
folded sentence is a substring of the folded section text. This module asks the
inverse question — *which sections contain this folded sentence* — over the
whole store, so an ANSWER's citation can be the words themselves and no
identifier needs to travel through the model's hands.

Why: three fixes moved a 20-hex section id around the prompt (off the rendered
line, prefix resolution, a ``cite_as`` token riding the copied text) and the
transcription failures kept coming — dropped characters, added characters, two
ids concatenated, three distinct failure modes in six answers. A 20-hex token
in the output contract of a 26B local model IS a transcription task. The words
the claim rests on are not: a quote that survives folding one character off no
longer matches anything, so it cannot fail silently into looking plausible, and
an auditor verifies it by reading.

The honesty rules carry over from ids unchanged: an unresolvable quote stays
unresolved and is reported as written — it is never mapped onto a near
neighbour. A quote that matches SEVERAL sections is reported with every match;
whether multi-match still grounds is the caller's policy, decided on the
measured distribution (``reports/compliance/cite_and_scope/p1/``), not here.
"""

from __future__ import annotations

import re
from typing import Any

from portal.modules.compliance.core.candidate_links import (
    _norm_for_verbatim as _fold,
)

__all__ = ["QUOTED_SPAN", "quoted_spans", "resolve_quote"]

#: A quoted span in an answer line — straight or curly double quotes, at least
#: one non-quote character. Single quotes are deliberately NOT spans: an
#: apostrophe is ordinary prose and a single-quote span would fire on it.
QUOTED_SPAN = re.compile(r'"([^"\n]{2,}?)"|“([^“”\n]{2,}?)”')

_INDEX_ATTR = "_citation_by_quote_index"


#: An elision mark inside a quoted span — the universal convention for
#: "material omitted here". Exactly three dots (a longer dot run is a
#: table-of-contents leader, and this corpus's TOC lines are full of them), or
#: the unicode ellipsis. Each side is checked separately, and all parts must
#: land in the SAME DOCUMENT — the store sections a table row at a time, so a
#: quote spanning two adjacent list items lands in two sections of one
#: document, and the convention is accepted without loosening what counts as
#: support: every word of every part must exist verbatim in that document, so
#: stitching one real fragment to an invented one still fails.
_ELLIPSIS = re.compile(r"\s*(?<!\.)\.{3}(?!\.)\s*|\s*…\s*")

#: A part shorter than this cannot be checked as words of its own and is
#: DROPPED when longer parts remain (a one-word elision stub adds nothing
#: evidentiary either way); a span whose every part is shorter resolves to
#: nothing — a quote that thin is not a quotation.
_MIN_PART_CHARS = 4

#: Punctuation a quotation absorbs at its end because ENGLISH HOUSE STYLE
#: PUTS IT INSIDE THE QUOTES (``"…alarms."`` when the section reads
#: ``…alarms``). Stripped from the folded SPAN before matching, never from a
#: section's text; every word must still exist.
_TRAILING_ABSORBED = re.compile(r"[.,]+$")


def quoted_spans(text: str) -> list[str]:
    """Every quoted span in a line, as written. The caller decides what each
    one means; a span is never trimmed, merged or repaired here."""
    out: list[str] = []
    for m in QUOTED_SPAN.finditer(str(text or "")):
        out.append(m.group(1) if m.group(1) is not None else m.group(2))
    return out


def _folded_index(repo: Any) -> dict[str, tuple[str, str]]:
    """``section_id -> (folded text, folded document id)``, every section in
    the store, built once.

    The text is ``section_index.resolve_sections``' own — the exact text the
    verbatim check proved stored quotes against — so a quote that once passed
    that check resolves here by construction. Cached on the repository object:
    the fold over ~10k sections is seconds, and a conversational run asks the
    inverse question many times.
    """
    index = getattr(repo, _INDEX_ATTR, None)
    if index is not None:
        return index
    from portal.modules.compliance.core.section_index import resolve_sections

    ids = [
        str(row[0])
        for row in repo._conn.execute("SELECT section_id FROM source_sections").fetchall()
    ]
    index = {}
    for section_id, entry in resolve_sections(repo, ids).items():
        folded = _fold(str(entry.get("text", "")))
        if folded:
            index[section_id] = (folded, _fold(str(entry.get("logical_id", ""))))
    setattr(repo, _INDEX_ATTR, index)
    return index


def resolve_quote(
    repo: Any,
    quote: str,
    *,
    min_chars: int = 0,
) -> list[str]:
    """Every section whose document the folded quote is verbatim IN.

    Returns ALL matches, store order — a quote matching several sections is
    ambiguity to be reported, never silently narrowed to one. An empty quote,
    or one shorter than ``min_chars``, matches nothing: there is no section to
    name and the caller reports the span unresolved, as written. Never a near
    neighbour: the fold covers typography, not rewording — a paraphrase finds
    nothing, and that finding is the answer.

    An elision mark (``...``) splits the span into parts and EVERY part must
    appear verbatim in the SAME DOCUMENT; sections of a hosting document that
    carry any part are returned. Stitching one real fragment to an invented
    one still fails — the invented part is in no document."""
    folded = _TRAILING_ABSORBED.sub("", _fold(str(quote or "")))
    if not folded or len(folded) < max(0, int(min_chars)):
        return []
    parts = [part for part in _ELLIPSIS.split(folded) if part]
    parts = [part for part in parts if len(part) >= _MIN_PART_CHARS]
    if not parts:
        return []
    index = _folded_index(repo)
    if len(parts) == 1:
        return [sid for sid, (text, _doc) in index.items() if parts[0] in text]
    part_docs: list[set[str]] = []
    part_sections: dict[str, bool] = {}
    for part in parts:
        docs: set[str] = set()
        for sid, (text, doc) in index.items():
            if part in text:
                docs.add(doc)
                part_sections[sid] = True
        part_docs.append(docs)
    hosting_docs = set.intersection(*part_docs)
    if not hosting_docs:
        return []
    return [
        sid for sid, (_text, doc) in index.items() if doc in hosting_docs and sid in part_sections
    ]
