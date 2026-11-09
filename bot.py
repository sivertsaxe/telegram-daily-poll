"""Small scheduled Telegram bot. Never log tokens, payloads or decrypted state."""
import base64
import copy
import html
import json
import os
import sys
from datetime import datetime, date, timedelta, timezone
from zoneinfo import ZoneInfo

import requests
from cryptography.fernet import Fernet

from motivation import QUOTE_DAYS, choose_quote, daily_target

TZ = ZoneInfo('Europe/Berlin')
OPTIONS = ['Ja 💪', 'Workout gemacht (Bild gesendet) 📸', 'Nein ❌']


class ServiceError(Exception):
    pass


class Telegram:
    def __init__(self):
        self.token = os.environ['TG_TOKEN']
        self.chat = int(os.environ['TG_CHAT_ID'])

    def call(self, method, **payload):
        try:
            response = requests.post(f'https://api.telegram.org/bot{self.token}/{method}',
                                     json=payload, timeout=40)
            body = response.json()
        except (requests.RequestException, ValueError):
            raise ServiceError(f'Telegram {method}: connection/response failure') from None
        if not response.ok or not body.get('ok'):
            raise ServiceError(f'Telegram {method}: API error {body.get("error_code", response.status_code)}')
        return body['result']


class Store:
    """Optimistic writes; one workflow concurrency group serializes all consumers."""
    def __init__(self):
        self.url = f'https://api.github.com/repos/{os.environ["GITHUB_REPOSITORY"]}/contents/state.enc'
        self.headers = {'Authorization': 'Bearer ' + os.environ['GH_TOKEN'],
                        'Accept': 'application/vnd.github+json'}
        self.cipher = Fernet(os.environ['STATE_KEY'].encode())
        self.sha = None

    def request(self, method, **kwargs):
        try:
            r = requests.request(method, self.url, headers=self.headers, timeout=30, **kwargs)
        except requests.RequestException:
            raise ServiceError('Encrypted state: connection failure') from None
        if not r.ok:
            raise ServiceError(f'Encrypted state: HTTP {r.status_code}')
        return r.json()

    def load(self):
        body = self.request('GET')  # Missing/corrupt state fails closed; never resets silently.
        self.sha = body['sha']
        try:
            state = json.loads(self.cipher.decrypt(base64.b64decode(body['content'])))
            assert state['version'] == 1
            return state
        except Exception:
            raise ServiceError('Cannot decrypt/validate state; check STATE_KEY') from None

    def save(self, state):
        encrypted = self.cipher.encrypt(json.dumps(state, ensure_ascii=False).encode())
        body = self.request('PUT', json={'message': 'Persist encrypted bot state [skip ci]',
                             'sha': self.sha, 'content': base64.b64encode(encrypted).decode()})
        self.sha = body['content']['sha']


def apply_update(state, update, chat):
    answer = update.get('poll_answer')
    if answer and answer.get('user'):
        poll = state['polls'].get(answer['poll_id'])
        if poll:
            uid = str(answer['user']['id'])
            values = answer['option_ids']
            if values:
                poll['votes'][uid] = values[0]
            else:
                poll['votes'].pop(uid, None)
    poll_update = update.get('poll')
    if poll_update and poll_update['id'] in state['polls']:
        state['polls'][poll_update['id']]['total'] = poll_update['total_voter_count']
    message = update.get('message', {})
    if message.get('chat', {}).get('id') == chat:
        # New members become eligible from their join date; leaving ends eligibility.
        day = datetime.fromtimestamp(message['date'], TZ).date().isoformat()
        for user in message.get('new_chat_members', []):
            if not user.get('is_bot'):
                uid = str(user['id'])
                state['members'][uid] = {'name': user['first_name'] + (' ' + user['last_name'] if user.get('last_name') else ''),
                                         'start': day, 'end': None}
        user = message.get('left_chat_member')
        if user and str(user['id']) in state['members']:
            state['members'][str(user['id'])]['end'] = day
    state['offset'] = max(state.get('offset', 0), update['update_id'] + 1)


def collect(tg, store, state, now):
    previous = state.get('collected_at')
    if previous and now.timestamp() - previous > 23 * 3600:
        # Telegram drops pending updates after 24h. Do not blame members for lost data.
        for poll in state['polls'].values():
            if not poll.get('historical'):
                poll['complete'] = False
    while True:
        updates = tg.call('getUpdates', offset=state.get('offset', 0), timeout=0,
                          limit=100, allowed_updates=['poll_answer', 'poll', 'message'])
        if not updates:
            break
        for update in updates:
            apply_update(state, update, tg.chat)
        store.save(state)  # Persist votes BEFORE acknowledging them in the next getUpdates.
    state['collected_at'] = now.timestamp()
    store.save(state)


def eligible(member, day):
    return member['start'] <= day and (not member.get('end') or day < member['end'])


def poll_date_link(poll, day, chat_id=None):
    label = date.fromisoformat(day).strftime('%d.%m.')
    chat = poll.get('chat_id', chat_id)
    message = poll.get('message_id')
    # Bot API supergroup IDs use the -100 prefix. Basic groups have no permalink.
    if (not isinstance(chat, int) or not str(chat).startswith('-100')
            or not isinstance(message, int) or isinstance(message, bool) or message <= 0):
        return label
    channel = str(chat)[4:]
    if not channel or int(channel) <= 0:
        return label
    return f'<a href="https://t.me/c/{channel}/{message}">{label}</a>'


