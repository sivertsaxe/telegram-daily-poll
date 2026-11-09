# Telegram challenge bot

One scheduled workflow collects non-anonymous votes hourly, sends a dated daily
125-push-up poll after 07:00 Europe/Berlin and reports the
previous Monday–Sunday after 08:00 Monday. Runs delayed past Monday catch up once.
GitHub schedules are best effort, so these are earliest times, not delivery guarantees.

The weekly message is an actionable reminder: one mention per person with all
missing dates, asking them to vote or pay the agreed contribution. It shows no
response percentages or performance statistics and never claims to verify payments. A negative answer counts as a response. It does not infer
whether training happened when there is no answer. Alternative workouts are
self-reported; the bot does not verify photos.

## Configuration

Repository Actions secrets: `TG_TOKEN`, `TG_CHAT_ID`, `STATE_KEY` (Fernet key).
`state.enc` contains only authenticated ciphertext. Never commit the key, plaintext
roster, vote exports, chat IDs or decrypted state. Do not upload plaintext artifacts.
The token supplied by GitHub is restricted to this repository's contents permission.
All runs use the same concurrency group and optimistic state writes.

The hourly encrypted-state commits also provide repository activity, preventing
normal 60-day inactivity of this public repository. They cannot guarantee GitHub
availability, prevent administrative disabling or overcome revoked credentials.
Workflow errors fail visibly; check Actions and your GitHub failure notifications.

Only this workflow may call getUpdates for this bot. An existing webhook stops
collection safely. The separate reminder.py repository retains the existing reminder schedule.
This workflow does not send daily reminders, avoiding duplicates.

## Reliability

Updates are saved before their offset is acknowledged. Vote changes replace the
previous vote; retractions remove it. A collection gap over 23 hours marks tracked
polls uncertain, because Telegram retains updates for at most 24 hours. Missing
polls, uncertain collection or mismatched voter totals suppress all missing-answer
mentions for that report. Historical imports are explicit snapshots from Telegram.

Send intent is saved before posting. A timeout may have sent the message already;
a `pending` marker stops retries. Inspect Telegram, then repair the encrypted
marker (set the actual message ID if delivered, or remove it only when confirmed
not delivered). Do not delete/reset state to fix a send failure. Back up STATE_KEY
securely before rotation; old encrypted commits remain in Git history.

Current state keeps polls for 90 days. Git history retains old ciphertext, so this
is not secure deletion of historical ciphertext. New members are eligible from
their join date, leaving ends eligibility. Initial roster is a manually verified
snapshot; admins should review eligibility if someone is an organizer or exempt.
Telegram text mentions use stable user IDs, including members without usernames.

## Manual use

Actions → Daily Telegram Poll → Run workflow → mode `collect` checks the
configuration and receives votes without posting. `auto` sends anything due;
`report` sends last week's report once; `poll` sends today's poll once after 07:00.
Repeated runs do not resend successful messages. Quotes are not enabled.

Run `python -m unittest -v` locally or in Actions. Never print raw Requests
exceptions: the request URL includes the bot token.
