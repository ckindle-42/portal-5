"""SHIM — moved to portal.platform.inference.sync_config. Removed in the final cleanup slice."""

import sys

from portal.platform.inference.sync_config import *  # noqa: F401,F403
from portal.platform.inference.sync_config import main  # noqa: F401

if __name__ == "__main__":
    sys.exit(main())
