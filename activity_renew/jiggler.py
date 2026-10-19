"""Дёргалка: виртуальная мышь через uinput и ингибит простоя через D-Bus.

Почему не XTest: в Wayland-сессии синтетическое движение через XWayland
(``xdotool``, ``pynput``, ``pyautogui``) счётчик простоя Mutter'а **не
сбрасывает** — проверено. Настоящее устройство ввода через ``/dev/uinput``
композитор видит как железо, и оно работает.

Почему нужен ``xdotool``: под Wayland позицию курсора иначе не прочитать, а
без неё у края экрана дёрганье накапливает дрейф — движение в стену
обрезается, а возврат добавляет пиксель. Позиция берётся из XWayland-зеркала.
"""

from __future__ import annotations

import random
import shutil
import subprocess
import time

import dbus

from .i18n import tr

DEVICE_NAME = "activity-renew virtual pointer"
VENDOR, PRODUCT, DEVICE_VERSION = 0x1A2B, 0x0001, 1

#: Четыре стороны света: при случайном угле диагональ дала бы 1.41 px.
CARDINALS = ((0, -1), (0, 1), (-1, 0), (1, 0))

XDOTOOL_TIMEOUT = 2.0
#: Сколько ждать, пока композитор заметит новое устройство ввода.
DEVICE_SETTLE_SECONDS = 0.8


class JigglerUnavailable(RuntimeError):
    """Дёргалка не может работать — с указанием, что именно поправить."""


