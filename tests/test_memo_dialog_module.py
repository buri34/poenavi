def test_memo_dialog_module_imports_without_main_window_cycle():
    from src.ui.main_window import MainWindow
    from src.ui.memo_dialog import MemoDialog

    assert MainWindow is not None
    assert MemoDialog is not None
