"""Open WebUI v0.12.5 document RAG: loaders, splitters, and the stock template."""

from __future__ import annotations

import csv
import re
import uuid
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

CHUNK_SIZE = 1500
CHUNK_OVERLAP = 100
TOP_K = 3
# Env default is true. The live DB key was not re-read; the orchestrator did not list an override.
MARKDOWN_HEADER_SPLIT = True

# Stock ``RAG_TEMPLATE`` from Open WebUI v0.12.5 config.py. No ``{{QUERY}}`` and no prompt placeholders.
DEFAULT_RAG_TEMPLATE = """### Task:
Respond to the user query using the provided context, incorporating inline citations in the format [id] **only when the <source> tag includes an explicit id attribute** (e.g., <source id="1">).

### Guidelines:
- If you don't know the answer, clearly state that.
- If uncertain, ask the user for clarification.
- Respond in the same language as the user's query.
- If the context is unreadable or of poor quality, inform the user and provide the best possible answer.
- If the answer isn't present in the context but you possess the knowledge, explain this to the user and provide the answer using your own understanding.
- **Only include inline citations using [id] (e.g., [1], [2]) when the <source> tag includes an id attribute.**
- Do not cite if the <source> tag does not contain an id attribute.
- Do not use XML tags in your response.
- Ensure citations are concise and directly related to the information provided.

### Example of Citation:
If the user asks about a specific topic and the information is found in a source with a provided id attribute, the response should include the citation like in the following example:
* "According to the study, the proposed method increases efficiency by 20% [1]."

### Output:
Provide a clear and direct response to the user's query, including inline citations in the format [id] only when the <source> tag with id attribute is present in the context.

<context>
{{CONTEXT}}
</context>
"""

# The one guideline Portal adds to the stock template. Seeded as OWUI's
# rag.template by openwebui_init.py from imports/openwebui/rag_template.txt —
# the golden test keeps that file and this string byte-equal.
PORTAL_RAG_GUIDELINE = (
    "- The context holds excerpts of attached files. When the full file matters "
    "(data, code, totals, or running a script), use the attached-file path with "
    "your tools instead of answering from excerpts."
)
PORTAL_RAG_TEMPLATE = DEFAULT_RAG_TEMPLATE.replace(
    "- Do not use XML tags in your response.",
    f"{PORTAL_RAG_GUIDELINE}\n- Do not use XML tags in your response.",
)

_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_HEADER_SEPS = ("######", "#####", "####", "###", "##", "#")
_SEPARATORS = ("\n\n", "\n", " ", "")
_SURROGATE_RE = re.compile("[\ud800-\udfff]")
_CHUNK_CACHE: dict[tuple[str, str], tuple[list[str], int]] = {}


def _sanitize(text: str) -> str:
    if "\x00" not in text and _SURROGATE_RE.search(text) is None:
        return text
    return _SURROGATE_RE.sub("", text.replace("\x00", ""))


def _xml2text(xml: bytes) -> str:
    text = ""
    for child in ET.fromstring(xml).iter():
        if child.tag == f"{_W}t":
            text += child.text or ""
        elif child.tag == f"{_W}tab":
            text += "\t"
        elif child.tag in (f"{_W}br", f"{_W}cr"):
            text += "\n"
        elif child.tag == f"{_W}p":
            text += "\n\n"
    return text


def docx_text(path: Path) -> str:
    """docx2txt 0.9 ``process``: headers, document, footers, then strip."""
    text = ""
    with zipfile.ZipFile(path) as zipf:
        names = zipf.namelist()
        for fname in names:
            if re.match(r"word/header[0-9]*.xml", fname):
                text += _xml2text(zipf.read(fname))
        text += _xml2text(zipf.read("word/document.xml"))
        for fname in names:
            if re.match(r"word/footer[0-9]*.xml", fname):
                text += _xml2text(zipf.read(fname))
    return text.strip()


