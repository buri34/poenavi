"""Global pytest isolation for files that PoENavi normally writes per user."""

import os
import tempfile


_TEST_USER_DATA_DIR = tempfile.mkdtemp(prefix="poenavi-pytest-user-data-")
os.environ.setdefault("POENAVI_USER_DATA_DIR", _TEST_USER_DATA_DIR)
