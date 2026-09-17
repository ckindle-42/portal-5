"""Wiring the reader (BILATERAL_CORPUS_V1 P6).

What this module builds is **the conditions for reading**, not a reading
procedure. There is no schema here, no field list, no outcome vocabulary and no
canonical stored reading of a requirement. There is no canonical reading of R2 —
there is a reading for *are we stricter than we need to be* and a different one
for *what would an auditor ask for*, and collapsing them into one artifact is the
mistake §0 names, in a new place.

What the module does is narrow and mechanical:

1. **Hand over the whole neighbourhood.** The reading call receives
   :func:`reading_assembly.assemble` output — every Part row with its cells, the
   Measures, the Guidelines and Technical Basis, the Rationale, the VSL rows,
   Section 4 applicability, Section 6 background and its reading conventions, the
   resolved Glossary terms, the implementation plan, the operator's linked
   sections in full, and the operator's own notes. Nothing is filtered on the
   model's behalf and nothing is marked ineligible to cite. What the budget could
   not hold is stated in the payload and repeated to the model, so it knows what
   it has not seen.

2. **Ask the question that was actually asked.** The prompt carries the
   analyst's question and the material. It does not decompose the question into
   stages, does not demand an output shape, and does not tell the model how to
   weigh a Measure against the Technical Basis against the requirement text.

3. **Verify citations; adjudicate nothing.** Every cited id is resolved against
   the pinned revision and **reported with what it resolves to** — a regulatory
   Part, a Measure, a GTB passage, an operator procedure, an operator note, a
   prior answer — so the reader and the analyst can both see what the argument
   rests on. A quantity the answer claims is checked against the text it cited.
   An unresolvable citation is named. **No code here decides that a citation is
   disqualified**, and no code here decides whether the answer is right.

4. **Keep the conversation.** Question, answer, citations, timestamp, model,
   latency and any operator correction are retained and projected into the
   corpus, labelled ``derived``. A stored answer is one analyst's notes pinned to
   the revisions it read: never a fact, never promoted by age, always outranked
   by a :mod:`~core.notes` note, and marked superseded when a revision it cited
   moves.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

#: Section ids as they appear in an answer. Both extractors' prefixes plus the
#: split sub-unit suffix, so an id the model copied from the material resolves
#: exactly as the model saw it.
CITATION_RE = re.compile(r"\b((?:c|i)section-[0-9a-f]{20}(?:#\d+)?)\b")

#: Dash characters a model substitutes for the ASCII hyphen when it renders an
#: id inside prose or Markdown.
#:
#: Found in the P6.8 seat probe, and it mattered: granite4.1 cited nine sections
#: and scored ZERO, because it wrote them with U+2011 NON-BREAKING HYPHEN
#: (``csection‑7ffb333ac44c2b9d3da3``). A citation checker that reads a correct
#: citation as a missing one does not just mis-score a model — it reports a
#: well-grounded answer as ungrounded, which is the opposite of its job. The id
#: is normalised before matching, and the answer's own spelling is kept in
#: ``cited_as`` so nothing is silently rewritten.
_DASHES = str.maketrans(dict.fromkeys("\u2010\u2011\u2012\u2013\u2014\u2015\u2212\uff0d", "-"))

#: A quantity claim in an answer: "35 calendar days", "thirty-five (35) days",
#: "three calendar years".
#:
#: The word list runs past ten and handles compounds, because this material is
#: full of them and getting it wrong is not a near miss. Measured in the P6.8
#: probe with the naive one-to-ten list: "thirty-five calendar days" matched as
#: **"five calendar days"** — the regex caught the tail of the compound and the
#: checker then went looking for a 5-day interval in a 35-day requirement. A
#: quantity checker that reads 35 as 5 is worse than no checker.
_TENS = ("twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety")
_UNITS = (
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
)
#: longest-first so a compound never loses to its own tail
_WORD_ALT = "|".join([f"{t}[- ]{u}" for t in _TENS for u in _UNITS] + list(_TENS) + list(_UNITS))
_QUANTITY_RE = re.compile(
    rf"\b(\d{{1,4}}|{_WORD_ALT})\s*"
    r"(?:\([0-9]+\)\s*)?"
    r"(?:calendar\s+|business\s+|working\s+)?"
    r"(day|days|month|months|year|years|hour|hours)\b",
    re.I,
)

_WORD_NUMBERS: dict[str, str] = {w: str(i + 1) for i, w in enumerate(_UNITS)}
_WORD_NUMBERS.update({t: str((i + 2) * 10) for i, t in enumerate(_TENS)})
_WORD_NUMBERS.update(
    {
        f"{t}{sep}{u}": str((i + 2) * 10 + j + 1)
        for i, t in enumerate(_TENS)
        for j, u in enumerate(_UNITS[:9])
        for sep in ("-", " ")
    }
)

#: How far a quantity may sit from the citation it is pinned to. Beyond this it
#: is reported as UNATTRIBUTED rather than misattributed: a concluding sentence
#: that carries a number and no nearby id is not the same failure as a number
#: sourced from one document and pinned to another, and calling it one would be
#: a false accusation.
_ATTRIBUTION_WINDOW_CHARS = 300

#: Where the reading prompt lives. It is an ARTIFACT, not a literal.
#:
#: On an agentic reader the prompt is the primary lever, and as a hardcoded
#: unversioned string it was the one input that left no trace: absent from every
#: stored answer, every closure receipt and every report. A prompt change could
#: not be measured because there was nothing to compare it with. It now carries
#: a declared ``prompt_version`` and a content sha, both recorded on every
#: answer and every acceptance row, so a change has a before and an after.
PROMPT_PATH = Path(__file__).resolve().parents[4] / "config" / "compliance" / "reading_prompt.md"

_FRONT_MATTER = re.compile(r"\A---\n(.*?)\n---\n", re.S)


def load_prompt(path: Path | None = None) -> tuple[str, str, str]:
    """The reading prompt, its declared version, and the sha of its body.

    Both identifiers are recorded. The declared version is what a person writes
    in a report; the sha is what makes a claim about "the new prompt" checkable,
    because an edited file carrying an unchanged version string is exactly the
    drift a version string alone cannot catch.
    """
    raw = (path or PROMPT_PATH).read_text(encoding="utf-8")
    version = ""
    body = raw
    front = _FRONT_MATTER.match(raw)
    if front:
        body = raw[front.end() :]
        match = re.search(r"^prompt_version:\s*(\S+)\s*$", front.group(1), re.M)
        version = match.group(1) if match else ""
    body = body.strip()
    return body, version or "undeclared", hashlib.sha256(body.encode()).hexdigest()[:12]


def _render_material(context: dict[str, Any]) -> str:
    """The assembly, as text the model reads. Structure only — every label says
    what a passage IS and where it came from, never what it means."""
    lines: list[str] = []
    revision = context.get("revision", {})
    lines.append(
        f"# {context.get('ref')} — {context.get('standard')} "
        f"(revision {revision.get('version') or 'unversioned'}, "
        f"effective {revision.get('effective_date') or 'unstated'}"
        + (f", inactive from {revision['inactive_date']}" if revision.get("inactive_date") else "")
        + f", read as at {context.get('valid_at')})"
    )
    for component in context.get("components", []):
        lines.append(f"\n## {component['component']} — {component['why']}")
        for section in component.get("sections", []):
            head = " / ".join(
                part
                for part in (section.get("headings"), section.get("title"))
                if part and part not in (section.get("headings") if part else "",)
            ) or str(section.get("headings") or section.get("title") or "")
            page = f", page {section['page']}" if section.get("page") else ""
            link = section.get("link_status")
            label = (
                f" [{link} link, {section.get('link_derivation') or 'unrecorded'}]" if link else ""
            )
            lines.append(f"\n[{section.get('section_id')}] {head}{page}{label}")
            if section.get("cells"):
                for cell in section["cells"]:
                    lines.append(f"    {cell['column']}: {cell['text']}")
            else:
                lines.append(str(section.get("text", "")).strip())
    notes = context.get("operator_notes") or []
    if notes:
        lines.append("\n## operator notes — the operator's own recorded decisions")
        for note in notes:
            lines.append(
                f"\n[{note['section_id']}] {note['kind']} about {note['subject_ref']}, "
                f"recorded {note['created_at'][:10]}"
                + (f" by {note['author']}" if note.get("author") else "")
            )
            lines.append(str(note.get("text", "")).strip())
    omitted = context.get("omitted") or []
    if omitted:
        # Loud, and it says what each missing component WOULD have answered.
        # Measured in the P6.8 small-seat probe: with the operator's own
        # sections outside the profile, every seat answered "are we stricter
        # than we need to be" confidently from an operator NOTE alone — and the
        # note turned out to misstate the procedure. A quiet footnote is not a
        # disclosure. The `why` text is the component's own description, not an
        # instruction about what to conclude.
        lines.append("\n## NOT IN THIS PACKET — you have not seen any of the following")
        for entry in omitted:
            lines.append(
                f"- **{entry['component']}** ({entry['sections']} sections, "
                f"~{entry['tokens']} tokens) — {entry['why']}. {entry['reason']}"
            )
        lines.append(
            "\nA question that depends on any of the above cannot be settled from what "
            "you have. Say which one you need."
        )
    return "\n".join(lines)


# ── citation verification (the one mechanical check that survives) ──────────


def _normalise_quantity(match: re.Match[str]) -> tuple[str, str]:
    number = re.sub(r"\s+", " ", match.group(1).lower())
    return _WORD_NUMBERS.get(number, number), match.group(2).lower().rstrip("s")


def _quantity_in(number: str, unit: str, haystack: str) -> bool:
    """Is this quantity stated in ``haystack``, in digits or in words?

    Tolerant of the shapes this material actually uses. A strict
    ``35\\s*\\S*\\s?day`` misses ``thirty-five (35) calendar days`` — the
    parenthesised digits sit between the word and the unit — and reporting a
    number as absent from the very section that states it is the worst thing
    this function can do.
    """
    if not haystack:
        return False
    spellings = [re.escape(number)]
    spellings += [w.replace("-", "[- ]") for w, digits in _WORD_NUMBERS.items() if digits == number]
    alternation = "|".join(sorted(spellings, key=len, reverse=True))
    return bool(re.search(rf"\b(?:{alternation})\b[^.;\n]{{0,30}}?\b{unit}s?\b", haystack, re.I))


def _nearest_citation(position: int, positions: list[tuple[int, str]]) -> str:
    """The citation a claim at ``position`` is pinned to: the first one that
    FOLLOWS it within the attribution window — a reader writes the claim, then
    the id — falling back to the most recent one just before it. A claim with no
    citation nearby is pinned to nothing, and says so."""
    after = [
        ref for start, ref in positions if position <= start <= position + _ATTRIBUTION_WINDOW_CHARS
    ]
    if after:
        return after[0]
    before = [
        ref for start, ref in positions if position - _ATTRIBUTION_WINDOW_CHARS <= start < position
    ]
    return before[-1] if before else ""


def _sentence_around(text: str, position: int) -> str:
    """The sentence a claim sits in, so a review pointer points at something a
    person can read without opening the transcript."""
    start = max(text.rfind(".", 0, position), text.rfind("\n", 0, position)) + 1
    end = min(
        (x for x in (text.find(".", position), text.find("\n", position)) if x != -1),
        default=len(text),
    )
    return text[start : end + 1].strip()


def verify_citations(repo: Any, answer: str, material: str = "") -> dict[str, Any]:
    """Resolve every id the answer cited, and report what each one IS.

    This adjudicates nothing. It reports:

    * whether the id resolves at all, in the pinned revision;
    * **what it resolves to** — jurisdiction, source kind, heading lineage,
      page — so an argument resting on the standard quoting itself as the
      operator's control is visible as exactly that, rather than passing as
      verified support (the ``_verify_duties`` defect, fixed here by resolving
      and labelling BOTH sides instead of checking one);
    * whether a quantity the answer claims appears in the text it cited.
    """
    from portal.modules.compliance.core.section_index import parent_section_id, resolve_sections

    normalised = answer.translate(_DASHES)
    cited = list(dict.fromkeys(CITATION_RE.findall(normalised)))
    resolved = resolve_sections(repo, cited)
    entries: list[dict[str, Any]] = []
    for ref in cited:
        entry = resolved.get(parent_section_id(ref))
        if entry is None:
            entries.append(
                {
                    "cited_ref": ref,
                    "resolved": False,
                    "detail": "does not resolve to any section in this store",
                }
            )
            continue
        entries.append(
            {
                "cited_ref": ref,
                "resolved": True,
                "resolves_to": _what_it_is(entry),
                "jurisdiction": entry.get("jurisdiction", ""),
                "source_kind": entry.get("source_kind", ""),
                "document": entry.get("document_title") or entry.get("logical_id", ""),
                "heading_lineage": entry.get("headings", ""),
                "page": entry.get("page_start"),
                "revision_id": entry.get("revision_id", ""),
                "effective_date": entry.get("effective_date"),
                "detail": "",
            }
        )

    # Attribution matters more than presence. Measured in the P6.8 seat probe:
    # three of four seats wrote "the operator's procedure evaluates every thirty
    # calendar days [isection-21a3…]" when that section says "thirty-five (35)".
    # The 30 was real — it came from an operator NOTE elsewhere in the packet —
    # so a check against the union of everything cited passed all three. A
    # quantity is therefore checked against the SECTION IT IS ATTRIBUTED TO:
    # the nearest citation that follows it in the sentence, or the nearest
    # preceding one. Sourcing a number from one document and pinning it to
    # another is exactly the shape of a confidently wrong compliance answer.
    texts = {
        ref: str(resolved[parent_section_id(ref)].get("text", ""))
        for ref in cited
        if parent_section_id(ref) in resolved
    }
    positions = [(m.start(), m.group(1)) for m in CITATION_RE.finditer(normalised)]
    quantities: list[dict[str, Any]] = []
    for match in _QUANTITY_RE.finditer(normalised):
        number, unit = _normalise_quantity(match)
        attributed = _nearest_citation(match.start(), positions)
        scope = texts.get(attributed or "", "")
        quantities.append(
            {
                "claim": match.group(0),
                "number": number,
                "unit": unit,
                "attributed_to": attributed,
                "appears_in_attributed_section": (
                    _quantity_in(number, unit, scope) if attributed else None
                ),
                "unattributed": not attributed,
                "sentence": _sentence_around(normalised, match.start()),
                "appears_somewhere_in_the_material": _quantity_in(
                    number, unit, "\n".join(texts.values()) + "\n" + material
                ),
            }
        )

    unresolved = [e["cited_ref"] for e in entries if not e["resolved"]]
    unsupported = [q["claim"] for q in quantities if q["appears_in_attributed_section"] is False]
    return {
        "citations": entries,
        "num_cited": len(entries),
        "unresolvable": unresolved,
        "quantities": quantities,
        "quantities_not_in_cited_text": unsupported,
        # A POINTER FOR A HUMAN, and deliberately not a verdict.
        #
        # Measured on the P6.8 transcripts, this signal is unreliable in both
        # directions on exactly the prose that matters — an answer that
        # correctly CONTRASTS two numbers:
        #
        #   false positive: "you are compressing the evaluation window by five
        #     days compared to the standard's 35-day maximum" — correct
        #     arithmetic, flagged because "five days" is not in the cited note.
        #   false negative: granite4.1:8b wrote "the operator's procedure
        #     evaluates every 30 calendar days" (it says thirty-five) and cited
        #     nothing within range, so nothing was flagged at all.
        #
        # Attribution is positional and prose is not. P6.3 says verify
        # citations and ADJUDICATE NOTHING, so this stays a pointer at a
        # sentence worth a human glance, carrying that sentence, and it is
        # named so no caller can mistake it for a judgement.
        "quantity_review_pointers": [
            {
                "claim": q["claim"],
                "nearest_citation": q["attributed_to"],
                "sentence": q["sentence"],
                "detail": (
                    "this number is in the packet but not in the nearest cited section — "
                    "may be a correct contrast, may be a misattribution; read it"
                ),
            }
            for q in quantities
            if q["appears_in_attributed_section"] is False
            and q["appears_somewhere_in_the_material"]
        ],
        "note": (
            "resolution and quantity attribution only — nothing here judges whether "
            "the answer is right, and no citation is disqualified"
        ),
    }


def _what_it_is(entry: dict[str, Any]) -> str:
    """A plain label for what a citation resolves to, from the section's own
    position and its document's own kind. No judgement, no eligibility."""
    kind = str(entry.get("source_kind") or "")
    heading = str(entry.get("headings") or "").lower()
    if kind == "glossary":
        return "NERC Glossary term"
    if kind == "operator_note":
        return "operator note — the operator's own recorded decision"
    if kind == "derived_answer":
        return "a stored answer from an earlier conversation, not a fact"
    if kind == "regulatory_standard":
        if "technical basis" in heading:
            return "regulatory — Guidelines and Technical Basis (interpretive, the standard's own)"
        if "compliance" in heading:
            return "regulatory — compliance and evidence retention"
        if "version history" in heading:
            return "regulatory — version history"
        if entry.get("unit_kind") == "table_row" and "requirements and measures" in heading:
            return "regulatory — a requirements table row (Part, Applicable Systems, Requirements, Measures)"
        return "regulatory — standard text"
    if kind in ("implementation_plan", "technical_rationale", "rsaw"):
        return f"regulatory companion document — {kind.replace('_', ' ')}"
    if str(entry.get("jurisdiction")) == "internal":
        return f"operator document — {kind.replace('_', ' ') or 'unclassified'}"
    return kind or "unclassified source"


