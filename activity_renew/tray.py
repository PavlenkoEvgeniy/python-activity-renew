"""Иконка в системном трее через StatusNotifierItem.

Трей — это не часть tkinter, а протокол D-Bus: приложение публикует объект
``org.kde.StatusNotifierItem``, регистрирует его у
``org.kde.StatusNotifierWatcher``, а рисует иконку хост. На GNOME хостом
служит расширение AppIndicator; без него иконку показать негде, и приложение
честно закрывается по крестику, а не прячет окно в никуда.

Входящие вызовы шины (клик, выбор пункта меню) приходят не сами по себе:
dbus-python отдаёт их тому циклу событий, который подключён к шине. tkinter
своего цикла не имеет, поэтому GLib-контекст прокачивается вручную из
:meth:`Tray.pump` — его зовёт окно по таймеру. Трей открывает **своё**
приватное соединение с явно указанным GLib-циклом: общая шина могла быть
создана раньше без диспетчера (её берёт источник простоя), и переключить его
задним числом нельзя.
"""

from __future__ import annotations

import os
import time
from typing import Callable

import dbus
import dbus.service

from .i18n import tr

try:  # pragma: no cover - зависит от системы
    import dbus.mainloop.glib
    from gi.repository import GLib
except Exception as _exc:  # PyGObject не стоит — трей просто недоступен
    GLib = None  # type: ignore[assignment]
    _GLIB_ERROR = f"{type(_exc).__name__}: {_exc}"
else:
    _GLIB_ERROR = ""

SNI_IFACE = "org.kde.StatusNotifierItem"
WATCHER_NAME = "org.kde.StatusNotifierWatcher"
WATCHER_PATH = "/StatusNotifierWatcher"
WATCHER_IFACE = "org.kde.StatusNotifierWatcher"
MENU_IFACE = "com.canonical.dbusmenu"
PROPS_IFACE = "org.freedesktop.DBus.Properties"

ITEM_PATH = "/StatusNotifierItem"
MENU_PATH = "/MenuBar"
MENU_REVISION = 1
SHOW_ITEM_ID = 1
QUIT_ITEM_ID = 2

#: Как часто проверять, жив ли хост трея: если расширение выключат, иконка
#: исчезнет, и спрятанное окно станет недоступным.
WATCHER_CHECK_SECONDS = 5.0

# ── иконка ─────────────────────────────────────────────────────────────────

ICON_WIDTH = 16
_DARK = (0x2E, 0x34, 0x36)
_LIGHT = (0xF6, 0xF5, 0xF4)

#: Мышь 16×16: «X» — контур, «#» — заливка, «.» — прозрачный пиксель.
#: Рисуем сами, потому что тема иконок может не знать имени ``input-mouse``.
_MOUSE_ROWS = (
    "................",
    "....XXXXXX......",
    "...X######X.....",
    "..X##X##X##X....",
    "..X##X##X##X....",
    "..X########X....",
    "..X########X....",
    "..X########X....",
    "..X########X....",
    "..X########X....",
    "..X########X....",
    "...X######X.....",
    "....XXXXXX......",
    "................",
    "................",
    "................",
)
ICON_HEIGHT = len(_MOUSE_ROWS)


def icon_argb() -> bytes:
    """Пиксели иконки в ARGB, как требует SNI (сетевой порядок байт)."""
    colors = {"X": _DARK, "#": _LIGHT}
    data = bytearray()
    for row in _MOUSE_ROWS:
        for cell in row:
            color = colors.get(cell)
            if color is None:
                data += b"\x00\x00\x00\x00"
            else:
                data += bytes((0xFF, *color))
    return bytes(data)


def menu_entries() -> list[tuple[int, str]]:
    """Пункты меню в текущем языке: (id, подпись)."""
    return [
        (SHOW_ITEM_ID, tr("tray_show_window")),
        (QUIT_ITEM_ID, tr("tray_quit")),
    ]


def _pixmap() -> dbus.Array:
    return dbus.Array(
        [
            dbus.Struct(
                (
                    dbus.Int32(ICON_WIDTH),
                    dbus.Int32(ICON_HEIGHT),
                    dbus.ByteArray(icon_argb()),
                ),
                signature=None,
            )
        ],
        signature="(iiay)",
    )


