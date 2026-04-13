import re
import logging
import os
import asyncio

from dotenv import load_dotenv
from telethon import TelegramClient, events, Button, utils

load_dotenv()

API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
NOTIFY_USER_ID = int(os.getenv("NOTIFY_USER_ID", "0"))
PHONE_NUMBER = os.getenv("PHONE_NUMBER", "")
CHAT_ID = int(os.getenv("CHAT_ID", "0"))
TOPIC_ID = int(os.getenv("TOPIC_ID", "0"))
# How many recent chat messages to scan on startup to print a topic sample (optional).
STARTUP_HISTORY_SCAN = int(os.getenv("STARTUP_HISTORY_SCAN", "200"))
STARTUP_TOPIC_PREVIEW = int(os.getenv("STARTUP_TOPIC_PREVIEW", "8"))

ALERT_INTERVAL = 15  # seconds

COUNTRY_CONFIG = {
    "italy": {
        "patterns": [
            re.compile(r"итал", re.IGNORECASE),
            re.compile(r"italy", re.IGNORECASE),
            re.compile(r"italian", re.IGNORECASE),
        ],
        "label": "🇮🇹 Италия / Italy",
        "link": "https://prenotami.esteri.it/Home?ReturnUrl=%2fServices",
    },
    "germany": {
        "patterns": [
            re.compile(r"герман", re.IGNORECASE),
            re.compile(r"germany", re.IGNORECASE),
            re.compile(r"german", re.IGNORECASE),
        ],
        "label": "🇩🇪 Германия / Germany",
        "link": "https://rs-appointment.visametric.com/en",
    },
}

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

SESSION_DIR = os.getenv("SESSION_DIR", ".")

user_client = TelegramClient(os.path.join(SESSION_DIR, "user_session"), API_ID, API_HASH)
bot_client = TelegramClient(os.path.join(SESSION_DIR, "bot_session"), API_ID, API_HASH)

alert_tasks: dict[str, asyncio.Task] = {}


def detect_countries(text: str) -> list[str]:
    found = []
    for key, cfg in COUNTRY_CONFIG.items():
        if any(p.search(text) for p in cfg["patterns"]):
            found.append(key)
    return found


def get_topic_id(message) -> int | None:
    """Return the forum topic / thread id for this message, if any.

    Telegram sets ``reply_to_top_id`` on messages inside forum topics. Do not
    require ``forum_topic`` — many clients set only ``reply_to_top_id``.
    """
    reply_to = message.reply_to
    if not reply_to:
        return None
    top_id = getattr(reply_to, "reply_to_top_id", None)
    if top_id is not None:
        return top_id
    if getattr(reply_to, "forum_topic", False):
        return reply_to.reply_to_top_id or reply_to.reply_to_msg_id
    return None


def _message_preview(message, max_len: int = 120) -> str:
    bits: list[str] = []
    if getattr(message, "photo", None):
        bits.append("[photo]")
    elif getattr(message, "document", None):
        bits.append("[document]")
    raw = (message.raw_text or "").strip()
    if raw:
        one = raw.replace("\n", " ")
        if len(one) > max_len:
            one = one[: max_len - 3] + "..."
        bits.append(one)
    elif not bits:
        bits.append("[no text]")
    return " ".join(bits)


async def ensure_chat_entity(client: TelegramClient) -> None:
    """Resolve numeric CHAT_ID by warming Telethon's entity cache."""
    try:
        await client.get_input_entity(CHAT_ID)
        return
    except ValueError:
        logger.info(
            "CHAT_ID=%s not in session cache; scanning all dialogs (including archived)...",
            CHAT_ID,
        )

    # Load regular + archived folders
    for folder in (0, 1):
        async for dialog in client.iter_dialogs(folder=folder):
            if dialog.entity and getattr(dialog.entity, "id", None):
                peer_id = utils.get_peer_id(dialog.entity)
                if peer_id == CHAT_ID:
                    logger.info(
                        "Found chat in folder=%s: %r (peer_id=%s)",
                        folder,
                        getattr(dialog.entity, "title", "?"),
                        peer_id,
                    )
                    return

    # Last resort: try the raw Telegram API with just channel_id
    channel_id = abs(CHAT_ID)
    if str(abs(CHAT_ID)).startswith("100"):
        channel_id = abs(CHAT_ID) - 10**( len(str(abs(CHAT_ID))) - 1 )
    # Telethon stores -100XXXX; strip the -100 prefix to get the actual channel id
    if abs(CHAT_ID) > 10**12:
        channel_id = abs(CHAT_ID) % (10**12)

    logger.info(
        "Chat not found in dialogs; trying raw API with channel_id=%s...",
        channel_id,
    )
    try:
        from telethon.tl import functions
        from telethon.tl.types import InputChannel

        result = await client(
            functions.channels.GetChannelsRequest(
                id=[InputChannel(channel_id=channel_id, access_hash=0)]
            )
        )
        if result.chats:
            logger.info("Resolved via API: %r", result.chats[0].title)
            return
    except Exception:
        logger.exception("Raw API channel lookup also failed")

    raise RuntimeError(
        f"Cannot resolve CHAT_ID={CHAT_ID}. Confirm the id is correct and "
        "that this account is a member of the chat."
    )


