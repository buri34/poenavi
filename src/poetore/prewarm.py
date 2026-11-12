"""Prepare local parser metadata before the first user-initiated search."""

from __future__ import annotations

import threading

from src.utils.poe_version_data import POE1, POE2

_START_LOCK = threading.Lock()
_STARTED = False


def warm_search_metadata(poe_version: str) -> None:
    """Synchronously prepare one mode's local, immutable search metadata."""
    if poe_version == POE2:
        from .poe2.metadata import prewarm_metadata

        prewarm_metadata()
        return

    from .metadata import default_metadata_index

    default_metadata_index()


def start_search_metadata_prewarm(preferred_version: str) -> threading.Thread | None:
    """Warm both modes once, prioritising the currently selected mode."""
    global _STARTED
    with _START_LOCK:
        if _STARTED:
            return None
        _STARTED = True

    first = POE2 if preferred_version == POE2 else POE1
    second = POE1 if first == POE2 else POE2

    def run() -> None:
        # Metadata is bundled local data.  Never perform Trade/API requests here.
        warm_search_metadata(first)
        warm_search_metadata(second)

    thread = threading.Thread(
        target=run,
        name="poetore-metadata-prewarm",
        daemon=True,
    )
    thread.start()
    return thread
