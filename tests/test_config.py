"""Конфиг: умолчания, валидация, сохранение незнакомых ключей."""

import json
import tempfile
import unittest
from pathlib import Path

from activity_renew import config as config_module
from activity_renew.config import (
    DEFAULT_INTERVAL,
    MAX_INTERVAL,
    MIN_INTERVAL,
    Config,
    from_dict,
    load,
    save,
)


class LoadTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "config.json"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_missing_file_gives_defaults_without_complaints(self) -> None:
        cfg, warnings = load(self.path)
        self.assertEqual(cfg.interval_seconds, DEFAULT_INTERVAL)
        self.assertEqual(cfg.mode, "uinput")
        self.assertTrue(cfg.pause_when_locked)
        self.assertEqual(warnings, [])

    def test_broken_json_gives_defaults_and_warning(self) -> None:
        self.path.write_text("{это не json", encoding="utf-8")
        cfg, warnings = load(self.path)
        self.assertEqual(cfg.interval_seconds, DEFAULT_INTERVAL)
        self.assertEqual(len(warnings), 1)
        self.assertIn("JSON", warnings[0])

    def test_round_trip(self) -> None:
        cfg = Config(interval_seconds=45, mode="both", pause_when_locked=False,
                     jiggle_hold_ms=80, log_limit=5)
        save(cfg, self.path)
        loaded, warnings = load(self.path)
        self.assertEqual(loaded.interval_seconds, 45)
        self.assertEqual(loaded.mode, "both")
        self.assertFalse(loaded.pause_when_locked)
        self.assertEqual(loaded.jiggle_hold_ms, 80)
        self.assertEqual(loaded.log_limit, 5)
        self.assertEqual(warnings, [])

    def test_save_creates_parent_directory(self) -> None:
        nested = Path(self.tmp.name) / "глубоко" / "config.json"
        save(Config(), nested)
        self.assertTrue(nested.exists())

    def test_unknown_keys_are_preserved(self) -> None:
        self.path.write_text(
            json.dumps({"interval_seconds": 60, "моя_настройка": {"a": 1}}),
            encoding="utf-8",
        )
        cfg, _ = load(self.path)
        save(cfg, self.path)
        written = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(written["моя_настройка"], {"a": 1})
        self.assertEqual(written["interval_seconds"], 60)


class ValidationTest(unittest.TestCase):
    def test_interval_is_clamped_with_warning(self) -> None:
        cfg, warnings = from_dict({"interval_seconds": 0})
        self.assertEqual(cfg.interval_seconds, MIN_INTERVAL)
        self.assertTrue(warnings)

        cfg, warnings = from_dict({"interval_seconds": 10 ** 9})
        self.assertEqual(cfg.interval_seconds, MAX_INTERVAL)
        self.assertTrue(warnings)

    def test_interval_that_is_not_a_number(self) -> None:
        cfg, warnings = from_dict({"interval_seconds": "две минуты"})
        self.assertEqual(cfg.interval_seconds, DEFAULT_INTERVAL)
        self.assertTrue(warnings)

    def test_unknown_mode_falls_back(self) -> None:
        cfg, warnings = from_dict({"mode": "телепортация"})
        self.assertEqual(cfg.mode, "uinput")
        self.assertTrue(warnings)

    def test_hold_ms_is_clamped(self) -> None:
        cfg, _ = from_dict({"jiggle_hold_ms": 99999})
        self.assertLessEqual(cfg.jiggle_hold_ms, 2000)

    def test_pause_accepts_strings_from_hand_edited_file(self) -> None:
        self.assertFalse(from_dict({"pause_when_locked": "false"})[0].pause_when_locked)
        self.assertTrue(from_dict({"pause_when_locked": "да"})[0].pause_when_locked)
        self.assertTrue(from_dict({"pause_when_locked": 1})[0].pause_when_locked)

    def test_not_a_dict(self) -> None:
        cfg, warnings = from_dict(["не", "словарь"])
        self.assertEqual(cfg.interval_seconds, DEFAULT_INTERVAL)
        self.assertTrue(warnings)

    def test_small_interval_flag(self) -> None:
        self.assertTrue(Config(interval_seconds=config_module.SMALL_INTERVAL - 1).small_interval)
        self.assertFalse(Config(interval_seconds=config_module.SMALL_INTERVAL).small_interval)


if __name__ == "__main__":
    unittest.main()