# ── the reading call ────────────────────────────────────────────────────────


#: Run before the model speaks, on every reading. Acquisition is not the seat's
#: to elect: measured live, Qwen3.8 answered the parent-level R2 question in
#: prose on the first turn, called nothing, and the loop accepted it. Both
#: operations are deterministic, so they sit inside the cacheable prefix.
BOOTSTRAP_TOOLS = ("compliance_requirement", "compliance_links")


def _acquire(
    repo: Any, ref: str, *, max_chars: int, trace: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], dict[str, set[str]]]:
    """The recorded first acquisition: the requirement packet, and the
    deterministic enumeration of the operator sections linked to it.

    ``compliance_links`` returns EDGES, not text, so what it names is
    ENUMERATED, never examined — counting those ids as read would let one call
    mark every linked section read without a word of it reaching the model.
    """
    from portal.modules.compliance.core.reading_tools import dispatch

    messages: list[dict[str, Any]] = []
    ids: dict[str, set[str]] = {"examined": set(), "enumerated": set()}
    for name in BOOTSTRAP_TOOLS:
        arguments = {"ref": ref}
        acquired = dispatch(repo, name, arguments, max_chars=max_chars)
        bucket = "enumerated" if name == "compliance_links" else "examined"
        ids[bucket].update(str(section_id) for section_id in acquired.get("section_ids", []))
        trace.append(
            {
                "step": 0,
                "tool": name,
                "derivation": "bootstrap",
                "section_ids": acquired.get("section_ids", []),
                "error": bool(acquired.get("error")),
            }
        )
        messages.extend(
            [
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [{"function": {"name": name, "arguments": arguments}}],
                },
                {
                    "role": "tool",
                    "tool_name": name,
                    "content": json.dumps(acquired.get("payload", acquired), default=str),
                },
            ]
        )
    return messages, ids


