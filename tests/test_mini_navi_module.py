def test_mini_navi_module_imports_without_main_window_cycle():
    from src.ui.main_window import MainWindow
    from src.ui.mini_navi import MiniNaviOverlay

    assert MainWindow is not None
    assert MiniNaviOverlay is not None
