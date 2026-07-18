import unittest

try:
    from src.ui.main_window import VendorSearchPresetDialog
except ModuleNotFoundError as exc:  # pragma: no cover - local dev without GUI deps
    VendorSearchPresetDialog = None
    IMPORT_ERROR = exc
else:
    IMPORT_ERROR = None

from src.utils.poe_version_data import POE2


class DummyQueryEdit:
    def __init__(self, text=""):
        self.text = text

    def toPlainText(self):
        return self.text

    def setPlainText(self, text):
        self.text = text


class DummyCheckBox:
    def __init__(self, checked=False):
        self._checked = checked

    def isChecked(self):
        return self._checked


@unittest.skipIf(VendorSearchPresetDialog is None, f"GUI dependencies unavailable: {IMPORT_ERROR}")
class VendorRegexHelperTest(unittest.TestCase):
    def make_dialog(self, query=""):
        dialog = VendorSearchPresetDialog.__new__(VendorSearchPresetDialog)
        dialog.poe_version = POE2
        dialog.query_edit = DummyQueryEdit(query)
        dialog.option_checkboxes = []
        return dialog

    def test_or_weapon_base_is_merged_into_the_same_or_group(self):
        dialog = self.make_dialog("")
        dialog.option_checkboxes = [
            (DummyCheckBox(True), "動ス", "共通"),
            (DummyCheckBox(True), "弓$", dialog.WEAPON_BASE_OR_CATEGORY),
        ]

        dialog._regenerate_query_from_helper_checkboxes()

        self.assertEqual(dialog.query_edit.toPlainText(), "(動ス|弓$)")
        self.assertEqual(dialog._or_base_tokens_from_query(), {"弓$"})

    def test_and_weapon_base_stays_adjacent_to_mod_conditions(self):
        dialog = self.make_dialog("")
        dialog.option_checkboxes = [
            (DummyCheckBox(True), "動ス", "共通"),
            (DummyCheckBox(True), "弓$", dialog.WEAPON_BASE_AND_CATEGORY),
        ]

        dialog._regenerate_query_from_helper_checkboxes()

        self.assertEqual(dialog.query_edit.toPlainText(), '"動ス""弓$"')
        self.assertEqual(dialog._and_base_tokens_from_query(), {"弓$"})
        self.assertEqual(dialog._or_base_tokens_from_query(), set())

    def test_and_and_or_weapon_bases_can_coexist(self):
        dialog = self.make_dialog("")
        dialog.option_checkboxes = [
            (DummyCheckBox(True), "動ス", "共通"),
            (DummyCheckBox(True), "弓$", dialog.WEAPON_BASE_AND_CATEGORY),
            (DummyCheckBox(True), "ロスボウ$", dialog.WEAPON_BASE_OR_CATEGORY),
        ]

        dialog._regenerate_query_from_helper_checkboxes()

        self.assertEqual(dialog.query_edit.toPlainText(), '"(動ス|ロスボウ$)""弓$"')
        self.assertEqual(dialog._and_base_tokens_from_query(), {"弓$"})
        self.assertEqual(dialog._or_base_tokens_from_query(), {"ロスボウ$"})

    def test_and_and_or_weapon_bases_without_mods_still_keeps_or_on_the_left(self):
        dialog = self.make_dialog("")
        dialog.option_checkboxes = [
            (DummyCheckBox(True), "弓$", dialog.WEAPON_BASE_AND_CATEGORY),
            (DummyCheckBox(True), "ロスボウ$", dialog.WEAPON_BASE_OR_CATEGORY),
        ]

        dialog._regenerate_query_from_helper_checkboxes()

        self.assertEqual(dialog.query_edit.toPlainText(), '"ロスボウ$""弓$"')
        self.assertEqual(dialog._and_base_tokens_from_query(), {"弓$"})
        self.assertEqual(dialog._or_base_tokens_from_query(), {"ロスボウ$"})


if __name__ == "__main__":
    unittest.main()