def _outstanding(population: dict[str, Any], examined: set[str]) -> str:
    """What is recorded as part of this requirement and has NOT been read yet.

    Measured on the live Part 2.2 reading with the acquisition in place and this
    disclosure absent: the seat answered in 3,709 characters, made ZERO tool
    calls, cited three sections and none of the operator's own — with the
    operator's patch procedure sitting unread in the population. It was not a
    capability failure (the same seat calls `compliance_read` correctly when
    asked to). Nothing had told it there was anything left to read.

    So the unread population is stated, with the same discipline the assembly
    already applies to what a budget could not hold: **omissions are named**. It
    imposes no output shape and demands no verdict — it says which ids exist,
    which side each is, and that reading them is available.
    """
    sections = population.get("sections") or {}
    unread = [
        (section_id, entry) for section_id, entry in sections.items() if section_id not in examined
    ]
    if not unread:
        return ""
    operator = [s for s, e in unread if e.get("side") == "operator"]
    lines = [
        f"{len(unread)} section(s) recorded as part of {population.get('ref')} are NOT in "
        "what you have been given, and you have not read them:",
        "",
    ]
    for section_id, entry in unread:
        side = str(entry.get("side", ""))
        label = (
            f"operator document, {entry.get('link_status', 'linked')} link to "
            f"{entry.get('requirement_id', '')}"
            if side == "operator"
            else f"regulatory, {entry.get('relation', '')} for {entry.get('requirement_id', '')}"
        )
        lines.append(f"- {section_id} — {label}")
    lines.append("")
    lines.append(
        "`compliance_read` takes any of these ids and returns the verbatim text. Read what "
        "your answer depends on, and say plainly which of them you did not read and why."
    )
    if operator:
        lines.append(
            f"{len(operator)} of them are the operator's OWN documents. An answer about what "
            "the operator does, written without reading them, is an answer about the standard."
        )
    return "\n".join(lines)


