import os
import subprocess
import sys
import textwrap
import time
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from PySide6.QtWidgets import QApplication

from src.single_instance import (
    ACTIVATE_MESSAGE,
    RESTART_PID_PREFIX,
    SingleInstanceGuard,
    consume_restart_pid,
    wait_for_previous_instance,
)


class _FakeMutex:
    def __init__(self, acquired: bool):
        self.acquired = acquired
        self.acquire_calls = 0
        self.release_calls = 0

    def acquire(self):
        self.acquire_calls += 1
        return self.acquired

    def release(self):
        self.release_calls += 1


def _app():
    return QApplication.instance() or QApplication([])


def test_restart_pid_is_consumed_without_forwarding_internal_argument():
    arguments = [
        "PoENavi.exe",
        "--sample",
        f"{RESTART_PID_PREFIX}4321",
    ]

    assert consume_restart_pid(arguments) == 4321
    assert arguments == ["PoENavi.exe", "--sample"]


def test_invalid_restart_pid_is_removed_and_ignored():
    arguments = ["PoENavi.exe", f"{RESTART_PID_PREFIX}invalid"]

    assert consume_restart_pid(arguments) is None
    assert arguments == ["PoENavi.exe"]


def test_restart_waits_until_previous_process_exits():
    with (
        patch("src.single_instance.process_exists", side_effect=[True, True, False]),
        patch("src.single_instance.time.sleep") as sleep,
    ):
        assert wait_for_previous_instance(4321, timeout_seconds=1) is True

    assert sleep.call_count == 2


def test_restart_does_not_wait_for_current_process():
    with patch("src.single_instance.process_exists") as exists:
        assert wait_for_previous_instance(os.getpid()) is True
    exists.assert_not_called()


def test_windows_process_check_uses_non_destructive_wait_handle():
    kernel32 = MagicMock()
    kernel32.OpenProcess.return_value = 99
    kernel32.WaitForSingleObject.return_value = 0x00000102
    fake_ctypes = MagicMock()
    fake_ctypes.windll.kernel32 = kernel32

    with (
        patch("src.single_instance.sys.platform", "win32"),
        patch.dict("sys.modules", {"ctypes": fake_ctypes}),
        patch("src.single_instance.os.kill") as kill,
    ):
        from src.single_instance import process_exists

        assert process_exists(4321) is True

    kernel32.OpenProcess.assert_called_once_with(0x00100000, False, 4321)
    kernel32.WaitForSingleObject.assert_called_once_with(99, 0)
    kernel32.CloseHandle.assert_called_once_with(99)
    kill.assert_not_called()


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="Windows notification is covered by the real-process integration test",
)
def test_second_instance_notifies_first_and_first_activates_window():
    app = _app()
    server_name = f"PoENavi-test-{uuid4().hex}"
    primary = SingleInstanceGuard(server_name)
    secondary = SingleInstanceGuard(server_name)
    window = MagicMock()
    window.isMinimized.return_value = False
    primary.set_window(window)

    try:
        assert primary.start() is True
        assert secondary.start() is False
        deadline = time.monotonic() + 1.0
        while window.show.call_count == 0 and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(0.01)

        window.show.assert_called_once_with()
        window.raise_.assert_called_once_with()
        window.activateWindow.assert_called_once_with()
    finally:
        secondary.close()
        primary.close()


def test_mutex_owner_is_the_only_instance_allowed_to_start():
    mutex = _FakeMutex(acquired=True)
    guard = SingleInstanceGuard(f"PoENavi-test-{uuid4().hex}", mutex=mutex)

    try:
        assert guard.start() is True
        assert mutex.acquire_calls == 1
    finally:
        guard.close()

    assert mutex.release_calls == 1


def test_second_instance_exits_even_when_activation_notification_fails():
    mutex = _FakeMutex(acquired=False)
    guard = SingleInstanceGuard(f"PoENavi-test-{uuid4().hex}", mutex=mutex)
    guard.server = MagicMock()

    with patch.object(guard, "_notify_running_instance", return_value=False) as notify:
        assert guard.start() is False

    notify.assert_called_once_with()
    guard.server.listen.assert_not_called()
    assert mutex.acquire_calls == 1


def test_mutex_owner_keeps_running_when_activation_server_cannot_start():
    mutex = _FakeMutex(acquired=True)
    guard = SingleInstanceGuard(f"PoENavi-test-{uuid4().hex}", mutex=mutex)
    guard.server = MagicMock()
    guard.server.listen.side_effect = [False, False]

    with patch("src.single_instance.QLocalServer.removeServer") as remove:
        assert guard.start() is True

    remove.assert_called_once_with(guard.server_name)
    assert guard.server.listen.call_count == 2