async def log_startup_topic_sample(client: TelegramClient) -> None:
    """Log chat title and a few recent messages so you can confirm topic access."""
    try:
        entity = await client.get_entity(CHAT_ID)
    except Exception:
        logger.exception("Could not resolve CHAT_ID=%s after ensure_chat_entity()", CHAT_ID)
        return

    title = getattr(entity, "title", None) or getattr(entity, "username", None) or str(
        CHAT_ID
    )
    logger.info(
        "User client can read chat: title=%r CHAT_ID=%s monitoring %s",
        title,
        CHAT_ID,
        f"topic_id={TOPIC_ID}" if TOPIC_ID else "all topics (TOPIC_ID=0)",
    )

    if TOPIC_ID == 0:
        logger.info(
            "Recent messages (any topic), up to %s:",
            STARTUP_TOPIC_PREVIEW,
        )
        msgs = await client.get_messages(CHAT_ID, limit=STARTUP_TOPIC_PREVIEW)
        for m in reversed(msgs):
            logger.info(
                "  [history] msg_id=%s topic_id=%s %s",
                m.id,
                get_topic_id(m),
                _message_preview(m),
            )
        return

    logger.info(
        "Scanning last %s chat messages for topic_id=%s (showing up to %s matches)...",
        STARTUP_HISTORY_SCAN,
        TOPIC_ID,
        STARTUP_TOPIC_PREVIEW,
    )
    matched = []
    async for m in client.iter_messages(CHAT_ID, limit=STARTUP_HISTORY_SCAN):
        if get_topic_id(m) != TOPIC_ID:
            continue
        matched.append(m)
        if len(matched) >= STARTUP_TOPIC_PREVIEW:
            break

    if matched:
        logger.info(
            "Found %s message(s) in topic_id=%s (newest first):",
            len(matched),
            TOPIC_ID,
        )
        for m in matched:
            logger.info(
                "  [topic %s] msg_id=%s sender_id=%s %s",
                TOPIC_ID,
                m.id,
                m.sender_id,
                _message_preview(m),
            )
    else:
        logger.warning(
            "No messages with topic_id=%s in the last %s chat messages — "
            "topic may be quiet or TOPIC_ID may not match this forum.",
            TOPIC_ID,
            STARTUP_HISTORY_SCAN,
        )
        logger.info("Last 5 messages in chat (any topic), for comparison:")
        async for m in client.iter_messages(CHAT_ID, limit=5):
            logger.info(
                "  [any topic] msg_id=%s topic_id=%s %s",
                m.id,
                get_topic_id(m),
                _message_preview(m),
            )


def _alert_key(country: str) -> str:
    return f"alert_{country}"


async def _alert_loop(country_key: str, original_text: str) -> None:
    cfg = COUNTRY_CONFIG[country_key]
    while True:
        buttons = [
            [Button.url(f"🔗 Записаться — {cfg['label']}", cfg["link"])],
            [Button.inline("🛑 Остановить / Stop", f"stop_{country_key}".encode())],
        ]
        text = f"⚡ <b>Есть слоты: {cfg['label']}</b>\n\nНайдено совпадение в чате!\n"
        if original_text:
            preview = original_text[:300]
            text += f"<blockquote>{preview}</blockquote>\n\n"
        text += f'<a href="{cfg["link"]}">👉 Перейти на сайт записи</a>'

        try:
            await bot_client.send_message(
                NOTIFY_USER_ID,
                text,
                buttons=buttons,
                parse_mode="html",
                link_preview=False,
            )
        except Exception:
            logger.exception("Failed to send alert for %s", country_key)

        await asyncio.sleep(ALERT_INTERVAL)


