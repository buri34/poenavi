import unittest

from src.qt_platform import configure_qt_platform


class QtPlatformTest(unittest.TestCase):
    def test_wayland_with_xwayland_uses_xcb(self):
        env = {
            "WAYLAND_DISPLAY": "wayland-0",
            "DISPLAY": ":0",
        }

        changed = configure_qt_platform(env, "linux")

        self.assertTrue(changed)
        self.assertEqual(env["QT_QPA_PLATFORM"], "xcb")

    def test_xdg_wayland_session_with_xwayland_uses_xcb(self):
        env = {
            "XDG_SESSION_TYPE": "Wayland",
            "DISPLAY": ":1",
        }

        changed = configure_qt_platform(env, "linux")

        self.assertTrue(changed)
        self.assertEqual(env["QT_QPA_PLATFORM"], "xcb")

    def test_explicit_qt_platform_is_preserved(self):
        env = {
            "WAYLAND_DISPLAY": "wayland-0",
            "DISPLAY": ":0",
            "QT_QPA_PLATFORM": "wayland",
        }

        changed = configure_qt_platform(env, "linux")

        self.assertFalse(changed)
        self.assertEqual(env["QT_QPA_PLATFORM"], "wayland")

    def test_native_wayland_without_xwayland_is_unchanged(self):
        env = {"WAYLAND_DISPLAY": "wayland-0"}

        changed = configure_qt_platform(env, "linux")

        self.assertFalse(changed)
        self.assertNotIn("QT_QPA_PLATFORM", env)

    def test_x11_and_non_linux_environments_are_unchanged(self):
        for env, platform_name in (({"DISPLAY": ":0"}, "linux"), ({}, "win32")):
            with self.subTest(env=env, platform_name=platform_name):
                changed = configure_qt_platform(env, platform_name)

                self.assertFalse(changed)
                self.assertNotIn("QT_QPA_PLATFORM", env)


if __name__ == "__main__":
    unittest.main()