def _read_text(path: Path) -> str:
    raw = path.read_bytes()
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("latin-1")


def _pdf_pages(path: Path) -> list[str]:
    # PyMuPDF matches pypdf page text on every realuse PDF. Unseen PDFs can still differ.
    import pymupdf

    doc = pymupdf.open(path)
    try:
        return [page.get_text().strip() for page in doc]
    finally:
        doc.close()


def _csv_rows(path: Path) -> list[str]:
    docs: list[str] = []
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            fields = []
            for key, value in row.items():
                if isinstance(value, str):
                    value = value.strip()
                elif isinstance(value, list):
                    value = ",".join(part.strip() for part in value)
                label = key.strip() if key is not None else key
                fields.append(f"{label}: {value}")
            docs.append("\n".join(fields))
    return docs


def _xlsx_text(path: Path) -> str:
    # OWUI's full image uses unstructured. This is its unstructured-missing ExcelLoader.
    import pandas as pd

    frame = pd.ExcelFile(path)
    parts = []
    for name in frame.sheet_names:
        sheet = pd.read_excel(frame, sheet_name=name)
        parts.append(f"Sheet: {name}\n{sheet.to_string(index=False)}")
    return "\n\n".join(parts)


def _pptx_text(path: Path) -> str:
    # OWUI's full image uses unstructured. This is its unstructured-missing PptxLoader.
    from pptx import Presentation

    deck = Presentation(str(path))
    parts = []
    for index, slide in enumerate(deck.slides, 1):
        lines = [shape.text_frame.text for shape in slide.shapes if shape.has_text_frame]
        if lines:
            parts.append(f"Slide {index}:\n" + "\n".join(lines))
    return "\n\n".join(parts)


def load_documents(path: Path, suffix: str) -> list[str]:
    """One raw document string per OWUI loader document, before the splitters."""
    if suffix == ".pdf":
        return _pdf_pages(path)
    if suffix == ".docx":
        return [docx_text(path)]
    if suffix == ".csv":
        return _csv_rows(path)
    if suffix in {".txt", ".md"}:
        return [_read_text(path)]
    if suffix == ".xlsx":
        return [_xlsx_text(path)]
    if suffix == ".pptx":
        return [_pptx_text(path)]
    return []


def _printable_strip(line: str) -> str:
    return "".join(ch for ch in line.strip() if ch.isprintable())


def _match_header(line: str) -> tuple[int, str] | None:
    for sep in _HEADER_SEPS:
        if line.startswith(sep) and (len(line) == len(sep) or line[len(sep)] == " "):
            return sep.count("#"), line[len(sep) :].strip()
    return None


def _aggregate(lines: list[dict]) -> list[str]:
    aggregated: list[dict] = []
    for line in lines:
        if aggregated and aggregated[-1]["metadata"] == line["metadata"]:
            aggregated[-1]["content"] += "  \n" + line["content"]
            continue
        last = aggregated[-1]["content"].split("\n")[-1] if aggregated else ""
        shallower = (
            aggregated
            and aggregated[-1]["metadata"] != line["metadata"]
            and len(aggregated[-1]["metadata"]) < len(line["metadata"])
            and bool(last)
            and last[0] == "#"
        )
        if shallower:
            aggregated[-1]["content"] += "  \n" + line["content"]
            aggregated[-1]["metadata"] = line["metadata"]
            continue
        aggregated.append({"content": line["content"], "metadata": dict(line["metadata"])})
    return [chunk["content"] for chunk in aggregated]


def _flush(out: list[dict], current: list[str], metadata: dict) -> None:
    if current:
        out.append({"content": "\n".join(current), "metadata": dict(metadata)})
        current.clear()


