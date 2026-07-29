"""選択モードから必要なトップレベル構成だけを遅延生成する。"""

import importlib

from src.app_mode import POENAVI_MODE, POETORE_MODE, normalize_app_mode


WINDOW_CLASS_BY_MODE = {
    POENAVI_MODE: ("src.ui.main_window", "MainWindow"),
    POETORE_MODE: ("src.ui.poetore_mode_window", "PoetoreModeWindow"),
}


def resolve_window_class(mode):
    module_name, class_name = WINDOW_CLASS_BY_MODE[normalize_app_mode(mode)]
    module = importlib.import_module(module_name)
    return getattr(module, class_name)


def create_mode_window(mode):
    return resolve_window_class(mode)()
