from PySide6.QtWidgets import QApplication


def test_qapplication_is_kept_alive_for_the_test_session(qt_application_session):
    assert QApplication.instance() is qt_application_session
    assert not qt_application_session.quitOnLastWindowClosed()
