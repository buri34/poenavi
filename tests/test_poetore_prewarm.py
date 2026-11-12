from unittest.mock import Mock, call, patch

from src.poetore import prewarm
from src.utils.poe_version_data import POE1, POE2


class _ImmediateThread:
    def __init__(self, *, target, name, daemon):
        self.target = target
        self.name = name
        self.daemon = daemon
        self.started = False

    def start(self):
        self.started = True
        self.target()


def test_prewarm_runs_once_and_prioritises_selected_mode(monkeypatch):
    monkeypatch.setattr(prewarm, "_STARTED", False)
    warm = Mock()
    monkeypatch.setattr(prewarm, "warm_search_metadata", warm)
    monkeypatch.setattr(prewarm.threading, "Thread", _ImmediateThread)

    thread = prewarm.start_search_metadata_prewarm(POE2)

    assert thread is not None
    assert thread.started
    assert thread.name == "poetore-metadata-prewarm"
    assert thread.daemon
    assert warm.call_args_list == [call(POE2), call(POE1)]
    assert prewarm.start_search_metadata_prewarm(POE1) is None
    assert warm.call_count == 2


def test_prewarm_dispatches_to_local_metadata_only():
    with patch("src.poetore.metadata.default_metadata_index") as poe1, patch(
        "src.poetore.poe2.metadata.prewarm_metadata",
    ) as poe2:
        prewarm.warm_search_metadata(POE1)
        prewarm.warm_search_metadata(POE2)

    poe1.assert_called_once_with()
    poe2.assert_called_once_with()
