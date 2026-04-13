# Telegram Chat Checker Bot

Monitors a Telegram supergroup topic for messages mentioning **Италия (Italy)** or **Германия (Germany)** and sends you repeated alerts with booking links until you dismiss them.

Uses a **userbot** (your own Telegram account via Telethon) to read messages from groups where you're a member — no need to add a bot to the group.

## Setup

1. **Get API credentials** at [my.telegram.org](https://my.telegram.org) → API development tools → create an app. Copy `API_ID` and `API_HASH`.

2. **Create a bot** via [@BotFather](https://t.me/BotFather) and get the token. The bot is only used to send you alerts with inline buttons.

3. **Get your user ID** — message [@userinfobot](https://t.me/userinfobot) in Telegram.

4. **Start a chat with your bot** — open the bot in Telegram and press `/start`. Otherwise the bot won't be able to message you.

5. **Configure environment**:
   ```bash
   cp .env.example .env
   # Edit .env with your values
   ```

6. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

7. **Run** (first run will ask for your phone number and auth code):
   ```bash
   python bot.py
   ```

## How It Works

- The **userbot** (your account) listens for new messages in the configured chat/topic via Telethon.
- When a message contains "Италия"/"Italy" or "Германия"/"Germany" (any word form, case-insensitive), the **bot** starts sending you alerts **every 15 seconds**.
- Each alert includes a link to the appointment booking site and a **Stop** button.
- Use `/stop` in your DM with the bot to stop all alerts, or press the inline button on any alert message.

## Docker (local)

First run must be done locally to create the Telethon session (interactive phone + code login):

```bash
python bot.py
# after login succeeds, Ctrl+C
```

Then run with Docker locally:

```bash
docker build -t chat-checker .
docker run --env-file .env -v ./sessions:/app/sessions chat-checker
```

## Auto Deploy (GitHub Actions)

Every push to `main` (or manual trigger via **Actions → Run workflow**) builds a Docker image, pushes it to GHCR, and deploys to your server via SSH.

The workflow automatically:
1. Builds the image and pushes to `ghcr.io`
2. SSHs into your server, clones/updates the repo at `~/chat-checker/`
3. Writes a `.env` file on the server from GitHub secrets
4. Creates `~/chat-checker/sessions/` directory
5. Pulls the new image and (re)starts the container

### GitHub Secrets to configure

Go to repo **Settings → Secrets and variables → Actions** and add:

| Secret           | Description                                    |
|------------------|------------------------------------------------|
| `API_ID`         | Telegram API ID from my.telegram.org           |
| `API_HASH`       | Telegram API hash from my.telegram.org         |
| `BOT_TOKEN`      | Telegram bot token from @BotFather             |
| `NOTIFY_USER_ID` | Your Telegram user ID                          |
| `PHONE_NUMBER`   | Phone number with country code (e.g. `+79...`) |
| `CHAT_ID`        | Supergroup chat ID (e.g. `-1003899039929`)     |
| `TOPIC_ID`       | Topic/thread ID (e.g. `2`), `0` = all topics  |
| `SERVER_HOST`    | Your server IP or hostname                     |
| `SERVER_USER`    | SSH username on the server                     |
| `SERVER_SSH_KEY` | Private SSH key for authentication             |

### Server prerequisites

- Docker and Docker Compose installed.
- Copy `user_session.session` (created during local first run) to `~/chat-checker/sessions/` on the server before the first deploy.

### Manual commands on the server

After deploy, you can manage the container directly:

```bash
cd ~/chat-checker
docker compose ps       # check status
docker compose logs -f  # watch logs
docker compose restart  # restart
docker compose down     # stop
```

The `.env` file is written by the deploy workflow, so `docker compose` commands work without extra setup.

## Bot Commands

| Command   | Description                        |
|-----------|------------------------------------|
| `/start`  | Shows your user ID and bot info    |
| `/status` | Lists currently active alerts      |
| `/stop`   | Stops all active alert loops       |
