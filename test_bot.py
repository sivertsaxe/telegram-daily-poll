import copy
import unittest
from datetime import date, datetime, timedelta
from unittest.mock import patch
from cryptography.fernet import Fernet, InvalidToken
from bot import apply_update, weekly_report, collect, send_once, ServiceError, TZ, run


def fixture():
    state = {'version': 1, 'offset': 0, 'members': {'1': {'name': 'A & B', 'start': '2026-11-02', 'end': None},
             '2': {'name': 'Late', 'start': '2026-11-08', 'end': None}}, 'polls': {}, 'sent': {}}
    for i in range(7):
        day = (date(2026, 11, 2) + timedelta(days=i)).isoformat()
        state['polls'][str(i)] = {'day': day, 'votes': {'1': 2}, 'total': 1, 'complete': True}
    return state


class Store:
    def __init__(self):
        self.saves = []
    def save(self, state):
        self.saves.append(copy.deepcopy(state))


class BotTest(unittest.TestCase):
    def test_no_is_answer_and_join_date_limits_missing(self):
        text = weekly_report(fixture(), date(2026, 11, 2))
        self.assertNotIn('%', text)
        self.assertNotIn('Bitte stimmt', text)
        self.assertNotIn('Zahlungen', text)
        self.assertIn('id=2', text)
        self.assertNotIn('id=1', text)
        self.assertIn('08.11.', text)

    def test_changes_and_retraction(self):
        s = fixture()
        for value in ([0], [1], []):
            apply_update(s, {'update_id': 5, 'poll_answer': {'poll_id': '0', 'user': {'id': 1}, 'option_ids': value}}, -1)
        self.assertEqual(s['polls']['0']['votes'], {})
        self.assertEqual(s['offset'], 6)

    def test_incomplete_days_or_total_mismatch_suppress_tags(self):
        for mutate in (lambda s: s['polls'].pop('0'),
                       lambda s: s['polls']['0'].update(complete=False),
                       lambda s: s['polls']['0'].update(total=2)):
            s = fixture()
            mutate(s)
            text = weekly_report(s, date(2026, 11, 2))
            self.assertIn('unvollständig', text)
            self.assertNotIn('tg://', text)

    def test_collection_persists_before_acknowledgement(self):
        s, store = fixture(), Store()
        class TG:
            chat = -1
            calls = 0
            def call(self, method, **payload):
                self.calls += 1
                if self.calls == 1:
                    return [{'update_id': 9, 'poll_answer': {'poll_id': '0', 'user': {'id': 1}, 'option_ids': [1]}}]
                assert store.saves[-1]['offset'] == payload['offset'] == 10
                return []
        collect(TG(), store, s, datetime(2026, 11, 9, 8, tzinfo=TZ))
        self.assertEqual(s['polls']['0']['votes']['1'], 1)

    def test_uncertain_send_never_retries_automatically(self):
        s, store = fixture(), Store()
        class TG:
            chat = -1
            calls = 0
            def call(self, *args, **kwargs):
                self.calls += 1
                raise ServiceError('timeout')
        tg = TG()
        for _ in range(2):
            with self.assertRaises(ServiceError):
                send_once(tg, store, s, 'test', 'sendMessage', {'text': 'test'})
        self.assertEqual(tg.calls, 1)
        self.assertEqual(s['sent']['test'], 'pending')

    def test_gap_marks_data_uncertain(self):
        s, store = fixture(), Store()
        s['collected_at'] = 1
        class TG:
            chat = -1
            def call(self, *args, **kwargs):
                return []
        collect(TG(), store, s, datetime(2026, 11, 9, 8, tzinfo=TZ))
        self.assertFalse(s['polls']['0']['complete'])

    def test_report_mode_sends_only_one_reminder_across_retries(self):
        s, store = fixture(), Store()
        class TG:
            chat = -1
            sent = []
            def call(self, method, **payload):
                if method == 'getWebhookInfo':
                    return {}
                if method == 'getUpdates':
                    return []
                self.sent.append((method, payload))
                return {'message_id': 42}
        tg = TG()
        now = datetime(2026, 11, 9, 8, tzinfo=TZ)
        run(tg, store, s, now, 'report')
        run(tg, store, s, now, 'report')
        self.assertEqual(len(tg.sent), 1)
        self.assertEqual(tg.sent[0][0], 'sendMessage')
        self.assertNotIn('%', tg.sent[0][1]['text'])

    def test_poll_uses_local_date_and_is_sent_once(self):
        for day in ((2026, 3, 29), (2026, 10, 25)):
            s, store = fixture(), Store()
            class TG:
                chat = -1
                calls = 0
                def call(self, method, **payload):
                    if method == 'getWebhookInfo':
                        return {}
                    if method == 'getUpdates':
                        return []
                    self.calls += 1
                    self.payload = payload
                    return {'message_id': 5, 'poll': {'id': 'new'}}
            tg = TG()
            now = datetime(*day, 7, tzinfo=TZ)
            run(tg, store, s, now, 'poll')
            run(tg, store, s, now, 'poll')
            self.assertEqual(tg.calls, 1)
            self.assertEqual(s['polls']['new']['day'], now.date().isoformat())
            self.assertFalse(tg.payload['is_anonymous'])

    def test_cipher_roundtrip_and_wrong_key(self):
        key = Fernet.generate_key()
        encrypted = Fernet(key).encrypt(b'private')
        self.assertEqual(Fernet(key).decrypt(encrypted), b'private')
        with self.assertRaises(InvalidToken):
            Fernet(Fernet.generate_key()).decrypt(encrypted)


if __name__ == '__main__':
    unittest.main()