class TrayUnavailable(RuntimeError):
    """Показать иконку негде или нечем."""


class Tray:
    """Иконка трея с меню «Показать окно» / «Выйти»."""

    def __init__(
        self,
        on_show: Callable[[], None],
        on_quit: Callable[[], None],
        on_lost: Callable[[], None] | None = None,
    ) -> None:
        self._on_show = on_show
        self._on_quit = on_quit
        self._on_lost = on_lost
        self._bus: dbus.Bus | None = None
        self._loop = None
        self._name: dbus.service.BusName | None = None
        self._item: _Item | None = None
        self._menu: _Menu | None = None
        self._running = False
        self._next_watcher_check = 0.0

    @property
    def available(self) -> bool:
        return self._item is not None

    @property
    def running(self) -> bool:
        return self._running

    # ── жизненный цикл ─────────────────────────────────────────────────────

    def start(self) -> None:
        if self.available:
            return
        if GLib is None:
            raise TrayUnavailable(tr("tray_no_glib", error=_GLIB_ERROR))
        try:
            # Приватное соединение с собственным GLib-циклом: общая шина
            # источника простоя могла быть создана без диспетчера.
            loop = dbus.mainloop.glib.DBusGMainLoop()
            bus = dbus.SessionBus(private=True, mainloop=loop)
            self._bus, self._loop = bus, loop

            if not bus.name_has_owner(WATCHER_NAME):
                raise TrayUnavailable(tr("tray_no_watcher"))

            name = dbus.service.BusName(
                f"org.kde.StatusNotifierItem-{os.getpid()}-1", bus,
                do_not_queue=True,
            )
            menu = _Menu(self, bus)
            item = _Item(self, bus)
            self._name, self._menu, self._item = name, menu, item

            watcher = dbus.Interface(
                bus.get_object(WATCHER_NAME, WATCHER_PATH), WATCHER_IFACE
            )
            watcher.RegisterStatusNotifierItem(name.get_name())
        except dbus.DBusException as exc:
            self._cleanup()
            raise TrayUnavailable(
                tr("tray_failed", error=exc.get_dbus_name() or exc)
            ) from exc
        except TrayUnavailable:
            self._cleanup()
            raise
        self._next_watcher_check = time.monotonic() + WATCHER_CHECK_SECONDS

    def stop(self) -> None:
        if self._bus is not None and self._name is not None:
            try:
                self._bus.release_name(self._name.get_name())
            except dbus.DBusException:
                pass
        self._cleanup()

    def _cleanup(self) -> None:
        for obj in (self._item, self._menu):
            if obj is not None:
                try:
                    obj.remove_from_connection()
                except Exception:  # pragma: no cover - объект уже отключён
                    pass
        # Соединение не закрываем руками: BusName при сборке сам отпускает
        # имя, а его __del__ дёргает шину — закрытая шина даёт предупреждение.
        self._bus = self._loop = self._name = self._item = self._menu = None

    # ── события ────────────────────────────────────────────────────────────

    def pump(self) -> None:
        """Обслужить входящие вызовы шины и проверить, жив ли хост трея."""
        if GLib is None or not self.available:
            return
        context = GLib.MainContext.default()
        while context.pending():
            context.iteration(False)
        self._check_watcher()

    def _check_watcher(self) -> None:
        now = time.monotonic()
        if now < self._next_watcher_check:
            return
        self._next_watcher_check = now + WATCHER_CHECK_SECONDS
        try:
            alive = bool(self._bus.name_has_owner(WATCHER_NAME))  # type: ignore[union-attr]
        except dbus.DBusException:
            alive = False
        if not alive:
            self.stop()
            if self._on_lost is not None:
                self._on_lost()

    def refresh(self) -> None:
        """Перестроить подписи меню (после смены языка) и подсказку."""
        if not self.available:
            return
        try:
            self._menu.refresh()  # type: ignore[union-attr]
            self._item.NewToolTip()  # type: ignore[union-attr]
        except dbus.DBusException:
            pass

    def set_running(self, running: bool) -> None:
        if self.available and running != self._running:
            self._running = running
            self.refresh()

    # ── обратные вызовы из меню ────────────────────────────────────────────

    def show(self) -> None:
        self._on_show()

    def quit(self) -> None:
        self._on_quit()


