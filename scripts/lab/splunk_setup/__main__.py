"""``python -m scripts.lab.splunk_setup`` -> the stage CLI."""

from __future__ import annotations

import sys

from .cli import main

sys.exit(main())
