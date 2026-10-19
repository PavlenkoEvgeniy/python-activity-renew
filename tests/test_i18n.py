"""Переводы: переключение языка, подстановки и запасной английский."""

import unittest

from activity_renew import i18n


class TranslationTest(unittest.TestCase):
    def tearDown(self) -> None:
        i18n.set_language(i18n.DEFAULT_LANGUAGE)

    def test_english_is_the_default(self) -> None:
        self.assertEqual(i18n.DEFAULT_LANGUAGE, "en")
        self.assertEqual(i18n.get_language(), "en")
        self.assertEqual(i18n.tr("button_start"), "Start")

    def test_switch_to_russian(self) -> None:
        i18n.set_language("ru")
        self.assertEqual(i18n.get_language(), "ru")
        self.assertEqual(i18n.tr("button_start"), "Старт")

    def test_unknown_language_falls_back_to_english(self) -> None:
        i18n.set_language("fr")
        self.assertEqual(i18n.get_language(), "en")

    def test_parameters_are_substituted(self) -> None:
        i18n.set_language("en")
        self.assertEqual(
            i18n.tr("reason_idle", idle=120, interval=120),
            "idle 120 s ≥ 120 s",
        )
        i18n.set_language("ru")
        self.assertIn("простой", i18n.tr("reason_idle", idle=120, interval=120))

    def test_unknown_key_is_visible(self) -> None:
        self.assertEqual(i18n.tr("no_such_key"), "no_such_key")

    def test_both_languages_cover_the_same_keys(self) -> None:
        english = set(i18n.TRANSLATIONS["en"])
        russian = set(i18n.TRANSLATIONS["ru"])
        self.assertEqual(english - russian, set())
        self.assertEqual(russian - english, set())


if __name__ == "__main__":
    unittest.main()
