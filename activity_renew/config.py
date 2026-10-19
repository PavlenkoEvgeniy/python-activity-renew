"""Конфигурация: схема, чтение, запись и валидация.

Файл лежит в ``~/.config/activity-renew/config.json``. Незнакомые ключи при
перезаписи сохраняются, отсутствующие берутся из умолчаний — чтобы файл,
правленный руками, не ломался и не терял чужие настройки.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import i18n
from .i18n import tr

APP_NAME = "activity-renew"
CONFIG_VERSION = 1

MODES = ("uinput", "inhibit", "both")
LANGUAGES = i18n.LANGUAGES
DEFAULT_LANGUAGE = i18n.DEFAULT_LANGUAGE

DEFAULT_INTERVAL = 120
MIN_INTERVAL = 5
MAX_INTERVAL = 86400
SMALL_INTERVAL = 10  # ниже — предупреждение в строке состояния
DEFAULT_HOLD_MS = 60
MIN_HOLD_MS, MAX_HOLD_MS = 10, 2000
DEFAULT_LOG_LIMIT = 20


def config_path() -> Path:
    """Путь к файлу конфигурации по XDG-канону."""
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(
        os.path.expanduser("~"), ".config"
    )
    return Path(base) / APP_NAME / "config.json"


@dataclass
class Config:
    interval_seconds: int = DEFAULT_INTERVAL
    mode: str = "uinput"
    pause_when_locked: bool = True
    jiggle_hold_ms: int = DEFAULT_HOLD_MS
    log_limit: int = DEFAULT_LOG_LIMIT
    language: str = DEFAULT_LANGUAGE
    version: int = CONFIG_VERSION
    #: Незнакомые ключи из файла — храним как есть, чтобы не терять их при записи.
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def small_interval(self) -> bool:
        """Интервал опасно мал: дёрганье будет заметным и частым."""
        return self.interval_seconds < SMALL_INTERVAL

    def to_json_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "version": self.version,
            "language": self.language,
            "interval_seconds": self.interval_seconds,
            "mode": self.mode,
            "pause_when_locked": self.pause_when_locked,
            "jiggle_hold_ms": self.jiggle_hold_ms,
            "log_limit": self.log_limit,
        }
        data.update(self.extra)
        return data


def _as_int(value: Any, default: int, low: int, high: int, what: str) -> tuple[int, str | None]:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default, tr("warn_not_number", what=what, value=value, default=default)
    if number < low:
        return low, tr("warn_below_min", what=what, number=number, low=low)
    if number > high:
        return high, tr("warn_above_max", what=what, number=number, high=high)
    return number, None


def _as_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in ("true", "yes", "1", "да"):
            return True
        if lowered in ("false", "no", "0", "нет"):
            return False
    return default


def _as_mode(value: Any, default: str) -> tuple[str, str | None]:
    if value in MODES:
        return str(value), None
    return default, tr("warn_mode_unknown", value=value, default=default)


def _as_language(value: Any, default: str) -> tuple[str, str | None]:
    if value in LANGUAGES:
        return str(value), None
    return default, tr("warn_language_unknown", value=value, default=default)


def from_dict(raw: Any) -> tuple[Config, list[str]]:
    """Собрать конфиг из словаря, собрав все замечания по валидации."""
    warnings: list[str] = []
    if not isinstance(raw, dict):
        return Config(), [tr("warn_broken_config")]

    interval, note = _as_int(
        raw.get("interval_seconds", DEFAULT_INTERVAL),
        DEFAULT_INTERVAL, MIN_INTERVAL, MAX_INTERVAL, tr("what_interval"),
    )
    if note:
        warnings.append(note)

    hold, note = _as_int(
        raw.get("jiggle_hold_ms", DEFAULT_HOLD_MS),
        DEFAULT_HOLD_MS, MIN_HOLD_MS, MAX_HOLD_MS, tr("what_hold"),
    )
    if note:
        warnings.append(note)

    limit, note = _as_int(
        raw.get("log_limit", DEFAULT_LOG_LIMIT),
        DEFAULT_LOG_LIMIT, 0, 500, tr("what_log_limit"),
    )
    if note:
        warnings.append(note)

    mode, note = _as_mode(raw.get("mode", "uinput"), "uinput")
    if note:
        warnings.append(note)

    language, note = _as_language(
        raw.get("language", DEFAULT_LANGUAGE), DEFAULT_LANGUAGE
    )
    if note:
        warnings.append(note)

    known = {
        "version", "language", "interval_seconds", "mode", "pause_when_locked",
        "jiggle_hold_ms", "log_limit",
    }
    extra = {key: value for key, value in raw.items() if key not in known}

    config = Config(
        interval_seconds=interval,
        mode=mode,
        pause_when_locked=_as_bool(raw.get("pause_when_locked", True), True),
        jiggle_hold_ms=hold,
        log_limit=limit,
        language=language,
        version=CONFIG_VERSION,
        extra=extra,
    )
    return config, warnings


def load(path: Path | None = None) -> tuple[Config, list[str]]:
    """Прочитать конфиг. Отсутствие файла — не ошибка, берём умолчания.

    Язык выставляется до валидации, чтобы замечания к конфигу были на том же
    языке, что и интерфейс.
    """
    path = path or config_path()
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        i18n.set_language(DEFAULT_LANGUAGE)
        return Config(), []
    except OSError as exc:
        i18n.set_language(DEFAULT_LANGUAGE)
        return Config(), [tr("warn_unreadable", path=path, error=exc)]

    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        i18n.set_language(DEFAULT_LANGUAGE)
        return Config(), [tr("warn_bad_json", path=path, error=exc.msg)]

    if isinstance(raw, dict) and raw.get("language") in LANGUAGES:
        i18n.set_language(str(raw["language"]))
    else:
        i18n.set_language(DEFAULT_LANGUAGE)

    return from_dict(raw)


def save(config: Config, path: Path | None = None) -> None:
    """Записать конфиг атомарно: сначала временный файл, потом подмена."""
    path = path or config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(config.to_json_dict(), ensure_ascii=False, indent=2) + "\n"

    handle, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=".config-", suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise
