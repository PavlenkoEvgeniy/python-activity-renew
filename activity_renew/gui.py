"""Окно на tkinter: интервал, пуск/останов, режим, язык, состояние и журнал.

Дёрганье выполняется в отдельном потоке: внутри него спят и зовут внешний
``xdotool``, а окно замирать не должно. Обратно в поток tkinter результаты
возвращаются через очередь — tkinter не любит обращения из чужих потоков.

Смена языка перестраивает окно целиком: так не приходится держать таблицу
«виджет → ключ перевода» и обновлять её в двух местах. Журнал хранится
структурно (ключ + параметры), поэтому после перестройки он перерисовывается
на новом языке.
"""

from __future__ import annotations

import queue
import threading
import tkinter as tk
import tkinter.font as tkfont
from datetime import datetime
from pathlib import Path
from tkinter import messagebox, ttk

from . import __version__
from . import config as config_module
from . import i18n
from .config import MAX_INTERVAL, MIN_INTERVAL, MODES, Config
from .i18n import tr
from .idle import GnomeIdleSource, IdleSourceUnavailable
from .jiggler import ActivityKeeper, JigglerUnavailable
from .scheduler import Decision, Scheduler
from .tray import Tray, TrayUnavailable

TICK_MS = 1000
#: Входящие вызовы D-Bus (клики по трею) обслуживаются этим же потоком:
#: своего цикла у tkinter нет, поэтому GLib-контекст прокачивается таймером.
TRAY_PUMP_MS = 100

DIRECTION_KEYS = {
    (0, -1): "direction_up",
    (0, 1): "direction_down",
    (-1, 0): "direction_left",
    (1, 0): "direction_right",
}


