"""Global pytest isolation for files that PoENavi normally writes per user."""

import os
import tempfile

_TEST_USER_DATA_DIR = tempfile.mkdtemp(prefix="poenavi-pytest-user-data-")
os.environ.setdefault("POENAVI_USER_DATA_DIR", _TEST_USER_DATA_DIR)
# 実運用用daemon writerをpytest終了時のQt teardownへ残さない。
os.environ.setdefault("POETORE_DISABLE_PERFORMANCE_LOG", "1")
