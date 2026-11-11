# Telegram challenge bot

Production runs on Cloudflare Workers with one SQLite-backed Durable Object. GitHub stores source and a manual deploy workflow; both former GitHub schedules are retired and their legacy workflows send nothing.

- Daily poll: 09:00 Europe/Berlin.
- Daily reminder: 21:00 Europe/Berlin.
- Missing-answer report: Monday after 08:00 for the previous Monday–Sunday.
- Approved motivation lines: Tuesday and Friday after the poll, shuffled without repetition until all 20 have been used.
- Confirmed target: 125 in November 2026, 130 from 1 December 2026; no further increases assumed.

The minutely Cloudflare trigger evaluates local time, including daylight saving time. Durable send markers prevent repeated invocations from sending duplicate messages. Scheduled delivery remains best effort; this removes the dependency on GitHub runner queues.

The Monday message is an actionable reminder: one mention per person and clickable missing dates. It ends after the date lists. Any poll answer, including a negative answer, counts as a response. No response percentages, payment checks or claims to verify training/photos are included. Incomplete collection or mismatched vote totals suppress missing-answer tags.

## Operations

See [Cloudflare deployment and cutover instructions](cloudflare/README.md). The manual **Deploy Cloudflare bot** workflow supports `stage`, `activate`, `update` and `deactivate`. Use `update` for normal code changes; it preserves live state. Do not run the legacy Python collector while Cloudflare is active.

The live encrypted state is in the Durable Object. Root `state.enc` is the final GitHub-era migration snapshot, not a current backup. Migration preserves answers, member eligibility, Telegram offsets, poll message IDs, quote choices and all send markers. The authenticated export endpoint provides current encrypted backups.

Cloudflare secrets: `TG_TOKEN`, `TG_CHAT_ID`, `STATE_KEY`. GitHub Actions retains the same secrets for deployment plus `CLOUDFLARE_API_TOKEN`. The deploy token is needed only for deployments; its expiration does not stop the running bot. Never commit tokens, keys, plaintext participant lists or decrypted answers.

Public status: https://telegram-challenge-bot.sivertsaxe-2e9.workers.dev/health. It exposes only readiness, activation, last tick and sanitized status. Check Cloudflare Workers observability for failed scheduled invocations. An ambiguous Telegram send persists a pending marker and stops retries until an operator checks whether the message arrived. Never reset state to resolve delivery problems.

Updates are saved before Telegram acknowledges their offset. Gaps over 23 hours mark tracked polls incomplete. Poll history is kept for 90 days; historical Git ciphertext remains in Git history. New members are eligible from their join date; leaving ends eligibility. Mentions use Telegram user IDs. Poll links work only for members and are not invented when old message IDs are unavailable.

## Checks

In `cloudflare/`: `npm ci`, `npm test`, `npm run check`. The retained Python implementation and its tests document the former system; they are not scheduled in production.
