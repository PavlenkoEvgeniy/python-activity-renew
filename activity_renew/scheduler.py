"""Чистая логика «пора дёргать» — без tkinter, D-Bus и сна.

Часы подменяются, поэтому поведение проверяется тестами мгновенно, без
реального ожидания двух минут.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable

#: Нижняя граница паузы между опросами, чтобы не крутиться вхолостую.
MIN_TICK_SECONDS = 0.5


@dataclass(frozen=True)
class Decision:
    """Что делать на этом такте.

    ``reason_key`` — машинный код причины (``stopped``, ``locked``, ``idle``,
    ``wait``); текст на нужном языке собирает интерфейс.
    """

    jiggle: bool
    seconds_until_next: float
    reason_key: str
    reason_value: float = 0.0


class Scheduler:
    """Решает, когда дёргать, исходя из простоя и собственной истории.

    Одного счётчика простоя мало: в режиме «только ингибит» настоящих событий
    ввода не возникает, счётчик не сбрасывается и рос бы бесконечно — тогда
    дёрганье повторялось бы на каждом такте. Поэтому второе условие — сколько
    времени прошло с прошлого дёрганья.
    """

    def __init__(
        self,
        interval_seconds: int,
        pause_when_locked: bool = True,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._interval = int(interval_seconds)
        self._pause_when_locked = bool(pause_when_locked)
        self._clock = clock
        self._last_jiggle: float | None = None

    @property
    def interval_seconds(self) -> int:
        return self._interval

    @property
    def pause_when_locked(self) -> bool:
        return self._pause_when_locked

    def set_interval(self, seconds: int) -> None:
        """Смена интервала на лету — без перезапуска."""
        self._interval = int(seconds)

    def set_pause_when_locked(self, value: bool) -> None:
        self._pause_when_locked = bool(value)

    def mark_jiggled(self) -> None:
        """Отметить, что дёрганье состоялось."""
        self._last_jiggle = self._clock()

    def decide(self, *, running: bool, idle_seconds: float, locked: bool) -> Decision:
        if not running:
            return Decision(False, 0.0, "stopped")

        if locked and self._pause_when_locked:
            return Decision(False, MIN_TICK_SECONDS, "locked")

        now = self._clock()
        if self._last_jiggle is None:
            since_last = None
        else:
            since_last = now - self._last_jiggle

        # Сколько ждать по простою и сколько — по собственной истории.
        wait = max(0.0, self._interval - float(idle_seconds))
        if since_last is not None:
            wait = max(wait, self._interval - since_last)

        if idle_seconds >= self._interval and wait <= 0.0:
            return Decision(True, 0.0, "idle", float(idle_seconds))

        wait = max(wait, MIN_TICK_SECONDS)
        return Decision(False, wait, "wait", wait)
