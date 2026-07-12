"""``python3 -m portal.modules.security.core capability ...`` — Phase 4.

Subcommands: list, query, tools, arsenal. Read-only over the capability
index and tool catalog — never touches the lab.
"""

from __future__ import annotations

import json


def capability_main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        prog="portal security capability",
        description="Capability index — query the unified security library",
    )
    sub = parser.add_subparsers(dest="subcommand", required=True)

    p_list = sub.add_parser("list", help="List all indexed capabilities")
    p_list.add_argument("--phase", default=None, help="Filter by phase")
    p_list.add_argument("--domain", default=None, help="Filter by domain")
    p_list.add_argument("--json", action="store_true", help="Output JSON")

    p_query = sub.add_parser("query", help="Query capabilities against observations")
    p_query.add_argument(
        "--observations",
        default="{}",
        metavar="JSON",
        help="JSON dict of observations, e.g. '{\"open_ports\": [445, 80]}'",
    )
    p_query.add_argument("--phase", default=None, help="Filter by phase")
    p_query.add_argument("--domain", default=None, help="Filter by domain")
    p_query.add_argument("--goal", default=None, help="Free-text goal filter")
    p_query.add_argument("--limit", type=int, default=12)
    p_query.add_argument("--json", action="store_true", help="Output JSON")

    p_tools = sub.add_parser("tools", help="List declared tool catalog entries")
    p_tools.add_argument("--service", default=None, help="Filter by targets_services")
    p_tools.add_argument("--phase", default=None, help="Filter by phase")
    p_tools.add_argument("--json", action="store_true", help="Output JSON")

    p_arsenal = sub.add_parser("arsenal", help="Render tool arsenal (human-readable)")
    p_arsenal.add_argument("--service", default=None)
    p_arsenal.add_argument("--phase", default=None)

    args = parser.parse_args(argv)

    from .index import build_index, query
    from .render import render_capabilities, render_tool_arsenal
    from .tool_inventory import load_tool_catalog

    if args.subcommand == "list":
        caps = build_index()
        if args.phase:
            caps = [c for c in caps if c.phase == args.phase]
        if args.domain:
            caps = [c for c in caps if c.domain == args.domain]
        if args.json:
            print(json.dumps([vars(c) for c in caps], indent=2, default=str))
        else:
            print(render_capabilities(caps))
        return 0

    if args.subcommand == "query":
        observations = json.loads(args.observations)
        results = query(
            observations,
            phase=args.phase,
            domain=args.domain,
            goal=args.goal,
            limit=args.limit,
        )
        if args.json:
            print(json.dumps([vars(c) for c in results], indent=2, default=str))
        else:
            print(render_capabilities(results))
        return 0

    if args.subcommand == "tools":
        tools = load_tool_catalog()
        if args.service:
            tools = [t for t in tools if args.service in (t.get("targets_services") or [])]
        if args.phase:
            tools = [t for t in tools if t.get("phase") == args.phase]
        if args.json:
            print(json.dumps(tools, indent=2, default=str))
        else:
            for t in tools:
                print(f"{t['name']:<24} {t.get('category', '-'):<12} {t.get('phase', '-')}")
        return 0

    if args.subcommand == "arsenal":
        print(render_tool_arsenal(phase=args.phase, service=args.service))
        return 0

    return 1