def _closure_failure(
    *,
    model_calls: int,
    eligible: set[str],
    cited: set[str],
    unread: list[str],
    absence_claim: bool,
) -> str:
    """``unread`` here is the UNDECLARED remainder: a section the answer names as
    one it did not read is accounted for, and does not bar an absence claim."""
    """The control contract, in the order a reading fails it.

    A terminal prose answer with no tool call at all used to be accepted as
    success: ``failed`` was set only when the narrow absence regex happened to
    fire, so ordinary unsupported prose travelled as a sound reading. That is
    exactly what the live parent-level run did, and exactly what the loop
    permitted.
    """
    if not model_calls:
        return (
            "the model answered without reading: it made no tool call, so the answer "
            f"rests on the acquired packet alone out of {len(eligible)} eligible section(s)"
        )
    if eligible and not (cited & eligible):
        return (
            f"the answer cites no section in scope: {len(eligible)} section(s) were "
            "eligible and none of them is cited"
        )
    if absence_claim and unread:
        return (
            "answer asserts an absence with "
            f"{len(unread)} eligible section(s) neither read nor named as unread"
        )
    return ""


def _dispatch_calls(
    repo: Any,
    calls: list[Any],
    *,
    step: int,
    max_chars: int,
    thread: list[dict[str, Any]],
    examined: set[str],
    enumerated: set[str],
    trace: list[dict[str, Any]],
) -> None:
    """Run one turn's model-elected tool calls and append their results.

    ``compliance_links`` hands back the EDGE LIST, so what it names is
    ENUMERATED, never examined — counting those ids as read would let one call
    mark every linked section read without a word of it reaching the model.
    """
    from portal.modules.compliance.core.reading_tools import dispatch

    for call in calls:
        function = call.get("function", call) if isinstance(call, dict) else {}
        name = str(function.get("name", ""))
        arguments = function.get("arguments", {})
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except json.JSONDecodeError:
                arguments = {}
        result = dispatch(
            repo, name, arguments if isinstance(arguments, dict) else {}, max_chars=max_chars
        )
        target = enumerated if name == "compliance_links" else examined
        target.update(str(section_id) for section_id in result.get("section_ids", []))
        trace.append(
            {
                "step": step + 1,
                "tool": name,
                "derivation": "model",
                "section_ids": result.get("section_ids", []),
                "error": bool(result.get("error")),
            }
        )
        thread.append(
            {
                "role": "tool",
                "tool_name": name,
                "content": json.dumps(result.get("payload", result), default=str),
            }
        )


