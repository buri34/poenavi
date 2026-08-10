"""PoENaviの単一起動と、起動済みウィンドウの再表示を管理する。"""

import os
import sys
import time

from PySide6.QtCore import QObject
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication


SERVER_NAME = "PoENavi-SingleInstance-v1"
RESTART_PID_PREFIX = "--single-instance-restart-pid="
ACTIVATE_MESSAGE = b"activate\n"


def consume_restart_pid(arguments: list[str]) -> int | None:
    """内部再起動用PID引数を取り除き、待機対象PIDを返す。"""
    restart_pid = None
    retained = []
    for argument in arguments:
        if argument.startswith(RESTART_PID_PREFIX):
            try:
                candidate = int(argument[len(RESTART_PID_PREFIX):])
            except ValueError:
                continue
            if candidate > 0:
                restart_pid = candidate
            continue
        retained.append(argument)
    arguments[:] = retained
    return restart_pid


def process_exists(pid: int) -> bool:
    if pid <= 0:
        return False
    if sys.platform == "win32":
        import ctypes

        synchronize = 0x00100000
        wait_timeout = 0x00000102
        handle = ctypes.windll.kernel32.OpenProcess(synchronize, False, pid)
        if not handle:
            return False
        try:
            return (
                ctypes.windll.kernel32.WaitForSingleObject(handle, 0)
                == wait_timeout
            )
        finally:
            ctypes.windll.kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def wait_for_previous_instance(
    pid: int | None,
    timeout_seconds: float = 15.0,
    poll_seconds: float = 0.05,
) -> bool:
    """モード切替前のプロセスが終了するまで待つ。"""
    if pid is None or pid == os.getpid():
        return True
    deadline = time.monotonic() + timeout_seconds
    while process_exists(pid):
        if time.monotonic() >= deadline:
            return False
        time.sleep(poll_seconds)
    return True


class SingleInstanceGuard(QObject):
    """最初のプロセスだけをserverにし、後続起動は前面化を依頼する。"""

    def __init__(self, server_name: str = SERVER_NAME, parent=None):
        super().__init__(parent)
        self.server_name = server_name
        self.server = QLocalServer(self)
        self.server.newConnection.connect(self._accept_connections)
        self.window = None
        self.activation_pending = False

    def start(self) -> bool:
        """最初のプロセスならTrue、起動済みへ通知できたらFalseを返す。"""
        if self.server.listen(self.server_name):
            return True
        if self._notify_running_instance():
            return False

        # 異常終了で残ったendpointだけを除去して、1回だけ取得し直す。
        self.server.close()
        QLocalServer.removeServer(self.server_name)
        if self.server.listen(self.server_name):
            return True
        if self._notify_running_instance():
            return False
        return False

    def set_window(self, window) -> None:
        self.window = window
        if self.activation_pending:
            self._activate_window()

    def close(self) -> None:
        self.server.close()

    def _notify_running_instance(self) -> bool:
        socket = QLocalSocket()
        socket.connectToServer(self.server_name)
        if not socket.waitForConnected(500):
            return False
        socket.write(ACTIVATE_MESSAGE)
        socket.flush()
        socket.waitForBytesWritten(500)
        socket.disconnectFromServer()
        return True

    def _accept_connections(self) -> None:
        while self.server.hasPendingConnections():
            socket = self.server.nextPendingConnection()
            if socket is None:
                continue
            socket.disconnected.connect(socket.deleteLater)
            socket.readyRead.connect(
                lambda connection=socket: self._read_message(connection)
            )
            if socket.bytesAvailable():
                self._read_message(socket)

    def _read_message(self, socket) -> None:
        message = bytes(socket.readAll())
        if ACTIVATE_MESSAGE.strip() in message:
            self._activate_window()

    def _activate_window(self) -> None:
        window = self.window or QApplication.activeWindow()
        if window is None:
            visible_windows = [
                candidate for candidate in QApplication.topLevelWidgets()
                if candidate.isVisible()
            ]
            window = visible_windows[0] if visible_windows else None
        if window is None:
            self.activation_pending = True
            return

        self.activation_pending = False
        if window.isMinimized():
            window.showNormal()
        else:
            window.show()
        window.raise_()
        window.activateWindow()
