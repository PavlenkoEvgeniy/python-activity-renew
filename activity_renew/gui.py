"""Окно на tkinter: интервал, пуск/останов, режим, состояние и журнал.

Дёрганье выполняется в отдельном потоке: внутри него спят и зовут внешний
``xdotool``, а окно замирать не должно. Обратно в поток tkinter результаты
возвращаются через очередь — tkinter не любит обращения из чужих потоков.
"""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import messagebox, ttk

from . import config as config_module
from .config import MAX_INTERVAL, MIN_INTERVAL, MODE_TITLES, MODES, Config
from .idle import GnomeIdleSource, IdleSourceUnavailable
from .jiggler import ActivityKeeper, JigglerUnavailable
from .scheduler import Decision, Scheduler

TICK_MS = 1000
WINDOW_TITLE = "activity-renew — имитация активности"

DIRECTION_TITLES = {
    (0, -1): "вверх",
    (0, 1): "вниз",
    (-1, 0): "влево",
    (1, 0): "вправо",
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
        #: Текст ошибки, который переживает остановку и не даёт такту затереть себя.
        self.status_override: str | None = None
        self.events: queue.Queue = queue.Queue()

        self._build()
        for note in self.startup_warnings:
            self._journal(f"замечание к конфигу: {note}")

    # ── построение окна ────────────────────────────────────────────────────

    def _build(self) -> None:
        self.root.title(WINDOW_TITLE)
        self.root.minsize(520, 240)

        outer = ttk.Frame(self.root, padding=12)
        outer.grid(row=0, column=0, sticky="nsew")
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        outer.columnconfigure(1, weight=1)

        ttk.Label(outer, text="Дёргать после простоя, с:").grid(
            row=0, column=0, sticky="w"
        )
        self.interval_var = tk.StringVar(value=str(self.cfg.interval_seconds))
        self.interval_entry = ttk.Entry(outer, textvariable=self.interval_var, width=10)
        self.interval_entry.grid(row=0, column=1, sticky="w", padx=(8, 8))
        ttk.Button(outer, text="Применить", command=self._apply_interval).grid(
            row=0, column=2, sticky="w"
        )

        self.toggle_button = ttk.Button(outer, text="Старт", command=self._toggle)
        self.toggle_button.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(12, 8))

        mode_box = ttk.LabelFrame(outer, text="Режим", padding=8)
        mode_box.grid(row=2, column=0, columnspan=3, sticky="ew")
        self.mode_var = tk.StringVar(value=self.cfg.mode)
        for index, mode in enumerate(MODES):
            ttk.Radiobutton(
                mode_box,
                text=MODE_TITLES[mode],
                value=mode,
                variable=self.mode_var,
                command=self._on_mode_change,
            ).grid(row=0, column=index, sticky="w", padx=(0, 16))

        self.pause_var = tk.BooleanVar(value=self.cfg.pause_when_locked)
        ttk.Checkbutton(
            outer,
            text="Пауза, когда экран заблокирован",
            variable=self.pause_var,
            command=self._on_pause_change,
        ).grid(row=3, column=0, columnspan=3, sticky="w", pady=(8, 0))

        self.journal_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            outer,
            text="Показывать журнал событий",
            variable=self.journal_var,
            command=self._on_journal_toggle,
        ).grid(row=4, column=0, columnspan=3, sticky="w", pady=(4, 0))

        self.status_var = tk.StringVar(value="остановлено")
        ttk.Label(outer, textvariable=self.status_var, foreground="#333").grid(
            row=5, column=0, columnspan=3, sticky="w", pady=(10, 0)
        )

        self.journal_frame = ttk.LabelFrame(outer, text="Последние события", padding=6)
        self.journal_frame.grid(row=6, column=0, columnspan=3, sticky="nsew", pady=(8, 0))
        outer.rowconfigure(6, weight=1)
        self.journal = tk.Listbox(self.journal_frame, height=8, activestyle="none")
        self.journal.grid(row=0, column=0, sticky="nsew")
        self.journal_frame.columnconfigure(0, weight=1)
        self.journal_frame.rowconfigure(0, weight=1)
        scroll = ttk.Scrollbar(self.journal_frame, orient="vertical", command=self.journal.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.journal.configure(yscrollcommand=scroll.set)

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._refresh_mode_sensitivity()
        self.root.after(TICK_MS, self._tick)

    # ── реакция на элементы управления ─────────────────────────────────────

    def _apply_interval(self) -> None:
        raw = self.interval_var.get().strip()
        try:
            value = int(raw)
        except ValueError:
            messagebox.showerror(
                "Не число", f"«{raw}» не похоже на число секунд.", parent=self.root
            )
            self.interval_var.set(str(self.scheduler.interval_seconds))
            return

        clamped = min(max(value, MIN_INTERVAL), MAX_INTERVAL)
        if clamped != value:
            messagebox.showwarning(
                "Интервал вне диапазона",
                f"Допустимо от {MIN_INTERVAL} до {MAX_INTERVAL} с — поставил {clamped}.",
                parent=self.root,
            )
        self.interval_var.set(str(clamped))
        self.scheduler.set_interval(clamped)
        self.cfg.interval_seconds = clamped
        self._save()
        self._journal(f"интервал изменён на {clamped} с")

    def _on_pause_change(self) -> None:
        value = bool(self.pause_var.get())
        self.scheduler.set_pause_when_locked(value)
        self.cfg.pause_when_locked = value
        self._save()
        self._journal("пауза при блокировке " + ("включена" if value else "выключена"))

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
        self._journal(f"режим: {MODE_TITLES.get(mode, mode)}")
        if was_running:
            self._start()

    def _on_journal_toggle(self) -> None:
        if self.journal_var.get():
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
            self._journal(f"не удалось запустить: {exc}")
            messagebox.showerror("Режим не запустился", str(exc), parent=self.root)
            return

        self.running = True
        self.jiggle_count = 0
        self.status_override = None
        self.scheduler.mark_jiggled()  # отсчёт интервала начинается с пуска
        self.toggle_button.configure(text="Стоп")
        for note in notes:
            self._journal(note)

    def _stop(self) -> None:
        self.running = False
        self.keeper.stop()
        self.toggle_button.configure(text="Старт")
        self._journal("остановлено")

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
                        f"работает · ингибит простоя активен · срабатываний {self.jiggle_count}"
                    )
            else:
                self.status_var.set(self.status_override or "остановлено")
        except IdleSourceUnavailable as exc:
            # Такт продолжает жить: после отказа источник может ожить, и «Старт»
            # должен снова работать. Повтора окна с ошибкой не будет — _fail
            # снимает признак «работает», а запросы делает только он.
            self._fail(str(exc))
        self.root.after(TICK_MS, self._tick)

    def _tick_with_mouse(self) -> None:
        idle = self.source.idle_seconds()
        locked = self.source.is_locked()
        decision = self.scheduler.decide(running=True, idle_seconds=idle, locked=locked)
        self.status_var.set(self._status_text(idle, decision))
        if decision.jiggle and not self.busy:
            self._start_jiggle(decision.reason)

    def _status_text(self, idle: float, decision: Decision) -> str:
        text = (
            f"работает · простой {idle:.0f} с · {decision.reason} "
            f"· срабатываний {self.jiggle_count}"
        )
        if self.cfg.small_interval:
            text += f" · ⚠ интервал меньше {config_module.SMALL_INTERVAL} с"
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
                self._fail(f"дёрганье не удалось: {error}")
                return

            self.scheduler.mark_jiggled()
            self.jiggle_count += 1
            where = DIRECTION_TITLES.get(direction, "?") if direction else "—"
            self._journal(f"дёрнул мышь на 1 px {where} и вернул ({reason})")

    def _fail(self, message: str) -> None:
        """Отказ, после которого продолжать нельзя."""
        self.running = False
        self.keeper.stop()
        self.toggle_button.configure(text="Старт")
        self.status_override = f"ошибка: {message.splitlines()[0]}"
        self.status_var.set(self.status_override)
        self._journal(f"ошибка: {message}")
        messagebox.showerror("Работа остановлена", message, parent=self.root)

    # ── журнал, конфиг, закрытие ────────────────────────────────────────────

    def _journal(self, text: str) -> None:
        stamp = datetime.now().strftime("%H:%M:%S")
        self.journal.insert(0, f"{stamp}  {text}")
        limit = max(0, int(self.cfg.log_limit))
        while self.journal.size() > limit:
            self.journal.delete("end")

    def _save(self) -> None:
        try:
            config_module.save(self.cfg, self.cfg_path)
        except OSError as exc:
            self._journal(f"конфиг не сохранён: {exc}")

    def _on_close(self) -> None:
        self._stop()
        self.root.destroy()


def run(source: GnomeIdleSource, cfg: Config, cfg_path: Path | None = None,
        warnings: list[str] | None = None) -> None:
    root = tk.Tk()
    App(root, source, cfg, cfg_path=cfg_path, warnings=warnings)
    root.mainloop()
