#!/usr/bin/env python3
"""Detect operator-derived text, identity terms and operator ids in any text.

READING_TRUTH_V1 P1. Three detection kinds, per the task's D0 classification:

* **text spans** — 8-token shingles of the operator documents and operator
  notes in the store, folded with the module's own verbatim fold
  (``candidate_links._norm_for_verbatim``), minus every shingle that also
  occurs in a regulatory (``US``) document, because NERC's text is public.
  A hit is reported as the EXACT original substring, via a char-offset map
  built while folding (``_fold_with_map``).
* **identity terms** — the local list
  ``portal/modules/compliance/data/private/profile/identity_terms.txt``
  (``term<TAB>replacement`` per line): entity, document-title and person
  names. Matched on word boundaries, longest first, case-insensitive.
* **operator ids** — ``isection-`` + 20 hex (the internal-corpus section id,
  ``internal_corpus.InternalSection.section_id``) and the operator-side
  short cite token ``O-`` + 6 hex (``addressing.cite_as``, side letter O).
  ``csection-`` is deliberately NOT an operator signal: it is the generic
  capture prefix and 21k+ regulatory sections carry it.

Surfaces:

* ``scan_text(text, index)`` — findings for one text.
* ``head_findings(root)`` — every git-tracked file under ``root`` (PDF and
  DOCX extracted). ``scripts/validation/compliance_public_text`` (HK) calls
  this for its content scan.
* ``history_scan(git_dir)`` — every blob reachable from every ref plus every
  commit message; returns the LOCAL-class historical paths and the
  ``git filter-repo --replace-text`` / ``--replace-message`` line files.
  It takes no exemption for text that is present at the tip (P1R: a tip
  veto made the scan certify itself).
* ``has_findings(text)`` — the boolean the rewrite-integrity check calls.

**Protected files (P1R).** A file that by provenance cannot hold operator
content (NERC-derived product data, the NIST catalog, synthetic corpora) is
listed in the local ``protected_globs.txt``. It is never flagged, never
scrubbed and never path-removed, and its text joins the regulatory exclusion.
* CLI: ``inventory`` (writes the local purge inventory), ``terms`` (drafts
  the identity-term list from the store for agent review), ``history``
  (writes the rewrite inputs).

Every write goes through :mod:`scripts.compliance.truth._local` and is
refused anywhere a commit could carry it. This module never names the
operator: the names live in the local profile, the store and nowhere else.
"""

from __future__ import annotations

import argparse
import fnmatch
import functools
import io
import json
import re
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from portal.modules.compliance.core.answer_contract import SECTION_ID_PATTERN
from scripts.compliance.truth._local import PRIVATE, is_local

if __package__ in (None, ""):  # direct-script execution: make the package importable
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

REPO = Path(__file__).resolve().parents[3]
PROFILE = PRIVATE / "profile"
IDENTITY_TERMS_PATH = PROFILE / "identity_terms.txt"
INVENTORY_PATH = PRIVATE / "purge" / "INVENTORY.json"
PROTECTED_GLOBS_PATH = PRIVATE / "purge" / "protected_globs.txt"
#: Local directory of the regulator's own source documents (public text).
NERC_OFFICIAL = PRIVATE / "nerc_official"

#: 8-token shingles, per the task's detector definition.
SHINGLE_N = 8

#: The operator side, by jurisdiction — the store's own truth, not a prefix
#: guess (``jurisdiction.py``: "Prefix is spelling; jurisdiction is truth").
OPERATOR_JURISDICTIONS = ("internal", "operator_note")
#: What a shingle must NOT also be for a hit to count: the regulator's text
#: is public.
REGULATORY_JURISDICTION = "US"

#: A shingle is prose, not structure, when at least this many of its
#: ``SHINGLE_N`` tokens are purely alphabetic: punctuation-blind tokens would
#: otherwise turn ``"2.1", "2.2", "2.3", "2.4"`` and Part/Requirement
#: references into "operator text".
MIN_ALPHA_TOKENS = 7
#: A lone shingle is a generic phrase collision ("at least once every 35
#: calendar days"), not a quoted passage: a text span needs this many
#: consecutive matching shingles (SHINGLE_N + this - 1 tokens).
MIN_SPAN_SHINGLES = 2

#: The all-zero ids are this module's own synthetic replacements and never
#: flag: otherwise a scrubbed file could never come clean. The id SHAPE is
#: owned by answer_contract (the citation-derivation singleton) — derived here,
#: never re-stated.
_ID_PREFIX = SECTION_ID_PATTERN.replace("[ci]", "i").split("-", 1)[0] + "-"
ID_RE = re.compile(rf"\b{_ID_PREFIX}(?!0{{20}}\b)[0-9a-f]{{20}}\b")
CITE_AS_RE = re.compile(r"\bO-(?!0{6}\b)[0-9a-f]{6}\b")
ID_REPLACEMENT = "isection-00000000000000000000"
CITE_AS_REPLACEMENT = "O-000000"
SPAN_REPLACEMENT = "[operator text removed]"