class _Item(dbus.service.Object):
    """Объект ``org.kde.StatusNotifierItem``: свойства, сигналы, клики."""

    def __init__(self, tray: Tray, bus: dbus.Bus) -> None:
        super().__init__(bus, ITEM_PATH)
        self._tray = tray

    def _properties(self) -> dict[str, object]:
        subtitle = tr("tray_tooltip_running") if self._tray.running else tr(
            "status_stopped"
        )
        return {
            "Category": dbus.String("ApplicationStatus"),
            "Id": dbus.String("activity-renew"),
            "Title": dbus.String("activity-renew"),
            "Status": dbus.String("Active"),
            "IconName": dbus.String("input-mouse"),
            "IconPixmap": _pixmap(),
            "OverlayIconName": dbus.String(""),
            "OverlayIconPixmap": dbus.Array([], signature="(iiay)"),
            "AttentionIconName": dbus.String(""),
            "AttentionIconPixmap": dbus.Array([], signature="(iiay)"),
            "ToolTip": dbus.Struct(
                (
                    dbus.String("input-mouse"),
                    _pixmap(),
                    dbus.String("activity-renew"),
                    dbus.String(subtitle),
                ),
                signature=None,
            ),
            "ItemIsMenu": dbus.Boolean(True),
            "Menu": dbus.ObjectPath(MENU_PATH),
        }

    @dbus.service.method(PROPS_IFACE, in_signature="ss", out_signature="v")
    def Get(self, interface_name: str, property_name: str):
        try:
            return self._properties()[property_name]
        except KeyError:
            raise dbus.exceptions.DBusException(
                f"no such property: {property_name}",
                name="org.freedesktop.DBus.Error.UnknownProperty",
            ) from None

    @dbus.service.method(PROPS_IFACE, in_signature="s", out_signature="a{sv}")
    def GetAll(self, interface_name: str):
        return dbus.Dictionary(self._properties(), signature="sv")

    @dbus.service.method(PROPS_IFACE, in_signature="ssv", out_signature="")
    def Set(self, interface_name: str, property_name: str, value: object) -> None:
        raise dbus.exceptions.DBusException(
            f"{property_name} is read-only",
            name="org.freedesktop.DBus.Error.PropertyReadOnly",
        )

    # Клик по иконке. ItemIsMenu=True обычно означает «покажи меню», но
    # не все хосты это соблюдают — второй путь не помешает.
    @dbus.service.method(SNI_IFACE, in_signature="ii", out_signature="")
    def Activate(self, x: int, y: int) -> None:
        self._tray.show()

    @dbus.service.method(SNI_IFACE, in_signature="ii", out_signature="")
    def SecondaryActivate(self, x: int, y: int) -> None:
        self._tray.show()

    @dbus.service.method(SNI_IFACE, in_signature="ii", out_signature="")
    def ContextMenu(self, x: int, y: int) -> None:
        pass

    @dbus.service.method(SNI_IFACE, in_signature="is", out_signature="")
    def Scroll(self, delta: int, orientation: str) -> None:
        pass

    @dbus.service.signal(SNI_IFACE, signature="s")
    def NewTitle(self, title: str) -> None:
        pass

    @dbus.service.signal(SNI_IFACE, signature="")
    def NewIcon(self) -> None:
        pass

    @dbus.service.signal(SNI_IFACE, signature="")
    def NewAttentionIcon(self) -> None:
        pass

    @dbus.service.signal(SNI_IFACE, signature="")
    def NewOverlayIcon(self) -> None:
        pass

    @dbus.service.signal(SNI_IFACE, signature="")
    def NewToolTip(self) -> None:
        pass

    @dbus.service.signal(SNI_IFACE, signature="s")
    def NewStatus(self, status: str) -> None:
        pass


