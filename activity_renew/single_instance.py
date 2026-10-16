"""Защита от нескольких запущенных копий.

Две копии дали бы двойное дёрганье, два виртуальных устройства и гонку при
записи конфига. Замок — ``flock`` на файле в ``$XDG_RUNTIME_DIR``: ядро снимает
его само при завершении процесса, поэтому «протухших» замков не бывает и
чистить нечего.
"""

from __future__ import annotations

import fcntl
import os
import tempfile

from .config import APP_NAME


def lock_path() -> str:
    runtime = os.environ.get("XDG_RUNTIME_DIR") or tempfile.gettempdir()
    return os.path.join(runtime, f"{APP_NAME}.lock")


def acquire() -> int | None:
    """Взять замок. ``None`` — копия уже запущена."""
    path = lock_path()
    fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        os.close(fd)
        return None

    os.truncate(fd, 0)
    os.write(fd, f"{os.getpid()}\n".encode("utf-8"))
    return fd


def release(fd: int | None) -> None:
    """Отпустить замок. Файл не удаляем: удаление гоняет наперегонки с новым запуском."""
    if fd is None:
        return
    try:
        fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)