#: LOCAL-class path prefixes: everything under them moves out of the tree and
#: out of history. The docs list is the compliance development narratives
#: (D0: a doc that records a run, an experiment, a diagnosis, a task's
#: progress or a mechanically measured outcome); design docs are not here.
LOCAL_PREFIXES = (
    "reports/compliance/",
    "config/compliance/cases/",
    "docs/RAG_COMPLIANCE_QA_REALIGNMENT_V1.md",
    "docs/PROBLEM_COMPLIANCE_ASSESSMENT_IS_NOT_READING_20260912.md",
    "docs/PROBLEM_COMPLIANCE_ASSESSMENT_20260912.evidence.json",
    "docs/IMPLEMENTATION_BRIEF_COMPLIANCE_READING_20260912.md",
    "docs/COMPLIANCE_END_TO_END_RESUME_20260915.md",
    "docs/TASK_COMPLIANCE_READING_RESUME_20260913.md",
    "docs/TASK_COMPLIANCE_READING_RESUME_20260914.md",
    "docs/TASK_COMPLIANCE_READING_SEAT_REPLACEMENT_V1.md",
    "docs/COMPLIANCE_CIP002_ADDRESSABILITY_V1.md",
    "docs/COMPLIANCE_FAMILY_CENSUS_V1.md",
    "docs/COMPLIANCE_INSTRUCTION_ABLATION_V1.md",
    "docs/COMPLIANCE_MATERIAL_CONVERSATION_V1.md",
    "docs/COMPLIANCE_REFUSALS_AND_REREAD_V1.md",
    "docs/COMPLIANCE_SAMPLE_DECIDED_V1.md",
)

#: a results-directory file whose name carries one of these is a compliance run
#: output (the same rule HK applies): run data is local-only, wherever kept.
COMPLIANCE_RESULT_MARKERS = ("compliance", "judgment_probe")

#: Extensions extracted rather than decoded (python-docx / pymupdf).
DOCX_EXTS = {".docx"}
PDF_EXTS = {".pdf"}
#: Blobs that are decoded as text and scanned; anything else is skipped
#: unless it is a PDF or DOCX.
TEXT_EXTS = {
    ".md",
    ".py",
    ".yaml",
    ".yml",
    ".json",
    ".jsonl",
    ".txt",
    ".toml",
    ".cfg",
    ".ini",
    ".sh",
    ".ts",
    ".js",
    ".html",
    ".css",
    ".xml",
    ".svg",
    ".csv",
    ".tsv",
    ".sql",
    ".rst",
    ".ipynb",
    ".plist",
    ".service",
    "",
}


# ── the fold, mirrored from candidate_links with a char map ─────────────────


_FOLD_MAP = {
    "\u2010": "-",
    "\u2011": "-",
    "\u2012": "-",
    "\u2013": "-",
    "\u2014": "-",
    "\u2015": "-",
    "\u2212": "-",
    "\uff0d": "-",
    "\u2018": '"',
    "\u2019": '"',
    "\u201a": '"',
    "\u201b": '"',
    "\u201c": '"',
    "\u201d": '"',
    "\u201e": '"',
    "\u201f": '"',
    "\u00ab": '"',
    "\u00bb": '"',
    "'": '"',
    '"': '"',
    "\u00a0": " ",
}
_FOLD_TRANS = str.maketrans(_FOLD_MAP)
_WS_RE = re.compile(r"\s+")
_DASH_SPACE_RE = re.compile(r"- ")


def _norm_for_verbatim_mirror(text: str) -> str:
    """``candidate_links._norm_for_verbatim`` re-stated from its pieces.

    Exists only so the test suite can prove the mirrored table and steps
    have not drifted; the detector folds via :func:`_fold_with_map`, which
    must produce this output exactly.
    """
    folded = text.translate(_FOLD_TRANS)
    folded = _WS_RE.sub(" ", folded).strip().lower()
    return _DASH_SPACE_RE.sub("-", folded)


def _fold_with_map(text: str) -> tuple[str, list[tuple[int, int]]]:
    """Fold ``text`` exactly like the module's verbatim fold, and keep, for
    every folded char, the ``(orig_start, orig_end)`` slice it came from.

    Steps mirror ``_norm_for_verbatim`` in its own order — translate,
    whitespace collapse, strip, lower, dash-space fold — so a quotation that
    passes (or would pass) the module's VERBATIM check folds to the same
    bytes here. Deletions (collapsed whitespace, stripped ends, folded
    dash-spaces) carry no entry; the single space a whitespace run collapses
    to maps onto the whole run, so a span that ends on it still recovers the
    exact original substring.
    """
    mapped = text.translate(_FOLD_TRANS)
    pieces: list[tuple[str, int, int]] = []  # (char, orig_start, orig_end)
    n = len(mapped)
    i = 0
    while i < n:
        if mapped[i].isspace():
            j = i
            while j < n and mapped[j].isspace():
                j += 1
            pieces.append((" ", i, j))
            i = j
        else:
            pieces.append((mapped[i].lower(), i, i + 1))
            i += 1
    while pieces and pieces[0][0] == " ":
        pieces.pop(0)
    while pieces and pieces[-1][0] == " ":
        pieces.pop()
    kept: list[tuple[str, int, int]] = []
    for idx, (ch, s, e) in enumerate(pieces):
        if ch == " " and idx and pieces[idx - 1][0] == "-":
            continue  # the dash-space fold: re.sub deletes exactly the space a dash owns
        kept.append((ch, s, e))
    folded = "".join(ch for ch, _, _ in kept)
    spans = [(s, e) for _, s, e in kept]
    return folded, spans


