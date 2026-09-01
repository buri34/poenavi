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
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox

from src.single_instance import (
    SingleInstanceGuard,
    consume_restart_pid,
    wait_for_previous_instance,
)
from src.app_font import apply_bundled_ui_font


def select_startup_options(config):
    """PoEバージョンと使用機能を確定し、必要なら統合選択画面を表示する。"""
    updated = dict(config or {})
    version_mode = updated.get("poe_version_mode", "ask")
    current_version = updated.get("poe_version", POE1)
    if current_version not in (POE1, POE2):
        current_version = POE1
    selected_version = version_mode if version_mode in (POE1, POE2) else current_version

    preferred_mode, show_selector = startup_preferences(config)
    if (
        preferred_mode == POETORE_MODE
        and not is_feature_supported(POETORE, selected_version)
    ):
        preferred_mode = POENAVI_MODE
        show_selector = True
    if version_mode in (POE1, POE2) and not show_selector:
        if updated.get("poe_version") != selected_version:
            updated["poe_version"] = selected_version
            ConfigManager.save_config(updated)
        return updated, preferred_mode

    from src.ui.startup_dialogs import StartupSelectionDialog

    dialog = StartupSelectionDialog(
        current_mode=preferred_mode,
        poe_version=selected_version,
    )
    if dialog.exec() != QDialog.Accepted:
        return None

    selected_mode = dialog.selected_mode
    if (
        selected_mode == POETORE_MODE
        and not is_feature_supported(POETORE, dialog.selected_version)
    ):
        selected_mode = POENAVI_MODE

    updated = save_startup_preferences(
        updated,
        selected_mode,
        dialog.skip_selector,
    )
    updated["poe_version"] = dialog.selected_version
    updated["poe_version_mode"] = (
        dialog.selected_version if dialog.skip_selector else "ask"
    )
    ConfigManager.save_config(updated)
    return updated, selected_mode


def run():
    started_at = perf_counter()
    restart_pid = consume_restart_pid(sys.argv)
    wait_for_previous_instance(restart_pid)
    app = QApplication(sys.argv)
    apply_bundled_ui_font(app)
    single_instance = SingleInstanceGuard(parent=app)
    if not single_instance.start():
        QMessageBox.information(
            None,
            "ぽえなびは起動済みです",
            "ぽえなびはすでに起動しています。\n"
            "起動中の画面を前面に表示します。",
        )
        return 0
    config = ConfigManager.load_config()

    from src.update.startup_gate import run_startup_update_gate

    if not run_startup_update_gate(config):
        return 0
    app.setProperty("startupUpdateChecked", True)

    config = ConfigManager.load_config()
    startup_selection = select_startup_options(config)
    if startup_selection is None:
        return 0
    config, app_mode = startup_selection
    app.setProperty("startupPoeVersionSelected", True)

    from src.app_composition import create_mode_window

    app.setProperty("appMode", app_mode)
    window = create_mode_window(app_mode, config.get("poe_version", POE1))
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