def read(  # noqa: PLR0912, PLR0915
    repo: Any,
    question: str,
    ref: str,
    *,
    model: str,
    budget_tokens: int = 6000,
    profile: str = "",
    num_ctx: int = 0,
    reasoning_effort: bool | str | None = None,
    answer_tokens: int = 3072,
    reasoning_allowance: int = 0,
    prompt_path: Path | None = None,
    valid_at: str = "",
    thread_id: str = "",
    store: bool = True,
    retain_run: bool = True,
    timeout: int = 900,
) -> dict[str, Any]:
    """Drive one bounded reading conversation and retain its receipt.

    ``budget_tokens`` is retained for API compatibility but is now the maximum
    per-tool-result character budget.  The seed is deliberately small; the
    agent must retrieve and read the material it relies on.

    ``store`` projects the ANSWER into the corpus as a derived source.
    ``retain_run`` retains the RECEIPT — scope, tool trace, closure, transcript
    and timings — and defaults on independently, because a reading that failed
    is the one most worth having a record of and is exactly the one that must
    not be projected as an answer.
    """
    from portal.modules.compliance.core import requirement_scope
    from portal.modules.compliance.core.notes import notes_for
    from portal.modules.compliance.core.reading_assembly import CHARS_PER_TOKEN, assemble
    from portal.modules.compliance.core.reading_tools import TOOL_SCHEMAS
    from portal.modules.compliance.core.reading_transport import (
        DEFAULT_NUM_CTX,
        DEFAULT_REASONING_ALLOWANCE,
        ChatResult,
        ContextCeilingError,
        chat,
    )

    if profile:
        return {
            "error": (
                "profile= is closed: the agent chooses material through its tools; "
                "remove profile and ask the question directly"
            ),
            "ref": ref,
            "failed": True,
        }

    context = assemble(
        repo,
        ref,
        budget_tokens=max(2048, min(int(budget_tokens), 12000)),
        include=["requirement"],
        valid_at=valid_at,
    )
    if "error" in context:
        return {"error": context["error"], "ref": ref}
    # Across the scope: a parent requirement's notes sit on its Parts, exactly
    # as its anchors and its edges do.
    context["operator_notes"] = [
        note
        for identity in requirement_scope.resolve(repo, ref).refs
        for note in notes_for(repo, identity)
    ]
    seed = _render_material(context)
    prior: list[dict[str, Any]] = []
    if thread_id:
        rows = repo._conn.execute(
            """SELECT question, answer, superseded_at FROM conversation_answers
               WHERE thread_id = ? AND subject_ref = ? ORDER BY asked_at""",
            (thread_id, ref),
        ).fetchall()
        for row in rows:
            standing = (
                "\n\n[standing superseded: the revision cited by this answer has moved]"
                if row[2]
                else ""
            )
            prior.extend(
                [
                    {"role": "user", "content": str(row[0])},
                    {"role": "assistant", "content": str(row[1]) + standing},
                ]
            )

    max_chars = max(1000, min(int(budget_tokens), 12000))
    examined: set[str] = set()
    enumerated: set[str] = set()
    tool_trace: list[dict[str, Any]] = []

    # The material handed over unasked is READ material, and the closure has to
    # count it as read. Leaving the seed out of `examined` made every reading
    # start owing the receipt sections it had already been given.
    examined.update(
        str(section.get("section_id", ""))
        for component in context.get("components", [])
        for section in component.get("sections", [])
        if section.get("section_id")
    )
    # The operator's notes travel in the seed too, under their own key rather
    # than as a component. Left out of this, a reading was handed the note and
    # then billed for not having read it: three live Part 2.2 runs came back
    # `examined=18 unread=1 complete=false`, and the one unread section was the
    # note quoted in the answer.
    examined.update(
        str(note.get("section_id", ""))
        for note in context.get("operator_notes", [])
        if note.get("section_id")
    )

    # P6.9: ACQUISITION IS NOT THE MODEL'S TO ELECT. The loop used to open with
    # nothing but the seed and hope the seat chose to call a tool; measured
    # live, Qwen3.8 answered the parent-level R2 question in prose on the first
    # turn, called nothing, and the loop accepted it. Two operations are
    # therefore RUN and RECORDED before the model speaks: the requirement packet
    # it is being asked about, and the deterministic enumeration of the operator
    # sections linked to it. Both are identical on every turn of a thread, so
    # they sit inside the cacheable prefix rather than costing a re-prefill.
    bootstrap, acquired_ids = _acquire(repo, context["ref"], max_chars=max_chars, trace=tool_trace)
    examined.update(acquired_ids["examined"])
    enumerated.update(acquired_ids["enumerated"])

    # The population is resolved BEFORE the reading, not after it, because the
    # reader has to be told what it has not read while it can still act on that.
    # The same object is the closure's eligible set, so the reading is judged
    # against exactly the population it was shown.
    population = requirement_scope.population(repo, context["ref"], valid_at=valid_at)

    # system -> material -> the recorded acquisition -> prior turns -> the
    # question now being asked. The prior turns used to be appended AFTER the
    # current question, so on turn two the last message in the thread was an old
    # assistant answer and the model was replying to its own previous turn.
    outstanding = _outstanding(population, examined)
    system_prompt, prompt_version, prompt_sha = load_prompt(prompt_path)
    thread: list[dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": seed},
        *bootstrap,
        *([{"role": "user", "content": outstanding}] if outstanding else []),
        *prior,
        {"role": "user", "content": f"The analyst asks:\n\n{question}"},
    ]
    # The estimate covers everything the FIRST call actually ships, which since
    # the acquisition became deterministic is the seed plus both recorded tool
    # payloads. Sizing the window from the seed alone under-counts, and
    # under-counting is the dangerous direction: it reserves a window too small
    # and the material is silently truncated, which is the keyhole returning.
    prefix = (
        seed
        + "".join(
            str(message.get("content", "")) for message in bootstrap if message["role"] == "tool"
        )
        + outstanding
    )
    estimated_prompt = int(len(prefix) / CHARS_PER_TOKEN)
    needed = estimated_prompt + answer_tokens + 2048
    # The window is fixed once, on the first turn — and then the loop APPENDS a
    # tool result per call, up to `max_steps` of them at `max_chars` each. Sizing
    # it from the first turn's prefix alone therefore sizes it for the smallest
    # thread this reading will ever have. On Ollama 0.34.0 an overflowing prompt
    # is not truncated: it is HTTP 400 `exceed_context_size_error`, which kills
    # the reading outright. So the floor is the transport's own default, which
    # is sized for the worst case this loop can build.
    #
    # `CHARS_PER_TOKEN` (2.1) OVER-counts on this material — measured at 4.22
    # chars/token on the seat (140,000 chars -> 33,142 prompt tokens), so the
    # estimate reserves about twice the window it needs. That is the safe
    # direction and it is left alone deliberately: the number that must never be
    # optimistic is the one that reserves the window.
    window = num_ctx or max(DEFAULT_NUM_CTX, -(-needed // 4096) * 4096)
    answer_result: Any = None
    stop_reason = ""
    model_calls = 0
    max_steps = 12
    ceiling_failure = ""
    for step in range(max_steps):
        try:
            answer_result = chat(
                model,
                messages=thread,
                tools=TOOL_SCHEMAS,
                answer_budget=answer_tokens,
                reasoning_allowance=reasoning_allowance or DEFAULT_REASONING_ALLOWANCE,
                fmt=None,
                think=reasoning_effort,
                num_ctx=window,
                timeout=timeout,
            )
        except ContextCeilingError as exc:
            # A reading whose thread outgrew its window is a FAILED reading with
            # a named reason, not an exception escaping into a generic handler
            # that reports it as a transport error of unknown kind.
            ceiling_failure = str(exc)
            stop_reason = f"context ceiling reached at step {step + 1}: {exc}"
            if answer_result is None:
                # Failed on the FIRST call: there is no result to report from, so
                # an empty one is constructed rather than letting the receipt
                # code dereference None.
                answer_result = ChatResult(content="", thinking="", num_ctx=window, model=model)
            break
        calls = list(
            getattr(answer_result, "tool_calls", []) or answer_result.get("tool_calls", [])
        )
        raw_message = dict(
            getattr(answer_result, "raw_message", {}) or answer_result.get("raw_message", {})
        )
        if not calls:
            stop_reason = "model returned an answer"
            break
        model_calls += len(calls)
        thread.append(raw_message or {"role": "assistant", "tool_calls": calls})
        _dispatch_calls(
            repo,
            calls,
            step=step,
            max_chars=max_chars,
            thread=thread,
            examined=examined,
            enumerated=enumerated,
            trace=tool_trace,
        )
    else:
        stop_reason = f"max_steps={max_steps} reached before the model returned an answer"

    answer = (answer_result.content if answer_result is not None else "").strip()
    if not stop_reason:
        stop_reason = f"max_steps={max_steps} reached"
    # What the model actually had in front of it on its first turn, which is
    # what "appears somewhere in the material" has to mean.
    material = prefix
    # The estimate is for the seed sent on the first turn. Later tool results
    # are accounted for by the receipt and the per-tool truncation disclosure.
    result = answer_result
    # An empty answer is a FAILED reading, and it must say so rather than travel
    # as a very short one. Measured on this call site (P6.7): with reasoning
    # enabled at "low" or "medium", Qwen3.8 spent the whole 1,600-token budget
    # inside `thinking` and emitted zero characters of content — 450 s and
    # 6,382 characters of reasoning for nothing. The same call with
    # `think: false` returned a complete, seven-citation, 4,756-character
    # answer. Returning "" as an answer would make that look like a terse model.
    # A budget error, named by the transport, which retried once at double the
    # reasoning allowance before giving up. It is never a substantive answer and
    # never evidence about reasoning — only about the budget it was given.
    exhausted = result.get("stop_reason") == "budget_exhausted_in_reasoning" or bool(
        not answer and result.thinking
    )
    verification = verify_citations(repo, answer, material)
    # P4.3: assembly, disclosure and closure resolve the SAME scope, from the one
    # `population` object built before the reading. Computing the eligible set
    # from an exact match on the ref as asked is what emptied it: `CIP-007-6 R2`
    # holds no anchors and no edges of its own — its four Parts hold all of them
    # — so the receipt reported eligible=[] examined=[] and classified the
    # answer's own regulatory citations as `outside`.
    eligible = {str(section_id) for section_id in population.get("section_ids", [])}
    cited = {
        str(entry.get("cited_ref"))
        for entry in verification.get("citations", [])
        if entry.get("resolved")
    }
    outside = sorted(cited - eligible)
    unread = sorted(eligible - examined)
    # An eligible section the answer NAMES is accounted for even when it was not
    # read: the disclosure asks the reader to read what its answer depends on
    # and to say plainly what it did not read and why, so a declared omission is
    # compliance with the contract, not a breach of it.
    #
    # Measured on three live Part 2.2 runs: the seat wrote "I did not read
    # csection-754b… (the regulatory applicable_systems cell) because that text
    # is already reproduced in the requirement row I have" — correct, checkable,
    # and scored as an undisclosed gap. Meanwhile its one absence claim ("I have
    # no evidence of actual evaluation dates") was about records the corpus does
    # not contain, which is the kind of absence a reading exists to surface.
    normalised_answer = answer.translate(_DASHES)
    omitted_with_reason = [section_id for section_id in unread if section_id in normalised_answer]
    undeclared_unread = [section_id for section_id in unread if section_id not in normalised_answer]
    absence_claim = bool(
        re.search(
            r"\b(?:no|none|not found|does not|without)\b.{0,80}\b(?:evidence|section|control|procedure|link)",
            answer,
            re.I,
        )
    )
    operator_eligible = {
        section_id
        for section_id, entry in (population.get("sections") or {}).items()
        if entry.get("side") == "operator"
    }
    closure = {
        "population_method": population.get("population_method"),
        "scope": population.get("scope"),
        "population_detail": population.get("detail"),
        # every eligible section with the leaf identity it belongs to, which side
        # it is, and — for an operator edge — whether it is approved or merely
        # proposed. A population built entirely from proposed edges must not read
        # like one built from approved ones.
        "population": population.get("sections"),
        "eligible": sorted(eligible),
        "examined": sorted(examined),
        "outside": outside,
        "unread": unread,
        # read, or named as not-read: the two ways a section is accounted for
        "omitted_with_reason": omitted_with_reason,
        "undeclared_unread": undeclared_unread,
        "accounted_for": bool(eligible) and not undeclared_unread,
        # Enumerated is not examined: `compliance_links` hands back the edge
        # list, so a section named there has been COUNTED, not read.
        "enumerated": sorted(enumerated),
        "operator_eligible": sorted(operator_eligible),
        "operator_examined": sorted(operator_eligible & examined),
        "operator_cited": sorted(operator_eligible & cited),
        "prompt_version": prompt_version,
        "prompt_sha": prompt_sha,
        "model_tool_calls": model_calls,
        "complete": bool(eligible) and not unread,
        "stop_reason": stop_reason,
        "tool_trace": tool_trace,
    }
    # The control contract, in the order a reading fails it.
    #
    # A terminal prose answer with no tool call at all was accepted as success:
    # `failed` was set only when the narrow absence regex happened to fire, so
    # ordinary unsupported prose travelled as a sound reading. That is precisely
    # what the live parent-level run did, and precisely what the loop permitted.
    closure_failure = _closure_failure(
        model_calls=model_calls,
        eligible=eligible,
        cited=cited,
        unread=undeclared_unread,
        absence_claim=absence_claim,
    )
    # The estimate is checked against the runner's own count on every call. An
    # under-estimate is the dangerous direction: it sizes the window too small
    # and the material is silently truncated, which is the keyhole returning.
    actual_prompt = int(result.get("prompt_eval_count") or 0)
    generated = int(result.get("eval_count") or 0)
    # The ratio is thread chars over prompt tokens, not MATERIAL chars over
    # prompt tokens. `material` is the first-turn prefix — the seed and the
    # acquisition payloads — while `prompt_eval_count` is for the WHOLE thread
    # the last call shipped, system prompt, question, tool results and all.
    # Dividing one by the other reported 1.4 chars/token on a live run where the
    # true figure is 3.15, i.e. an apparent ratio less than half the real one. A
    # calibration constant taken from that would size every window at less than
    # half of what it needs, which is the direction that refuses the prompt.
    thread_chars = sum(len(str(message.get("content", "") or "")) for message in thread)
    fit = {
        "estimated_prompt_tokens": estimated_prompt,
        "actual_prompt_tokens": actual_prompt,
        "thread_chars": thread_chars,
        "material_chars": len(material),
        "chars_per_token_observed": (
            round(thread_chars / actual_prompt, 2) if actual_prompt else None
        ),
        "num_ctx": window,
        "headroom_tokens": window - actual_prompt - generated,
        "overflowed": bool(actual_prompt and actual_prompt + generated >= window),
        "estimate_error_pct": (
            round(100 * (estimated_prompt - actual_prompt) / actual_prompt, 1)
            if actual_prompt
            else None
        ),
    }
    payload: dict[str, Any] = {
        "question": question,
        "ref": context["ref"],
        "answer": answer,
        "thinking_chars": len(result.thinking),
        "model": model,
        # The prompt is an input like any other, and the one that moves the
        # answer most. Recorded on the payload, the stored answer, the receipt
        # and every acceptance row, so "did the prompt change help" is a
        # question with an answer.
        "prompt_version": prompt_version,
        "prompt_sha": prompt_sha,
        # REQUESTED is not APPLIED. `num_ctx` is what the call asked for;
        # `applied` is what /api/ps says the runner loaded.
        "num_ctx": window,
        "applied_settings": {
            "num_ctx_requested": window,
            "num_ctx_applied": result.get("num_ctx_applied"),
            "seat_ceiling": result.get("seat_ceiling"),
            "temperature": result.get("temperature"),
            "answer_budget": result.get("answer_budget"),
            "reasoning_allowance": result.get("reasoning_allowance"),
            "num_predict": result.get("num_predict"),
            "attempts": result.get("attempts"),
            "transport_stop_reason": result.get("stop_reason"),
        },
        "material_chars": len(material),
        "material_tokens": len(material) // CHARS_PER_TOKEN,
        "profile": "agent",
        "components": [c["component"] for c in context["components"]],
        "omitted": context["omitted"],
        "verification": verification,
        "failed": bool(exhausted or ceiling_failure or not answer or closure_failure),
        "failure": (
            (
                (
                    "budget_exhausted_in_reasoning: the answer came back empty with "
                    f"{len(result.thinking)} characters of reasoning, after a retry at "
                    f"double the allowance (attempts: {result.get('attempts')}). This is a "
                    "BUDGET result, not a reasoning result and not an answer."
                )
                if result.get("stop_reason") == "budget_exhausted_in_reasoning"
                else (
                    "the answer came back empty with "
                    f"{len(result.thinking)} characters of reasoning although reasoning was "
                    f"OFF for this call (effort={result.get('reasoning_effort')}): the "
                    "template reasoned anyway and spent the answer budget doing it. This is "
                    "a BUDGET result, not a reasoning result and not an answer."
                )
            )
            if exhausted
            else (
                ceiling_failure
                or closure_failure
                or ("the model produced no answer" if not answer else "")
            )
        ),
        "closure_receipt": closure,
        "context_fit": fit,
        "latency": {
            "elapsed_s": round(float(result.get("elapsed", 0)), 2),
            "load_duration_s": result.get("load_duration_s"),
            "prompt_eval_duration_s": result.get("prompt_eval_duration_s"),
            "eval_duration_s": result.get("eval_duration_s"),
            "eval_count": result.get("eval_count"),
            "prompt_eval_count": result.get("prompt_eval_count"),
            "prompt_bytes": result.get("prompt_bytes"),
        },
        "reasoning_effort": result.get("reasoning_effort"),
        "reasoning_downgraded": result.get("downgraded", ""),
    }
    if store:
        payload["answer_id"] = store_answer(repo, payload, context, thread_id=thread_id)
        if not re.search(r"\b(?:hypothetical|scenario|if we|suppose)\b", question, re.I):
            from portal.modules.compliance.core.candidate_links import links_from_answer

            payload["proposed_links"] = links_from_answer(
                repo, payload["answer_id"], context["ref"]
            )
    if retain_run:
        payload["run_id"] = store_run(repo, payload, context, thread=thread, thread_id=thread_id)
    return payload


# ── the conversation corpus ─────────────────────────────────────────────────


def store_answer(
    repo: Any, payload: dict[str, Any], context: dict[str, Any], *, thread_id: str = ""
) -> str:
    """Retain one answer, its citations and its provenance, and project it into
    the corpus as a ``derived`` source.

    A stored answer is never a fact. It is one analyst's notes pinned to the
    revisions it read, and it says so wherever it is returned.
    """
    from pathlib import Path

    from portal.modules.compliance.core.capture import CapturedDocument, CapturedUnit, store_capture
    from portal.modules.compliance.core.models import SourceDocument
    from portal.modules.compliance.core.temporal import now_iso

    asked_at = now_iso()
    answer_id = (
        "answer-"
        + hashlib.sha256(
            f"{payload['question']}|{payload['answer']}|{asked_at}".encode()
        ).hexdigest()[:20]
    )
    latency = payload.get("latency", {})
    with repo._lock, repo._conn:
        repo._conn.execute(
            """INSERT INTO conversation_answers(answer_id, thread_id, asked_at, question,
                   answer, model, subject_ref, elapsed_s, eval_count, prompt_bytes,
                   load_duration_s, reasoning_effort, num_ctx, prompt_version, prompt_sha,
                   org_id)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'default')
               ON CONFLICT(answer_id) DO NOTHING""",
            (
                answer_id,
                thread_id,
                asked_at,
                payload["question"],
                payload["answer"],
                payload.get("model", ""),
                payload.get("ref", ""),
                float(latency.get("elapsed_s") or 0),
                int(latency.get("eval_count") or 0),
                int(latency.get("prompt_bytes") or 0),
                float(latency.get("load_duration_s") or 0),
                str(payload.get("reasoning_effort", "")),
                int(payload.get("num_ctx") or 0),
                str(payload.get("prompt_version", "")),
                str(payload.get("prompt_sha", "")),
            ),
        )
        repo._conn.executemany(
            """INSERT INTO answer_citations(answer_id, cited_ref, resolved, resolves_to,
                   revision_id, jurisdiction, source_kind, detail)
               VALUES (?,?,?,?,?,?,?,?)
               ON CONFLICT(answer_id, cited_ref) DO NOTHING""",
            [
                (
                    answer_id,
                    entry["cited_ref"],
                    1 if entry["resolved"] else 0,
                    entry.get("resolves_to", ""),
                    entry.get("revision_id", ""),
                    entry.get("jurisdiction", ""),
                    entry.get("source_kind", ""),
                    entry.get("detail", ""),
                )
                for entry in payload["verification"]["citations"]
            ],
        )

    logical_id = f"answer/{answer_id}"
    body = (
        f"Q: {payload['question']}\n\n{payload['answer']}\n\n"
        f"[stored answer about {payload.get('ref', '')}, read from revision "
        f"{context.get('revision_id', '')} by {payload.get('model', '')} on {asked_at[:10]}. "
        f"One analyst's notes pinned to the revisions it read — not a fact, and outranked "
        f"by any operator note on the same subject.]\n"
    )
    repo.upsert_source_document(
        SourceDocument(
            logical_id=logical_id,
            title=payload["question"][:120],
            issuer=payload.get("model", ""),
            source_kind="derived_answer",
            jurisdiction="derived",
        )
    )
    revision = repo.add_document_revision(
        logical_id, logical_id, body.encode(), binding_effect="descriptive"
    )
    store_capture(
        repo,
        revision.revision_id,
        CapturedDocument(
            path=Path(logical_id),
            page_count=1,
            full_text=body,
            units=[
                CapturedUnit(
                    ordinal=0,
                    unit_kind="prose",
                    heading_path=f"stored answer about {payload.get('ref', '')}",
                    title=payload["question"][:120],
                    page_start=1,
                    page_end=1,
                    char_start=0,
                    char_end=len(body),
                    text=body,
                )
            ],
            extractor="conversation",
            extractor_version="1",
            reader_strings=(payload["answer"],),
        ),
    )
    return answer_id


def store_run(
    repo: Any,
    payload: dict[str, Any],
    context: dict[str, Any],
    *,
    thread: list[dict[str, Any]],
    thread_id: str = "",
) -> str:
    """Retain one reading RUN: what was in scope, what was actually called, what
    the receipt said, and the transcript that produced it.

    ``conversation_answers`` keeps the prose, the timing and the citations —
    enough to re-read an answer, not enough to audit one. The closure receipt,
    the scope it was computed over, the tool trace and the tool messages
    themselves lived only in the returned payload, so the receipt a live reading
    produced was gone the moment the process exited. A run is retained whether
    or not the answer was projected into the corpus, and **whether or not the
    reading failed** — a failed reading is the one most worth keeping.
    """
    from portal.modules.compliance.core.temporal import now_iso

    asked_at = now_iso()
    closure = payload.get("closure_receipt", {}) or {}
    run_id = (
        "run-"
        + hashlib.sha256(
            f"{payload.get('question', '')}|{payload.get('ref', '')}|{asked_at}".encode()
        ).hexdigest()[:20]
    )
    messages = json.dumps(thread, default=str)
    with repo._lock, repo._conn:
        repo._conn.execute(
            """INSERT INTO reading_runs(run_id, answer_id, thread_id, asked_at, subject_ref,
                   question, answer, model, failed, failure, stop_reason, scope_json,
                   closure_json, tool_trace_json, messages_json, verification_json,
                   latency_json, context_fit_json, prompt_fingerprint, material_fingerprint,
                   revision_id, reasoning_effort, num_ctx, prompt_version, prompt_sha, org_id)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'default')
               ON CONFLICT(run_id) DO NOTHING""",
            (
                run_id,
                str(payload.get("answer_id", "")),
                thread_id,
                asked_at,
                str(payload.get("ref", "")),
                str(payload.get("question", "")),
                str(payload.get("answer", "")),
                str(payload.get("model", "")),
                1 if payload.get("failed") else 0,
                str(payload.get("failure", "")),
                str(closure.get("stop_reason", "")),
                json.dumps(closure.get("scope", {}), default=str),
                json.dumps(closure, default=str),
                json.dumps(closure.get("tool_trace", []), default=str),
                messages,
                json.dumps(payload.get("verification", {}), default=str),
                json.dumps(payload.get("latency", {}), default=str),
                json.dumps(payload.get("context_fit", {}), default=str),
                hashlib.sha256(messages.encode()).hexdigest()[:20],
                hashlib.sha256(str(context.get("ref", "")).encode()).hexdigest()[:20],
                str(context.get("revision_id", "")),
                str(payload.get("reasoning_effort", "")),
                int(payload.get("num_ctx") or 0),
                str(payload.get("prompt_version", "")),
                str(payload.get("prompt_sha", "")),
            ),
        )
    return run_id


def runs_for(
    repo: Any, subject_ref: str = "", *, thread_id: str = "", limit: int = 50
) -> list[dict[str, Any]]:
    """Retained reading runs, newest first, each with its receipt decoded."""
    clauses, params = [], []
    if subject_ref:
        clauses.append("subject_ref = ?")
        params.append(subject_ref)
    if thread_id:
        clauses.append("thread_id = ?")
        params.append(thread_id)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    rows = repo._conn.execute(
        f"SELECT * FROM reading_runs {where} ORDER BY asked_at DESC LIMIT ?",  # noqa: S608
        (*params, int(limit)),
    ).fetchall()
    out: list[dict[str, Any]] = []
    for row in rows:
        entry = dict(row)
        for column in (
            "scope_json",
            "closure_json",
            "tool_trace_json",
            "messages_json",
            "verification_json",
            "latency_json",
            "context_fit_json",
        ):
            entry[column.removesuffix("_json")] = json.loads(entry.pop(column) or "null")
        entry["failed"] = bool(entry["failed"])
        out.append(entry)
    return out


def supersede_answers_for_revisions(repo: Any, revision_ids: list[str]) -> list[str]:
    """Mark stored answers superseded when a revision they cited moves.

    An answer is pinned to what it read. When that text is replaced, the answer
    is not wrong — it is about a document that no longer governs, which is a
    different thing and must be visible as one.
    """
    from portal.modules.compliance.core.temporal import now_iso

    if not revision_ids:
        return []
    marks = ",".join("?" for _ in revision_ids)
    rows = repo._conn.execute(
        f"""SELECT DISTINCT a.answer_id FROM conversation_answers a
            JOIN answer_citations c ON c.answer_id = a.answer_id
            WHERE c.revision_id IN ({marks}) AND a.superseded_at IS NULL""",  # noqa: S608
        tuple(revision_ids),
    ).fetchall()
    ids = [str(r[0]) for r in rows]
    if ids:
        stamp = now_iso()
        with repo._lock, repo._conn:
            repo._conn.executemany(
                "UPDATE conversation_answers SET superseded_at = ? WHERE answer_id = ?",
                [(stamp, answer_id) for answer_id in ids],
            )
    return ids


def record_correction(
    repo: Any, answer_id: str, correction: str, author: str = ""
) -> dict[str, Any]:
    """An operator's correction of a stored answer. Recorded as a NOTE about the
    answer — the operator's word outranks the reading, and both remain."""
    from portal.modules.compliance.core.notes import write_note

    note = write_note(
        repo,
        subject_ref=answer_id,
        body=correction,
        kind="correction",
        author=author,
    )
    with repo._lock, repo._conn:
        repo._conn.execute(
            "UPDATE conversation_answers SET correction_of = ? WHERE answer_id = ?",
            (note["note_id"], answer_id),
        )
    return note


def answers_for(
    repo: Any, subject_ref: str = "", *, include_superseded: bool = True
) -> list[dict[str, Any]]:
    """Stored answers about a subject, newest first, each with its citations and
    its standing relative to any operator note on the same subject."""
    clause = "WHERE subject_ref = ?" if subject_ref else ""
    params: tuple[Any, ...] = (subject_ref,) if subject_ref else ()
    if not include_superseded:
        clause += (" AND " if clause else "WHERE ") + "superseded_at IS NULL"
    rows = repo._conn.execute(
        f"SELECT * FROM conversation_answers {clause} ORDER BY asked_at DESC LIMIT 200",  # noqa: S608
        params,
    ).fetchall()
    out: list[dict[str, Any]] = []
    notes = {
        str(r[0])
        for r in repo._conn.execute(
            "SELECT subject_ref FROM operator_notes WHERE subject_ref = ?", (subject_ref,)
        ).fetchall()
    }
    for row in rows:
        entry = dict(row)
        entry["citations"] = [
            dict(c)
            for c in repo._conn.execute(
                "SELECT * FROM answer_citations WHERE answer_id = ?", (entry["answer_id"],)
            ).fetchall()
        ]
        entry["standing"] = (
            "one analyst's notes pinned to the revisions it read — "
            + ("SUPERSEDED: a revision it cited has moved" if entry["superseded_at"] else "current")
            + ("; an operator note on this subject outranks it" if notes else "")
        )
        out.append(entry)
    return out


# ── standing questions ──────────────────────────────────────────────────────


def add_standing_question(repo: Any, question: str, subject_ref: str = "") -> str:
    """A question the operator already cares about. Run on ingest and on every
    auto-sync change — that IS the initial assessment, rather than a schema
    filled in by a machine nobody asked."""
    from portal.modules.compliance.core.temporal import now_iso

    question_id = "sq-" + hashlib.sha256(f"{question}|{subject_ref}".encode()).hexdigest()[:16]
    with repo._lock, repo._conn:
        repo._conn.execute(
            """INSERT INTO standing_questions(question_id, question, subject_ref, created_at,
                   active, org_id) VALUES (?,?,?,?,1,'default')
               ON CONFLICT(question_id) DO UPDATE SET active = 1""",
            (question_id, question, subject_ref, now_iso()),
        )
    return question_id


def standing_questions(repo: Any, subject_ref: str = "") -> list[dict[str, Any]]:
    clause = "WHERE active = 1"
    params: tuple[Any, ...] = ()
    if subject_ref:
        clause += " AND (subject_ref = ? OR subject_ref = '')"
        params = (subject_ref,)
    rows = repo._conn.execute(
        f"SELECT * FROM standing_questions {clause} ORDER BY created_at",  # noqa: S608
        params,
    ).fetchall()
    return [dict(r) for r in rows]


def run_standing_questions(
    repo: Any, subject_ref: str, *, model: str, thread_id: str = "", **kwargs: Any
) -> list[dict[str, Any]]:
    """Run every standing question against one subject and keep the answers."""
    out: list[dict[str, Any]] = []
    for entry in standing_questions(repo, subject_ref):
        out.append(
            read(
                repo,
                str(entry["question"]),
                subject_ref,
                model=model,
                thread_id=thread_id or f"standing:{subject_ref}",
                **kwargs,
            )
        )
    return out


def as_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, indent=2, default=str)
