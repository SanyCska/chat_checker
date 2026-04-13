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

## Docker

First run must be done locally to create the Telethon session (interactive phone + code login):

```bash
python bot.py
# after login succeeds, Ctrl+C
```

Then copy the session to the server and run with Docker:

```bash
docker build -t chat-checker .
docker run --env-file .env -v ./sessions:/app/sessions chat-checker
```

## Auto Deploy (GitHub Actions)

Every push to `main` builds a Docker image, pushes it to GitHub Container Registry, and deploys to your server via SSH.

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

> **Important**: You need to create the Telethon session locally first and copy `user_session.session` to `~/chat-checker/sessions/` on the server before the first deploy.

### Server prerequisites

The server needs Docker and Docker Compose installed. The deploy workflow will:
1. Build the image and push to `ghcr.io`
2. SCP `docker-compose.yml` to `~/chat-checker/` on your server
3. SSH in, pull the new image, and restart the container

## Bot Commands

| Command   | Description                        |
|-----------|------------------------------------|
| `/start`  | Shows your user ID and bot info    |
| `/status` | Lists currently active alerts      |
| `/stop`   | Stops all active alert loops       |
