"""Drop download claims that are not backed by a successful file creation."""

from __future__ import annotations

import json
import re
from typing import Any

_DOWNLOAD_LINE_START = re.compile(
    r"^\s*(?:(?:[-*+>]\s+|\d+[.)]\s+))?(?:\*\*|__)?\s*"
    r"Download(?:\*\*|__)?(?=\W|$)",
    re.IGNORECASE,
)
_DOWNLOAD_TARGET = re.compile(
    r"(?:https?://\S+|www\.\S+|(?:^|\s)(?:file://)?(?:/|\.\.?/|[A-Za-z]:[\\/])\S+"
    r"|(?:^|\s)[\w.-]+(?:[/\\][\w.-]+)+"
    r"|(?:^|\s)[\w.-]+\.[A-Za-z][A-Za-z0-9]{1,12}\b)",
    re.IGNORECASE,
)


def _is_download_link_line(line: str) -> bool:
    return bool(_DOWNLOAD_LINE_START.search(line) and _DOWNLOAD_TARGET.search(line))


# A markdown link whose label or target is an office file this turn did not create.
_MD_LINK_RE = re.compile(r"\[([^\]]*)\]\(([^)\s]+)\)")
_OFFICE_EXT_RE = re.compile(r"\.(?:docx|xlsx|pptx)\b", re.IGNORECASE)
_DOWNLOAD_LEADIN_RE = re.compile(
    r"(?:you can\s+)?download(?:\s+it)?(?:\s+(?:from|here))?\s*:?\s*",
    re.IGNORECASE,
)


def _office_link_sub(match: re.Match[str]) -> str:
    label, url = match.group(1), match.group(2)
    if _OFFICE_EXT_RE.search(label) or _OFFICE_EXT_RE.search(url):
        return ""
    return match.group(0)


def _strip_office_markdown(text: str) -> str:
    return _MD_LINK_RE.sub(_office_link_sub, text)


def _split_ending(line: str) -> tuple[str, str]:
    if line.endswith("\r\n"):
        return line[:-2], "\r\n"
    if line.endswith("\n"):
        return line[:-1], "\n"
    return line, ""


def strip_unbacked_download_lines(content: str) -> str:
    """Remove download lines and office-file links no create tool returned."""
    kept: list[str] = []
    for line in content.splitlines(keepends=True):
        if _is_download_link_line(line):
            continue
        body, ending = _split_ending(line)
        cleaned = _strip_office_markdown(body)
        if cleaned != body and (
            not cleaned.strip() or _DOWNLOAD_LEADIN_RE.fullmatch(cleaned.strip()) is not None
        ):
            continue
        kept.append(cleaned + ending)
    return "".join(kept)


def _creates_files(name: str) -> bool:
    return name.startswith("create_") or name == "convert_document"


def offers_file_creation(tools: Any) -> bool:
    """Whether the request offered a create/convert tool. Only those turns are filtered: a
    workspace with no file tools may legitimately say "Download VS Code from https://…"."""
    for tool in tools or []:
        spec = tool.get("function", tool) if isinstance(tool, dict) else None
        name = spec.get("name") if isinstance(spec, dict) else None
        if isinstance(name, str) and _creates_files(name):
            return True
    return False


def successful_file_creation(result: dict[str, Any]) -> bool:
    """Whether a dispatched tool result confirms a create/convert success."""
    name = str(result.get("name") or "")
    if not _creates_files(name):
        return False
    try:
        payload = json.loads(result.get("content") or "")
    except (json.JSONDecodeError, TypeError):
        return False
    return isinstance(payload, dict) and payload.get("success") is True


