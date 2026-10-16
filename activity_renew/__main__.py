"""Точка входа: ``python3 -m activity_renew``."""

from __future__ import annotations

import argparse
import sys
import tkinter as tk
from pathlib import Path

from . import __version__
from . import config as config_module
from . import single_instance
from .gui import run as run_gui
from .idle import GnomeIdleSource, IdleSourceUnavailable


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="activity-renew",
        description=(
            "Дёргает мышь на 1 пиксель и возвращает обратно, если за компьютером "
            "нет ввода дольше заданного времени."
        ),
    )
    parser.add_argument(
        "--version", action="version", version=f"activity-renew {__version__}"
    )
    parser.add_argument(
        "--config", metavar="ПУТЬ", help="файл конфигурации (по умолчанию в ~/.config)"
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="проверить источники простоя и виртуальную мышь, затем выйти",
    )
    return parser.parse_args(argv)


def _report_error(title: str, message: str) -> int:
    """Показать ошибку окном, а если окна нет — хотя бы в поток ошибок."""
    try:
        root = tk.Tk()
        root.withdraw()
        from tkinter import messagebox

        messagebox.showerror(title, message)
        root.destroy()
    except Exception:
        print(f"{title}: {message}", file=sys.stderr)
    return 1


def _run_check(source: GnomeIdleSource, cfg: config_module.Config) -> int:
    """Диагностика: что доступно, что нет. Мышь проверяется сдвигом на 25 px."""
    from .jiggler import ActivityKeeper, JigglerUnavailable

    print(f"activity-renew {__version__}")
    print(f"источник простоя: {source.describe()}")

    keeper = ActivityKeeper("uinput", cfg.jiggle_hold_ms)
    try:
        notes = keeper.start()
    except JigglerUnavailable as exc:
        print(f"виртуальная мышь: НЕ РАБОТАЕТ — {exc}")
        return 1
    finally:
        keeper.stop()
    for note in notes:
        print(f"виртуальная мышь: {note}")

    keeper = ActivityKeeper("inhibit", cfg.jiggle_hold_ms)
    try:
        keeper.start()
        print("ингибит простоя: доступен")
    except JigglerUnavailable as exc:
        print(f"ингибит простоя: НЕ РАБОТАЕТ — {exc}")
        return 1
    finally:
        keeper.stop()
    return 0


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    cfg_path = Path(args.config) if args.config else None
    cfg, warnings = config_module.load(cfg_path)

    try:
        source = GnomeIdleSource()
    except IdleSourceUnavailable as exc:
        return _report_error("Нет источника простоя", str(exc))

    if args.check:
        return _run_check(source, cfg)

    lock = single_instance.acquire()
    if lock is None:
        return _report_error(
            "Уже запущено",
            "Вторая копия дёргала бы мышь вдвое чаще и спорила за файл "
            "конфигурации. Найдите уже открытое окно activity-renew.",
        )

    try:
        run_gui(source, cfg, cfg_path=cfg_path, warnings=warnings)
    finally:
        single_instance.release(lock)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