_WORD_RE = re.compile(r"[^\W_]+")


def _tokens_with_spans(text: str) -> tuple[list[str], list[tuple[int, int]]]:
    """Word tokens of the folded text, each with its original span.

    A token is a run of letters and digits, so punctuation never separates two
    renderings of the same text ("Acme, shall" and "Acme shall" are one
    shingle) - the punctuation-sensitive tokens this replaces let a comma hide
    an operator sentence from the detector (P1R).
    """
    folded, spans = _fold_with_map(text)
    tokens: list[str] = []
    token_spans: list[tuple[int, int]] = []
    for m in _WORD_RE.finditer(folded):
        tokens.append(m.group(0))
        token_spans.append((spans[m.start()][0], spans[m.end() - 1][1]))
    return tokens, token_spans


# ── the index ───────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Finding:
    kind: str  # "text_span" | "identity_term" | "operator_id"
    start: int
    end: int
    match: str
    replacement: str


@dataclass
class OperatorIndex:
    """Everything detection needs, precomputed from the store and profile.

    Built once per process (``load_index``); tests build one directly from
    synthetic sets — no store needed.
    """

    operator_shingles: frozenset[str]
    regulatory_shingles: frozenset[str]
    #: longest first; a shorter term never fires inside a longer one's match.
    identity_terms: tuple[tuple[str, str], ...] = ()
    #: fnmatch globs of files that cannot hold operator content by provenance
    protected_globs: tuple[str, ...] = ()
    _term_res: list[re.Pattern[str]] = field(default_factory=list, repr=False)
    _term_map: dict[str, str] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        if not self._term_res:
            for term, _ in self.identity_terms:
                self._term_res.append(
                    re.compile(r"(?<![0-9A-Za-z])" + re.escape(term) + r"(?![0-9A-Za-z])", re.I)
                )
            self._term_map = dict(self.identity_terms)

    def is_protected(self, rel: str) -> bool:
        return any(fnmatch.fnmatch(rel, g) for g in self.protected_globs)

    def scan(self, text: str) -> list[Finding]:
        findings: list[Finding] = []
        taken: list[tuple[int, int]] = []

        def _free(s: int, e: int) -> bool:
            return all(e <= a or s >= b for a, b in taken)

        # Text spans decide first: their replacement must be complete, so
        # terms and ids never carve a span up.
        tokens, token_spans = _tokens_with_spans(text)
        n = SHINGLE_N
        covered: list[tuple[int, int]] = []  # token-index ranges, merged
        for i in range(0, max(0, len(tokens) - n + 1)):
            shingle = " ".join(tokens[i : i + n])
            if (
                shingle in self.operator_shingles
                and shingle not in self.regulatory_shingles
                and _is_prose(shingle)
            ):
                if covered and i <= covered[-1][1]:  # overlap or adjacency merges
                    covered[-1] = (covered[-1][0], i + n)
                else:
                    covered.append((i, i + n))
        for a, b in covered:
            if b - a < n + MIN_SPAN_SHINGLES - 1:
                continue
            start, end = token_spans[a][0], token_spans[b - 1][1]
            findings.append(Finding("text_span", start, end, text[start:end], SPAN_REPLACEMENT))
            taken.append((start, end))

        for pattern in self._term_res:
            for m in pattern.finditer(text):
                if _free(m.start(), m.end()):
                    replacement = self._term_map[m.group(0).lower()]
                    findings.append(
                        Finding("identity_term", m.start(), m.end(), m.group(0), replacement)
                    )
                    taken.append((m.start(), m.end()))

        for pattern in (ID_RE, CITE_AS_RE):
            for m in pattern.finditer(text):
                if _free(m.start(), m.end()):
                    repl = ID_REPLACEMENT if pattern is ID_RE else CITE_AS_REPLACEMENT
                    findings.append(Finding("operator_id", m.start(), m.end(), m.group(0), repl))
                    taken.append((m.start(), m.end()))

        findings.sort(key=lambda f: (f.start, f.end))
        return findings


