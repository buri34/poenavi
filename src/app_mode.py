"""PoENaviの起動モード定義と設定正規化。"""

POENAVI_MODE = "poenavi"
POETORE_MODE = "poetore"
VALID_APP_MODES = frozenset({POENAVI_MODE, POETORE_MODE})


def normalize_app_mode(value):
    """未知の値を安全な既定モードへ戻す。"""
    return value if value in VALID_APP_MODES else POENAVI_MODE


def startup_preferences(config):
    """設定から (前回モード, 選択画面を表示するか) を安全に取得する。"""
    startup = (config or {}).get("startup")
    if not isinstance(startup, dict):
        startup = {}
    return (
        normalize_app_mode(startup.get("preferred_mode")),
        bool(startup.get("show_mode_selector", True)),
    )


def save_startup_preferences(config, mode, skip_selector):
    """選択結果を設定へ反映する。元の設定辞書は破壊しない。"""
    updated = dict(config or {})
    startup = updated.get("startup")
    startup = dict(startup) if isinstance(startup, dict) else {}
    startup["preferred_mode"] = normalize_app_mode(mode)
    startup["show_mode_selector"] = not bool(skip_selector)
    updated["startup"] = startup
    return updated