def _download_prefix_status(line: str) -> str:
    """Return possible/candidate/no while the beginning of a streamed line arrives."""
    prefix = line.lstrip()
    if not prefix:
        return "possible"

    if prefix.startswith(("**", "__")):
        prefix = prefix[2:].lstrip()
    elif prefix[0] in "*-+>":
        if len(prefix) == 1:
            return "possible"
        if not prefix[1].isspace():
            return "no"
        prefix = prefix[1:].lstrip()
        if prefix.startswith(("**", "__")):
            prefix = prefix[2:].lstrip()

    if not prefix:
        return "possible"
    if len(prefix) < len("Download"):
        return "possible" if "Download".lower().startswith(prefix.lower()) else "no"
    if prefix[: len("Download")].lower() != "download":
        return "no"

    suffix = prefix[len("Download") :]
    if not suffix:
        return "possible"
    if suffix.startswith(("**", "__")):
        suffix = suffix[2:]
    if not suffix:
        return "possible"
    return "candidate" if not (suffix[0].isalnum() or suffix[0] == "_") else "no"


class DownloadLineFilter:
    """Stream content immediately except a possible Download line.

    Candidate link lines are held until the turn establishes whether a file was
    created. Ordinary lines stream as soon as they stop matching the line prefix.
    """

    def __init__(self) -> None:
        self._line = ""
        self._link = ""
        self._mode = "prefix"
        self._deferred: list[str] = []
        self._keep_downloads = False

    def _complete_line(self, emitted: list[str]) -> None:
        line = self._line
        self._line = ""
        self._mode = "prefix"
        if _is_download_link_line(line) and not self._keep_downloads:
            self._deferred.append(line)
        else:
            emitted.append(line)

    def _take_non_download(self) -> str:
        """Emit a non-Download prefix, holding a trailing ``[`` as a possible link."""
        bracket = self._line.rfind("[")
        if bracket == -1:
            text = self._line
            self._line = ""
            self._mode = "passthrough"
            return text
        head = self._line[:bracket]
        self._link = self._line[bracket:]
        self._line = ""
        self._mode = "link"
        return head

    def _link_char(self, char: str) -> str:
        """Hold a markdown span. An office-file link is deferred until a create succeeds."""
        self._link += char
        if char == "\n":
            text = _strip_office_markdown(self._link)
            self._link = ""
            self._mode = "prefix"
            return text
        if "](" in self._link and char == ")":
            text = self._link
            self._link = ""
            self._mode = "passthrough"
            if _strip_office_markdown(text) != text:
                self._deferred.append(text)
                return ""
            return text
        if re.fullmatch(r"\[[^\]]*\]", self._link):
            return ""
        if "](" not in self._link and re.match(r"\[[^\]]*\]", self._link):
            text = self._link
            self._link = ""
            self._mode = "passthrough"
            return text
        if len(self._link) > 600 and "](" not in self._link:
            text = self._link
            self._link = ""
            self._mode = "passthrough"
            return text
        return ""

    def _feed_free(self, char: str) -> str:
        if self._mode == "link":
            return self._link_char(char)
        if char == "[":
            self._mode = "link"
            self._link = "["
            return ""
        if char == "\n":
            self._mode = "prefix"
        return char

    def feed(self, text: str) -> str:
        if self._keep_downloads:
            return text

        emitted: list[str] = []
        for char in text:
            if self._mode in {"passthrough", "link"}:
                emitted.append(self._feed_free(char))
                continue

            self._line += char
            if self._mode == "candidate":
                if char == "\n":
                    self._complete_line(emitted)
                continue

            if char == "\n":
                emitted.append(self._line)
                self._line = ""
                self._mode = "prefix"
                continue

            status = _download_prefix_status(self._line)
            if status == "candidate":
                self._mode = "candidate"
            elif status == "no":
                emitted.append(self._take_non_download())

        return "".join(emitted)

    def mark_successful_creation(self) -> str:
        """Keep and release held link lines once a create tool succeeds."""
        self._keep_downloads = True
        pending = "".join(self._deferred) + self._line + self._link
        self._deferred.clear()
        self._line = ""
        self._link = ""
        self._mode = "prefix"
        return pending

    def finish(self) -> str:
        """Flush ordinary pending text and discard unbacked link lines."""
        link = _strip_office_markdown(self._link)
        if self._keep_downloads:
            pending = "".join(self._deferred) + self._line + self._link
        else:
            pending = "" if self._line and _is_download_link_line(self._line) else self._line
            pending += link
        self._deferred.clear()
        self._line = ""
        self._link = ""
        self._mode = "prefix"
        return pending
