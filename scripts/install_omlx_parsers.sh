#!/bin/zsh
# Install the repo-maintained oMLX tool parsers into the running brew oMLX
# install and stamp the models that need them. Re-run after every
# `brew upgrade omlx` — site-packages is replaced wholesale on upgrade and
# any parser that only lived there silently disappears (it happened once:
# the DeepSeek council-operator seat lost tool calls until this was found).
#
# Usage: scripts/install_omlx_parsers.sh
set -euo pipefail

REPO_ROOT="${0:a:h:h}"
PARSER_SRC="$REPO_ROOT/scripts/omlx/deepseek_r1_tool_parser.py"
MODEL_DIR="/Volumes/data01/omlx-models/DeepSeek-R1-0528-Qwen3-8B-4bit"

TARGET_DIR=$(ls -d /opt/homebrew/Cellar/omlx/*/libexec/lib/python*/site-packages/mlx_lm/tool_parsers 2>/dev/null | sort | tail -1)
if [[ -z "$TARGET_DIR" ]]; then
  echo "ERROR: no mlx_lm/tool_parsers dir under /opt/homebrew/Cellar/omlx — is omlx installed?" >&2
  exit 1
fi

cp "$PARSER_SRC" "$TARGET_DIR/deepseek_r1.py"
echo "installed: $TARGET_DIR/deepseek_r1.py"

python3 - "$MODEL_DIR" <<'EOF'
import json, sys, pathlib
cfg_path = pathlib.Path(sys.argv[1]) / "tokenizer_config.json"
cfg = json.loads(cfg_path.read_text())
if cfg.get("tool_parser_type") != "deepseek_r1":
    cfg["tool_parser_type"] = "deepseek_r1"
    cfg_path.write_text(json.dumps(cfg, indent=2, ensure_ascii=False))
    print(f"stamped: {cfg_path} tool_parser_type=deepseek_r1")
else:
    print(f"already stamped: {cfg_path}")
EOF

echo "restart oMLX to pick up the parser (brew services restart omlx)"
