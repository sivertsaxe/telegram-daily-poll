import unittest
from datetime import datetime, timezone
from bot import TZ, run
from test_bot import fixture, Store
from test_motivation import TG


class PollTimingTest(unittest.TestCase):
    def test_only_nine_oclock_window_sends_polls(self):
        for hour, minute, expected in [(8, 59, False), (9, 0, True), (9, 59, True),
                                       (10, 0, False), (20, 45, False)]:
            state, store, tg = fixture(), Store(), TG()
            run(tg, store, state, datetime(2026, 11, 10, hour, minute, tzinfo=TZ), 'poll')
            self.assertEqual(any(method == 'sendPoll' for method, _ in tg.messages), expected)
            if not expected:
                self.assertEqual(tg.messages, [])

    def test_hourly_auto_never_sends_a_poll_or_quote(self):
        for hour in (7, 9, 10, 20):
            state, store, tg = fixture(), Store(), TG()
            state['sent']['report:2026-11-02'] = 42
            run(tg, store, state, datetime(2026, 11, 10, hour, tzinfo=TZ), 'auto')
            self.assertEqual(tg.messages, [])

    def test_winter_and_summer_use_nine_local(self):
        for month, utc_hour in ((1, 8), (7, 7)):
            local = datetime(2027, month, 12, utc_hour, tzinfo=timezone.utc).astimezone(TZ)
            self.assertEqual(local.hour, 9)
            state, store, tg = fixture(), Store(), TG()
            run(tg, store, state, local, 'poll')
            self.assertEqual(sum(method == 'sendPoll' for method, _ in tg.messages), 1)


if __name__ == '__main__':
    unittest.main()
