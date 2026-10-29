"""MLX Metal buffer-cache cap and per-request release for the host speech servers.

The loaded model stays resident. Only MLX's free-buffer cache is bounded and cleared.
"""

from __future__ import annotations

import logging
import os
import sys

# Free-cache cap. 0 leaves MLX's default (this lane treats that as unlimited).
DEFAULT_LIMIT_GB = 2.0
_GIB = 1024**3
_noted: set[str] = set()


def _note(logger: logging.Logger, key: str, message: str) -> None:
    if key in _noted:
        return
    _noted.add(key)
    logger.info(message)


def _mlx_core() -> object | None:
    loaded = sys.modules.get("mlx.core")
    if loaded is not None:
        return loaded
    try:
        import mlx.core as mx
    except ImportError:
        return None
    return mx


def _callable(obj: object, name: str) -> object | None:
    fn = getattr(obj, name, None)
    return fn if callable(fn) else None


def _cache_api(mx: object) -> tuple[object | None, object | None]:
    """Prefer mlx.core.clear_cache / set_cache_limit; older mlx exposes them on .metal."""
    clear = _callable(mx, "clear_cache")
    limit = _callable(mx, "set_cache_limit")
    metal = getattr(mx, "metal", None)
    if metal is not None:
        if clear is None:
            clear = _callable(metal, "clear_cache")
        if limit is None:
            limit = _callable(metal, "set_cache_limit")
    return clear, limit


def _limit_gb(env_var: str, default_gb: float, logger: logging.Logger) -> float:
    raw = os.environ.get(env_var)
    if raw is None or not raw.strip():
        return default_gb
    try:
        gb = float(raw.strip())
    except ValueError:
        logger.warning("%s=%r is not a number; using %.1f GB", env_var, raw, default_gb)
        return default_gb
    if gb < 0:
        logger.warning("%s=%s is negative; using %.1f GB", env_var, gb, default_gb)
        return default_gb
    return gb


def apply_cache_limit(
    env_var: str,
    logger: logging.Logger,
    *,
    default_gb: float = DEFAULT_LIMIT_GB,
) -> None:
    """Set the free-cache cap from `env_var` (GB, 1024^3). 0 leaves MLX's default."""
    gb = _limit_gb(env_var, default_gb, logger)
    if gb == 0:
        logger.info("%s=0; MLX cache limit left unlimited", env_var)
        return
    mx = _mlx_core()
    if mx is None:
        _note(logger, "no-mlx-limit", "MLX is not installed; cache limit is a no-op")
        return
    _, set_limit = _cache_api(mx)
    if set_limit is None:
        _note(logger, "no-set-cache-limit", "MLX has no set_cache_limit; cache limit is a no-op")
        return
    nbytes = int(gb * _GIB)
    set_limit(nbytes)
    logger.info("MLX cache limit %d bytes (%s=%.3f GB)", nbytes, env_var, gb)


def release_cache(logger: logging.Logger) -> None:
    """Drop MLX's free buffer cache after a request. Never raises."""
    mx = _mlx_core()
    if mx is None:
        _note(logger, "no-mlx-clear", "MLX is not installed; cache release is a no-op")
        return
    clear, _ = _cache_api(mx)
    if clear is None:
        _note(logger, "no-clear-cache", "MLX has no clear_cache; cache release is a no-op")
        return
    try:
        clear()
    except Exception:
        logger.warning("MLX cache release failed", exc_info=True)