def weekly_report(state, monday, chat_id=None):
    days = [(monday + timedelta(days=i)).isoformat() for i in range(7)]
    by_day = {p['day']: p for p in state['polls'].values() if p['day'] in days}
    uncertain = [d for d in days if d not in by_day or not by_day[d].get('complete')
                 or by_day[d].get('total') != len(by_day[d]['votes'])]
    title = f'📝 Fehlende Abstimmungen {monday:%d.%m.}–{monday + timedelta(days=6):%d.%m.%Y}'
    if uncertain:
        return title + '\n\nDie Datenerfassung ist unvollständig. Deshalb heute keine Tags wegen fehlender Antworten.\nBetroffene Tage: ' + ', '.join(date.fromisoformat(d).strftime('%d.%m.') for d in uncertain)
    missing = {}
    for uid, member in state['members'].items():
        for day in days:
            if not eligible(member, day):
                continue
            value = by_day[day]['votes'].get(uid)
            if value is None:
                missing.setdefault(uid, []).append(day)
    lines = [title, '', 'Für diese Tage fehlt noch eure Antwort:' if missing else 'Alle haben geantwortet – danke euch! 🙌']
    for uid, days_missing in sorted(missing.items(), key=lambda item: state['members'][item[0]]['name']):
        name = html.escape(state['members'][uid]['name'])
        lines.append(f'<a href="tg://user?id={int(uid)}">{name}</a>: ' + ', '.join(poll_date_link(by_day[d], d, chat_id) for d in days_missing))
    if missing:
        lines += ['', 'Bitte stimmt in den jeweiligen Umfragen ab oder bezahlt den vereinbarten Beitrag. Falls ihr bereits bezahlt habt, gebt bitte kurz Bescheid. 🙌', '', 'Diese Liste zeigt nur fehlende Abstimmungen. Zahlungen werden vom Bot nicht geprüft.']
    return '\n'.join(lines)


def send_once(tg, store, state, key, method, payload, on_success=None):
    if key in state['sent']:
        if state['sent'][key] == 'pending':
            raise ServiceError('An earlier send has an uncertain outcome; inspect Telegram before resolving encrypted state')
        return
    # A timeout must not silently send duplicate polls/reports on retry.
    state['sent'][key] = 'pending'
    store.save(state)
    result = tg.call(method, chat_id=tg.chat, **payload)
    state['sent'][key] = result['message_id']
    if on_success:
        on_success(result)
    store.save(state)


def run(tg, store, state, now, mode='auto'):
    if tg.call('getWebhookInfo').get('url'):
        raise ServiceError('A webhook is active; refusing to compete with another update consumer')
    collect(tg, store, state, now)
    today = now.date().isoformat()
    if mode == 'collect':
        return
    if mode == 'report' or (mode == 'auto' and (now.weekday() > 0 or now.hour >= 8)):
        monday = now.date() - timedelta(days=now.weekday() + 7)
        send_once(tg, store, state, 'report:' + monday.isoformat(), 'sendMessage',
                  {'text': weekly_report(state, monday, tg.chat), 'parse_mode': 'HTML',
                   'link_preview_options': {'is_disabled': True}})
    if mode in ('auto', 'poll') and now.hour >= 7:
        def register(result):
            poll = result['poll']
            state['polls'][poll['id']] = {'day': today, 'message_id': result['message_id'],
                                         'chat_id': result.get('chat', {}).get('id', tg.chat),
                                         'votes': {}, 'total': 0, 'complete': True}
        send_once(tg, store, state, 'poll:' + today, 'sendPoll',
                  {'question': f'{now:%d.%m.} · Hast du heute {daily_target(now.date())} Liegestütze gemacht?',
                   'options': [{'text': option} for option in OPTIONS], 'is_anonymous': False, 'allows_multiple_answers': False}, register)
    if (mode in ('auto', 'poll') and now.hour >= 7
            and now.weekday() in QUOTE_DAYS
            and isinstance(state['sent'].get('poll:' + today), int)
            and 'quote:' + today not in state['sent']):
        text = choose_quote(state, now.date())
        store.save(state)
        send_once(tg, store, state, 'quote:' + today, 'sendMessage', {'text': text})
    # Keep enough history for corrections and week comparisons; limit personal-data retention.
    cutoff = (now.date() - timedelta(days=90)).isoformat()
    state['polls'] = {k: p for k, p in state['polls'].items() if p['day'] >= cutoff}
    store.save(state)


if __name__ == '__main__':
    try:
        run(Telegram(), store := Store(), store.load(), datetime.now(TZ), os.environ.get('BOT_MODE', 'auto'))
    except Exception as exc:
        # Requests exceptions contain the bot credential URL: never print raw exceptions.
        print(str(exc) if isinstance(exc, ServiceError) else 'Bot failed; check configuration and encrypted state', file=sys.stderr)
        sys.exit(1)