def load_identity_terms(path: Path | None = None) -> tuple[tuple[str, str], ...]:
    """The reviewed ``term<TAB>replacement`` pairs, longest first."""
    path = path or IDENTITY_TERMS_PATH
    if not path.exists():
        return ()
    pairs: list[tuple[str, str]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        term, _, repl = line.partition("\t")
        pairs.append((term.strip().lower(), repl.strip()))
    pairs.sort(key=lambda p: -len(p[0]))
    return tuple(pairs)


def load_index(repo: Any = None) -> OperatorIndex:
    """Build the index from the live store and the local profile."""
    if repo is None:
        from portal.modules.compliance.core.repository import Repository

        repo = Repository()
    op = _corpus_shingles(repo, OPERATOR_JURISDICTIONS, note_sections=True)
    reg = _corpus_shingles(repo, (REGULATORY_JURISDICTION,))
    globs = load_protected_globs()
    reg |= _protected_shingles(REPO, globs)
    reg |= _regulator_source_shingles()
    return OperatorIndex(
        operator_shingles=frozenset(op),
        regulatory_shingles=frozenset(reg),
        identity_terms=load_identity_terms(),
        protected_globs=globs,
    )


def load_protected_globs(path: Path | None = None) -> tuple[str, ...]:
    """The local list of provenance-protected globs, one per line."""
    path = path or PROTECTED_GLOBS_PATH
    if not path.exists():
        return ()
    return tuple(
        g.strip()
        for g in path.read_text(encoding="utf-8").splitlines()
        if g.strip() and not g.startswith("#")
    )


def _protected_shingles(root: Path, globs: tuple[str, ...]) -> set[str]:
    """The text of every protected tracked file joins the public-text exclusion."""
    out: set[str] = set()
    if not globs:
        return out
    for rel in _tracked(root):
        if not any(fnmatch.fnmatch(rel, g) for g in globs):
            continue
        try:
            text = _file_text(rel, (root / rel).read_bytes())
        except OSError:
            continue
        if text is not None:
            out |= _shingles(text)
    return out


def _regulator_source_shingles(source: Path | None = None) -> set[str]:
    """Every regulator source document held locally (every revision, attachment, table)."""
    source = source or NERC_OFFICIAL
    out: set[str] = set()
    if not source.is_dir():
        return out
    for path in sorted(source.rglob("*")):
        if not path.is_file():
            continue
        try:
            text = _file_text(path.name, path.read_bytes())
        except OSError:
            continue
        if text is not None:
            out |= _shingles(text)
    return out


def _revisions(repo: Any, jurisdictions: tuple[str, ...]) -> list[tuple[str, str]]:
    placeholders = ",".join("?" for _ in jurisdictions)
    rows = repo._conn.execute(
        f"""SELECT r.revision_id FROM document_revisions r
            JOIN source_documents d ON d.logical_id = r.logical_id
            WHERE d.jurisdiction IN ({placeholders})""",
        jurisdictions,
    ).fetchall()
    return [str(row[0]) for row in rows]


def _corpus_shingles(
    repo: Any, jurisdictions: tuple[str, ...], *, note_sections: bool = False
) -> set[str]:
    """8-token shingles over whole revision texts (and, for notes, over the
    note sections' own slices)."""
    out: set[str] = set()
    for revision_id in _revisions(repo, jurisdictions):
        text = repo.get_document_text(revision_id) or ""
        out.update(_shingles(text))
    if note_sections:
        rows = repo._conn.execute(
            """SELECT s.revision_id, s.char_start, s.char_end FROM source_sections s
               JOIN operator_notes n ON n.section_id = s.section_id"""
        ).fetchall()
        for revision_id, start, end in rows:
            text = repo.get_document_text(str(revision_id)) or ""
            out.update(_shingles(text[int(start or 0) : int(end or 0)]))
    return out


def _is_prose(shingle: str) -> bool:
    return sum(t.isalpha() for t in shingle.split(" ")) >= MIN_ALPHA_TOKENS


def _shingles(text: str) -> set[str]:
    tokens, _ = _tokens_with_spans(text)
    n = SHINGLE_N
    return {" ".join(tokens[i : i + n]) for i in range(0, max(0, len(tokens) - n + 1))}


# ── file text extraction ────────────────────────────────────────────────────


def _docx_text(data: bytes) -> str:
    import docx  # python-docx

    document = docx.Document(io.BytesIO(data))
    parts = [p.text for p in document.paragraphs]
    for table in document.tables:
        for row in table.rows:
            for cell in row.cells:
                parts.append(cell.text)
    return "\n".join(parts)


def _pdf_text(data: bytes) -> str:
    import fitz  # pymupdf

    with fitz.open(stream=data, filetype="pdf") as pdf:
        return "\n".join(page.get_text() for page in pdf)


def _file_text(rel: str, data: bytes) -> str | None:
    suffix = Path(rel).suffix.lower()
    try:
        if suffix in DOCX_EXTS:
            return _docx_text(data)
        if suffix in PDF_EXTS:
            return _pdf_text(data)
        if suffix in TEXT_EXTS:
            if b"\x00" in data[:4096]:
                return None
            return data.decode("utf-8", "replace")
    except Exception:
        return None
    return None


# ── surfaces ────────────────────────────────────────────────────────────────


def scan_text(text: str, index: OperatorIndex | None = None) -> list[dict[str, Any]]:
    """Findings for one text, as plain dicts (kind, start, end, match)."""
    index = index or load_index()
    return [
        {"kind": f.kind, "start": f.start, "end": f.end, "match": f.match} for f in index.scan(text)
    ]


@functools.lru_cache(maxsize=1)
def _default_index() -> OperatorIndex:
    return load_index()


def has_findings(text: str, index: OperatorIndex | None = None) -> bool:
    """True when ``text`` carries any finding - ``scan_text`` reduced to a boolean.

    The callable ``rewrite_integrity.py`` uses to decide whether a changed
    kept file's ORIGINAL blob had a reason to change.
    """
    return bool(scan_text(text, index or _default_index()))


def _tracked(root: Path) -> list[str]:
    out = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z"], capture_output=True, check=True, timeout=120
    ).stdout
    return [p for p in out.decode("utf-8", "replace").split("\0") if p]


