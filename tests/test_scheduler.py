"""Логика «пора дёргать» на подменяемых часах — без реального ожидания."""

import unittest

from activity_renew.scheduler import MIN_TICK_SECONDS, Scheduler


class FakeClock:
    def __init__(self, start: float = 1000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class SchedulerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.clock = FakeClock()
        self.scheduler = Scheduler(120, pause_when_locked=True, clock=self.clock)

    def decide(self, idle: float, *, locked: bool = False, running: bool = True):
        return self.scheduler.decide(
            running=running, idle_seconds=idle, locked=locked
        )

    def test_stopped_never_jiggles(self) -> None:
        decision = self.decide(9999, running=False)
        self.assertFalse(decision.jiggle)

    def test_waits_while_idle_below_interval(self) -> None:
        decision = self.decide(30)
        self.assertFalse(decision.jiggle)
        self.assertAlmostEqual(decision.seconds_until_next, 90)

    def test_jiggles_when_idle_reaches_interval(self) -> None:
        self.assertTrue(self.decide(120).jiggle)

    def test_first_tick_with_huge_idle_jiggles_immediately(self) -> None:
        # Приложение запустили после долгого простоя — ждать ещё дважды незачем.
        self.assertTrue(self.decide(5000).jiggle)

    def test_locked_pauses(self) -> None:
        decision = self.decide(9999, locked=True)
        self.assertFalse(decision.jiggle)
        self.assertEqual(decision.reason_key, "locked")

    def test_reason_keys_describe_the_decision(self) -> None:
        self.assertEqual(self.decide(30).reason_key, "wait")
        self.assertEqual(self.decide(120).reason_key, "idle")
        self.assertEqual(self.decide(120).reason_value, 120.0)

    def test_locked_jiggles_when_pause_disabled(self) -> None:
        self.scheduler.set_pause_when_locked(False)
        self.assertTrue(self.decide(9999, locked=True).jiggle)

    def test_wait_never_below_min_tick(self) -> None:
        decision = self.decide(119.9)
        self.assertGreaterEqual(decision.seconds_until_next, MIN_TICK_SECONDS)

    def test_own_history_prevents_spam_when_idle_never_resets(self) -> None:
        """Режим «только ингибит»: реального ввода нет, счётчик простоя не сбрасывается."""
        self.assertTrue(self.decide(120).jiggle)
        self.scheduler.mark_jiggled()

        decision = self.decide(121)  # счётчик всё ещё растёт, но мы только что дёрнули
        self.assertFalse(decision.jiggle)
        self.assertAlmostEqual(decision.seconds_until_next, 120)

        # Пока часы не прошли интервал, рост простоя ничего не меняет.
        self.assertFalse(self.decide(200).jiggle)

        self.clock.advance(120)
        self.assertTrue(self.decide(241).jiggle)

    def test_interval_change_applies_immediately(self) -> None:
        self.assertFalse(self.decide(30).jiggle)
        self.scheduler.set_interval(20)
        self.assertTrue(self.decide(30).jiggle)

    def test_history_survives_interval_change(self) -> None:
        self.scheduler.mark_jiggled()
        self.scheduler.set_interval(300)
        self.assertFalse(self.decide(400).jiggle)
        self.clock.advance(300)
        self.assertTrue(self.decide(700).jiggle)


if __name__ == "__main__":
    unittest.main()
