"""
Shared utilities for portal_mcp generation servers.
"""


def get_torch_device() -> str:
    """Auto-select the best available torch device.

    Priority: MPS (Apple Silicon) -> CUDA (NVIDIA GPU) -> CPU.

    Used by TTS (Fish Speech) and Music (Stable Audio) generation servers.
    """
    import torch

    if torch.backends.mps.is_available():
        return "mps"
    if torch.cuda.is_available():
        return "cuda"
    return "cpu"
