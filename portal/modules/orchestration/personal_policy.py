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
# The local seat loses tool-selection accuracy past this many schemas: room for the
# always-offered core (12) plus the largest domain bundle (documents, 7).
MAX_ROUTE_TOOLS = 19

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

# The always-offered read bundle (12 tools). ``read_local_file`` is S2's host-file read.
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
        "read_local_file",
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
# The operator's own sentence is the exact memory text the confirm asks them to approve.
_MEMORY_SENTENCE = re.compile(
    r"^\s*(?:please\s+)?(remember|forget)\s+(?:that\s+)?(.+?)\s*$", re.IGNORECASE
)


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
    tools = set(CORE_TOOLS) | _named_confirm_tools(text)
    bundles = ["core"]
    for name, patterns, bundle in _DOMAIN_BUNDLES:
        if not any(pattern.search(text or "") for pattern in patterns):
            continue
        if len(tools | bundle) > MAX_ROUTE_TOOLS:
            continue
        tools |= bundle
        bundles.append(name)
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
        confirm_summary=_confirm_summary(text, needs_confirm, tools),
    )


def _confirm_summary(text: str, needs_confirm: bool, tools: set[str]) -> str:
    """What the Confirm prompt names: the exact memory sentence, else the action and its target."""
    if not needs_confirm:
        return ""
    memory = memory_write_summary(text)
    if memory:
        return memory
    action = "run code" if tools & CODE_TOOLS else "run this request"
    return f"{action}: {text.strip()[:160]}"


def memory_write_summary(text: str) -> str:
    """The exact sentence a remember/forget request would save, or "" for any other request."""
    match = _MEMORY_SENTENCE.match(text or "")
    if match is None:
        return ""
    verb, sentence = match.group(1).lower(), match.group(2).strip().rstrip(".")
    action = "save memory" if verb == "remember" else "forget memory"
    return f"{action} '{sentence}'"


def _named_confirm_tools(text: str) -> set[str]:
    """``remember``/``forget`` are only ever offered once the operator has confirmed."""
    return {match.group(1).lower() for match in _MEMORY_WRITE_TEXT.finditer(text or "")}


def _tool_is_hidden(name: str, hidden: frozenset[str]) -> bool:
    return any(name == fleet_id or name.startswith(f"{fleet_id}_") for fleet_id in hidden)


ACCEPTANCE_EMPTY = "acceptance: empty final answer"
ACCEPTANCE_NO_TOOL = "acceptance: data request answered without a tool call"
# Creating a file is only done when the tool names what it wrote.
DOCUMENT_CREATE_TOOLS = frozenset({"create_word_document", "create_excel", "create_powerpoint"})
_DELIVERED_KEYS = ("path", "filename", "download_url", "url")
_FABRICATED_ANSWER = re.compile(
    r"\[(?:insert|current|item|optional)\b[^\]]{0,80}\]"
    r"|\b(?:cannot|can not|can't) fulfill\b"
    r"|\bdoes not include any steps\b"
    r"|\bnot included in the (?:current )?validated plan\b",
    re.IGNORECASE,
)


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
    hops: int = 0,
    requires_tools: bool = False,
) -> str | None:
    """J9: why one finished local attempt failed, or None when it passed."""
    if not content.strip():
        return ACCEPTANCE_EMPTY
    error = _unrecovered_tool_error(tool_outputs)
    if error is not None:
        return f"acceptance: tool error: {error}"
    if requires_tools and hops < 1:
        return ACCEPTANCE_NO_TOOL
    if _FABRICATED_ANSWER.search(content):
        return "acceptance: answer is not a completed result"
    if set(called) & DOCUMENT_CREATE_TOOLS and not _document_delivered(called, tool_outputs):
        return "acceptance: document tool returned no path"
    return None


def _unrecovered_tool_error(tool_outputs: list[str]) -> str | None:
    """A tool error is fatal only when no later call returned a result."""
    last_error = -1
    last_success = -1
    for index, output in enumerate(tool_outputs):
        parsed = _json_object(output)
        if isinstance(parsed, dict) and parsed.get("error"):
            last_error = index
        else:
            last_success = index
    if last_error < 0 or last_success > last_error:
        return None
    failed = _json_object(tool_outputs[last_error]) or {}
    return str(failed.get("error"))[:200]


def _document_delivered(called: list[str], tool_outputs: list[str]) -> bool:
    """The create call succeeded when its own result names the file it wrote."""
    if len(called) == len(tool_outputs):
        returns = [
            output
            for name, output in zip(called, tool_outputs, strict=True)
            if name in DOCUMENT_CREATE_TOOLS
        ]
    else:
        returns = tool_outputs
    return any(_reports_a_file(output) for output in returns)


def _reports_a_file(output: str) -> bool:
    parsed = _json_object(output)
    if not isinstance(parsed, dict) or parsed.get("error") or parsed.get("success") is False:
        return False
    return any(isinstance(parsed.get(key), str) and parsed[key] for key in _DELIVERED_KEYS)
