import os
import sys
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from src.ui.main_window import MiniNaviOverlay


class MiniNaviImageIconsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(sys.argv)

    def test_wp_and_portal_tags_render_as_png_images(self):
        overlay = MiniNaviOverlay(None)
        try:
            rendered = overlay._render_line("[wp]WPを取って[portal]ポータルを出す")

            self.assertIn("<img", rendered)
            self.assertIn("wp.png", rendered)
            self.assertIn("portal.png", rendered)
            self.assertNotIn("[wp]", rendered)
            self.assertNotIn("[portal]", rendered)
        finally:
            overlay.close()


if __name__ == "__main__":
    unittest.main()
