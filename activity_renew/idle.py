"""Простой и блокировка экрана — через D-Bus GNOME.

Расширения XScreenSaver в Wayland-сессии нет, свои глобальные хуки там
невозможны, поэтому единственный авторитетный источник простоя — счётчик
Mutter. Если он недоступен, приложение обязано отказаться работать, а не
дёргать вслепую.
"""

from __future__ import annotations

import dbus

IDLE_NAME = "org.gnome.Mutter.IdleMonitor"
IDLE_PATH = "/org/gnome/Mutter/IdleMonitor/Core"
IDLE_IFACE = "org.gnome.Mutter.IdleMonitor"

SAVER_NAME = "org.gnome.ScreenSaver"
SAVER_PATH = "/org/gnome/ScreenSaver"
SAVER_IFACE = "org.gnome.ScreenSaver"

LOGIND_NAME = "org.freedesktop.login1"
LOGIND_PATH = "/org/freedesktop/login1/session/auto"
LOGIND_IFACE = "org.freedesktop.login1.Session"
PROPERTIES_IFACE = "org.freedesktop.DBus.Properties"


class IdleSourceUnavailable(RuntimeError):
    """Счётчик простоя недоступен — работать вслепую нельзя."""


class GnomeIdleSource:
    """Счётчик простоя Mutter и признак заблокированного экрана."""

    def __init__(self) -> None:
        try:
            bus = dbus.SessionBus()
            idle = dbus.Interface(bus.get_object(IDLE_NAME, IDLE_PATH), IDLE_IFACE)
            idle.GetIdletime()  # проверка, что сервис жив, а не только на шине
        except dbus.DBusException as exc:
            raise IdleSourceUnavailable(
                "счётчик простоя GNOME недоступен: "
                f"{exc.get_dbus_name() or type(exc).__name__}.\n"
                "Приложение рассчитано на сессию GNOME (Wayland или X11) и берёт "
                "простой из org.gnome.Mutter.IdleMonitor. Без него непонятно, "
                "когда дёргать, поэтому работа не начинается."
            ) from exc

        self._bus = bus
        self._idle = idle
        self._saver = None
        self._logind = None
        self._system_bus = None

    def idle_seconds(self) -> float:
        """Сколько секунд прошло с последнего ввода."""
        try:
            return int(self._idle.GetIdletime()) / 1000.0
        except dbus.DBusException as exc:
            raise IdleSourceUnavailable(
                f"счётчик простоя перестал отвечать: {exc.get_dbus_name() or exc}"
            ) from exc

    def is_locked(self) -> bool:
        """Заблокирован ли экран. Незнание трактуем как «не заблокирован»."""
        for probe in (self._locked_via_saver, self._locked_via_logind):
            try:
                value = probe()
            except Exception:
                continue
            if value is not None:
                return value
        return False

    def _locked_via_saver(self) -> bool | None:
        if self._saver is None:
            self._saver = dbus.Interface(
                self._bus.get_object(SAVER_NAME, SAVER_PATH), SAVER_IFACE
            )
        return bool(self._saver.GetActive())

    def _locked_via_logind(self) -> bool | None:
        # logind живёт на системной шине, а не на сессионной.
        if self._system_bus is None:
            self._system_bus = dbus.SystemBus()
        if self._logind is None:
            self._logind = self._system_bus.get_object(LOGIND_NAME, LOGIND_PATH)
        props = self._logind.GetAll(LOGIND_IFACE, dbus_interface=PROPERTIES_IFACE)
        hint = props.get("LockedHint")
        return None if hint is None else bool(hint)

    def describe(self) -> str:
        """Строка для диагностики (``--check``)."""
        try:
            locked = self.is_locked()
        except Exception as exc:  # pragma: no cover - диагностика
            return f"простой {self.idle_seconds():.1f} с; состояние блокировки неизвестно: {exc}"
        return f"простой {self.idle_seconds():.1f} с; экран {'заблокирован' if locked else 'не заблокирован'}"
