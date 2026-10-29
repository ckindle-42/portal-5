from pathlib import Path

config_path = Path("/workspace/uploads/config.json")
if config_path.is_file() and "mode" in config_path.read_text(encoding="utf-8"):
    print("READY")
else:
    print(f"ERROR: missing file or mode: {config_path}")
