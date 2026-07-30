import sys
import os
from time import perf_counter

# srcディレクトリへのパスを通す (VSCodeなどで実行した際のパスずれ対策)
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(current_dir)

from src.version import APP_VERSION
from src.app_mode import save_startup_preferences, startup_preferences
from src.utils.config_manager import ConfigManager

__version__ = APP_VERSION

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QDialog


def select_app_mode(config):
    """保存設定に従い、必要な場合だけ起動モード選択画面を表示する。"""
    preferred_mode, show_selector = startup_preferences(config)
    if not show_selector:
        return preferred_mode

    from src.ui.startup_dialogs import AppModeSelectionDialog

    dialog = AppModeSelectionDialog(current_mode=preferred_mode)
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
    app = QApplication(sys.argv)
    config = ConfigManager.load_config()

    from src.update.startup_gate import run_startup_update_gate

    if not run_startup_update_gate(config):
        return 0
    app.setProperty("startupUpdateChecked", True)

    config = ConfigManager.load_config()
    app_mode = select_app_mode(config)
    if app_mode is None:
        return 0

    from src.app_composition import create_mode_window

    app.setProperty("appMode", app_mode)
    window = create_mode_window(app_mode)
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
