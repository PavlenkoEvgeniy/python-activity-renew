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
from .i18n import tr
from .idle import GnomeIdleSource, IdleSourceUnavailable


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="activity-renew",
        description=(
            "Moves the mouse 1 pixel and back when there has been no input "
            "for longer than the configured interval."
        ),
    )
    parser.add_argument(
        "--version", action="version", version=f"activity-renew {__version__}"
    )
    parser.add_argument(
        "--config", metavar="PATH",
        help="configuration file (default: ~/.config)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="check the idle source and the virtual mouse, then exit",
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
    from .tray import Tray, TrayUnavailable

    print(f"activity-renew {__version__}")
    print(tr("check_idle_source", description=source.describe()))

    tray = Tray(lambda: None, lambda: None)
    try:
        tray.start()
        print(tr("check_tray_available"))
    except TrayUnavailable as exc:
        print(tr("check_tray_failed", error=exc))
    else:
        tray.stop()

    keeper = ActivityKeeper("uinput", cfg.jiggle_hold_ms)
    try:
        notes = keeper.start()
    except JigglerUnavailable as exc:
        print(tr("check_mouse_failed", error=exc))
        return 1
    finally:
        keeper.stop()
    for note in notes:
        print(tr("check_mouse_note", note=note))

    keeper = ActivityKeeper("inhibit", cfg.jiggle_hold_ms)
    try:
        keeper.start()
        print(tr("check_inhibit_available"))
    except JigglerUnavailable as exc:
        print(tr("check_inhibit_failed", error=exc))
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
        return _report_error(tr("error_no_idle_title"), str(exc))

    if args.check:
        return _run_check(source, cfg)

    lock = single_instance.acquire()
    if lock is None:
        return _report_error(
            tr("error_already_running_title"),
            tr("error_already_running_message"),
        )

    try:
        run_gui(source, cfg, cfg_path=cfg_path, warnings=warnings)
    finally:
        single_instance.release(lock)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
