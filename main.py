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
from aiohttp import web

logging.basicConfig(level=logging.INFO, format="%(asctime)s - [%(levelname)s] - %(message)s")


async def run_dummy_http_server():
    """
    HTTP-сервер для Render.com (Web Service) и Telegram Mini App!
    Обслуживает API предложений из базы данных и статические файлы мини-приложения из папки webapp/.
    """
    port = int(os.getenv("PORT", 8080))
    app = web.Application()

    async def handle_ping(request):
        return web.Response(text="✅ Villas Bot & Mini App are running 24/7!", status=200)

    async def handle_api_villas(request):
        category = request.query.get("category", "rent_paphos")
        try:
            limit = int(request.query.get("limit", 50))
        except ValueError:
            limit = 50
        try:
            max_price = int(request.query.get("max_price", 100000000))
        except ValueError:
            max_price = 100000000
        villas_list = await db.get_latest_villas(category=category, max_price=max_price, limit=limit)
        return web.json_response(villas_list)

    async def handle_root(request):
        raise web.HTTPFound("/webapp/index.html")

    app.router.add_get("/", handle_root)
    app.router.add_get("/health", handle_ping)
    app.router.add_get("/api/villas", handle_api_villas)

    webapp_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "webapp")
    if os.path.exists(webapp_dir):
        app.router.add_static("/webapp", webapp_dir)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logging.info(f"🌐 [HTTP] Веб-сервер и Telegram Mini App запущены на порту {port} (/webapp/index.html)")


async def scan_history_on_startup(client: TelegramClient):
    """
    Сканирует последние 2000 старых сообщений из каждого чата при запуске.
    """
    logging.info("⏳ [USERBOT] Полная проверка старых сообщений (до 2000 постов из каждого канала)...")
    for channel_name in config.CHANNELS:
        try:
            logging.info(f" -> Чтение @{channel_name}...")
            count = 0
            async for message in client.iter_messages(channel_name, limit=2000):
                if not message.text:
                    continue
                count += 1
                results = await classify_post(message.text, channel_name)
                for cat, price in results:
                    post_id = message.id
                    post_url = f"https://t.me/{channel_name}/{post_id}"
                    await db.add_villa(channel_name, post_id, price, message.text, post_url, cat)
            logging.info(f"    Готово! Обработано сообщений: {count} из @{channel_name}")
        except Exception as e:
            logging.error(f"❌ Ошибка сканирования @{channel_name}: {e}")


async def run_userbot(bot: Bot):
    """
    Запуск Telethon Юзербота. Читает сообщения как обычный Telegram-аккаунт.
    """
    api_id = os.getenv("API_ID")
    api_hash = os.getenv("API_HASH")

    if not api_id or not api_hash:
        logging.error("⚠️ API_ID или API_HASH не указаны в файле .env! Юзербот отключен.")
        return

    client = TelegramClient("userbot_session", int(api_id), api_hash)

    @client.on(events.NewMessage(chats=config.CHANNELS))
    async def handler(event):
        channel_username = event.chat.username or str(event.chat_id)
        text = event.text or ""

        logging.info(f"⚡ [USERBOT] Новая публикация в @{channel_username} (id: {event.id}). Анализ...")
        results = await classify_post(text, channel_username)

        for cat, price in results:
            post_url = f"https://t.me/{channel_username}/{event.id}"
            is_new = await db.add_villa(channel_username, event.id, price, text, post_url, cat)
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
    logging.info("🚀 Запуск единого сервера: Telegram-Бот + Юзербот + Mini App")
    logging.info("=====================================================")
    bot = Bot(token=config.BOT_TOKEN)

    await asyncio.gather(
        run_bot(bot),
        run_userbot(bot),
        run_dummy_http_server()
    )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Остановка сервера.")
