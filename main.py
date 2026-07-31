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
from aiogram import Bot, Dispatcher
from handlers import start, villas
from parser import notify_users
from ai_classifier import classify_post_smart as classify_post

logging.basicConfig(level=logging.INFO, format="%(asctime)s - [%(levelname)s] - %(message)s")


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


async def run_userbot(bot: Bot):
    """
    Запуск Telethon-клиента для мониторинга любых чатов и каналов Telegram от вашего аккаунта.
    """
    API_ID = os.getenv("API_ID")
    API_HASH = os.getenv("API_HASH")
    if not API_ID or not API_HASH:
        logging.error("⚠️ API_ID или API_HASH не указаны в файле .env! Юзербот отключен.")
        return

    client = TelegramClient("userbot_session", int(API_ID), API_HASH)

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
                logging.info(f"✅ [USERBOT] Новое объявление [{cat}] {price}€. Отправка подписчикам!")
                villa_data = {
                    "channel": channel_username,
                    "text": text,
                    "url": post_url
                }
                await notify_users(bot, villa_data, cat, price)

    await client.start()
    logging.info("✅ [USERBOT] Успешно подключен! Мониторим каналы: " + ", ".join(config.CHANNELS))
    await scan_history_on_startup(client)
    logging.info("🎧 [USERBOT] Мониторинг в реальном времени активен!")
    await client.run_until_disconnected()


async def run_bot(bot: Bot):
    """
    Запуск Aiogram-бота (интерфейс в Telegram с кнопками и меню).
    """
    dp = Dispatcher()
    dp.include_router(start.router)
    dp.include_router(villas.router)
    await bot.delete_webhook(drop_pending_updates=True)
    logging.info("✅ [BOT] Telegram-бот готов к работе! Отправьте /start в боте.")
    await dp.start_polling(bot)


async def main():
    await db.init_db()
    logging.info("=====================================================")
    logging.info("🚀 Запуск единого сервера: Telegram-Бот + Юзербот")
    logging.info("=====================================================")
    bot = Bot(token=config.BOT_TOKEN)

    # Запускаем одновременно оба процесса в одном цикле asyncio:
    await asyncio.gather(
        run_bot(bot),
        run_userbot(bot)
    )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Остановка сервера.")