def head_findings(root: Path = REPO, index: OperatorIndex | None = None) -> list[dict[str, Any]]:
    """Every tracked file under ``root`` with findings (PDF/DOCX extracted)."""
    index = index or load_index()
    out: list[dict[str, Any]] = []
    for rel in _tracked(root):
        if index.is_protected(rel):
            continue
        path = root / rel
        try:
            data = path.read_bytes()
        except OSError:
            continue
        text = _file_text(rel, data)
        if text is None:
            continue
        found = index.scan(text)
        if found:
            out.append(
                {
                    "path": rel,
                    "findings": [
                        {"kind": f.kind, "start": f.start, "end": f.end, "match": f.match}
                        for f in found
                    ],
                }
            )
    return out


def _run_output(rel: str) -> bool:
    """A compliance run output in a ``results`` directory, wherever it was kept."""
    parts = rel.split("/")
    name = parts[-1].lower()
    return "results" in parts[:-1] and any(m in name for m in COMPLIANCE_RESULT_MARKERS)


def _local_class(rel: str) -> bool:
    return _run_output(rel) or any(rel == p or rel.startswith(p) for p in LOCAL_PREFIXES)


def _filter_repo_line(literal: str, replacement: str) -> str:
    """One ``git filter-repo --replace-text`` line for ``literal``.

    A literal that would break the line format (``==>``) goes through the
    ``regex:`` escape hatch instead.
    """
    if "==>" in literal:
        return f"regex:{re.escape(literal)}==>{replacement}"
    return f"{literal}==>{replacement}"


def _term_line(match: str, replacement: str) -> str:
    """A word-bounded, case-insensitive ``regex:`` line for one identity term.

    ``--replace-text`` is a substring match: a plain literal would also rewrite
    the term inside longer words, exactly what the detector's word boundaries
    forbid."""
    body = r"(?i)(?<![0-9A-Za-z])" + re.escape(match.lower()) + r"(?![0-9A-Za-z])"
    return f"regex:{body}==>{replacement}"


def _span_lines(match: str, replacement: str) -> list[str]:
    """Lines for one span; a span that crosses lines is emitted per line, so
    no replacement literal ever contains a newline."""
    if "\n" not in match:
        return [_filter_repo_line(match, replacement)]
    out = []
    for segment in match.split("\n"):
        if segment.strip():
            out.append(_filter_repo_line(segment, replacement))
    return out


def parse_replacement_lines(lines: list[str]) -> list[tuple[str, str]]:
    """The inverse of the line writer — the round-trip half of the tests."""
    pairs: list[tuple[str, str]] = []
    for line in lines:
        if line.startswith("regex:"):
            body, _, repl = line[len("regex:") :].rpartition("==>")

            pairs.append((re.unescape(body), repl))
        else:
            literal, _, repl = line.partition("==>")

            pairs.append((literal, repl))
    return pairs


@dataclass
class _HistoryCollector:
    """Feeds texts to the index and accumulates the three rewrite inputs."""

    index: OperatorIndex
    #: paths the corrected tip still carries: history never deletes a kept path,
    #: it only carries replacements in it. A PATH guard only - it exempts no text.
    kept_paths: frozenset[str] = frozenset()
    local_paths: set[str] = field(default_factory=set)
    lines: set[str] = field(default_factory=set)
    span_lines: set[str] = field(default_factory=set)
    census: Counter[str] = field(default_factory=Counter)

    def record(self, text: str, rel_for_class: str | None) -> None:
        if rel_for_class is not None and self.index.is_protected(rel_for_class):
            return  # provenance: cannot hold operator content; never flagged
        found = self.index.scan(text)
        for f in found:
            self.census[f.kind] += 1
            if f.kind == "text_span":
                span = _span_lines(f.match, f.replacement)
                self.lines.update(span)
                self.span_lines.update(span)
            elif f.kind == "identity_term":
                self.lines.add(_term_line(f.match, f.replacement))
            else:
                self.lines.add(_filter_repo_line(f.match, f.replacement))
        if rel_for_class is None:
            return
        suffix = Path(rel_for_class).suffix.lower()
        office_json = suffix in {".json", ".jsonl", ".pdf", ".docx"}
        if rel_for_class in self.kept_paths and not _run_output(rel_for_class):
            return
        if _local_class(rel_for_class) or (office_json and found):
            self.local_paths.add(rel_for_class)


