"""Exhaustive scenario generator for tool-preselect acceptance bench.

Reads the live tool inventory from tool_registry.refresh() and generates:
1. One clean positive scenario per tool (hand-crafted per category)
2. Decoy scenarios for ~20% of tools
3. 10 compound/ambiguous scenarios
4. 10 reorder-check scenarios (subset of positives, reversed tool list)
5. 5 no-good-fit scenarios

Output: tests/toolpreselect/scenarios.json
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Hand-crafted positive scenarios per tool category.
#
# Each entry: (category_name, {tool_name: user_turn})
# Tools not listed here get a generic-but-realistic scenario derived from
# their description (see _FALLBACK_SCENARIOS below).
# ---------------------------------------------------------------------------

_CATEGORY_POSITIVES: dict[str, dict[str, str]] = {
    "pipeline": {
        "explore_repository": "Where is the LLM router's workspace detection logic in this codebase?",
        "get_loaded_models": "Which Ollama models are currently loaded in memory right now?",
        "get_metrics_summary": "Show me the current request counts and error rates from Prometheus.",
        "get_pipeline_status": "Is the pipeline healthy? How many backends and workspaces are configured?",
        "get_workspace_recommendation": "I need to analyze a CVE and write a detection — which workspace should I use?",
        "list_directory": "What files are in the portal/platform/inference/router/ directory?",
        "list_workspaces": "Show me all available workspaces, especially any related to security.",
        "read_text_file": "Read the contents of config/portal.yaml so I can review the workspace definitions.",
        "search_files": "Find all Python files that reference the ToolRegistry class.",
        "trigger_backend_warmup": "Pre-load the coding workspace model before I start a long session.",
        "write_file": "Create a new file at /tmp/test_output.txt with the text 'hello world'.",
    },
    "execution": {
        "execute_bash": "Run a shell command to check the disk usage on this machine.",
        "execute_nodejs": "Execute a quick JavaScript snippet to parse some JSON data.",
        "execute_powershell": "Run a PowerShell command to list running processes on this system.",
        "execute_python": "Run a Python one-liner to calculate the factorial of 20.",
        "sandbox_status": "Is the code sandbox Docker environment available and healthy?",
    },
    "documents": {
        "convert_document": "Convert this markdown file to a PDF document.",
        "create_excel": "Create a spreadsheet with the quarterly revenue numbers for each department.",
        "create_powerpoint": "Build a presentation summarizing the key findings from our security audit.",
        "create_word_document": "Generate a Word document with the meeting notes from today's standup.",
        "list_generated_files": "What documents have been generated recently in the output directory?",
        "read_excel": "Extract the data from this Excel spreadsheet so I can analyze it.",
        "read_pdf": "Read the contents of this PDF report and extract the key tables.",
        "read_powerpoint": "Pull the text and speaker notes from this PowerPoint presentation.",
        "read_word_document": "Extract the text content from this Word document.",
    },
    "memory": {
        "clear_memories": "Delete all stored memories — I want a fresh start.",
        "forget": "Remove the memory about my old SSH key configuration.",
        "list_memories": "Show me everything stored in memory right now.",
        "recall": "What do you remember about my preferred coding style?",
        "remember": "Save that I prefer dark mode and tabs over spaces for indentation.",
    },
    "tts": {
        "clone_voice": "Clone this voice sample and speak the announcement text with it.",
        "list_voices": "What voices are available for text-to-speech right now?",
        "speak": "Read this paragraph aloud using a female voice.",
    },
    "cad_render": {
        "convert_cad": "Convert this STL file to 3MF format for my slicer.",
        "render_mesh": "Render this 3D mesh file to a PNG image so I can preview it.",
        "render_openscad": "Render this OpenSCAD code to a PNG image of the resulting 3D model.",
    },
    "research": {
        "news_search": "Find recent news articles about vulnerabilities in OpenSSH.",
        "web_fetch": "Fetch the content of this URL and extract the main text.",
        "web_search": "Search the web for the latest Ollama release notes.",
    },
    "rag": {
        "kb_ingest": "Ingest these markdown files into the security knowledge base.",
        "kb_list": "What knowledge bases are available and how many documents does each have?",
        "kb_optimize": "Build a vector index on the detection library KB for faster search.",
        "kb_restore": "Restore the security KB to the version from before the last bad ingest.",
        "kb_search": "Search the security KB for information about lateral movement techniques.",
        "kb_search_all": "Search across all knowledge bases for anything related to Cobalt Strike.",
        "kb_versions": "Show me the version history of the detection library knowledge base.",
    },
    "mitre": {
        "mitre_data_sources_for_technique": "What data sources do I need to detect pass-the-hash attacks?",
        "mitre_detections_for_technique": "Show me our local SPL detections for credential dumping.",
        "mitre_technique_lookup": "Look up technique T1190 in the ATT&CK framework.",
        "mitre_techniques_list": "List all ATT&CK techniques in the initial-access tactic.",
    },
    "detections": {
        "spl_diff_hypothesis": "Compare this Splunk query result against the expected signal for T1003.",
        "spl_explain_detection": "Explain the logic behind our credential-dumping detection rule.",
        "spl_search_library": "Find all SPL detections that cover Kerberoasting.",
        "spl_techniques_covered": "Which technique IDs have SPL detections in our library?",
        "spl_validate_syntax": "Check if this SPL query has any syntax errors before I run it.",
    },
    "whisper": {
        "transcribe_audio": "Transcribe this audio recording to text.",
        "transcribe_with_speakers": "Transcribe this meeting recording and label each speaker.",
    },
    "wiki": {
        "wiki_explain": "Explain how the tool preselector works in Portal 5.",
        "wiki_get_unit": "Get the knowledge unit about the RBP benchmark engine.",
        "wiki_search": "Search the wiki for information about the MCP tool fleet.",
    },
    "security": {
        "classify_vulnerability": "Classify this CVE description to determine its severity level.",
    },
}

# Decoy scenarios: user turn mentions a plausible-but-wrong tool domain,
# correct tool is different.  ~20% of tools = ~12 tools.
DECOY_TOOLS: dict[str, tuple[str, str]] = {
    # (user_turn, correct_tool)
    "execute_bash": (
        "I need to run a Python script in an isolated container.",
        "execute_python",
    ),
    "web_search": (
        "Fetch the full text content of this specific URL.",
        "web_fetch",
    ),
    "create_word_document": (
        "Generate a spreadsheet with the quarterly revenue numbers.",
        "create_excel",
    ),
    "kb_search": (
        "Search across all knowledge bases for Cobalt Strike indicators.",
        "kb_search_all",
    ),
    "read_pdf": (
        "Extract text from this Word document.",
        "read_word_document",
    ),
    "recall": (
        "Store this fact about my preferences for later.",
        "remember",
    ),
    "render_openscad": (
        "Render this existing STL mesh file to a PNG image.",
        "render_mesh",
    ),
    "wiki_search": (
        "Explain how the tool preselector works in Portal 5.",
        "wiki_explain",
    ),
    "mitre_technique_lookup": (
        "List all ATT&CK techniques in the initial-access tactic.",
        "mitre_techniques_list",
    ),
    "spl_search_library": (
        "Check if this SPL query has syntax errors.",
        "spl_validate_syntax",
    ),
    "news_search": (
        "Search the web for the latest Ollama release notes.",
        "web_search",
    ),
    "transcribe_audio": (
        "Transcribe this meeting recording and label each speaker.",
        "transcribe_with_speakers",
    ),
}

# 10 compound/ambiguous scenarios — multi-tool asks.
# Scored PASS if any acceptable tool lands in top-K.
COMPOUND_SCENARIOS: list[dict] = [
    {
        "id": "C1",
        "user_turn": "I found a suspicious binary on a host — analyze the CVE it might exploit and write up a report.",
        "acceptable_tools": [
            "classify_vulnerability",
            "create_word_document",
            "web_search",
            "mitre_technique_lookup",
        ],
    },
    {
        "id": "C2",
        "user_turn": "Search for Kerberoasting detections, validate the SPL syntax, then run it in the sandbox.",
        "acceptable_tools": [
            "spl_search_library",
            "spl_validate_syntax",
            "execute_bash",
            "execute_python",
        ],
    },
    {
        "id": "C3",
        "user_turn": "Read this PDF report, extract the key findings, and save them to a Word document.",
        "acceptable_tools": ["read_pdf", "create_word_document", "read_text_file"],
    },
    {
        "id": "C4",
        "user_turn": "What models are loaded, and can you pre-load the coding model before I start?",
        "acceptable_tools": ["get_loaded_models", "trigger_backend_warmup"],
    },
    {
        "id": "C5",
        "user_turn": "Search the web for recent proxy shell exploits, then look up the relevant ATT&CK technique.",
        "acceptable_tools": ["web_search", "mitre_technique_lookup", "news_search"],
    },
    {
        "id": "C6",
        "user_turn": "Transcribe this audio file and store the key points in memory for later.",
        "acceptable_tools": ["transcribe_audio", "transcribe_with_speakers", "remember"],
    },
    {
        "id": "C7",
        "user_turn": "Find all Python files referencing ToolRegistry, read the main module, and explain it.",
        "acceptable_tools": [
            "search_files",
            "read_text_file",
            "explore_repository",
            "wiki_explain",
        ],
    },
    {
        "id": "C8",
        "user_turn": "Create a presentation about our detection coverage — pull stats from the SPL library and format it as slides.",
        "acceptable_tools": ["spl_techniques_covered", "create_powerpoint", "spl_search_library"],
    },
    {
        "id": "C9",
        "user_turn": "Ingest these documents into the KB, build a vector index, then search for lateral movement.",
        "acceptable_tools": ["kb_ingest", "kb_optimize", "kb_search"],
    },
    {
        "id": "C10",
        "user_turn": "Check pipeline health, list all workspaces, and tell me which one is best for a security analysis task.",
        "acceptable_tools": [
            "get_pipeline_status",
            "list_workspaces",
            "get_workspace_recommendation",
        ],
    },
]

# 5 no-good-fit scenarios — conversational turns with no real tool need.
NO_GOOD_FIT_SCENARIOS: list[dict] = [
    {
        "id": "NGF1",
        "user_turn": "What's your opinion on the best programming language for AI?",
    },
    {
        "id": "NGF2",
        "user_turn": "Tell me a joke about computers.",
    },
    {
        "id": "NGF3",
        "user_turn": "How are you feeling today?",
    },
    {
        "id": "NGF4",
        "user_turn": "What did you have for breakfast?",
    },
    {
        "id": "NGF5",
        "user_turn": "Summarize the meaning of life.",
    },
]


def _build_positive_scenarios(tools: list[dict]) -> list[dict]:
    """Build one positive scenario per tool from hand-crafted category maps."""
    scenarios: list[dict] = []
    seen_turns: set[str] = set()

    # Index tools by category
    by_category: dict[str, list[dict]] = {}
    for t in tools:
        cat = t["server_id"]
        by_category.setdefault(cat, []).append(t)

    for cat, tool_list in sorted(by_category.items()):
        cat_map = _CATEGORY_POSITIVES.get(cat, {})
        for t in sorted(tool_list, key=lambda x: x["name"]):
            name = t["name"]
            user_turn = cat_map.get(name)
            if user_turn is None:
                # Fallback: derive from description
                desc = t["description"]
                user_turn = f"I need to use a tool that can: {desc[:120]}"
            # Deduplicate turns (can happen if fallback matches a hand-crafted one)
            if user_turn in seen_turns:
                user_turn = f"[{name}] {user_turn}"
            seen_turns.add(user_turn)

            scenarios.append(
                {
                    "id": f"P_{name}",
                    "user_turn": user_turn,
                    "tool_list_order": "normal",
                    "acceptable_tools": [name],
                    "category": "positive",
                    "target_tool": name,
                }
            )

    return scenarios


def _build_decoy_scenarios(tools: list[dict]) -> list[dict]:
    """Build decoy scenarios for ~20% of tools."""
    all_names = [t["name"] for t in tools]
    scenarios: list[dict] = []

    for tool_name, (user_turn, correct_tool) in DECOY_TOOLS.items():
        if tool_name not in all_names:
            continue
        scenarios.append(
            {
                "id": f"D_{tool_name}",
                "user_turn": user_turn,
                "tool_list_order": "normal",
                "acceptable_tools": [correct_tool],
                "category": "decoy",
                "target_tool": correct_tool,
                "decoy_tool": tool_name,
            }
        )

    return scenarios


def _build_compound_scenarios(tools: list[dict]) -> list[dict]:
    """Build compound/ambiguous scenarios."""
    scenarios: list[dict] = []
    for sc in COMPOUND_SCENARIOS:
        # Filter acceptable_tools to only those that actually exist in the fleet
        valid = [t for t in sc["acceptable_tools"] if t in {x["name"] for x in tools}]
        if not valid:
            continue
        scenarios.append(
            {
                "id": sc["id"],
                "user_turn": sc["user_turn"],
                "tool_list_order": "normal",
                "acceptable_tools": valid,
                "category": "compound",
            }
        )
    return scenarios


def _build_reorder_scenarios(positive_scenarios: list[dict], tools: list[dict]) -> list[dict]:
    """Take 10 positive scenarios and create reversed-list variants."""

    # Pick 10 diverse positive scenarios (spread across categories)
    by_cat: dict[str, list[dict]] = {}
    for sc in positive_scenarios:
        cat = sc.get("target_tool", "")
        # Find the server_id for this tool
        tool_info = next((t for t in tools if t["name"] == cat), None)
        server = tool_info["server_id"] if tool_info else "unknown"
        by_cat.setdefault(server, []).append(sc)

    selected: list[dict] = []
    cats = sorted(by_cat.keys())
    for cat in cats:
        if len(selected) >= 10:
            break
        # Pick one from each category until we have 10
        picks = by_cat[cat]
        selected.append(picks[0])

    scenarios: list[dict] = []
    for sc in selected[:10]:
        scenarios.append(
            {
                "id": f"R_{sc['id']}",
                "user_turn": sc["user_turn"],
                "tool_list_order": "reversed",
                "acceptable_tools": sc["acceptable_tools"],
                "category": "reorder",
                "target_tool": sc["target_tool"],
                "original_id": sc["id"],
            }
        )

    return scenarios


def _build_no_good_fit_scenarios(tools: list[dict]) -> list[dict]:
    """Build no-good-fit scenarios."""
    scenarios: list[dict] = []
    for sc in NO_GOOD_FIT_SCENARIOS:
        scenarios.append(
            {
                "id": sc["id"],
                "user_turn": sc["user_turn"],
                "tool_list_order": "normal",
                "acceptable_tools": [],
                "category": "no_good_fit",
            }
        )
    return scenarios


async def generate_scenarios() -> list[dict]:
    """Generate all scenarios from the live tool inventory."""
    from portal.platform.inference.tool_registry import ToolRegistry

    r = ToolRegistry()
    n = await r.refresh(force=True)
    print(f"Discovered {n} tools from live MCP fleet", file=sys.stderr)

    tools = []
    for name, td in sorted(r._tools.items()):
        tools.append(
            {
                "name": name,
                "server_id": td.server_id,
                "description": td.description,
            }
        )

    all_scenarios: list[dict] = []

    # 1. Positive scenarios (one per tool)
    positives = _build_positive_scenarios(tools)
    all_scenarios.extend(positives)
    print(f"  Positive scenarios: {len(positives)}", file=sys.stderr)

    # 2. Decoy scenarios (~20% of tools)
    decoys = _build_decoy_scenarios(tools)
    all_scenarios.extend(decoys)
    print(f"  Decoy scenarios: {len(decoys)}", file=sys.stderr)

    # 3. Compound/ambiguous scenarios
    compounds = _build_compound_scenarios(tools)
    all_scenarios.extend(compounds)
    print(f"  Compound scenarios: {len(compounds)}", file=sys.stderr)

    # 4. Reorder-check scenarios (10 from positives, reversed list)
    reorders = _build_reorder_scenarios(positives, tools)
    all_scenarios.extend(reorders)
    print(f"  Reorder scenarios: {len(reorders)}", file=sys.stderr)

    # 5. No-good-fit scenarios
    ngf = _build_no_good_fit_scenarios(tools)
    all_scenarios.extend(ngf)
    print(f"  No-good-fit scenarios: {len(ngf)}", file=sys.stderr)

    total = len(all_scenarios)
    print(f"  TOTAL: {total} scenarios", file=sys.stderr)
    print(
        f"  Expected roughly: {n} + {int(n * 0.2)} + 10 + 10 + 5 = {n + int(n * 0.2) + 25}",
        file=sys.stderr,
    )

    # Persist the tool list alongside scenarios for the runner
    output = {
        "tool_count": n,
        "tools": tools,
        "scenarios": all_scenarios,
    }

    return output


def main() -> int:
    output = asyncio.run(generate_scenarios())

    out_path = Path(__file__).parent / "scenarios.json"
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2)

    print(f"\nWrote {len(output['scenarios'])} scenarios to {out_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