def markdown_pieces(text: str) -> list[str]:
    """MarkdownHeaderTextSplitter, headers ``#``..``######``, ``strip_headers=False``."""
    if not MARKDOWN_HEADER_SPLIT:
        return [text] if text else []
    rows: list[dict] = []
    current: list[str] = []
    current_meta: dict[str, str] = {}
    stack: list[dict] = []
    initial: dict[str, str] = {}
    in_code = False
    fence = ""
    for line in text.split("\n"):
        stripped = _printable_strip(line)
        in_code, fence = _code_state(stripped, in_code, fence)
        if in_code:
            current.append(stripped)
            continue
        matched = _match_header(stripped)
        if matched is not None:
            level, header_text = matched
            name = f"Header {level}"
            while stack and stack[-1]["level"] >= level:
                initial.pop(stack.pop()["name"], None)
            stack.append({"level": level, "name": name})
            initial[name] = header_text
            _flush(rows, current, current_meta)
            current.append(stripped)
        elif stripped:
            current.append(stripped)
        else:
            _flush(rows, current, current_meta)
        current_meta = dict(initial)
    _flush(rows, current, current_meta)
    return _aggregate(rows)


def _code_state(stripped: str, in_code: bool, fence: str) -> tuple[bool, str]:
    if not in_code:
        if stripped.startswith("```") and stripped.count("```") == 1:
            return True, "```"
        if stripped.startswith("~~~"):
            return True, "~~~"
        return False, ""
    if stripped.startswith(fence):
        return False, ""
    return True, fence


def _split_with_regex(text: str, separator: str, *, keep_separator: bool | str) -> list[str]:
    if separator:
        if keep_separator:
            parts = re.split(f"({separator})", text)
            if keep_separator == "end":
                splits = [parts[i] + parts[i + 1] for i in range(0, len(parts) - 1, 2)]
            else:
                splits = [parts[i] + parts[i + 1] for i in range(1, len(parts), 2)]
            if len(parts) % 2 == 0:
                splits += parts[-1:]
            splits = [*splits, parts[-1]] if keep_separator == "end" else [parts[0], *splits]
        else:
            splits = re.split(separator, text)
    else:
        splits = list(text)
    return [part for part in splits if part]


def _join_docs(docs: list[str], separator: str) -> str | None:
    text = separator.join(docs).strip()
    return text or None


def _merge_splits(splits: list[str], separator: str) -> list[str]:
    separator_len = len(separator)
    docs: list[str] = []
    current: list[str] = []
    total = 0
    for piece in splits:
        length = len(piece)
        over = total + length + (separator_len if current else 0) > CHUNK_SIZE
        if over and current:
            joined = _join_docs(current, separator)
            if joined is not None:
                docs.append(joined)
            while total > CHUNK_OVERLAP or (
                total + length + (separator_len if current else 0) > CHUNK_SIZE and total > 0
            ):
                total -= len(current[0]) + (separator_len if len(current) > 1 else 0)
                current = current[1:]
        current.append(piece)
        total += length + (separator_len if len(current) > 1 else 0)
    joined = _join_docs(current, separator)
    if joined is not None:
        docs.append(joined)
    return docs


def _split_recursive(text: str, separators: tuple[str, ...]) -> list[str]:
    final: list[str] = []
    separator = separators[-1]
    rest: tuple[str, ...] = ()
    for index, candidate in enumerate(separators):
        if not candidate:
            separator = candidate
            break
        if re.search(re.escape(candidate), text):
            separator = candidate
            rest = separators[index + 1 :]
            break
    splits = _split_with_regex(text, re.escape(separator), keep_separator=True)
    good: list[str] = []
    for piece in splits:
        if len(piece) < CHUNK_SIZE:
            good.append(piece)
            continue
        if good:
            final.extend(_merge_splits(good, ""))
            good = []
        final.extend([piece] if not rest else _split_recursive(piece, rest))
    if good:
        final.extend(_merge_splits(good, ""))
    return final


def character_chunks(text: str) -> list[str]:
    """RecursiveCharacterTextSplitter defaults at 1500/100, separator kept, whitespace stripped."""
    return _split_recursive(text, _SEPARATORS)