class App:
    """Состояние и вид окна."""

    def __init__(
        self,
        root: tk.Tk,
        source: GnomeIdleSource,
        cfg: Config,
        cfg_path: Path | None = None,
        warnings: list[str] | None = None,
    ) -> None:
        self.root = root
        self.source = source
        self.cfg = cfg
        self.cfg_path = cfg_path
        self.startup_warnings = list(warnings or [])

        self.scheduler = Scheduler(cfg.interval_seconds, cfg.pause_when_locked)
        self.keeper = ActivityKeeper(cfg.mode, cfg.jiggle_hold_ms)

        self.running = False
        self.busy = False
        self.jiggle_count = 0
        self.journal_visible = True
        self.tray: Tray | None = None
        self._tray_job: str | None = None
        self._closing = False
        #: Текст ошибки, который переживает остановку и не даёт такту затереть себя.
        self.status_override: str | None = None
        self.events: queue.Queue = queue.Queue()
        #: Записи журнала: (метка времени, ключ перевода или None, параметры/текст).
        self.journal_entries: list[tuple[str, str | None, object]] = []

        self._build()
        for note in self.startup_warnings:
            self._journal_raw(tr("journal_config_note", note=note))
        self._start_tray()
        self._tick_job: str | None = self.root.after(TICK_MS, self._tick)

    # ── построение окна ────────────────────────────────────────────────────

    def _build(self) -> None:
        self.root.title(tr("window_title"))
        self.root.minsize(560, 320)

        self._build_menu()

        outer = ttk.Frame(self.root, padding=12)
        outer.grid(row=0, column=0, sticky="nsew")
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        outer.columnconfigure(1, weight=1)

        ttk.Label(outer, text=tr("interval_label")).grid(
            row=0, column=0, sticky="w"
        )
        self.interval_var = tk.StringVar(value=str(self.cfg.interval_seconds))
        self.interval_entry = ttk.Entry(outer, textvariable=self.interval_var, width=10)
        self.interval_entry.grid(row=0, column=1, sticky="w", padx=(8, 8))
        ttk.Button(outer, text=tr("button_apply"), command=self._apply_interval).grid(
            row=0, column=2, sticky="w"
        )

        self.toggle_button = ttk.Button(
            outer,
            text=tr("button_stop") if self.running else tr("button_start"),
            command=self._toggle,
        )
        self.toggle_button.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(12, 8))

        mode_box = ttk.LabelFrame(outer, text=tr("mode_box"), padding=8)
        mode_box.grid(row=2, column=0, columnspan=3, sticky="ew")
        self.mode_var = tk.StringVar(value=self.cfg.mode)
        for index, mode in enumerate(MODES):
            ttk.Radiobutton(
                mode_box,
                text=tr(f"mode_{mode}"),
                value=mode,
                variable=self.mode_var,
                command=self._on_mode_change,
            ).grid(row=0, column=index, sticky="w", padx=(0, 16))

        language_box = ttk.LabelFrame(outer, text=tr("language_box"), padding=8)
        language_box.grid(row=3, column=0, columnspan=3, sticky="ew", pady=(8, 0))
        self.language_var = tk.StringVar(value=i18n.get_language())
        for index, language in enumerate(i18n.LANGUAGES):
            ttk.Radiobutton(
                language_box,
                text=i18n.language_name(language),
                value=language,
                variable=self.language_var,
                command=self._on_language_change,
            ).grid(row=0, column=index, sticky="w", padx=(0, 16))

        self.pause_var = tk.BooleanVar(value=self.cfg.pause_when_locked)
        ttk.Checkbutton(
            outer,
            text=tr("pause_check"),
            variable=self.pause_var,
            command=self._on_pause_change,
        ).grid(row=4, column=0, columnspan=3, sticky="w", pady=(8, 0))

        self.journal_var = tk.BooleanVar(value=self.journal_visible)
        ttk.Checkbutton(
            outer,
            text=tr("journal_check"),
            variable=self.journal_var,
            command=self._on_journal_toggle,
        ).grid(row=5, column=0, columnspan=3, sticky="w", pady=(4, 0))

        self.status_var = tk.StringVar(
            value=self.status_override or tr("status_stopped")
        )
        ttk.Label(outer, textvariable=self.status_var, foreground="#333").grid(
            row=6, column=0, columnspan=3, sticky="w", pady=(10, 0)
        )

        self.journal_frame = ttk.LabelFrame(
            outer, text=tr("journal_box"), padding=6
        )
        self.journal_frame.grid(row=7, column=0, columnspan=3, sticky="nsew", pady=(8, 0))
        outer.rowconfigure(7, weight=1)
        self.journal = tk.Listbox(self.journal_frame, height=8, activestyle="none")
        self.journal.grid(row=0, column=0, sticky="nsew")
        self.journal_frame.columnconfigure(0, weight=1)
        self.journal_frame.rowconfigure(0, weight=1)
        scroll = ttk.Scrollbar(
            self.journal_frame, orient="vertical", command=self.journal.yview
        )
        scroll.grid(row=0, column=1, sticky="ns")
        self.journal.configure(yscrollcommand=scroll.set)

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._refresh_mode_sensitivity()
        self._render_journal()
        if not self.journal_visible:
            self.journal_frame.grid_remove()

    def _build_menu(self) -> None:
        menubar = tk.Menu(self.root)
        help_menu = tk.Menu(menubar, tearoff=False)
        help_menu.add_command(label=tr("menu_about"), command=self._show_about)
        menubar.add_cascade(label=tr("menu_help"), menu=help_menu)
        self.root.configure(menu=menubar)

    def _rebuild(self) -> None:
        """Перестроить окно после смены языка, сохранив состояние."""
        self.root.configure(menu="")
        for child in self.root.winfo_children():
            child.destroy()
        self._build()

    # ── реакция на элементы управления ─────────────────────────────────────

    def _apply_interval(self) -> None:
        raw = self.interval_var.get().strip()
        try:
            value = int(raw)
        except ValueError:
            messagebox.showerror(
                tr("error_not_number_title"),
                tr("error_not_number_message", value=raw),
                parent=self.root,
            )
            self.interval_var.set(str(self.scheduler.interval_seconds))
            return

        clamped = min(max(value, MIN_INTERVAL), MAX_INTERVAL)
        if clamped != value:
            messagebox.showwarning(
                tr("interval_out_of_range_title"),
                tr(
                    "interval_out_of_range_message",
                    min=MIN_INTERVAL,
                    max=MAX_INTERVAL,
                    value=clamped,
                ),
                parent=self.root,
            )
        self.interval_var.set(str(clamped))
        self.scheduler.set_interval(clamped)
        self.cfg.interval_seconds = clamped
        self._save()
        self._journal("journal_interval_changed", seconds=clamped)

    def _on_pause_change(self) -> None:
        value = bool(self.pause_var.get())
        self.scheduler.set_pause_when_locked(value)
        self.cfg.pause_when_locked = value
        self._save()
        self._journal("journal_pause_on" if value else "journal_pause_off")

    def _on_mode_change(self) -> None:
        mode = self.mode_var.get()
        self.cfg.mode = mode
        self._save()
        self._refresh_mode_sensitivity()
        if mode == self.keeper.mode:
            return

        was_running = self.running
        if was_running:
            self.keeper.stop()
            self.running = False

        self.keeper.mode = mode
        self._journal("journal_mode_changed", mode=tr(f"mode_{mode}"))
        if was_running:
            self._start()

    def _on_language_change(self) -> None:
        language = self.language_var.get()
        if language not in i18n.LANGUAGES or language == i18n.get_language():
            return

        i18n.set_language(language)
        self.cfg.language = language
        self._save()
        self._rebuild()
        if self.tray is not None:
            self.tray.refresh()
        self._journal(
            "journal_language_changed", language=i18n.language_name(language)
        )

    def _on_journal_toggle(self) -> None:
        self.journal_visible = bool(self.journal_var.get())
        if self.journal_visible:
            self.journal_frame.grid()
        else:
            self.journal_frame.grid_remove()

    def _refresh_mode_sensitivity(self) -> None:
        # В режиме «только ингибит» экран не гаснет постоянно, поэтому интервал
        # простоя ни на что не влияет — поле честно гасим.
        mouse = self.mode_var.get() in ActivityKeeper.MOUSE_MODES
        state = "normal" if mouse else "disabled"
        self.interval_entry.configure(state=state)

    # ── пуск и останов ─────────────────────────────────────────────────────

    def _toggle(self) -> None:
        if self.running:
            self._stop()
        else:
            self._start()

    def _start(self) -> None:
        self.keeper.mode = self.mode_var.get()
        self.keeper.hold_ms = self.cfg.jiggle_hold_ms
        try:
            notes = self.keeper.start()
        except JigglerUnavailable as exc:
            self.keeper.stop()
            self._journal("journal_start_failed", error=exc)
            messagebox.showerror(tr("mode_failed_title"), str(exc), parent=self.root)
            return

        self.running = True
        if self.tray is not None:
            self.tray.set_running(True)
        self.jiggle_count = 0
        self.status_override = None
        self.scheduler.mark_jiggled()  # отсчёт интервала начинается с пуска
        self.toggle_button.configure(text=tr("button_stop"))
        for note in notes:
            self._journal_raw(note)

    def _stop(self) -> None:
        self.running = False
        if self.tray is not None:
            self.tray.set_running(False)
        self.keeper.stop()
        self.toggle_button.configure(text=tr("button_start"))
        self._journal("journal_stopped")

    # ── основной такт ──────────────────────────────────────────────────────

    def _tick(self) -> None:
        try:
            self._drain_events()
            if self.running:
                if self.keeper.jiggles_mouse:
                    self._tick_with_mouse()
                else:
                    self.source.idle_seconds()  # держим связь живой и ловим отказ
                    self.status_var.set(
                        tr("status_running_inhibit", count=self.jiggle_count)
                    )
            else:
                self.status_var.set(self.status_override or tr("status_stopped"))
        except IdleSourceUnavailable as exc:
            # Такт продолжает жить: после отказа источник может ожить, и «Старт»
            # должен снова работать. Повтора окна с ошибкой не будет — _fail
            # снимает признак «работает», а запросы делает только он.
            self._fail(str(exc))
        self._tick_job = self.root.after(TICK_MS, self._tick)

    def _tick_with_mouse(self) -> None:
        idle = self.source.idle_seconds()
        locked = self.source.is_locked()
        decision = self.scheduler.decide(running=True, idle_seconds=idle, locked=locked)
        self.status_var.set(self._status_text(idle, decision))
        if decision.jiggle and not self.busy:
            self._start_jiggle(self._reason_text(decision))

    def _reason_text(self, decision: Decision) -> str:
        if decision.reason_key == "locked":
            return tr("reason_locked")
        if decision.reason_key == "idle":
            return tr(
                "reason_idle",
                idle=decision.reason_value,
                interval=self.scheduler.interval_seconds,
            )
        if decision.reason_key == "wait":
            return tr("reason_wait", wait=decision.reason_value)
        return tr("status_stopped")

    def _status_text(self, idle: float, decision: Decision) -> str:
        text = tr(
            "status_running_mouse",
            idle=idle,
            reason=self._reason_text(decision),
            count=self.jiggle_count,
        )
        if self.cfg.small_interval:
            text += tr("status_small_interval", seconds=config_module.SMALL_INTERVAL)
        return text

    def _start_jiggle(self, reason: str) -> None:
        self.busy = True

        def work() -> None:
            try:
                direction = self.keeper.jiggle()
                self.events.put(("ok", reason, direction, None))
            except Exception as exc:  # поток не должен падать молча
                self.events.put(("error", reason, None, exc))

        threading.Thread(target=work, daemon=True, name="jiggle").start()

    def _drain_events(self) -> None:
        while True:
            try:
                kind, reason, direction, error = self.events.get_nowait()
            except queue.Empty:
                return

            self.busy = False
            if kind == "error":
                self._fail(tr("journal_jiggle_failed", error=error))
                return

            self.scheduler.mark_jiggled()
            self.jiggle_count += 1
            where = tr(DIRECTION_KEYS[direction]) if direction else "—"
            self._journal(
                "journal_jiggled", direction=where, reason=reason
            )

    def _fail(self, message: str) -> None:
        """Отказ, после которого продолжать нельзя."""
        self.running = False
        if self.tray is not None:
            self.tray.set_running(False)
        self.keeper.stop()
        self.toggle_button.configure(text=tr("button_start"))
        self.status_override = tr("status_error", message=message.splitlines()[0])
        self.status_var.set(self.status_override)
        self._journal("journal_error", message=message)
        messagebox.showerror(tr("work_stopped_title"), message, parent=self.root)

    # ── журнал, конфиг, закрытие ────────────────────────────────────────────

    def _journal(self, key: str, **params: object) -> None:
        self._add_journal_entry((datetime.now().strftime("%H:%M:%S"), key, params))

    def _journal_raw(self, text: str) -> None:
        """Готовая строка: замечания из конфига и сообщения дёргалки."""
        self._add_journal_entry((datetime.now().strftime("%H:%M:%S"), None, text))

    def _add_journal_entry(self, entry: tuple[str, str | None, object]) -> None:
        self.journal_entries.insert(0, entry)
        self._trim_journal()
        self._render_journal()

    def _trim_journal(self) -> None:
        limit = max(0, int(self.cfg.log_limit))
        while len(self.journal_entries) > limit:
            self.journal_entries.pop()

    def _render_journal(self) -> None:
        if not hasattr(self, "journal"):
            return
        self.journal.delete(0, "end")
        for stamp, key, payload in reversed(self.journal_entries):
            if key is None:
                text = str(payload)
            else:
                text = tr(key, **payload)  # type: ignore[arg-type]
            self.journal.insert(0, f"{stamp}  {text}")

    def _save(self) -> None:
        try:
            config_module.save(self.cfg, self.cfg_path)
        except OSError as exc:
            self._journal("journal_config_save_failed", error=exc)

    # ── трей ────────────────────────────────────────────────────────────────

    def _start_tray(self) -> None:
        """Завести иконку, если в сессии есть кому её нарисовать."""
        tray = Tray(
            on_show=self._show_window,
            on_quit=self._quit,
            on_lost=self._on_tray_lost,
        )
        try:
            tray.start()
        except TrayUnavailable as exc:
            self._journal("journal_tray_unavailable", error=exc)
            return
        except Exception as exc:  # иконка не имеет права ронять приложение
            self._journal("journal_tray_unavailable", error=exc)
            return
        self.tray = tray
        self.tray.set_running(self.running)
        self._tray_job = self.root.after(TRAY_PUMP_MS, self._pump_tray)

    def _pump_tray(self) -> None:
        if self.tray is not None:
            self.tray.pump()
        if not self._closing:
            self._tray_job = self.root.after(TRAY_PUMP_MS, self._pump_tray)

    def _show_window(self) -> None:
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def _hide_to_tray(self) -> None:
        self.root.withdraw()
        self._journal("journal_hidden_to_tray")

    def _on_tray_lost(self) -> None:
        # Хост трея (расширение) выключили: иконки больше нет. Если окно было
        # спрятано, его надо вернуть, иначе программа станет невидимой.
        self.tray = None
        if self.root.state() == "withdrawn":
            self._show_window()
        self._journal("journal_tray_lost")

    def _on_close(self) -> None:
        if self.tray is not None and self.tray.available:
            self._hide_to_tray()
        else:
            self._quit()

    def _quit(self) -> None:
        self._closing = True
        if self.tray is not None:
            self.tray.stop()
            self.tray = None
        self._stop()
        self.root.destroy()

    # ── About ──────────────────────────────────────────────────────────────

    def _show_about(self) -> None:
        window = tk.Toplevel(self.root)
        window.title(tr("about_title"))
        window.transient(self.root)
        window.resizable(False, False)

        title_font = tkfont.nametofont("TkDefaultFont").copy()
        title_font.configure(size=14, weight="bold")

        outer = ttk.Frame(window, padding=16)
        outer.grid(row=0, column=0, sticky="nsew")
        outer.columnconfigure(0, weight=1)

        ttk.Label(outer, text="activity-renew", font=title_font).grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(outer, text=tr("about_version", version=__version__)).grid(
            row=1, column=0, sticky="w", pady=(2, 10)
        )
        ttk.Label(
            outer,
            text=tr("about_description"),
            wraplength=380,
            justify="left",
        ).grid(row=2, column=0, sticky="w")
        ttk.Label(
            outer,
            text=tr("about_platform"),
            wraplength=380,
            justify="left",
        ).grid(row=3, column=0, sticky="w", pady=(8, 16))
        close_button = ttk.Button(
            outer, text=tr("button_close"), command=window.destroy
        )
        close_button.grid(row=4, column=0, sticky="e")
        close_button.focus_set()

        # По центру главного окна, а не по центру экрана. Первая установка
        # нужна, чтобы окно появилось и оконный менеджер сообщил реальные
        # размеры вместе с рамкой; вторая — поправка на эту рамку.
        window.update_idletasks()
        width = window.winfo_reqwidth()
        height = window.winfo_reqheight()
        root_width = self.root.winfo_width() or self.root.winfo_reqwidth()
        root_height = self.root.winfo_height() or self.root.winfo_reqheight()
        x = self.root.winfo_rootx() + max(0, (root_width - width) // 2)
        y = self.root.winfo_rooty() + max(0, (root_height - height) // 2)
        window.geometry(f"+{x}+{y}")
        window.update()

        target_x = self.root.winfo_rootx() + max(
            0, (root_width - window.winfo_width()) // 2
        )
        target_y = self.root.winfo_rooty() + max(
            0, (root_height - window.winfo_height()) // 2
        )
        x += target_x - window.winfo_rootx()
        y += target_y - window.winfo_rooty()
        window.geometry(f"+{x}+{y}")

        window.bind("<Escape>", lambda _event: window.destroy())
        window.bind("<Return>", lambda _event: window.destroy())
        window.grab_set()


def run(source: GnomeIdleSource, cfg: Config, cfg_path: Path | None = None,
        warnings: list[str] | None = None) -> None:
    root = tk.Tk()
    App(root, source, cfg, cfg_path=cfg_path, warnings=warnings)
    root.mainloop()
