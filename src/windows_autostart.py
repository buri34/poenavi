"""Windowsログイン時にぽえとれを直接起動するユーザー別登録。"""

import subprocess
import sys
from pathlib import Path

WINDOWS_STARTUP_POETORE_ARGUMENT = "--windows-startup-poetore"
REGISTRY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
REGISTRY_VALUE_NAME = "PoENaviPoetore"


def consume_windows_startup_poetore_argument(arguments: list[str]) -> bool:
    """内部用起動引数を取り除き、自動起動経由かを返す。"""
    found = WINDOWS_STARTUP_POETORE_ARGUMENT in arguments[1:]
    if found:
        arguments[:] = [
            argument
            for argument in arguments
            if argument != WINDOWS_STARTUP_POETORE_ARGUMENT
        ]
    return found


def is_windows_poetore_autostart_enabled(config: dict | None) -> bool:
    startup = (config or {}).get("startup")
    if not isinstance(startup, dict):
        return False
    return bool(startup.get("windows_autostart_poetore", False))


def build_windows_poetore_autostart_command(executable: str | Path) -> str:
    """Windows Run値へ保存する、引用符を含む安全なコマンドを返す。"""
    return subprocess.list2cmdline(
        [str(Path(executable)), WINDOWS_STARTUP_POETORE_ARGUMENT]
    )


def sync_windows_poetore_autostart(
    config: dict | None,
    *,
    executable: str | Path | None = None,
    platform: str | None = None,
    frozen: bool | None = None,
    registry=None,
) -> bool:
    """現在の設定と実行場所を、ユーザー別Run登録へ同期する。

    非Windows環境と開発実行ではOS設定を変更しない。製品版を通常起動した
    ときにも呼ぶことで、ZIPの移動後は新しい実行場所へ登録を修正する。
    """
    active_platform = sys.platform if platform is None else platform
    active_frozen = bool(getattr(sys, "frozen", False)) if frozen is None else frozen
    if active_platform != "win32" or not active_frozen:
        return False

    if registry is None:
        import winreg as registry

    enabled = is_windows_poetore_autostart_enabled(config)
    access = registry.KEY_SET_VALUE
    if enabled:
        executable_path = Path(executable or sys.executable)
        command = build_windows_poetore_autostart_command(executable_path)
        with registry.CreateKeyEx(
            registry.HKEY_CURRENT_USER,
            REGISTRY_PATH,
            0,
            access,
        ) as key:
            registry.SetValueEx(
                key,
                REGISTRY_VALUE_NAME,
                0,
                registry.REG_SZ,
                command,
            )
        return True

    try:
        key_context = registry.OpenKey(
            registry.HKEY_CURRENT_USER,
            REGISTRY_PATH,
            0,
            access,
        )
    except FileNotFoundError:
        return True
    with key_context as key:
        try:
            registry.DeleteValue(key, REGISTRY_VALUE_NAME)
        except FileNotFoundError:
            pass
    return True


def sync_windows_poetore_autostart_with_error(
    config: dict | None,
) -> str | None:
    """同期失敗をアプリ継続可能なエラー文字列へ変換する。"""
    try:
        sync_windows_poetore_autostart(config)
    except OSError as error:
        return str(error)
    return None
