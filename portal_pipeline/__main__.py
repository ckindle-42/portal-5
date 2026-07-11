"""SHIM — moved to portal.platform.inference.__main__. Removed in the final cleanup slice."""

from portal.platform.inference.__main__ import *  # noqa: F401,F403
from portal.platform.inference.__main__ import main  # noqa: F401

if __name__ == "__main__":
    main()
