import unittest
from unittest.mock import MagicMock, patch

from src.ui.main_window import MainWindow
from src.utils.poelab_links import extract_daily_notes_url, find_daily_notes_url


class _Response:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def read(self):
        return b'<a href="/today-normal/">Normal Labyrinth Daily Notes</a>'


class PoELabLinksTest(unittest.TestCase):
    HTML = """
        <a href="https://www.poelab.com/90yem/"><span>Normal Labyrinth Daily Notes</span></a>
        <a href="/t83o6/">Cruel Labyrinth Daily Notes</a>
        <a href="/dhekv/">Merciless Labyrinth Daily Notes</a>
    """

    def test_extracts_each_daily_notes_url(self):
        self.assertEqual(extract_daily_notes_url(self.HTML, "normal"), "https://www.poelab.com/90yem/")
        self.assertEqual(extract_daily_notes_url(self.HTML, "cruel"), "https://www.poelab.com/t83o6/")
        self.assertEqual(extract_daily_notes_url(self.HTML, "merciless"), "https://www.poelab.com/dhekv/")

    def test_rejects_unknown_lab_type(self):
        with self.assertRaises(ValueError):
            extract_daily_notes_url(self.HTML, "uber")

    def test_link_button_is_limited_to_three_aspirants_plaza_zones(self):
        self.assertEqual(
            MainWindow.POELAB_ZONE_TYPES,
            {
                "act4_area3": "normal",
                "act8_area2": "cruel",
                "act10_area8": "merciless",
            },
        )

    def test_main_guide_button_visibility_follows_lab_zone(self):
        window = MainWindow.__new__(MainWindow)
        window.poelab_link_button = MagicMock()
        window._reset_poelab_link_button = MagicMock()

        MainWindow._update_poelab_link_visibility(window, "act8_area2")
        self.assertEqual(window._current_poelab_type, "cruel")
        window.poelab_link_button.setVisible.assert_called_with(True)
        window._reset_poelab_link_button.assert_not_called()

        MainWindow._update_poelab_link_visibility(window, "act8_area3")
        self.assertIsNone(window._current_poelab_type)
        window.poelab_link_button.setVisible.assert_called_with(False)
        window._reset_poelab_link_button.assert_called_once_with()

    @patch("src.ui.main_window.QDesktopServices.openUrl")
    def test_all_three_lab_buttons_open_poelab_home(self, open_url):
        window = MainWindow.__new__(MainWindow)
        for zone_id in MainWindow.POELAB_ZONE_TYPES:
            window._current_poelab_type = MainWindow.POELAB_ZONE_TYPES[zone_id]
            MainWindow.open_daily_poelab(window)

        self.assertEqual(open_url.call_count, 3)
        self.assertTrue(all(
            call.args[0].toString() == "https://www.poelab.com/"
            for call in open_url.call_args_list
        ))

    @patch("src.utils.poelab_links.urllib.request.urlopen", return_value=_Response())
    def test_fetches_only_top_page_and_extracts_link(self, urlopen):
        self.assertEqual(find_daily_notes_url("normal"), "https://www.poelab.com/today-normal/")
        self.assertEqual(urlopen.call_count, 1)


if __name__ == "__main__":
    unittest.main()
