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

from portal.platform.data_loader import load_data

# ---------------------------------------------------------------------------
# Hand-crafted positive scenarios per tool category.
#
# Each entry: (category_name, {tool_name: user_turn})
# Tools not listed here get a generic-but-realistic scenario derived from
# their description (see _FALLBACK_SCENARIOS below).
# ---------------------------------------------------------------------------


_CATEGORY_POSITIVES: dict[str, dict[str, str]] = load_data(
    "tests/data", "toolpreselect_scenario_gen_category_positives"
)

# Decoy scenarios: user turn mentions a plausible-but-wrong tool domain,
# correct tool is different.  ~20% of tools = ~12 tools.
DECOY_TOOLS: dict[str, tuple[str, str]] = {
    k: tuple(v)
    for k, v in load_data("tests/data", "toolpreselect_scenario_gen_decoy_tools").items()
}

# 10 compound/ambiguous scenarios — multi-tool asks.
# Scored PASS if any acceptable tool lands in top-K.
COMPOUND_SCENARIOS: list[dict] = load_data(
    "tests/data", "toolpreselect_scenario_gen_compound_scenarios"
)

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
