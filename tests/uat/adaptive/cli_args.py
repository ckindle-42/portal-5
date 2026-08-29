"""Adaptive UAT — argparse flags for the main driver (TASK_UAT_ADAPTIVE_OVERHAUL_V1).

Kept in the adaptive package so the driver's parser gains the flags with a
single call (`add_adaptive_args(parser)`), and the adaptive surface stays
self-contained. Execution flags only — the offline packet/ingest flags live in
tests/portal5_uat_adaptive.py.
"""

from __future__ import annotations

import argparse


def add_adaptive_args(parser: argparse.ArgumentParser) -> None:
    g = parser.add_argument_group("adaptive UAT (v9 release sign-off)")
    g.add_argument(
        "--adaptive",
        action="store_true",
        help="Run the adaptive (generative, per-space, operator-reviewed) UAT "
        "through OWUI instead of the static catalog.",
    )
    g.add_argument(
        "--adaptive-regenerate",
        action="store_true",
        help="Re-author challenge suites with the author model (default: replay frozen).",
    )
    g.add_argument(
        "--adaptive-dry-run",
        action="store_true",
        help="Author challenges from templates only (no author-model call).",
    )
    g.add_argument(
        "--adaptive-space",
        action="append",
        metavar="ID",
        help="Restrict to space id(s) e.g. auto-cad, persona:githubexpert (repeatable).",
    )
    g.add_argument(
        "--adaptive-dimension",
        action="append",
        metavar="DIM",
        help="Restrict to dimension(s): depth breadth edge boundary tool format continuity.",
    )
    g.add_argument(
        "--adaptive-author-model",
        metavar="SLUG",
        default="",
        help="Author-model workspace slug (env UAT_ADAPTIVE_AUTHOR_MODEL).",
    )
    g.add_argument(
        "--adaptive-include-unreachable",
        action="store_true",
        help="Also emit spaces with no OWUI exposure signal (agent resolves live).",
    )