def _history_blob_paths(git: list[str]) -> dict[str, list[str]]:
    """Every (blob, path) pair in history.

    ``rev-list --objects`` names an object once, under one path, so a blob kept
    under two paths would be judged under only one; the per-commit raw diff
    lists every path a blob was ever written to. The object listing stays as the
    fallback for blobs the diffs do not reach."""
    blob_paths: dict[str, list[str]] = {}

    def add(sha: str, path: str) -> None:
        if path and path not in blob_paths.setdefault(sha, []):
            blob_paths[sha].append(path)

    raw = subprocess.run(
        git
        + [
            "log",
            "--all",
            "--root",
            "-m",
            "--no-renames",
            "--raw",
            "--no-abbrev",
            "-z",
            "--format=",
        ],
        capture_output=True,
        check=True,
        timeout=1800,
    ).stdout.decode("utf-8", "replace")
    fields = raw.split("\0")
    i = 0
    while i < len(fields):
        meta = fields[i].lstrip("\n")
        if not meta.startswith(":"):
            i += 1
            continue
        parts = meta[1:].split(" ")
        i += 2  # meta, path
        if len(parts) >= 5 and parts[1] != "160000" and set(parts[3]) != {"0"}:
            add(parts[3], fields[i - 1])
    listing = (
        subprocess.run(
            git + ["rev-list", "--objects", "--all"], capture_output=True, check=True, timeout=600
        )
        .stdout.decode("utf-8", "replace")
        .splitlines()
    )
    for row in listing:
        sha, _, path = row.partition(" ")
        if path and sha not in blob_paths:
            add(sha, path)
    return blob_paths


def _scan_history_blobs(
    git: list[str],
    blob_paths: dict[str, list[str]],
    record: Any,
    *,
    max_blob_bytes: int,
) -> None:
    """One ``cat-file --batch`` pass over every reachable blob."""
    batch = subprocess.Popen(
        git + ["cat-file", "--batch"], stdin=subprocess.PIPE, stdout=subprocess.PIPE
    )
    assert batch.stdin is not None and batch.stdout is not None
    try:
        for sha in sorted(blob_paths):
            batch.stdin.write(f"{sha}\n".encode())
            batch.stdin.flush()
            header = batch.stdout.readline().decode().split()
            if len(header) < 3:
                continue  # "<sha> missing"
            size = int(header[2])
            data = batch.stdout.read(size)  # always consume: the batch stream desyncs otherwise
            batch.stdout.read(1)
            if header[1] != "blob":
                continue
            oversize = size > max_blob_bytes
            for path in blob_paths[sha]:  # one blob, every path it was ever kept under
                text = None if oversize else _file_text(path, data)
                # A path's class never depends on whether its bytes decode: run logs and
                # exit files under a local prefix are removed too (P1R). "" has no findings.
                record("" if text is None else text, path)
    finally:
        batch.stdin.close()
        batch.wait(timeout=60)


def _scan_history_messages(git: list[str], record: Any) -> None:
    """Annotated tag messages and every commit message on every ref."""
    tag_lines = (
        subprocess.run(
            git + ["for-each-ref", "refs/tags", "--format=%(objecttype) %(objectname)"],
            capture_output=True,
            check=True,
            timeout=120,
        )
        .stdout.decode("utf-8", "replace")
        .splitlines()
    )
    for line in tag_lines:
        parts = line.split()
        if len(parts) != 2 or parts[0] != "tag":
            continue  # lightweight tags point straight at commits; log --all covers those
        tag = subprocess.run(
            git + ["cat-file", "tag", parts[1]], capture_output=True, check=True, timeout=30
        ).stdout.decode("utf-8", "replace")
        record(tag.partition("\n\n")[2], None)
    messages = subprocess.run(
        git + ["log", "--all", "--format=%B%x00"], capture_output=True, check=True, timeout=600
    ).stdout.decode("utf-8", "replace")
    for message in messages.split("\0"):
        if message.strip():
            record(message, None)


def history_scan(
    git_dir: Path,
    index: OperatorIndex | None = None,
    *,
    tip_root: Path | None = None,
    extra_local_paths: frozenset[str] = frozenset(),
    max_blob_bytes: int = 32_000_000,
) -> dict[str, Any]:
    """Every blob reachable from every ref, and every commit message.

    Returns the three rewrite inputs plus a census:

    * ``local_paths`` - LOCAL-class historical paths (under a LOCAL prefix, a
      compliance run output, or any JSON/JSONL/PDF/DOCX whose content carries
      a finding), plus ``extra_local_paths``, minus every path ``tip_root``
      still carries (a kept path is never deleted from history);
    * ``blob_replacements`` / ``message_replacements`` - ``--replace-text`` /
      ``--replace-message`` line files (spans split per line, identity terms,
      ``regex:`` lines for ids), longest literal first;
    * ``tip_withheld`` - literals that also occur in the ``tip_root`` tree (inputs
      only; the finding stays in the census and the post-rewrite scan judges);
    * ``protected_conflicts`` - literals that also occur inside a protected
      file's history: ``--replace-text`` is not path-scoped, so such a literal
      cannot be applied without touching a protected file; it is withheld
      from the line files and reported;
    * census counts per kind, for the inventory.

    No text is exempt because it is present at the tip: a finding at the tip is
    fixed at the tip, never used to excuse the history (P1R RC2).
    """
    index = index or load_index()
    git = ["git", "-C", str(git_dir)]
    collector = _HistoryCollector(index)
    if tip_root is not None:
        collector.kept_paths = frozenset(_tracked(tip_root))
    blob_paths = _history_blob_paths(git)
    protected_text: list[str] = []

    def _remember_protected(text: str, rel: str | None) -> None:
        if rel is not None and index.is_protected(rel):
            protected_text.append(text)

    _scan_history_blobs(git, blob_paths, _remember_protected, max_blob_bytes=max_blob_bytes)
    _scan_history_blobs(git, blob_paths, collector.record, max_blob_bytes=max_blob_bytes)
    _scan_history_messages(git, collector.record)
    ordered = sorted(collector.lines, key=lambda line: -len(line.partition("==>")[0]))
    haystack = "\n".join(protected_text)
    conflicts = [ln for ln in ordered if _hits(ln, haystack)] if haystack else []
    withheld = set(conflicts)
    tip_withheld: list[str] = []
    if tip_root is not None:
        tip_text = _tip_text(tip_root)
        tip_withheld = [
            ln for ln in ordered if ln in collector.span_lines and _literal_of(ln) in tip_text
        ]
        withheld |= set(tip_withheld)
    ordered = [ln for ln in ordered if ln not in withheld]
    return {
        "local_paths": sorted(collector.local_paths | set(extra_local_paths)),
        "blob_replacements": ordered,
        "message_replacements": ordered,
        "protected_conflicts": conflicts,
        "tip_withheld": tip_withheld,
        "census": dict(collector.census),
        "n_blobs_scanned": len(blob_paths),
    }


