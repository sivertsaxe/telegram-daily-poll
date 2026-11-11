# Telegram challenge on Cloudflare

Cloudflare Cron runs every minute. One SQLite-backed Durable Object serializes updates and sends; `Europe/Berlin` determines local times including DST:

- Daily poll: 09:00, retried within that hour with durable deduplication.
- Daily reminder: 21:00, only when today's poll is recorded.
- Monday missing-answer report: 08:00 for previous Monday–Sunday, clickable dates and no footer.
- Approved motivation lines: Tuesday and Friday immediately after the poll.

A new object starts **inactive**. Deploying code does not enable Telegram collection or messages. Scheduled invocations do nothing until authenticated activation.

## State and secrets

`STATE_KEY`, `TG_TOKEN`, `TG_CHAT_ID` are Cloudflare secrets. State is authenticated AES-GCM ciphertext in Durable Object storage. Migration imports the existing Fernet `state.enc`, preserving answers, collection offset, member eligibility and all send markers. No participant data belongs in source files. The synthetic encrypted test fixture contains only dummy data.

Both a single object and a serial operation queue prevent overlapping sends. A pending send is persisted before contacting Telegram; ambiguous delivery requires manual inspection instead of risking a duplicate. Updates are saved before the next Telegram offset acknowledgement. Collection gaps over 23 hours mark affected polls incomplete; reports suppress tags if records are incomplete.

## Deployment and cutover

Use the repository's manual **Deploy Cloudflare bot** workflow. `CLOUDFLARE_API_TOKEN` is a GitHub Actions secret, scoped to the selected account's Workers Scripts, Account Settings Read, and Workers Observability. It is needed for deploys, not continued operation.

1. `stage`: deploy code and bot secrets. Initially leave `worker_url` empty if the Workers subdomain is not known. Repeat with the HTTPS origin shown by deployment to import `state.enc` and run a message-free Telegram preflight.
2. Confirm `/health` reports `ready: true, active: false` and preflight succeeds.
3. Retire schedules in both old repositories. Wait for every old queued/in-progress run to finish. Do not run the Python consumer after activation.
4. `activate`: uses the latest main-branch state; check `previous_scheduler_stopped`. The shared GitHub concurrency group prevents collision with any remaining old poll job. It imports the final snapshot, repeats preflight and activates.
5. Verify a scheduled invocation and health `active: true`, `status: ok`, recent `lastTick`. Check the next real 09:00/21:00 deliveries in Telegram; do not generate extra test messages in the group.

`update` deploys changes without replacing live state. Never use `stage` against an active worker: import is rejected. `deactivate` stops collection and sends. The authenticated `/admin/export` endpoint returns encrypted current state for backup/rollback; it never returns plaintext. To restore Python, export and convert AES-GCM back to Fernet offline, preserve all markers, and stop Cloudflare before enabling the old scheduler.

`/health` contains only readiness, activation and delivery status. `/tick` is not public. Admin endpoints require a bearer token derived from `STATE_KEY` with HMAC; tokens must stay in headers and never in URLs or logs.

## Checks

Run `npm ci`, `npm test`, and `npm run check`. Tests cover local time/DST, deduplication, ambiguous sends, collection acknowledgements, historical migration, encryption, report contents, quote order and December's confirmed 130 target. The minutely trigger avoids GitHub runner queues; it is not a contractual exact-time delivery guarantee. Cloudflare trigger changes may take several minutes to propagate.