def split_text(text: str) -> list[str]:
    pieces: list[str] = []
    for part in markdown_pieces(text):
        pieces.extend(character_chunks(part))
    return [_sanitize(part) for part in pieces if part]


def chunk_file(path: Path, suffix: str) -> tuple[list[str], int]:
    """``(kept, raw)``. ``kept`` is the ``splitter_order_prefix`` stand-in, at most ``TOP_K``."""
    key = (str(path), suffix)
    cached = _CHUNK_CACHE.get(key)
    if cached is not None:
        return cached
    pieces: list[str] = []
    for doc in load_documents(path, suffix):
        pieces.extend(split_text(doc))
    found = (pieces[:TOP_K], len(pieces))
    _CHUNK_CACHE[key] = found
    return found


def render_sources(rows: list[tuple[str, str, str]]) -> str:
    """``<source>`` tags. Chunks of one file share a numeric id. Names and bodies are not escaped."""
    source_ids: dict[str, int] = {}
    parts: list[str] = []
    for source_key, name, body in rows:
        if source_key not in source_ids:
            source_ids[source_key] = len(source_ids) + 1
        number = source_ids[source_key]
        parts.append(
            f'<source id="{number}" name="{name}" resource-type="file" '
            f'resource-id="{source_key}">{body}</source>\n'
        )
    return "".join(parts)


def rag_prefix(context: str, query: str) -> str:
    """Portal template (stock v0.12.5 + attached-file guideline) with ``{{CONTEXT}}``
    filled. ``prompt_template`` is a no-op on this text."""
    template = PORTAL_RAG_TEMPLATE
    held: list[tuple[str, str]] = []
    if "[query]" in context:
        token = "{{QUERY" + uuid.uuid4().hex + "}}"
        template = template.replace("[query]", token)
        held.append((token, "[query]"))
    if "{{QUERY}}" in context:
        token = "{{QUERY" + uuid.uuid4().hex + "}}"
        template = template.replace("{{QUERY}}", token)
        held.append((token, "{{QUERY}}"))
    template = template.replace("[context]", context).replace("{{CONTEXT}}", context)
    template = template.replace("[query]", query).replace("{{QUERY}}", query)
    for token, original in held:
        template = template.replace(token, original)
    return template


def prefix_for(
    items: list[tuple[Path, str, str, str]], query: str
) -> tuple[str, list[str], int, bool]:
    """``(prefix, file ids, kept chunks, ranked_standin)`` for files in introduction order."""
    rows: list[tuple[str, str, str]] = []
    file_ids: list[str] = []
    ranked = False
    for path, suffix, file_id, name in items:
        bodies, raw = chunk_file(path, suffix)
        if raw > TOP_K:
            ranked = True
        if not bodies:
            continue
        file_ids.append(file_id)
        rows.extend((file_id, name, body) for body in bodies)
    context = render_sources(rows).strip()
    if not context:
        return "", [], 0, ranked
    return rag_prefix(context, query), file_ids, len(rows), ranked


def copied_content(content):
    if isinstance(content, list):
        return [dict(part) if isinstance(part, dict) else part for part in content]
    return "" if content is None else content


def prepend_message(message: dict, prefix: str) -> None:
    content = message.get("content")
    if isinstance(content, list):
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                item["text"] = f"{prefix}\n{item.get('text', '')}"
                return
        return
    message["content"] = f"{prefix}\n{'' if content is None else content}"


def restore_message(message: dict, prefix: str) -> None:
    if not prefix:
        return
    lead = prefix + "\n"
    content = message.get("content")
    if isinstance(content, str) and content.startswith(lead):
        message["content"] = content[len(lead) :]
        return
    if not isinstance(content, list):
        return
    for item in content:
        if isinstance(item, dict) and item.get("type") == "text":
            text = str(item.get("text", ""))
            if text.startswith(lead):
                item["text"] = text[len(lead) :]
            return
