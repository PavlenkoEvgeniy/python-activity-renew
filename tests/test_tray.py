"""Трей: иконка и состав меню, ради которых не нужна живая сессия."""

import unittest

from activity_renew import i18n, tray
from activity_renew.tray import ICON_HEIGHT, ICON_WIDTH, QUIT_ITEM_ID, SHOW_ITEM_ID


class IconTest(unittest.TestCase):
    def test_pixels_have_the_argb_layout(self) -> None:
        # SNI ждёт 4 байта на пиксель в сетевом порядке: A, R, G, B.
        self.assertEqual(len(tray.icon_argb()), ICON_WIDTH * ICON_HEIGHT * 4)

    def test_corners_are_transparent_and_the_body_is_opaque(self) -> None:
        data = tray.icon_argb()
        self.assertEqual(data[0:4], b"\x00\x00\x00\x00")
        inside = (5 * ICON_WIDTH + 5) * 4
        self.assertEqual(data[inside], 0xFF)


class MenuTest(unittest.TestCase):
    def tearDown(self) -> None:
        i18n.set_language(i18n.DEFAULT_LANGUAGE)

    def test_menu_has_show_and_quit(self) -> None:
        self.assertEqual(
            [item_id for item_id, _label in tray.menu_entries()],
            [SHOW_ITEM_ID, QUIT_ITEM_ID],
        )

    def test_labels_follow_the_language(self) -> None:
        i18n.set_language("en")
        english = dict(tray.menu_entries())
        self.assertEqual(english[SHOW_ITEM_ID], "Show window")
        self.assertEqual(english[QUIT_ITEM_ID], "Quit")

        i18n.set_language("ru")
        russian = dict(tray.menu_entries())
        self.assertEqual(russian[SHOW_ITEM_ID], "Показать окно")
        self.assertEqual(russian[QUIT_ITEM_ID], "Выйти")


class NotStartedTest(unittest.TestCase):
    def test_tray_is_unavailable_until_started(self) -> None:
        instance = tray.Tray(lambda: None, lambda: None)
        self.assertFalse(instance.available)

    def test_pump_without_a_tray_does_nothing(self) -> None:
        tray.Tray(lambda: None, lambda: None).pump()


if __name__ == "__main__":
    unittest.main()
