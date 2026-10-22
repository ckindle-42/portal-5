"""Module plugin hooks discovered by the platform."""

from __future__ import annotations

import importlib
import importlib.util
import sys
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Any

import portal.modules


def module_code_present(dotted: str) -> bool:
    """Return whether a module path can be imported."""
    if dotted in sys.modules:
        return True
    try:
        return importlib.util.find_spec(dotted) is not None
    except (ModuleNotFoundError, ValueError):
        return False


def plugins() -> list[ModuleType]:
    """Load every module plugin in module-name order."""
    found: list[ModuleType] = []
    for root in portal.modules.__path__:
        for plugin_py in sorted(Path(root).glob("*/plugin.py")):
            name = plugin_py.parent.name
            found.append(importlib.import_module(f"portal.modules.{name}.plugin"))
    return found


def register_cli(app: Any) -> None:
    for plugin in plugins():
        hook = getattr(plugin, "register_cli", None)
        if hook is not None:
            hook(app)


def wiki_probes() -> dict[str, Callable[[Path], Any]]:
    merged: dict[str, Callable[[Path], Any]] = {}
    for plugin in plugins():
        hook = getattr(plugin, "wiki_probes", None)
        if hook is None:
            continue
        for name, fn in hook().items():
            if name in merged:
                raise ValueError(f"wiki probe {name!r} is contributed by two module plugins")
            merged[name] = fn
    return merged


def wiki_seeders() -> list[Callable[[bool], list[Any]]]:
    seeders: list[Callable[[bool], list[Any]]] = []
    for plugin in plugins():
        hook = getattr(plugin, "wiki_seeders", None)
        if hook is not None:
            seeders.extend(hook())
    return seeders


def owui_tools() -> dict[str, Callable[..., dict[str, Any]]]:
    """Merge each module's Open WebUI tool handlers by tool name.

    Handlers are plain callables that return the tool's response dict and
    report failures inside it rather than raising.
    """
    merged: dict[str, Callable[..., dict[str, Any]]] = {}
    for plugin in plugins():
        hook = getattr(plugin, "owui_tools", None)
        if hook is None:
            continue
        for name, fn in hook().items():
            if name in merged:
                raise ValueError(f"owui tool {name!r} is contributed by two module plugins")
            merged[name] = fn
    return merged


def document_reader() -> Any | None:
    """Return the first module-provided document reader."""
    for plugin in plugins():
        hook = getattr(plugin, "document_reader", None)
        if hook is not None:
            reader = hook()
            if reader is not None:
                return reader
    return None
