from __future__ import annotations

from pathlib import Path


def canonical_attack_data_root(root: Path) -> Path:
    """Normalize either attack_data checkout root or its datasets directory."""
    resolved = root.resolve()
    checkout = resolved.parent if resolved.name == "datasets" else resolved
    if not (checkout / "datasets").is_dir():
        raise ValueError(
            f"attack_data root must be the checkout directory containing datasets/ "
            f"or that datasets/ directory: {root}"
        )
    return checkout


def attack_data_test_id(episode_dir: Path, root: Path) -> str:
    """Build attack_data episode-directory test_id relative to the checkout root containing datasets/."""
    checkout = canonical_attack_data_root(root)
    try:
        relative = episode_dir.resolve().relative_to(checkout)
    except ValueError as exc:
        raise ValueError(
            f"episode directory {episode_dir} is outside attack_data root {checkout}"
        ) from exc
    if not relative.parts or relative.parts[0] != "datasets":
        raise ValueError(f"episode directory {episode_dir} is not under attack_data datasets/")
    return relative.as_posix()
