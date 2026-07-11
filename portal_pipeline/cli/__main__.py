"""SHIM — moved to portal.platform.inference.cli.__main__. Removed in the final cleanup slice."""

from portal.platform.inference.cli import app  # noqa: F401

if __name__ == "__main__":
    app()