class _Menu(dbus.service.Object):
    """Меню трея по протоколу ``com.canonical.dbusmenu``."""

    def __init__(self, tray: Tray, bus: dbus.Bus) -> None:
        super().__init__(bus, MENU_PATH)
        self._tray = tray
        self._revision = MENU_REVISION

    # ── описание пунктов ───────────────────────────────────────────────────

    def _properties(self, item_id: int) -> dbus.Dictionary:
        if item_id == 0:
            return dbus.Dictionary(
                {"children-display": dbus.String("submenu")}, signature="sv"
            )
        label = dict(menu_entries()).get(item_id)
        if label is None:
            return dbus.Dictionary({}, signature="sv")
        return dbus.Dictionary(
            {
                "label": dbus.String(label),
                "enabled": dbus.Boolean(True),
                "visible": dbus.Boolean(True),
            },
            signature="sv",
        )

    def _layout(self, item_id: int) -> dbus.Struct:
        children = dbus.Array([], signature="v")
        if item_id == 0:
            for child_id, _label in menu_entries():
                children.append(
                    dbus.Struct(
                        (
                            dbus.Int32(child_id),
                            self._properties(child_id),
                            dbus.Array([], signature="v"),
                        ),
                        signature=None,
                    )
                )
        return dbus.Struct(
            (dbus.Int32(item_id), self._properties(item_id), children),
            signature=None,
        )

    # ── методы протокола ───────────────────────────────────────────────────

    @dbus.service.method(MENU_IFACE, in_signature="iias", out_signature="u(ia{sv}av)")
    def GetLayout(self, parent_id: int, recursion_depth: int, property_names):
        return dbus.UInt32(self._revision), self._layout(int(parent_id))

    @dbus.service.method(MENU_IFACE, in_signature="aias", out_signature="a(ia{sv})")
    def GetGroupProperties(self, ids, property_names):
        return dbus.Array(
            [
                dbus.Struct(
                    (dbus.Int32(int(item_id)), self._properties(int(item_id))),
                    signature=None,
                )
                for item_id in ids
            ],
            signature="(ia{sv})",
        )

    @dbus.service.method(MENU_IFACE, in_signature="isvu", out_signature="")
    def Event(self, item_id: int, event_id: str, data, timestamp: int) -> None:
        if str(event_id) != "clicked":
            return
        if int(item_id) == SHOW_ITEM_ID:
            self._tray.show()
        elif int(item_id) == QUIT_ITEM_ID:
            self._tray.quit()

    @dbus.service.method(MENU_IFACE, in_signature="i", out_signature="b")
    def AboutToShow(self, item_id: int) -> bool:
        return False

    @dbus.service.method(MENU_IFACE, in_signature="ai", out_signature="aiai")
    def AboutToShowGroup(self, ids):
        return dbus.Array([], signature="i"), dbus.Array([], signature="i")

    @dbus.service.signal(MENU_IFACE, signature="ui")
    def LayoutUpdated(self, revision: int, parent: int) -> None:
        pass

    def refresh(self) -> None:
        self._revision += 1
        self.LayoutUpdated(self._revision, 0)

    # ── свойства самого меню ───────────────────────────────────────────────
    # Некоторые хосты (KDE) читают Version/Status у меню, остальные молча
    # обходятся без них.

    def _menu_properties(self) -> dict[str, object]:
        return {
            "Version": dbus.UInt32(3),
            "TextDirection": dbus.String("ltr"),
            "Status": dbus.String("normal"),
            "IconThemePath": dbus.Array([], signature="s"),
        }

    @dbus.service.method(PROPS_IFACE, in_signature="ss", out_signature="v")
    def Get(self, interface_name: str, property_name: str):
        try:
            return self._menu_properties()[property_name]
        except KeyError:
            raise dbus.exceptions.DBusException(
                f"no such property: {property_name}",
                name="org.freedesktop.DBus.Error.UnknownProperty",
            ) from None

    @dbus.service.method(PROPS_IFACE, in_signature="s", out_signature="a{sv}")
    def GetAll(self, interface_name: str):
        return dbus.Dictionary(self._menu_properties(), signature="sv")

    @dbus.service.method(PROPS_IFACE, in_signature="ssv", out_signature="")
    def Set(self, interface_name: str, property_name: str, value: object) -> None:
        raise dbus.exceptions.DBusException(
            f"{property_name} is read-only",
            name="org.freedesktop.DBus.Error.PropertyReadOnly",
        )
