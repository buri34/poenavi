import unittest

from src.ui.main_window import MiniNaviOverlay


class MiniNaviImageIconsTest(unittest.TestCase):
    def test_wp_and_portal_tags_render_as_png_images(self):
        overlay = MiniNaviOverlay.__new__(MiniNaviOverlay)
        rendered = overlay._render_line("[wp]WPを取って[portal]ポータルを出す")

        self.assertIn("<img", rendered)
        self.assertIn("wp.png", rendered)
        self.assertIn("portal.png", rendered)
        self.assertNotIn("[wp]", rendered)
        self.assertNotIn("[portal]", rendered)


if __name__ == "__main__":
    unittest.main()
