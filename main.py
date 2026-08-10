import os
import sys
from time import perf_counter

# srcディレクトリへのパスを通す (VSCodeなどで実行した際のパスずれ対策)
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(current_dir)

from src.qt_platform import configure_qt_platform

# Wayland上でXWaylandが利用可能なら、Qtのクリップボード互換性を優先する。
# PySide6を読み込む前に設定する必要がある。
configure_qt_platform()

from src.app_mode import POENAVI_MODE, POETORE_MODE, save_startup_preferences, startup_preferences
from src.utils.feature_support import POETORE, is_feature_supported
from src.utils.config_manager import ConfigManager
from src.utils.poe_version_data import POE1, POE2
from src.version import APP_VERSION

__version__ = APP_VERSION

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QDialog

from src.single_instance import (
    SingleInstanceGuard,
    consume_restart_pid,
    wait_for_previous_instance,
)


def select_poe_version(config):
    """機能選択より先に、今回起動するPoEバージョンを確定する。"""
    updated = dict(config or {})
    version_mode = updated.get("poe_version_mode", "ask")
    if version_mode in (POE1, POE2):
        selected_version = version_mode
    else:
        from src.ui.startup_dialogs import PoeVersionSelectionDialog

        dialog = PoeVersionSelectionDialog(
            current_version=updated.get("poe_version", POE1),
        )
        if dialog.exec() != QDialog.Accepted:
            return None
        selected_version = dialog.selected_version

    if updated.get("poe_version") != selected_version:
        updated["poe_version"] = selected_version
        ConfigManager.save_config(updated)
    return updated


def select_app_mode(config):
    """保存設定に従い、必要な場合だけ起動モード選択画面を表示する。"""
    preferred_mode, show_selector = startup_preferences(config)
    poe_version = (config or {}).get("poe_version", POE1)
    if (
        preferred_mode == POETORE_MODE
        and not is_feature_supported(POETORE, poe_version)
    ):
        preferred_mode = POENAVI_MODE
        show_selector = True
    if not show_selector:
        return preferred_mode

    from src.ui.startup_dialogs import AppModeSelectionDialog

    dialog = AppModeSelectionDialog(
        current_mode=preferred_mode,
        poe_version=poe_version,
    )
    if dialog.exec() != QDialog.Accepted:
        return None

    updated = save_startup_preferences(
        config,
        dialog.selected_mode,
        dialog.skip_selector,
    )
    ConfigManager.save_config(updated)
    return dialog.selected_mode


def run():
    started_at = perf_counter()
    restart_pid = consume_restart_pid(sys.argv)
    wait_for_previous_instance(restart_pid)
    app = QApplication(sys.argv)
    single_instance = SingleInstanceGuard(parent=app)
    if not single_instance.start():
        return 0
    config = ConfigManager.load_config()

    from src.update.startup_gate import run_startup_update_gate

    if not run_startup_update_gate(config):
        return 0
    app.setProperty("startupUpdateChecked", True)

    config = ConfigManager.load_config()
    config = select_poe_version(config)
    if config is None:
        return 0
    app.setProperty("startupPoeVersionSelected", True)
    app_mode = select_app_mode(config)
    if app_mode is None:
        return 0

    from src.app_composition import create_mode_window

    app.setProperty("appMode", app_mode)
    window = create_mode_window(app_mode)
    single_instance.set_window(window)
    window.show()

    def report_runtime():
        from src.utils.runtime_diagnostics import (
            capture_runtime_snapshot,
            print_runtime_snapshot,
        )

        print_runtime_snapshot(
            capture_runtime_snapshot(app_mode, started_at, window)
        )

    QTimer.singleShot(0, report_runtime)
    return app.exec()

if __name__ == "__main__":
    sys.exit(run())
