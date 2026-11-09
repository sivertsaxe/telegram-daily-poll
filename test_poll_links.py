import unittest
from datetime import date, datetime
from bot import poll_date_link, weekly_report, run, TZ
from test_bot import fixture, Store
from test_motivation import TG


class PollLinkTest(unittest.TestCase):
    def test_private_supergroup_url(self):
        self.assertEqual(poll_date_link({'chat_id': -1001234567890, 'message_id': 123}, '2026-11-02'),
                         '<a href="https://t.me/c/1234567890/123">02.11.</a>')

    def test_legacy_poll_uses_configured_chat(self):
        self.assertIn('https://t.me/c/1234567890/456',
                      poll_date_link({'message_id': 456}, '2026-11-02', -1001234567890))

    def test_no_guessed_links_for_historical_or_invalid_data(self):
        for poll in ({}, {'chat_id': -1001234567890}, {'chat_id': -1234, 'message_id': 42},
                     {'chat_id': -1001234567890, 'message_id': 0},
                     {'chat_id': -1001234567890, 'message_id': True}):
            self.assertEqual(poll_date_link(poll, '2026-11-02'), '02.11.')

    def test_weekly_links_correspond_to_missing_days_only(self):
        state = fixture()
        state['members']['2']['start'] = '2026-11-07'
        for i, poll in enumerate(state['polls'].values()):
            poll.update(message_id=100 + i, chat_id=-1001234567890)
        text = weekly_report(state, date(2026, 11, 2))
        self.assertIn('<a href="tg://user?id=2">Late</a>', text)
        self.assertIn('<a href="https://t.me/c/1234567890/105">07.11.</a>', text)
        self.assertIn('<a href="https://t.me/c/1234567890/106">08.11.</a>', text)
        self.assertNotIn('https://t.me/c/1234567890/100', text)

    def test_report_disables_previews_and_poll_records_chat(self):
        state, store, tg = fixture(), Store(), TG()
        tg.chat = -1001234567890
        run(tg, store, state, datetime(2026, 11, 9, 8, tzinfo=TZ), 'report')
        self.assertEqual(tg.messages[0][1]['link_preview_options'], {'is_disabled': True})
        run(tg, store, state, datetime(2026, 11, 9, 8, tzinfo=TZ), 'poll')
        self.assertEqual(state['polls']['new']['chat_id'], tg.chat)


if __name__ == '__main__':
    unittest.main()
