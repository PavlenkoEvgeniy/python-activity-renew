"""Переводы интерфейса: английский по умолчанию и русский по выбору.

Строки лежат в двух словарях, ключи общие. Язык — глобальное состояние
процесса: его выставляет конфиг при загрузке и переключатель в окне. Этого
достаточно, потому что окно одно, а ошибки D-Bus и evdev формируются уже
после загрузки конфига.
"""

from __future__ import annotations

DEFAULT_LANGUAGE = "en"
LANGUAGES = ("en", "ru")
LANGUAGE_NAMES = {"en": "English", "ru": "Русский"}

_current = DEFAULT_LANGUAGE

TRANSLATIONS: dict[str, dict[str, str]] = {
    "en": {
        # ── окно ───────────────────────────────────────────────────────────
        "window_title": "activity-renew — activity simulation",
        "interval_label": "Jiggle after idle, s:",
        "button_apply": "Apply",
        "button_start": "Start",
        "button_stop": "Stop",
        "mode_box": "Mode",
        "mode_uinput": "Jiggle the mouse",
        "mode_inhibit": "Inhibit only",
        "mode_both": "Mouse + inhibit",
        "language_box": "Language",
        "pause_check": "Pause while the screen is locked",
        "journal_check": "Show event log",
        "journal_box": "Recent events",
        "status_stopped": "stopped",
        "status_running_inhibit": (
            "running · idle inhibit active · jiggles {count}"
        ),
        "status_running_mouse": (
            "running · idle {idle:.0f} s · {reason} · jiggles {count}"
        ),
        "status_small_interval": " · ⚠ interval below {seconds} s",
        "status_error": "error: {message}",
        "reason_locked": "screen locked — paused",
        "reason_idle": "idle {idle:.0f} s ≥ {interval} s",
        "reason_wait": "{wait:.0f} s until the next jiggle",
        "direction_up": "up",
        "direction_down": "down",
        "direction_left": "left",
        "direction_right": "right",
        # ── журнал ─────────────────────────────────────────────────────────
        "journal_config_note": "config note: {note}",
        "journal_interval_changed": "interval changed to {seconds} s",
        "journal_pause_on": "pause while locked enabled",
        "journal_pause_off": "pause while locked disabled",
        "journal_mode_changed": "mode: {mode}",
        "journal_start_failed": "could not start: {error}",
        "journal_stopped": "stopped",
        "journal_jiggled": "moved the mouse 1 px {direction} and back ({reason})",
        "journal_jiggle_failed": "jiggle failed: {error}",
        "journal_error": "error: {message}",
        "journal_config_save_failed": "config not saved: {error}",
        "journal_language_changed": "interface language: {language}",
        "journal_inhibit_acquired": "idle inhibit acquired via {via}",
        # ── диалоги ────────────────────────────────────────────────────────
        "error_not_number_title": "Not a number",
        "error_not_number_message": (
            "“{value}” does not look like a number of seconds."
        ),
        "interval_out_of_range_title": "Interval out of range",
        "interval_out_of_range_message": (
            "Allowed range is {min} to {max} s — set to {value}."
        ),
        "mode_failed_title": "Mode failed to start",
        "work_stopped_title": "Work stopped",
        "error_no_idle_title": "No idle source",
        "error_already_running_title": "Already running",
        "error_already_running_message": (
            "A second copy would jiggle the mouse twice as often and fight "
            "over the configuration file. Find the activity-renew window "
            "that is already open."
        ),
        # ── About ──────────────────────────────────────────────────────────
        "about_title": "About activity-renew",
        "menu_help": "Help",
        "menu_about": "About activity-renew",
        "about_version": "Version {version}",
        "about_description": (
            "Moves the mouse by 1 pixel and back when the computer has been "
            "idle, so the session is not considered idle."
        ),
        "about_platform": "Designed for the GNOME desktop (Wayland or X11).",
        "button_close": "Close",
        # ── диагностика ────────────────────────────────────────────────────
        "check_idle_source": "idle source: {description}",
        "check_mouse_failed": "virtual mouse: NOT WORKING — {error}",
        "check_mouse_note": "virtual mouse: {note}",
        "check_inhibit_available": "idle inhibit: available",
        "check_inhibit_failed": "idle inhibit: NOT WORKING — {error}",
        # ── конфиг ─────────────────────────────────────────────────────────
        "warn_not_number": (
            "{what}: {value!r} does not look like a number — using {default}"
        ),
        "warn_below_min": "{what}: {number} is below the minimum — raised to {low}",
        "warn_above_max": "{what}: {number} is above the maximum — lowered to {high}",
        "warn_mode_unknown": "mode {value!r} is unknown — using “{default}”",
        "warn_language_unknown": (
            "language {value!r} is unknown — using “{default}”"
        ),
        "warn_broken_config": "the configuration file is damaged — using defaults",
        "warn_unreadable": "cannot read {path}: {error} — using defaults",
        "warn_bad_json": (
            "{path}: cannot parse as JSON ({error}) — using defaults"
        ),
        "what_interval": "interval",
        "what_hold": "delay between moving away and back",
        "what_log_limit": "log size",
        # ── D-Bus и evdev ──────────────────────────────────────────────────
        "idle_unavailable": (
            "the GNOME idle counter is unavailable: {error}.\n"
            "This application targets a GNOME session (Wayland or X11) and "
            "reads idle time from org.gnome.Mutter.IdleMonitor. Without it "
            "there is no way to know when to jiggle, so it will not start."
        ),
        "idle_stopped": "the idle counter stopped responding: {error}",
        "jiggler_no_evdev": (
            "the evdev module is missing (python3-evdev) — cannot create the "
            "virtual mouse"
        ),
        "jiggler_uinput_failed": (
            "could not open /dev/uinput: {error}.\n"
            "A udev rule granting the current user access to /dev/uinput is "
            "required (see README)."
        ),
        "jiggler_untested": (
            "could not check: xdotool is unavailable, so the pointer position "
            "is unknown"
        ),
        "jiggler_not_seen": (
            "the virtual mouse was created, but the pointer did not move — the "
            "compositor does not see it. A udev rule with TAG+=\"uaccess\" is "
            "required for the “{name}” device (see README)."
        ),
        "jiggler_works": (
            "virtual mouse works (checked with a 25 px move: {before} → {after})"
        ),
        "inhibit_failed": (
            "could not acquire the idle inhibit: neither "
            "org.gnome.SessionManager nor org.freedesktop.ScreenSaver responds "
            "({error})"
        ),
        "screen_locked": "locked",
        "screen_unlocked": "not locked",
        "describe_idle": "idle {seconds:.1f} s; screen {state}",
        "describe_idle_unknown": (
            "idle {seconds:.1f} s; lock state unknown: {error}"
        ),
    },
    "ru": {
        # ── окно ───────────────────────────────────────────────────────────
        "window_title": "activity-renew — имитация активности",
        "interval_label": "Дёргать после простоя, с:",
        "button_apply": "Применить",
        "button_start": "Старт",
        "button_stop": "Стоп",
        "mode_box": "Режим",
        "mode_uinput": "дёргать мышью",
        "mode_inhibit": "только ингибит",
        "mode_both": "мышь + ингибит",
        "language_box": "Язык",
        "pause_check": "Пауза, когда экран заблокирован",
        "journal_check": "Показывать журнал событий",
        "journal_box": "Последние события",
        "status_stopped": "остановлено",
        "status_running_inhibit": (
            "работает · ингибит простоя активен · срабатываний {count}"
        ),
        "status_running_mouse": (
            "работает · простой {idle:.0f} с · {reason} · срабатываний {count}"
        ),
        "status_small_interval": " · ⚠ интервал меньше {seconds} с",
        "status_error": "ошибка: {message}",
        "reason_locked": "экран заблокирован — пауза",
        "reason_idle": "простой {idle:.0f} с ≥ {interval} с",
        "reason_wait": "до дёрганья {wait:.0f} с",
        "direction_up": "вверх",
        "direction_down": "вниз",
        "direction_left": "влево",
        "direction_right": "вправо",
        # ── журнал ─────────────────────────────────────────────────────────
        "journal_config_note": "замечание к конфигу: {note}",
        "journal_interval_changed": "интервал изменён на {seconds} с",
        "journal_pause_on": "пауза при блокировке включена",
        "journal_pause_off": "пауза при блокировке выключена",
        "journal_mode_changed": "режим: {mode}",
        "journal_start_failed": "не удалось запустить: {error}",
        "journal_stopped": "остановлено",
        "journal_jiggled": "дёрнул мышь на 1 px {direction} и вернул ({reason})",
        "journal_jiggle_failed": "дёрганье не удалось: {error}",
        "journal_error": "ошибка: {message}",
        "journal_config_save_failed": "конфиг не сохранён: {error}",
        "journal_language_changed": "язык интерфейса: {language}",
        "journal_inhibit_acquired": "ингибит простоя взят через {via}",
        # ── диалоги ────────────────────────────────────────────────────────
        "error_not_number_title": "Не число",
        "error_not_number_message": "«{value}» не похоже на число секунд.",
        "interval_out_of_range_title": "Интервал вне диапазона",
        "interval_out_of_range_message": (
            "Допустимо от {min} до {max} с — поставил {value}."
        ),
        "mode_failed_title": "Режим не запустился",
        "work_stopped_title": "Работа остановлена",
        "error_no_idle_title": "Нет источника простоя",
        "error_already_running_title": "Уже запущено",
        "error_already_running_message": (
            "Вторая копия дёргала бы мышь вдвое чаще и спорила за файл "
            "конфигурации. Найдите уже открытое окно activity-renew."
        ),
        # ── About ──────────────────────────────────────────────────────────
        "about_title": "О программе activity-renew",
        "menu_help": "Справка",
        "menu_about": "О программе activity-renew",
        "about_version": "Версия {version}",
        "about_description": (
            "Двигает мышь на 1 пиксель и возвращает обратно, если за "
            "компьютером давно нет ввода, — чтобы сессия не считалась "
            "простаивающей."
        ),
        "about_platform": "Рассчитано на рабочий стол GNOME (Wayland или X11).",
        "button_close": "Закрыть",
        # ── диагностика ────────────────────────────────────────────────────
        "check_idle_source": "источник простоя: {description}",
        "check_mouse_failed": "виртуальная мышь: НЕ РАБОТАЕТ — {error}",
        "check_mouse_note": "виртуальная мышь: {note}",
        "check_inhibit_available": "ингибит простоя: доступен",
        "check_inhibit_failed": "ингибит простоя: НЕ РАБОТАЕТ — {error}",
        # ── конфиг ─────────────────────────────────────────────────────────
        "warn_not_number": "{what}: {value!r} не похоже на число — беру {default}",
        "warn_below_min": "{what}: {number} меньше минимума — поднял до {low}",
        "warn_above_max": "{what}: {number} больше максимума — опустил до {high}",
        "warn_mode_unknown": "режим {value!r} неизвестен — беру «{default}»",
        "warn_language_unknown": "язык {value!r} неизвестен — беру «{default}»",
        "warn_broken_config": "файл конфигурации повреждён — беру умолчания",
        "warn_unreadable": "не читается {path}: {error} — беру умолчания",
        "warn_bad_json": (
            "{path}: не разбирается как JSON ({error}) — беру умолчания"
        ),
        "what_interval": "интервал",
        "what_hold": "пауза между уходом и возвратом",
        "what_log_limit": "размер журнала",
        # ── D-Bus и evdev ──────────────────────────────────────────────────
        "idle_unavailable": (
            "счётчик простоя GNOME недоступен: {error}.\n"
            "Приложение рассчитано на сессию GNOME (Wayland или X11) и берёт "
            "простой из org.gnome.Mutter.IdleMonitor. Без него непонятно, "
            "когда дёргать, поэтому работа не начинается."
        ),
        "idle_stopped": "счётчик простоя перестал отвечать: {error}",
        "jiggler_no_evdev": (
            "нет модуля evdev (пакет python3-evdev) — виртуальную мышь "
            "создать нельзя"
        ),
        "jiggler_uinput_failed": (
            "не удалось открыть /dev/uinput: {error}.\n"
            "Нужно udev-правило, дающее доступ к /dev/uinput текущему "
            "пользователю (см. README)."
        ),
        "jiggler_untested": (
            "проверить не удалось: xdotool недоступен, позиция курсора "
            "неизвестна"
        ),
        "jiggler_not_seen": (
            "виртуальная мышь создана, но курсор не сдвинулся — композитор её "
            "не видит. Нужно udev-правило с TAG+=\"uaccess\" для устройства "
            "«{name}» (см. README)."
        ),
        "jiggler_works": (
            "виртуальная мышь работает (проверка сдвигом на 25 px: "
            "{before} → {after})"
        ),
        "inhibit_failed": (
            "не удалось взять ингибит простоя: ни org.gnome.SessionManager, "
            "ни org.freedesktop.ScreenSaver не отвечают ({error})"
        ),
        "screen_locked": "заблокирован",
        "screen_unlocked": "не заблокирован",
        "describe_idle": "простой {seconds:.1f} с; экран {state}",
        "describe_idle_unknown": (
            "простой {seconds:.1f} с; состояние блокировки неизвестно: {error}"
        ),
    },
}


def set_language(language: str) -> str:
    """Переключить язык. Неизвестный код откатывается к английскому."""
    global _current
    _current = language if language in LANGUAGES else DEFAULT_LANGUAGE
    return _current


def get_language() -> str:
    return _current


def language_name(language: str) -> str:
    return LANGUAGE_NAMES.get(language, language)


def tr(key: str, **params: object) -> str:
    """Строка по ключу на текущем языке; неизвестный ключ виден как есть."""
    table = TRANSLATIONS.get(_current, TRANSLATIONS[DEFAULT_LANGUAGE])
    text = table.get(key)
    if text is None:
        text = TRANSLATIONS[DEFAULT_LANGUAGE].get(key, key)
    if not params:
        return text
    try:
        return text.format(**params)
    except (KeyError, IndexError, ValueError):
        return text