def _tip_text(tip_root: Path) -> str:
    """The tree's own text. A ``--replace-text`` literal that occurs in it is
    withheld (per-line span fragments like ``"section",`` would rewrite the
    tip). This filters INPUTS only: the finding is still censused, and the
    independent post-rewrite scan (no exemptions) decides whether anything
    genuine was left behind."""
    parts: list[str] = []
    for rel in _tracked(tip_root):
        try:
            text = _file_text(rel, (tip_root / rel).read_bytes())
        except OSError:
            continue
        if text is not None:
            parts.append(text)
    return "\n".join(parts)


def _hits(line: str, text: str) -> bool:
    """Would this ``--replace-text`` line change ``text``?"""
    if line.startswith("regex:(?i)"):
        pattern = line[len("regex:") :].rpartition("==>")[0]
        return re.search(pattern, text) is not None
    return _literal_of(line) in text


def _literal_of(line: str) -> str:
    """The text a ``--replace-text`` line matches (regex lines are unescaped)."""
    if line.startswith("regex:"):
        return re.sub(r"\\(.)", r"\1", line[len("regex:") :].rpartition("==>")[0])
    return line.partition("==>")[0]


# ── the identity-term draft (agent-reviewed before use) ─────────────────────


_ORG_MINING_STOP = frozenset(
    {
        "the",
        "and",
        "for",
        "with",
        "from",
        "that",
        "this",
        "shall",
        "must",
        "will",
        "not",
        "are",
        "was",
        "were",
        "has",
        "have",
        "had",
        "its",
        "their",
        "our",
        "your",
        "all",
        "any",
        "each",
        "per",
        "may",
        "can",
        "should",
        "would",
        "could",
        "within",
        "without",
        "during",
        "after",
        "before",
        "under",
        "over",
        "into",
        "onto",
        "upon",
        "by",
        "at",
        "as",
        "of",
        "on",
        "in",
        "to",
        "a",
        "an",
        "or",
        "nor",
        "but",
        "if",
        "then",
        "than",
        "so",
        "such",
        "no",
        "only",
        "own",
        "same",
        "very",
        "inc",
        "llc",
        "ltd",
        "co",
        "corp",
        "page",
        "section",
        "appendix",
        "revision",
        "version",
        "date",
        "effective",
        "approval",
        "approved",
        "review",
        "document",
        "procedure",
        "process",
        "plan",
        "policy",
        "work",
        "instruction",
        "standard",
        "requirement",
    }
)


def _capitalised_runs(text: str) -> list[str]:
    out: list[str] = []
    for m in re.finditer(
        r"\b(?:[A-Z][A-Za-z0-9&.\-]*\s+){1,5}[A-Z][A-Za-z0-9&.\-]*|\b[A-Z]{3,}\b", text
    ):
        run = " ".join(m.group(0).split())
        out.append(run)
    return out


def draft_identity_terms(repo: Any = None, top: int = 80) -> dict[str, Any]:
    """Candidate identity terms from the store, for the agent's review.

    Titles, issuers, operator document file names, person names from the
    revision tables, and capitalised runs that occur in operator documents
    and nowhere in the regulatory corpus. Nothing here is written to the
    profile until a human-checked pass has pruned it (the caller decides).
    """
    if repo is None:
        from portal.modules.compliance.core.repository import Repository

        repo = Repository()
    titles = [
        str(r[0])
        for r in repo._conn.execute(
            "SELECT DISTINCT title FROM source_documents WHERE jurisdiction IN ('internal','operator_note')"
        ).fetchall()
        if str(r[0]).strip()
    ]
    issuers = [
        str(r[0])
        for r in repo._conn.execute(
            "SELECT DISTINCT issuer FROM source_documents WHERE jurisdiction IN ('internal','operator_note')"
        ).fetchall()
        if str(r[0]).strip()
    ]
    files = [
        Path(str(r[0])).name
        for r in repo._conn.execute(
            "SELECT DISTINCT logical_id FROM source_documents WHERE jurisdiction IN ('internal','operator_note')"
        ).fetchall()
    ]
    people: set[str] = set()
    for (owner,) in repo._conn.execute(
        """SELECT DISTINCT dr.owner FROM document_revisions dr
           JOIN source_documents d ON d.logical_id = dr.logical_id
           WHERE d.jurisdiction IN ('internal','operator_note')"""
    ).fetchall():
        for part in str(owner or "").split(","):
            part = part.strip()
            if part and len(part.split()) <= 4 and part[0].isupper():
                people.add(part)
    reg_text = "\n".join(
        str(r[0])
        for r in repo._conn.execute(
            """SELECT t.full_text FROM document_texts t
               JOIN document_revisions r ON t.revision_id = r.revision_id
               JOIN source_documents d ON d.logical_id = r.logical_id
               WHERE d.jurisdiction = ?""",
            (REGULATORY_JURISDICTION,),
        ).fetchall()
    )
    op_text = "\n".join(
        str(r[0])
        for r in repo._conn.execute(
            """SELECT t.full_text FROM document_texts t
               JOIN document_revisions r ON t.revision_id = r.revision_id
               JOIN source_documents d ON d.logical_id = r.logical_id
               WHERE d.jurisdiction IN ('internal','operator_note')"""
        ).fetchall()
    )
    reg_norm = _norm_for_verbatim_mirror(reg_text)
    counts: Counter[str] = Counter()
    for run in _capitalised_runs(op_text):
        lowered = run.lower()
        if lowered in _ORG_MINING_STOP or len(run) < 4:
            continue
        if re.search(r"(?<![0-9A-Za-z])" + re.escape(run) + r"(?![0-9A-Za-z])", reg_text, re.I):
            continue
        counts[run] += 1
    return {
        "titles": titles,
        "issuers": issuers,
        "file_names": sorted(set(files)),
        "people": sorted(people),
        "org_candidates": [name for name, _ in counts.most_common(top)],
    }


# ── CLI ─────────────────────────────────────────────────────────────────────


def _refuse(path: Path, what: str) -> None:
    if not is_local(path):
        raise SystemExit(
            f"REFUSED: {what} is local-only - write it under {PRIVATE} or outside the repo, not {path}"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_inv = sub.add_parser("inventory", help="scan HEAD's tracked files; write the local inventory")
    p_inv.add_argument("--out", type=Path, default=INVENTORY_PATH)

    p_terms = sub.add_parser("terms", help="draft identity terms from the store (agent-reviewed)")
    p_terms.add_argument("--out", type=Path, required=True)

    p_hist = sub.add_parser("history", help="scan a git dir; write the rewrite inputs")
    p_hist.add_argument("--git-dir", type=Path, required=True)
    p_hist.add_argument("--out-dir", type=Path, required=True)
    p_hist.add_argument(
        "--tip-root", type=Path, default=REPO, help="tree whose paths history never deletes"
    )
    p_hist.add_argument(
        "--extra-local-paths", type=Path, help="file of extra removal-set paths, one per line"
    )

    args = parser.parse_args(argv)
    if args.cmd == "inventory":
        _refuse(args.out, "the inventory")
        index = load_index()
        from scripts.validation import compliance_public_text as hk

        files = _tracked(REPO)
        structural = hk._structural(REPO, files)
        found = head_findings(REPO, index)
        payload = {
            "head": subprocess.run(
                ["git", "-C", str(REPO), "rev-parse", "HEAD"],
                capture_output=True,
                check=True,
                timeout=30,
            )
            .stdout.decode()
            .strip(),
            "n_tracked": len(files),
            "structural_findings": len(structural),
            "structural_by_rule": dict(Counter(f["rule"] for f in structural)),
            "content_findings": len(found),
            "content_by_kind": dict(
                Counter(f["kind"] for entry in found for f in entry["findings"])
            ),
            "files_with_content_findings": [
                {"path": e["path"], "n": len(e["findings"])} for e in found
            ],
            "identity_terms_loaded": len(index.identity_terms),
        }
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({k: v for k, v in payload.items() if k != "head"}, indent=2))
        return 0
    if args.cmd == "terms":
        _refuse(args.out, "the identity-term draft")
        draft = draft_identity_terms()
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(draft, indent=2) + "\n", encoding="utf-8")
        print(f"draft written: {args.out}")
        return 0
    _refuse(args.out_dir, "the rewrite inputs")
    extra = (
        frozenset(
            ln.strip() for ln in args.extra_local_paths.read_text().splitlines() if ln.strip()
        )
        if args.extra_local_paths
        else frozenset()
    )
    result = history_scan(args.git_dir, tip_root=args.tip_root, extra_local_paths=extra)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "local_paths.txt").write_text(
        "\n".join(result["local_paths"]) + "\n", encoding="utf-8"
    )
    (args.out_dir / "blob_replacements.txt").write_text(
        "\n".join(result["blob_replacements"]) + "\n", encoding="utf-8"
    )
    (args.out_dir / "message_replacements.txt").write_text(
        "\n".join(result["message_replacements"]) + "\n", encoding="utf-8"
    )
    (args.out_dir / "history_census.json").write_text(
        json.dumps({k: v for k, v in result.items() if k != "blob_replacements"}, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        f"local paths: {len(result['local_paths'])}; "
        f"replacement lines: {len(result['blob_replacements'])}; census: {result['census']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
