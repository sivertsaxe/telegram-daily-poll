import unittest
from datetime import datetime, timezone
from unittest.mock import patch
from bot import TZ, run, ServiceError
from test_bot import fixture, Store
from test_motivation import TG


class PollTimingTest(unittest.TestCase):
    def test_only_nine_oclock_window_sends_polls(self):
        for hour, minute, expected in [(8, 59, False), (9, 0, True), (9, 59, True),
                                       (10, 0, False), (20, 45, False)]:
            state, store, tg = fixture(), Store(), TG()
            now = datetime(2026, 11, 10, hour, minute, tzinfo=TZ)
            if expected:
                run(tg, store, state, now, 'poll')
            else:
                with self.assertRaisesRegex(ServiceError, 'Morning poll was missed'):
                    run(tg, store, state, now, 'poll')
            self.assertEqual(any(method == 'sendPoll' for method, _ in tg.messages), expected)

    def test_hourly_auto_never_sends_poll_outside_morning(self):
        for hour in (7, 10, 20):
            state, store, tg = fixture(), Store(), TG()
            state['sent']['report:2026-11-02'] = 42
            run(tg, store, state, datetime(2026, 11, 10, hour, tzinfo=TZ), 'auto')
            self.assertEqual(tg.messages, [])

    def test_hourly_morning_backup_and_retries_do_not_duplicate(self):
        state, store, tg = fixture(), Store(), TG()
        state['sent']['report:2026-11-02'] = 42
        for minute, mode in ((17, 'auto'), (20, 'poll'), (30, 'poll'), (40, 'poll')):
            run(tg, store, state, datetime(2026, 11, 10, 9, minute, tzinfo=TZ), mode)
        self.assertEqual([m for m, _ in tg.messages], ['sendPoll', 'sendMessage'])

    def test_recovery_requires_manual_event_and_exact_date(self):
        now = datetime(2026, 11, 10, 22, tzinfo=TZ)
        for event, day in [('schedule', '2026-11-10'), ('workflow_dispatch', ''),
                           ('workflow_dispatch', '2026-11-09')]:
            state, store, tg = fixture(), Store(), TG()
            with patch.dict('os.environ', GITHUB_EVENT_NAME=event, BOT_RECOVERY_DATE=day):
                with self.assertRaisesRegex(ServiceError, 'Manual recovery requires'):
                    run(tg, store, state, now, 'poll_now')
            self.assertEqual(tg.messages, [])

    def test_recovery_sends_only_one_dated_poll_no_report_or_quote(self):
        state, store, tg = fixture(), Store(), TG()
        now = datetime(2026, 11, 10, 22, tzinfo=TZ)
        with patch.dict('os.environ', GITHUB_EVENT_NAME='workflow_dispatch', BOT_RECOVERY_DATE='2026-11-10'):
            run(tg, store, state, now, 'poll_now')
            run(tg, store, state, now, 'poll_now')
        self.assertEqual([m for m, _ in tg.messages], ['sendPoll'])
        self.assertTrue(tg.messages[0][1]['question'].startswith('10.11.'))

    def test_winter_and_summer_use_nine_local(self):
        for month, utc_hour in ((1, 8), (7, 7)):
            local = datetime(2027, month, 12, utc_hour, tzinfo=timezone.utc).astimezone(TZ)
            self.assertEqual(local.hour, 9)
            state, store, tg = fixture(), Store(), TG()
            run(tg, store, state, local, 'poll')
            self.assertEqual(sum(method == 'sendPoll' for method, _ in tg.messages), 1)


if __name__ == '__main__':
    unittest.main()