def pointer_position() -> tuple[int, int] | None:
    """Позиция курсора через XWayland-зеркало. ``None`` — прочитать не удалось."""
    if shutil.which("xdotool") is None:
        return None
    try:
        done = subprocess.run(
            ["xdotool", "getmouselocation", "--shell"],
            capture_output=True, text=True, timeout=XDOTOOL_TIMEOUT,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if done.returncode != 0:
        return None

    values: dict[str, str] = {}
    for line in done.stdout.splitlines():
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip()
    try:
        return int(values["X"]), int(values["Y"])
    except (KeyError, ValueError):
        return None


def screen_size() -> tuple[int, int] | None:
    """Размер экрана через XWayland-зеркало. ``None`` — прочитать не удалось."""
    if shutil.which("xdotool") is None:
        return None
    try:
        done = subprocess.run(
            ["xdotool", "getdisplaygeometry"],
            capture_output=True, text=True, timeout=XDOTOOL_TIMEOUT,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if done.returncode != 0:
        return None
    parts = done.stdout.split()
    try:
        return int(parts[0]), int(parts[1])
    except (IndexError, ValueError):
        return None


def choose_direction(
    position: tuple[int, int] | None,
    size: tuple[int, int] | None,
    rng: random.Random | None = None,
) -> tuple[int, int]:
    """Сторона, в которую уход на 1 px не упрётся в край экрана.

    Если позиция неизвестна — любая из четырёх: дрейф в этом случае возможен,
    но не чаще одного пикселя за дёрганье и только у самой кромки.
    """
    rng = rng or random
    if position is None or size is None:
        return rng.choice(CARDINALS)

    x, y = position
    width, height = size
    allowed = [
        (dx, dy)
        for dx, dy in CARDINALS
        if 0 <= x + dx < width and 0 <= y + dy < height
    ]
    return rng.choice(allowed) if allowed else rng.choice(CARDINALS)


def _load_evdev():
    """Импорт evdev по требованию: без него режим «только ингибит» обязан работать."""
    try:
        from evdev import UInput, ecodes
    except ImportError as exc:
        raise JigglerUnavailable(tr("jiggler_no_evdev")) from exc
    return UInput, ecodes


class UinputJiggler:
    """Виртуальная мышь: уход на 1 px и возврат в исходную точку."""

    def __init__(self, hold_ms: int = 60, rng: random.Random | None = None) -> None:
        UInput, ecodes = _load_evdev()
        self._ecodes = ecodes
        self._hold = max(0.0, int(hold_ms) / 1000.0)
        self._rng = rng or random.Random()
        try:
            self._ui = UInput(
                {
                    ecodes.EV_REL: [ecodes.REL_X, ecodes.REL_Y],
                    ecodes.EV_KEY: [
                        ecodes.BTN_LEFT, ecodes.BTN_RIGHT, ecodes.BTN_MIDDLE,
                    ],
                },
                name=DEVICE_NAME,
                bustype=ecodes.BUS_USB,
                vendor=VENDOR,
                product=PRODUCT,
                version=DEVICE_VERSION,
            )
        except (OSError, PermissionError) as exc:
            raise JigglerUnavailable(
                tr("jiggler_uinput_failed", error=exc)
            ) from exc

    def _move(self, dx: int, dy: int) -> None:
        e = self._ecodes
        self._ui.write(e.EV_REL, e.REL_X, dx)
        self._ui.write(e.EV_REL, e.REL_Y, dy)
        self._ui.syn()

    def jiggle(self) -> tuple[int, int]:
        """Уйти на 1 px в выбранную сторону, выждать и вернуться."""
        before = pointer_position()
        direction = choose_direction(before, screen_size(), self._rng)

        self._move(*direction)
        time.sleep(self._hold)
        self._move(-direction[0], -direction[1])

        # Одна страховая поправка, не в цикле: позиция обязана вернуться пиксель в пиксель.
        if before is not None:
            after = pointer_position()
            if after is not None and after != before:
                self._move(before[0] - after[0], before[1] - after[1])
        return direction

    def self_test(self) -> tuple[bool, str]:
        """Проверить, что композитор действительно принимает наше устройство.

        Устройство создаётся всегда, но если узел ``/dev/input/eventN`` ему
        недоступен, события уходят в пустоту — молчаливый отказ, который надо
        превратить в понятное сообщение.
        """
        time.sleep(DEVICE_SETTLE_SECONDS)
        before = pointer_position()
        if before is None:
            return True, tr("jiggler_untested")

        self._move(25, 0)
        time.sleep(0.15)
        moved = pointer_position()
        self._move(-25, 0)
        time.sleep(0.15)

        if moved is None or moved == before:
            return False, tr("jiggler_not_seen", name=DEVICE_NAME)
        return True, tr(
            "jiggler_works", before=before[0], after=moved[0]
        )

    def close(self) -> None:
        try:
            self._ui.close()
        except Exception:
            pass


class InhibitKeeper:
    """Ингибит простоя: прямо просим сессию не засыпать — мышь не двигается."""

    #: Причина видна в системных средствах управления сессией.
    REASON = "activity-renew: activity simulation"
    #: Флаги org.gnome.SessionManager.Inhibit: 1 — выход, 2 — смена пользователя,
    #: 4 — спящий режим, 8 — простой.
    FLAG_IDLE = 8

    def __init__(self) -> None:
        self._release = None
        self._via = ""

    @property
    def active(self) -> bool:
        return self._release is not None

    @property
    def via(self) -> str:
        return self._via

    def acquire(self) -> None:
        if self._release is not None:
            return
        bus = dbus.SessionBus()

        try:
            manager = dbus.Interface(
                bus.get_object("org.gnome.SessionManager", "/org/gnome/SessionManager"),
                "org.gnome.SessionManager",
            )
            cookie = manager.Inhibit(
                "activity-renew", dbus.UInt32(0), self.REASON, dbus.UInt32(self.FLAG_IDLE)
            )
        except dbus.DBusException:
            try:
                saver = dbus.Interface(
                    bus.get_object("org.freedesktop.ScreenSaver", "/org/freedesktop/ScreenSaver"),
                    "org.freedesktop.ScreenSaver",
                )
                cookie = saver.Inhibit("activity-renew", self.REASON)
            except dbus.DBusException as exc:
                raise JigglerUnavailable(
                    tr("inhibit_failed", error=exc.get_dbus_name() or exc)
                ) from exc
            self._release = lambda: saver.Uninhibit(cookie)
            self._via = "org.freedesktop.ScreenSaver"
            return

        self._release = lambda: manager.Uninhibit(cookie)
        self._via = "org.gnome.SessionManager"

    def release(self) -> None:
        if self._release is None:
            return
        try:
            self._release()
        except dbus.DBusException:
            pass  # сессия могла уже закрыться — снимать нечего
        finally:
            self._release = None
            self._via = ""


class ActivityKeeper:
    """Выбранный режим целиком: мышь, ингибит или оба."""

    MOUSE_MODES = ("uinput", "both")
    INHIBIT_MODES = ("inhibit", "both")

    def __init__(self, mode: str = "uinput", hold_ms: int = 60) -> None:
        self.mode = mode
        self.hold_ms = hold_ms
        self._jiggler: UinputJiggler | None = None
        self._inhibit = InhibitKeeper()
        self.notes: list[str] = []

    @property
    def jiggles_mouse(self) -> bool:
        return self.mode in self.MOUSE_MODES and self._jiggler is not None

    def start(self) -> list[str]:
        """Поднять режим. Возвращает замечания для строки состояния."""
        self.notes = []
        if self.mode in self.INHIBIT_MODES:
            self._inhibit.acquire()
            self.notes.append(tr("journal_inhibit_acquired", via=self._inhibit.via))
        if self.mode in self.MOUSE_MODES:
            self._jiggler = UinputJiggler(self.hold_ms)
            ok, detail = self._jiggler.self_test()
            self.notes.append(detail)
            if not ok:
                self._jiggler.close()
                self._jiggler = None
                raise JigglerUnavailable(detail)
        return list(self.notes)

    def jiggle(self) -> tuple[int, int] | None:
        if self._jiggler is None:
            return None
        return self._jiggler.jiggle()

    def stop(self) -> None:
        if self._jiggler is not None:
            self._jiggler.close()
            self._jiggler = None
        self._inhibit.release()