async def start_alert(country: str, original_text: str) -> None:
    key = _alert_key(country)
    if key in alert_tasks and not alert_tasks[key].done():
        logger.info("Alert %s already running", key)
        return
    logger.info("Starting alert %s", key)
    alert_tasks[key] = asyncio.create_task(_alert_loop(country, original_text))


async def stop_alert(country: str) -> bool:
    key = _alert_key(country)
    task = alert_tasks.pop(key, None)
    if task and not task.done():
        task.cancel()
        logger.info("Stopped alert %s", key)
        return True
    return False


# --------------- user client: monitor the group ---------------


@user_client.on(events.NewMessage(chats=CHAT_ID))
async def on_group_message(event):
    msg = event.message
    text = (msg.raw_text or "").strip()
    if not text:
        return

    topic_id = get_topic_id(msg)
    logger.info(
        "NewMessage in chat: chat_id=%s topic_id=%s msg_id=%s sender_id=%s text=%s",
        event.chat_id,
        topic_id,
        msg.id,
        msg.sender_id,
        text[:80],
    )

    if TOPIC_ID and topic_id != TOPIC_ID:
        logger.info(
            "Skipping (topic filter): want topic_id=%s, message has topic_id=%s",
            TOPIC_ID,
            topic_id,
        )
        return

    countries = detect_countries(text)
    if not countries:
        return

    logger.info("Matched countries: %s", countries)
    for c in countries:
        await start_alert(c, text)


# --------------- bot client: alerts & commands ---------------


@bot_client.on(events.CallbackQuery(pattern=rb"stop_(.+)"))
async def on_stop_button(event):
    country = event.pattern_match.group(1).decode()
    stopped = await stop_alert(country)
    cfg = COUNTRY_CONFIG.get(country)
    label = cfg["label"] if cfg else country

    if stopped:
        await event.edit(
            f"✅ Уведомления для {label} остановлены.\n\n"
            f"Notifications for {label} stopped."
        )
    else:
        await event.edit(
            f"ℹ️ Уведомления для {label} уже остановлены.\n\n"
            f"Alerts for {label} were already stopped."
        )


@bot_client.on(events.NewMessage(pattern=r"^/start", func=lambda e: e.is_private))
async def on_cmd_start(event):
    await event.reply(
        f"Привет! Ваш user ID: <code>{event.sender_id}</code>\n\n"
        f"Бот следит за чатом и уведомит вас, когда появятся слоты для "
        f"Италии или Германии.\n\n"
        f"/status — активные уведомления\n"
        f"/stop — остановить все уведомления",
        parse_mode="html",
    )


@bot_client.on(events.NewMessage(pattern=r"^/status", func=lambda e: e.is_private))
async def on_cmd_status(event):
    active = []
    for country, cfg in COUNTRY_CONFIG.items():
        key = _alert_key(country)
        if key in alert_tasks and not alert_tasks[key].done():
            active.append(cfg["label"])

    if active:
        text = "🔔 Активные уведомления:\n" + "\n".join(f"  • {a}" for a in active)
    else:
        text = "Нет активных уведомлений."
    await event.reply(text)


@bot_client.on(events.NewMessage(pattern=r"^/stop", func=lambda e: e.is_private))
async def on_cmd_stop(event):
    stopped_any = False
    for country in list(COUNTRY_CONFIG):
        if await stop_alert(country):
            stopped_any = True

    if stopped_any:
        await event.reply("✅ Все уведомления остановлены.")
    else:
        await event.reply("Нет активных уведомлений.")


# --------------- entry point ---------------


async def main() -> None:
    if not API_ID or not API_HASH:
        raise RuntimeError(
            "API_ID / API_HASH not set. Get them at https://my.telegram.org"
        )
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN not set.")
    if not NOTIFY_USER_ID:
        raise RuntimeError("NOTIFY_USER_ID not set.")

    await user_client.start(phone=PHONE_NUMBER)
    await bot_client.start(bot_token=BOT_TOKEN)

    await ensure_chat_entity(user_client)
    await log_startup_topic_sample(user_client)

    logger.info(
        "Live listener active: NewMessage(chats=%s). Notifying user %s.",
        CHAT_ID,
        NOTIFY_USER_ID,
    )

    await asyncio.gather(
        user_client.run_until_disconnected(),
        bot_client.run_until_disconnected(),
    )


if __name__ == "__main__":
    asyncio.run(main())