@pytest.mark.skipif(sys.platform != "win32", reason="Windows named Mutex integration")
def test_named_mutex_rejects_a_second_real_process_on_windows():
    mutex_name = rf"Local\PoENavi-test-{uuid4().hex}"
    script = textwrap.dedent(
        """
        import sys
        import time
        from src.single_instance import _WindowsNamedMutex

        mutex = _WindowsNamedMutex(sys.argv[1])
        acquired = mutex.acquire()
        print("acquired" if acquired else "blocked", flush=True)
        if acquired:
            time.sleep(30)
        """
    )
    primary = subprocess.Popen(
        [sys.executable, "-c", script, mutex_name],
        cwd=os.getcwd(),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert primary.stdout.readline().strip() == "acquired"
        secondary = subprocess.run(
            [sys.executable, "-c", script, mutex_name],
            cwd=os.getcwd(),
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        )
        assert secondary.stdout.strip() == "blocked"
    finally:
        primary.terminate()
        primary.wait(timeout=10)


@pytest.mark.skipif(sys.platform != "win32", reason="Windows activation integration")
def test_second_real_process_notifies_the_running_instance_on_windows(tmp_path):
    server_name = f"PoENavi-test-{uuid4().hex}"
    mutex_name = rf"Local\{server_name}"
    activated_path = tmp_path / "activated.txt"
    primary_script = textwrap.dedent(
        """
        import sys
        from pathlib import Path
        from PySide6.QtCore import QCoreApplication, QTimer
        from src.single_instance import SingleInstanceGuard, _WindowsNamedMutex

        app = QCoreApplication([])
        activated_path = Path(sys.argv[3])

        class Window:
            def isMinimized(self):
                return False
            def show(self):
                activated_path.write_text("activated", encoding="utf-8")
            def raise_(self):
                pass
            def activateWindow(self):
                pass

        guard = SingleInstanceGuard(
            sys.argv[1], parent=app, mutex=_WindowsNamedMutex(sys.argv[2])
        )
        if not guard.start():
            raise SystemExit(2)
        guard.set_window(Window())
        print("ready", flush=True)
        QTimer.singleShot(10000, app.quit)
        raise SystemExit(app.exec())
        """
    )
    secondary_script = textwrap.dedent(
        """
        import sys
        from PySide6.QtCore import QCoreApplication
        from src.single_instance import SingleInstanceGuard, _WindowsNamedMutex

        app = QCoreApplication([])
        guard = SingleInstanceGuard(
            sys.argv[1], parent=app, mutex=_WindowsNamedMutex(sys.argv[2])
        )
        print("started" if guard.start() else "blocked", flush=True)
        """
    )
    primary = subprocess.Popen(
        [
            sys.executable, "-c", primary_script,
            server_name, mutex_name, str(activated_path),
        ],
        cwd=os.getcwd(),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert primary.stdout.readline().strip() == "ready"
        secondary = subprocess.run(
            [sys.executable, "-c", secondary_script, server_name, mutex_name],
            cwd=os.getcwd(),
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        )
        assert secondary.stdout.strip() == "blocked"
        deadline = time.monotonic() + 3.0
        while not activated_path.exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        assert activated_path.read_text(encoding="utf-8") == "activated"
    finally:
        primary.terminate()
        primary.wait(timeout=10)


def test_activation_restores_minimized_window():
    guard = SingleInstanceGuard(f"PoENavi-test-{uuid4().hex}")
    window = MagicMock()
    window.isMinimized.return_value = True
    guard.set_window(window)

    guard._read_message(MagicMock(readAll=lambda: ACTIVATE_MESSAGE))

    window.showNormal.assert_called_once_with()
    window.show.assert_not_called()
    window.raise_.assert_called_once_with()
    window.activateWindow.assert_called_once_with()


def test_activation_is_deferred_until_window_is_available():
    guard = SingleInstanceGuard(f"PoENavi-test-{uuid4().hex}")
    window = MagicMock()
    window.isMinimized.return_value = False

    with (
        patch.object(QApplication, "activeWindow", return_value=None),
        patch.object(QApplication, "topLevelWidgets", return_value=[]),
    ):
        guard._activate_window()

    assert guard.activation_pending is True
    guard.set_window(window)
    assert guard.activation_pending is False
    window.activateWindow.assert_called_once_with()


def test_stale_endpoint_is_removed_and_listen_is_retried():
    guard = SingleInstanceGuard(f"PoENavi-test-{uuid4().hex}")
    guard.server = MagicMock()
    guard.server.listen.side_effect = [False, True]

    with (
        patch.object(guard, "_notify_running_instance", return_value=False),
        patch("src.single_instance.QLocalServer.removeServer") as remove,
    ):
        assert guard.start() is True

    remove.assert_called_once_with(guard.server_name)
    assert guard.server.listen.call_count == 2
