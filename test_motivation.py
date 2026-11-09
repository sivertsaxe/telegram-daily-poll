import unittest
from datetime import date, datetime, timedelta
from unittest.mock import patch
from motivation import QUOTES, choose_quote, daily_target
from bot import TZ, run
from test_bot import Store, fixture


class TG:
    chat = -1
    def __init__(self):
        self.messages = []
    def call(self, method, **payload):
        if method == 'getWebhookInfo':
            return {}
        if method == 'getUpdates':
            return []
        self.messages.append((method, payload))
        return {'message_id': len(self.messages), 'poll': {'id': 'new'}}


class MotivationTest(unittest.TestCase):
    def test_confirmed_december_increase(self):
        self.assertEqual(daily_target(date(2026, 11, 30)), 125)
        self.assertEqual(daily_target(date(2026, 12, 1)), 130)
        self.assertEqual(daily_target(date(2027, 1, 1)), 130)
        for day, target in [(date(2026, 11, 30), 125), (date(2026, 12, 1), 130)]:
            state = {'quote_choices': {day.isoformat(): 5}}
            self.assertIn(str(target), choose_quote(state, day))

    def test_shuffled_bag_and_stable_choice(self):
        state = {}
        values = [choose_quote(state, date(2026, 11, 1) + timedelta(days=i)) for i in range(20)]
        self.assertEqual(len(set(values)), 20)
        self.assertEqual(len(QUOTES), 20)
        self.assertEqual(choose_quote(state, date(2026, 11, 1)), values[0])
        next_value = choose_quote(state, date(2026, 11, 21))
        self.assertNotEqual(next_value, values[-1])

    def test_only_tuesday_friday_after_poll_without_duplicates(self):
        for offset in range(7):
            state, store, tg = fixture(), Store(), TG()
            now = datetime(2026, 12, 7 + offset, 7, tzinfo=TZ)
            run(tg, store, state, now, 'poll')
            run(tg, store, state, now, 'poll')
            self.assertEqual(tg.messages[0][0], 'sendPoll')
            self.assertIn('130 Liegestütze', tg.messages[0][1]['question'])
            self.assertEqual(len(tg.messages), 2 if now.weekday() in (1, 4) else 1)
            if len(tg.messages) == 2:
                self.assertEqual(tg.messages[1][0], 'sendMessage')
                self.assertIn('quote:' + now.date().isoformat(), state['sent'])

    def test_collect_and_report_do_not_send_quotes(self):
        for mode in ('collect', 'report'):
            state, store, tg = fixture(), Store(), TG()
            run(tg, store, state, datetime(2026, 12, 8, 8, tzinfo=TZ), mode)
            self.assertNotIn('quote_choices', state)
            self.assertLessEqual(len(tg.messages), 1)


if __name__ == '__main__':
    unittest.main()
