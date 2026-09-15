# GpSirEra Referral Joining Giveaway Bot

## ⚠️ Important: file structure

Keep `index.py` INSIDE the `api/` folder — `api/index.py`, not at the repo
root. Last time a file was uploaded to GitHub at the wrong path
(root instead of `api/`), the deployed bot returned 404 everywhere. Upload
this exact folder structure and it will work.

```
your-repo/
├── api/
│   └── index.py
├── requirements.txt
└── vercel.json
```

## Deploy

1. Create a NEW bot with @BotFather, grab the token.
2. Push this exact folder structure to a new GitHub repo.
3. Import it on Vercel → new project.
4. Environment Variables:

| Key | Value |
|---|---|
| `BOT_TOKEN` | your new bot's token |
| `DEVELOPER` | `@GpsirEra` |
| `ADMIN_USERS` | your Telegram ID `8932695749` is already built in as a default admin; add more comma-separated IDs here if needed |
| `UPSTASH_REDIS_REST_URL` | can reuse the SAME Upstash database as your file vault bot, or make a new one — either works, since keys are namespaced (`giveaways`, `participants:*`, etc.) and won't collide with the file bot's `files:*`/`batches:*` keys |
| `UPSTASH_REDIS_REST_TOKEN` | matching token for whichever database you pick |

5. Deploy, then check `https://<your-app>.vercel.app/api/index` shows
   `{"status": "Referral giveaway bot is alive", ...}` before setting the
   webhook.
6. Set the webhook (include `chat_join_request` so request-based channels
   work correctly, same as your other bot):

```bash
curl -X POST "https://api.telegram.org/bot<TOKEN>/setWebhook" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://<your-app>.vercel.app/api/index", "allowed_updates": ["message", "callback_query", "chat_join_request"]}'
```

7. **Add the bot as admin** in all 3 required channels (same 3 as your
   file vault bot) — the force-join gate won't work otherwise.

## How it works

- `/start` — welcome banner + giveaway menu
- `/giveaways` — browse & join active giveaways
- `/mystats` — your progress across all giveaways you've joined
- `/newgiveaway` (admin only) — step-by-step wizard: title → description →
  required referral points → optional extra required channel(s) for that
  specific giveaway
- `/giveaways` also shows admin management buttons: Leaderboard, Pick
  Winner, End Giveaway, Delete Giveaway

## Referral rules (built in, can't be bypassed by users)

- A referral only counts if the referred person is **brand new to the
  bot** — someone who already used the bot before (even for a different
  giveaway) clicking a friend's link does NOT award a point.
- The referred person must pass the required-channel join gate (bot-wide
  channels + any extra ones set for that specific giveaway) before the
  point is awarded.
- Self-referral (clicking your own link) never counts.
- When someone hits the required points, every admin gets pinged
  immediately with a "Pick Winner" shortcut — you make the final call,
  the bot never auto-declares a winner.
