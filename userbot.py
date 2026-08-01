import os
import asyncio
import logging
from dotenv import load_dotenv

load_dotenv()

try:
    from telethon import TelegramClient, events
except ImportError:
    print("❌ Библиотека Telethon не установлена! Выполните: pip install telethon")
    exit(1)

import database as db
import config
from aiogram import Bot
from parser import notify_users
from ai_classifier import classify_post_smart as classify_post

logging.basicConfig(level=logging.INFO, format="%(asctime)s - [%(levelname)s] - %(message)s")

API_ID = os.getenv("API_ID", "35554083")
API_HASH = os.getenv("API_HASH", "f3308dd71c039f71e565eabe1938e8f8")

if not API_ID or not API_HASH:
    print("=" * 60)
    print("⚠️  API_ID или API_HASH не найдены в файле .env!")
    print("👉 Чтобы юзербот мог читать любые каналы и чаты от вашего имени:")
    print("   1. Перейдите на сайт https://my.telegram.org/apps (войдите по номеру телефона)")
    print("   2. Скопируйте App api_id и App api_hash")
    print("   3. Вставьте их в файл .env в строки API_ID=... и API_HASH=...")
    print("=" * 60)
    exit(1)

client = TelegramClient("userbot_session", int(API_ID), API_HASH)
bot = Bot(token=config.BOT_TOKEN)


async def scan_history_on_startup(client: TelegramClient):
    """
    Сканирует последние 2000 старых сообщений из каждого чата при запуске.
    """
    logging.info("⏳ [USERBOT] Полная проверка старых сообщений (до 2000 постов из каждого канала)...")
    for ch in config.CHANNELS:
        ch_clean = ch.strip()
        if not ch_clean:
            continue
        try:
            entity = await client.get_entity(ch_clean)
            title = getattr(entity, "title", ch_clean)
            logging.info(f"📂 Анализ истории из @{ch_clean} ({title})...")
            count_new = 0
            async for message in client.iter_messages(entity, limit=2000):
                text = message.message or ""
                if not text:
                    continue
                post_id = message.id
                post_url = f"https://t.me/{ch_clean}/{post_id}"
                matches = await classify_post(text, channel=ch_clean)
                for cat, price in matches:
                    is_new = await db.add_villa(
                        channel=ch_clean,
                        post_id=post_id,
                        price=price,
                        text=text,
                        url=post_url,
                        category=cat
                    )
                    if is_new:
                        count_new += 1
                        logging.info(f"   [+] Сохранено старое объявление: {cat} (цена: {price}) из @{ch_clean}")
            logging.info(f"✅ В чате @{ch_clean} найдено и сохранено из истории: {count_new} объявлений.")
        except Exception as e:
            logging.warning(f"⚠️ Не удалось получить историю для @{ch_clean}: {e}")


@client.on(events.NewMessage(chats=config.CHANNELS))
async def handle_new_message(event):
    text = event.message.message or ""
    if not text:
        return

    chat = await event.get_chat()
    channel_username = getattr(chat, "username", None) or str(chat.id)
    post_id = event.message.id
    post_url = f"https://t.me/{channel_username}/{post_id}" if getattr(chat, "username", None) else ""

    logging.info(f"[USERBOT] Новая публикация в @{channel_username} (id: {post_id}). Анализ...")
    matches = await classify_post(text, channel=channel_username)
    for cat, price in matches:
        is_new = await db.add_villa(
            channel=channel_username,
            post_id=post_id,
            price=price,
            text=text,
            url=post_url,
            category=cat
        )
        if is_new:
            if cat == "currency_exchange":
                logging.info(f"💾 [USERBOT] Новое объявление [currency_exchange] {price}€ сохранено в базу (без уведомления в чат).")
            else:
                logging.info(f"✅ [USERBOT] Новое объявление [{cat}] {price}€. Отправка подписчикам!")
                villa_data = {
                    "channel": channel_username,
                    "text": text,
                    "url": post_url
                }
                await notify_users(bot, villa_data, cat, price)


async def main():
    await db.init_db()
    logging.info("🚀 Запуск Юзербота для чтения чужих каналов и чатов...")
    await client.start()
    logging.info("✅ Юзербот успешно подключен! Слушаем каналы: " + ", ".join(config.CHANNELS))
    await scan_history_on_startup(client)
    logging.info("🎧 Режим реального времени активен! Ожидаем новые сообщения...")
    await client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())
