"""Deterministic tool-bundle router and request denylist for one personal task.

No model plans the task: ``route_personal_task`` picks the seat and a bounded tool
bundle from the request text, and the chosen seat calls those tools itself.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

FAST_WORKSPACE = "auto-daily::fast"
CODE_WORKSPACE = "auto-coding"
HOP_CAP = 8
HELD_TEXT = "held: operator must run launch.sh"
# The local seat loses tool-selection accuracy past this many schemas.
MAX_ROUTE_TOOLS = 18

# Read-only git tools run without a confirm; every other git_ tool (commit,
# push, ...) waits for one.
GIT_READ_TOOLS = frozenset({"git_status", "git_log", "git_diff"})
# Read-only Proxmox queries answer a question; every other proxmox_ tool changes the lab
# and waits for one (2026-11-20: a "list the stopped VMs" ask must not prompt to confirm).
PROXMOX_READ_TOOLS = frozenset(
    {
        "proxmox_list_nodes",
        "proxmox_node_status",
        "proxmox_cluster_status",
        "proxmox_list_all_vms",
        "proxmox_find_vm",
        "proxmox_list_vms",
        "proxmox_vm_status",
        "proxmox_vm_config",
        "proxmox_list_snapshots",
        "proxmox_vm_agent_info",
        "proxmox_list_containers",
        "proxmox_container_status",
        "proxmox_list_storage",
        "proxmox_list_storage_content",
        "proxmox_list_networks",
        "proxmox_task_status",
        "proxmox_list_tasks",
    }
)
# Host-native Pipeline MCP tools: they read the repository and never write it.
REPO_READ_TOOLS = frozenset({"read_text_file", "search_files", "list_directory"})
READ_TOOLS = (
    frozenset(
        {
            "recall",
            "wiki_search",
            "wiki_get_unit",
            "queue_status",
            "read_receipt",
            "workspace_files",
            "security_sweep",
        }
    )
    | REPO_READ_TOOLS
    | GIT_READ_TOOLS
    | PROXMOX_READ_TOOLS
)
CODE_TOOLS = frozenset({"execute_python", "execute_bash", "execute_nodejs"})
CONFIRM_TOOLS = CODE_TOOLS | frozenset(
    {"remember", "forget", "file_write", "send_message", "send_mail"}
)
CONFIRM_TOOL_PREFIXES = ("unifi_", "browser_")

# The always-offered read bundle (11 tools). ``read_local_file`` joins it in slice S2.
CORE_TOOLS = frozenset(
    {
        "workspace_files",
        "read_text_file",
        "search_files",
        "list_directory",
        "queue_status",
        "read_receipt",
        "wiki_search",
        "wiki_get_unit",
        "get_pipeline_status",
        "get_loaded_models",
        "recall",
    }
)
DOCUMENT_TOOLS = frozenset(
    {
        "create_word_document",
        "read_word_document",
        "create_excel",
        "read_excel",
        "read_pdf",
        "create_powerpoint",
        "security_sweep",
    }
)
# The seven read-only Proxmox queries the design's proxmox bundle names; the full
# read allowlist above is wider than a bundle may be.
PROXMOX_BUNDLE_TOOLS = frozenset(
    {
        "proxmox_list_vms",
        "proxmox_list_all_vms",
        "proxmox_list_nodes",
        "proxmox_vm_status",
        "proxmox_cluster_status",
        "proxmox_list_containers",
        "proxmox_list_storage",
    }
)
WEB_BUNDLE_TOOLS = frozenset({"web_search", "web_fetch"})
CODE_BUNDLE_TOOLS = frozenset({"execute_python"})

_HARD_TEXT = re.compile(r"\b(unifi|browser)\b", re.IGNORECASE)
_CONFIRM_TEXT = re.compile(
    r"\b(restart|reboot|shutdown|systemctl|launch\.sh|execute_bash|execute_python|"
    r"execute_nodejs|remember|forget|send mail|send an email|send a message|"
    r"docker\s+(?:run|exec|rm|rmi|stop|start|restart|kill|build|pull|push|compose|system|"
    r"volume|network))\b",
    re.IGNORECASE,
)
# A request that can change state goes to Confirm even when it names no tool.
_MUTATING_TEXT = re.compile(
    r"\b(snapshot|clone|delete|destroy|remove|start|stop|reboot|shutdown|power\s+(?:off|on)|"
    r"provision|deploy|commit|push|migrate|resize|restore|rollback)\b",
    re.IGNORECASE,
)
# Requests refused before any routing: they would tear down the stack or delete data, and no
# personal task can mean them. The reason reaches the operator's Telegram reply verbatim.
_REFUSALS = (
    (
        re.compile(r"\bdocker\s+compose\s+(?:down|rm)\b", re.IGNORECASE),
        "docker compose down would tear down the live stack",
    ),
    (
        re.compile(r"\bdocker\s+(?:system|volume|builder|image|container)\s+prune\b", re.I),
        "a docker prune would delete live images, volumes or models",
    ),
    (
        re.compile(r"\brm\s+-[a-z]*r[a-z]*f\b|\brm\s+-[a-z]*f[a-z]*r\b", re.IGNORECASE),
        "rm -rf is never run for a personal task",
    ),
    (
        re.compile(r"\blaunch\.sh\s+(?:down|rebuild)\b", re.IGNORECASE),
        "launch.sh down/rebuild belongs to the operator, not to a personal task",
    ),
    (
        re.compile(r"\bgit\s+push\s+(?:--force|-f)\b", re.IGNORECASE),
        "a force push is never run for a personal task",
    ),
)


# A question *about* a destructive command is a read-only request, not a request to run it.
_EXPLAINING = re.compile(
    r"^\s*(?:what\s+(?:does|is|are)|explain|why|how\s+(?:does|do|is)|describe|document|"
    r"summari[sz]e|review|audit|critique)\b",
    re.IGNORECASE,
)

_NO_CONCRETE_WORK = re.compile(
    r"^\s*(?:please\s+)?(?:just\s+)?"
    r"(?:clean(?:\s+things)?\s+up|tidy(?:\s+this)?\s+up|sort this out|organize this)"
    r"\s*[.!]?\s*$",
    re.IGNORECASE,
)
_DOCUMENT_TEXT = re.compile(
    r"\b(?:word\s+documents?|docx|excel|spreadsheets?|powerpoint|slides?|pdf)\b", re.IGNORECASE
)
_SWEEP_TEXT = re.compile(r"\bsecurity\s+sweep\b|\bsweep\s+report\b", re.IGNORECASE)
_PROXMOX_TEXT = re.compile(
    r"\b(?:proxmox|vmid|vms?|virtual\s+machines?|lxc|containers?|hypervisor|cluster)\b",
    re.IGNORECASE,
)
_GIT_TEXT = re.compile(r"\bgit\b", re.IGNORECASE)
_WEB_TEXT = re.compile(
    r"\b(?:web\s+search|search\s+the\s+web|search\s+online|web\s+fetch|"
    r"fetch\s+(?:the\s+)?(?:url|page)|https?://)",
    re.IGNORECASE,
)
_CODE_TEXT = re.compile(
    r"\b(?:run|execute)\b[^.\n]{0,24}\b(?:python|node|nodejs|javascript|bash|shell|script)\b",
    re.IGNORECASE,
)
_DOMAIN_BUNDLES = (
    ("documents", (_DOCUMENT_TEXT, _SWEEP_TEXT), DOCUMENT_TOOLS),
    ("proxmox", (_PROXMOX_TEXT,), PROXMOX_BUNDLE_TOOLS),
    ("git", (_GIT_TEXT,), GIT_READ_TOOLS),
    ("web", (_WEB_TEXT,), WEB_BUNDLE_TOOLS),
    ("code", (_CODE_TEXT,), CODE_BUNDLE_TOOLS),
)
_MEMORY_WRITE_TEXT = re.compile(r"\b(remember|forget)\b", re.IGNORECASE)


@dataclass(frozen=True)
class PersonalRoute:
    """One deterministic decision: seat, offered tools, and whether a confirm is due."""

    workspace: str
    tools: frozenset[str]
    bundle_name: str
    needs_confirm: bool = False
    confirm_summary: str = ""
    ask_question: str = ""

    def as_receipt(self) -> dict[str, Any]:
        return {
            "bundle": self.bundle_name,
            "workspace": self.workspace,
            "tools": sorted(self.tools),
        }

    def as_stored(self) -> dict[str, Any]:
        return {
            **self.as_receipt(),
            "needs_confirm": self.needs_confirm,
            "confirm_summary": self.confirm_summary,
            "ask_question": self.ask_question,
        }


def refusal_reason(text: str) -> str | None:
    """Why this request is refused outright, or None when it may be routed."""
    if _EXPLAINING.match(text or ""):
        return None
    for pattern, reason in _REFUSALS:
        if pattern.search(text or ""):
            return reason
    return None


def hidden_fleet_ids(config: dict[str, Any]) -> frozenset[str]:
    """Fleet ids the Pipeline does not expose. Naming one is a hard deny."""
    fleet = config.get("mcp_fleet")
    if not isinstance(fleet, list):
        return frozenset()
    hidden: set[str] = set()
    for item in fleet:
        if not isinstance(item, dict) or item.get("expose_to_pipeline") is not False:
            continue
        fleet_id = item.get("id")
        if isinstance(fleet_id, str) and fleet_id:
            hidden.add(fleet_id)
    return frozenset(hidden)


def workspace_for(tools: frozenset[str] | set[str]) -> str:
    return CODE_WORKSPACE if set(tools) & CODE_TOOLS else FAST_WORKSPACE


def text_gate(text: str, hidden: frozenset[str]) -> str:
    """``deny``, ``confirm``, or ``allow`` from the request text, before any tool call."""
    if refusal_reason(text) is not None:
        return "deny"
    lowered = text.lower()
    if any(re.search(rf"\b{re.escape(name)}\b", lowered) for name in hidden):
        return "deny"
    if _HARD_TEXT.search(text):
        return "confirm"
    if _CONFIRM_TEXT.search(text):
        return "confirm"
    return "allow"


def concrete_work_question(text: str) -> str | None:
    """No named files or action: one question, never a guessed cleanup."""
    if _NO_CONCRETE_WORK.match(text or ""):
        return "Which files may I delete?"
    return None


def route_personal_task(text: str, hidden_fleets: frozenset[str] = frozenset()) -> PersonalRoute:
    """The seat and bounded tool bundle one personal request gets. No model call."""
    question = concrete_work_question(text)
    if question is not None:
        return PersonalRoute(FAST_WORKSPACE, frozenset(), "ask", ask_question=question)
    tools = set(CORE_TOOLS)
    bundles = ["core"]
    for name, patterns, bundle in _DOMAIN_BUNDLES:
        if not any(pattern.search(text or "") for pattern in patterns):
            continue
        if len(tools | bundle) > MAX_ROUTE_TOOLS:
            continue
        tools |= bundle
        bundles.append(name)
    tools |= _named_confirm_tools(text)
    tools = {name for name in tools if not _tool_is_hidden(name, hidden_fleets)}
    needs_confirm = (
        text_gate(text, hidden_fleets) != "allow"
        or bool(_MUTATING_TEXT.search(text or ""))
        or bool(tools & CODE_TOOLS)
    )
    return PersonalRoute(
        workspace=workspace_for(tools),
        tools=frozenset(tools),
        bundle_name="+".join(bundles),
        needs_confirm=needs_confirm,
        confirm_summary=(
            f"run a state-changing request: {text.strip()[:160]}" if needs_confirm else ""
        ),
    )


def _named_confirm_tools(text: str) -> set[str]:
    """``remember``/``forget`` are only ever offered once the operator has confirmed."""
    return {match.group(1).lower() for match in _MEMORY_WRITE_TEXT.finditer(text or "")}


def _tool_is_hidden(name: str, hidden: frozenset[str]) -> bool:
    return any(name == fleet_id or name.startswith(f"{fleet_id}_") for fleet_id in hidden)


ACCEPTANCE_EMPTY = "acceptance: empty final answer"
_WORD_DOC_REQUEST = re.compile(r"\bword\s+documents?\b|\.docx\b", re.IGNORECASE)
_FABRICATED_ANSWER = re.compile(
    r"\[(?:insert|current|item|optional)\b[^\]]{0,80}\]"
    r"|\b(?:cannot|can not|can't) fulfill\b"
    r"|\bdoes not include any steps\b"
    r"|\bnot included in the (?:current )?validated plan\b",
    re.IGNORECASE,
)
_REPO_FILE = re.compile(
    r"(?<![\w./-])((?:scripts|portal|portal_channels|tests|config|docs)/[\w./-]+\.[A-Za-z0-9]+)"
)
_LARGEST_REQUEST = re.compile(r"\blargest\b", re.IGNORECASE)


def _json_object(text: str) -> dict[str, Any] | None:
    try:
        parsed = json.loads(text)
    except ValueError:
        return None
    return parsed if isinstance(parsed, dict) else None


def acceptance_failure(
    content: str,
    called: list[str],
    tool_outputs: list[str],
    *,
    request: str = "",
) -> str | None:
    """J9: why one finished local attempt failed, or None when it passed."""
    if not content.strip():
        return ACCEPTANCE_EMPTY
    for output in tool_outputs:
        parsed = _json_object(output)
        if parsed is not None and parsed.get("error"):
            return f"acceptance: tool error: {str(parsed['error'])[:200]}"
    return _ungrounded_answer(request, content, called, tool_outputs)


def _ungrounded_answer(
    request: str, content: str, called: list[str], tool_outputs: list[str]
) -> str | None:
    """Reject a done answer the live queue accepted with no supporting tool result."""
    if _WORD_DOC_REQUEST.search(request) and "create_word_document" not in called:
        return "acceptance: word document was not created"
    missing = _repo_file_missing(request, tool_outputs)
    if missing is not None:
        return f"acceptance: repository file not in tool results: {missing}"
    if _FABRICATED_ANSWER.search(content):
        return "acceptance: answer is not a completed result"
    return _omitted_largest_size(request, content, tool_outputs)


def _repo_file_missing(request: str, tool_outputs: list[str]) -> str | None:
    for found in _REPO_FILE.findall(request):
        path = str(found)
        if not _repo_file_read(path, tool_outputs):
            return path
    return None


def _repo_file_read(path: str, tool_outputs: list[str]) -> bool:
    """A repo path is grounded only by a read of it — a listing that echoes the request is not."""
    for output in tool_outputs:
        parsed = _json_object(output)
        if not isinstance(parsed, dict):
            continue
        content = parsed.get("content")
        reported = str(parsed.get("path") or "")
        if isinstance(content, str) and content.strip() and reported.endswith(path):
            return True
        matches = parsed.get("matches")
        if isinstance(matches, list) and any(str(hit).startswith(f"{path}:") for hit in matches):
            return True
    return False


def _omitted_largest_size(request: str, content: str, tool_outputs: list[str]) -> str | None:
    if _LARGEST_REQUEST.search(request) is None:
        return None
    sizes: list[int] = []
    for output in tool_outputs:
        for item in _file_rows(output):
            size = item.get("size")
            if isinstance(size, int) and not isinstance(size, bool):
                sizes.append(size)
    if not sizes:
        return None
    top = max(sizes)
    if re.search(rf"(?<!\d)(?:{top}|{top:,})(?!\d)", content):
        return None
    return "acceptance: answer omits the largest file size from the tool result"


def _file_rows(output: str) -> list[dict[str, Any]]:
    parsed = _json_object(output)
    files = parsed.get("files") if isinstance(parsed, dict) else None
    if not isinstance(files, list):
        return []
    return [item for item in files if isinstance(item, dict)]
