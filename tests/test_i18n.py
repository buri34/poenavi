import unittest

from src.utils.i18n import (
    EN,
    JA,
    get_supported_locales,
    normalize_locale,
    set_locale,
    tr,
    tr_ui,
)


class I18nTest(unittest.TestCase):
    def tearDown(self):
        set_locale(JA)

    def test_supported_locale_normalization_and_catalog_lookup(self):
        self.assertEqual(normalize_locale("en-US"), EN)
        self.assertEqual(normalize_locale("ja-JP"), JA)
        self.assertEqual(get_supported_locales(), (JA, EN))

        set_locale(EN)
        self.assertEqual(tr("app.title"), "PoENavi")
        self.assertIn("The Coast", tr("guide.missing", zone="The Coast"))

    def test_missing_named_placeholder_is_reported(self):
        set_locale(EN)
        with self.assertRaises(KeyError):
            tr("guide.missing")

    def test_exact_ui_catalog_lookup(self):
        set_locale(EN)
        self.assertEqual(tr_ui("保存"), "Save")

    def test_dynamic_ui_catalog_lookup_preserves_runtime_value(self):
        set_locale(EN)
        self.assertEqual(tr_ui("キャラLv. 42"), "Character Lv. 42")

    def test_ui_translation_falls_back_to_exact_source(self):
        set_locale(EN)
        self.assertEqual(tr_ui("未登録の表示"), "未登録の表示")

    def test_japanese_ui_source_is_unchanged_in_japanese_locale(self):
        set_locale(JA)
        self.assertEqual(tr_ui("保存"), "保存")


if __name__ == "__main__":
    unittest.main()
