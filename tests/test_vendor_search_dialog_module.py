def test_vendor_search_dialog_module_imports_without_main_window_cycle():
    from src.ui.main_window import MainWindow
    from src.ui.vendor_search_dialog import VendorSearchPresetDialog

    assert MainWindow is not None
    assert VendorSearchPresetDialog is not None
