#!/bin/bash
# EmbeddingGemma 2 platform embedder — dedicated venv bootstrap
# (TASK_EMBEDDINGGEMMA2_PLATFORM_V1). arm64 only. Idempotent.
#   scripts/eg2-venv-setup.sh            create/refresh venv + fetch model
#   EG2_VENV=/path scripts/eg2-venv-setup.sh
set -euo pipefail
PORTAL_ROOT="${PORTAL_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
EG2_VENV="${EG2_VENV:-$HOME/.portal5/eg2-venv}"
EG2_MODEL="${EG2_MODEL:-google/embeddinggemma-2}"
UV_BIN="${UV_BIN:-$(command -v uv || echo "$HOME/.local/bin/uv")}"

[ "$(uname -m)" = "arm64" ] || { echo "eg2-venv-setup: arm64 only (got $(uname -m))" >&2; exit 1; }
[ -x "$UV_BIN" ] || { echo "eg2-venv-setup: uv not found" >&2; exit 1; }

if [ ! -x "$EG2_VENV/bin/python3" ]; then
    # The macOS TCC grant for /Volumes/data01 (model cache) is per interpreter BINARY. This
    # interpreter (uv cpython-3.12.12) was approved by the operator on 2026-10-07; changing the
    # version or the uv patch level yields a new binary that needs approval again.
    "$UV_BIN" venv --python 3.12 "$EG2_VENV"
fi
"$EG2_VENV/bin/python3" -c 'import platform,sys; assert platform.machine()=="arm64", platform.machine(); print("venv python", sys.version.split()[0], platform.machine())'

# sentence-transformers >= 6.1.0 is the model card's floor for EmbeddingGemma 2.
# transformers 5.19.0 is the first release that ships models/embedding_gemma2
# (5.18.0 does not; the card was exported from 5.18.0.dev0). Pin the floor so a
# resolver backtrack fails here, not at model load.
# Media decoders are listed explicitly (the sentence-transformers[audio] extra drags in
# pyctcdecode -> kenlm, which fails to build on newer interpreters).
"$UV_BIN" pip install --python "$EG2_VENV/bin/python3" \
    "sentence-transformers>=6.1.0" "transformers>=5.19.0" "torch" "torchvision" "torchcodec" "librosa" "soundfile" "av" "huggingface_hub" \
    "fastapi" "uvicorn" "httpx" "pillow" "numpy"

"$EG2_VENV/bin/python3" - <<'PY'
import importlib.metadata as md, platform
for pkg in ("sentence-transformers", "transformers", "torch"):
    print(f"{pkg}=={md.version(pkg)}")
import torch
print("mps available:", torch.backends.mps.is_available(), "| arch:", platform.machine())
PY

# Pre-fetch (the launchd service runs HF_HUB_OFFLINE=1). A 401/403 here means the
# repo is gated: that is an account-holder action -> [GATE] G-HF-ACCESS.
"$EG2_VENV/bin/python3" - "$EG2_MODEL" <<'PY'
import sys
from huggingface_hub import snapshot_download
p = snapshot_download(sys.argv[1])
print("model snapshot:", p)
PY
echo "eg2-venv-setup: OK ($EG2_VENV)"
