"""Guard the default R2 hunt tool views against the served chat-loop budget."""

from __future__ import annotations

import asyncio

HUNT_TOOLS = {"hunt_sources", "hunt_start", "hunt_status", "hunt_leads", "hunt_case"}

BOUNDED_TOOL_PARAMETERS = {
    "hunt_sources": {"job_id", "index", "n", "offset", "source"},
    "hunt_start": {
        "index",
        "start",
        "end",
        "judge",
    },
    "hunt_status": {"job_id", "index"},
    "hunt_leads": {"job_id", "index", "n", "offset", "notable_id"},
    "hunt_case": {"job_id", "index", "case", "n", "offset", "evidence"},
}


def test_chat_hunt_tool_schemas_expose_only_budgeted_parameters() -> None:
    from portal.modules.security.tools import review_mcp

    tools = asyncio.run(review_mcp.mcp.list_tools())
    properties = {
        tool.name: set(tool.input_schema["properties"]) for tool in tools if tool.name in HUNT_TOOLS
    }
    assert properties == BOUNDED_TOOL_PARAMETERS
