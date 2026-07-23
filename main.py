import sys
import os

# srcディレクトリへのパスを通す (VSCodeなどで実行した際のパスずれ対策)
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(current_dir)

from src.version import APP_VERSION

__version__ = APP_VERSION

from PySide6.QtWidgets import QApplication
from src.ui.main_window import MainWindow
from src.ui.language_dialog import LanguageSelectionDialog
from src.utils.config_manager import ConfigManager
from src.utils.i18n import set_locale

def run(argv=None):
    app = QApplication(argv or sys.argv)
    config = ConfigManager.load_config()
    if not config.get("language_selected", False):
        language_dialog = LanguageSelectionDialog()
        if not language_dialog.exec():
            return 0
        config["language"] = language_dialog.selected_locale
        config["language_selected"] = True
        ConfigManager.save_config(config)
    set_locale(config.get("language", "ja"))
    window = MainWindow(config=config)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(run())
