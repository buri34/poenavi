import unittest

try:
    from PySide6.QtWidgets import QApplication
    from src.ui.main_window import MiniNaviOverlay
except ModuleNotFoundError as exc:  # pragma: no cover - local dev without GUI deps
    QApplication = None
    MiniNaviOverlay = None
    IMPORT_ERROR = exc
else:
    IMPORT_ERROR = None


@unittest.skipIf(MiniNaviOverlay is None, f"GUI dependencies unavailable: {IMPORT_ERROR}")
class MiniNaviAreaNoteBadgeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def make_overlay(self):
        overlay = MiniNaviOverlay(None)
        overlay.config = lambda: {
            **MiniNaviOverlay.DEFAULT_CONFIG,
            "enabled": True,
            "fade_enabled": False,
        }
        return overlay

    def test_badge_is_visible_when_current_area_has_note(self):
        overlay = self.make_overlay()
        overlay.update_content(
            {"text": "みになび本文", "direction": "none"},
            zone_id="act1_area1",
            has_area_note=True,
        )

        self.assertTrue(overlay.area_note_badge.isVisible())
        self.assertEqual(overlay.area_note_badge.text(), "エリアメモあり")
        overlay.close()

    def test_badge_is_hidden_when_current_area_has_no_note(self):
        overlay = self.make_overlay()
        overlay.update_content(
            {"text": "みになび本文", "direction": "none"},
            zone_id="act1_area1",
            has_area_note=False,
        )

        self.assertFalse(overlay.area_note_badge.isVisible())
        overlay.close()


if __name__ == "__main__":
    unittest.main()
