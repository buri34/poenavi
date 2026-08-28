"""選択モードから必要なトップレベル構成だけを遅延生成する。"""

from src.app_mode import POETORE_MODE, normalize_app_mode
from src.utils.feature_support import POETORE, is_feature_supported


def resolve_window_class(mode, poe_version=None):
    """必要な画面だけを実行時に読み込む。

    import文を関数内へ置くことで遅延読込を保ちつつ、PyInstallerにも
    配布対象モジュールとして静的に検出させる。
    """
    if normalize_app_mode(mode) == POETORE_MODE:
        if not is_feature_supported(POETORE, poe_version):
            raise ValueError(f"ぽえとれはPoEバージョン {poe_version!r} では利用できません")
        from src.ui.poetore_mode_window import PoetoreModeWindow

        return PoetoreModeWindow

    from src.ui.main_window import MainWindow

    return MainWindow


def create_mode_window(mode, poe_version=None):
    return resolve_window_class(mode, poe_version)()
