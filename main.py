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
    Легковесный HTTP-сервер для Render.com (Web Service),
    чтобы сервис успешно проходил проверку порта ($PORT) и работал бесплатно 24/7.
    """
    port = int(os.getenv("PORT", 8080))
    app = web.Application()

    async def handle_ping(request):
        return web.Response(text="✅ Villas Bot & Userbot are running 24/7!", status=200)

    app.router.add_get("/", handle_ping)
    app.router.add_get("/health", handle_ping)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logging.info(f"🌐 [HTTP] Веб-сервер для Render.com успешно запущен на порту {port} (0.0.0.0:{port})")


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


async def periodic_channel_check(client: TelegramClient, bot: Bot):
    """
    Фоновая проверка каждые 15 минут: сканирует последние 30 постов в каналах,
    чтобы 100% гарантировать, что ни одна публикация виллы не была пропущена.
    """
    while True:
        await asyncio.sleep(900)  # 15 минут
        logging.info("🔄 [USERBOT] Периодическая проверка новых сообщений в каналах...")
        for channel_name in config.CHANNELS:
            try:
                async for message in client.iter_messages(channel_name, limit=30):
                    if not message.text:
                        continue
                    results = await classify_post(message.text, channel_name)
                    for cat, price in results:
                        post_id = message.id
                        post_url = f"https://t.me/{channel_name}/{post_id}"
                        is_new = await db.add_villa(channel_name, post_id, price, message.text, post_url, cat)
                        if is_new:
                            logging.info(f"✅ [USERBOT] Новая вилла найдена при фоновой проверке [{cat}] {price}€! Отправка...")
                            villa_data = {
                                "channel": channel_name,
                                "text": message.text,
                                "url": post_url
                            }
                            await notify_users(bot, villa_data, cat, price)
            except Exception as e:
                logging.error(f"❌ Ошибка фоновой проверки @{channel_name}: {e}")


async def ensure_joined_channels(client: TelegramClient):
    """
    Автоматически проверяет и при необходимости вступает во все отслеживаемые каналы/группы,
    чтобы Telegram не блокировал чтение сообщений по юзернейму или ссылке.
    """
    try:
        from telethon.tl.functions.channels import JoinChannelRequest
        from telethon.tl.functions.messages import ImportChatInviteRequest
    except ImportError:
        return

    for ch in config.CHANNELS:
        try:
            entity = await client.get_entity(ch)
            logging.info(f"✅ [USERBOT] Канал доступен: {getattr(entity, 'title', ch)} (id: {entity.id})")
        except Exception as e:
            logging.info(f"⚠️ Канал @{ch} ещё не в списке чатов аккаунта. Попытка автоматического вступления...")
            try:
                if "+" in ch or "joinchat" in ch:
                    hash_part = ch.split("+")[-1] if "+" in ch else ch.split("joinchat/")[-1]
                    await client(ImportChatInviteRequest(hash_part))
                else:
                    await client(JoinChannelRequest(ch))
                logging.info(f"✅ [USERBOT] Успешно вступили в канал: {ch}!")
            except Exception as e2:
                logging.warning(f"⚠️ Не удалось автоматически вступить в {ch}: {e2}. Убедитесь, что аккаунт подписан на него в Telegram.")


async def run_userbot_with_client(bot: Bot, client: TelegramClient):
    """
    Запуск Telethon Юзербота. Читает сообщения как обычный Telegram-аккаунт.
    """
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

    logging.info("✅ [USERBOT] Успешно подключен! Мониторим каналы: " + ", ".join(config.CHANNELS))
    await ensure_joined_channels(client)
    await scan_history_on_startup(client)
    asyncio.create_task(periodic_channel_check(client, bot))
    logging.info("🎧 [USERBOT] Мониторинг в реальном времени и фоновые проверки каждые 15 минут активны!")
    await client.run_until_disconnected()


async def run_bot(bot: Bot):
    """
    Запуск Aiogram-бота (интерфейс в Telegram с кнопками и меню).
    """
    dp = Dispatcher()
    dp.include_router(start.router)
    dp.include_router(villas.router)
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        logging.info("✅ [BOT] Telegram-бот готов к работе! Отправьте /start в боте.")
        await dp.start_polling(bot)
    except Exception as e:
        err_str = str(e)
        if "Conflict" in err_str or "terminated by other getUpdates request" in err_str:
            logging.warning("⚠️ [BOT] Telegram-бот уже работает на другом сервере (Render.com). Локальный polling бота остановлен без ошибок, Юзербот продолжает работу.")
        else:
            logging.error(f"❌ [BOT] Ошибка polling: {e}")


async def main():
    await db.init_db()
    logging.info("=====================================================")
    logging.info("🚀 Запуск единого сервера: Telegram-Бот + Юзербот")
    logging.info("=====================================================")
    bot = Bot(token=config.BOT_TOKEN)

    api_id = os.getenv("API_ID", config.API_ID)
    api_hash = os.getenv("API_HASH", config.API_HASH)
    client = TelegramClient("userbot_session", int(api_id), api_hash)
    await client.connect()

    if not await client.is_user_authorized():
        print("\n=====================================================")
        print("🔑 ТРЕБУЕТСЯ АВТОРИЗАЦИЯ ЮЗЕРБОТА В TELEGRAM")
        print("=====================================================")
        phone = input("📱 Введите номер телефона (например: +7999... или +380...): ").strip()
        await client.send_code_request(phone)
        code = input("💬 Введите код подтверждения из Telegram: ").strip()
        try:
            await client.sign_in(phone=phone, code=code)
        except Exception as e:
            err_msg = str(e)
            if "SessionPasswordNeededError" in err_msg or "password" in err_msg.lower() or "2fa" in err_msg.lower():
                print("\n🔒 У вас включена двухфакторная аутентификация (2FA)!")
                for attempt in range(1, 6):
                    password = input("🔑 Введите ваш облачный пароль 2FA: ").strip()
                    try:
                        await client.sign_in(password=password)
                        break
                    except Exception as pass_err:
                        if "PasswordHashInvalidError" in str(pass_err) or "invalid" in str(pass_err).lower() or "password" in str(pass_err).lower():
                            print(f"❌ Неверный пароль! (попытка {attempt}/5). Проверьте заглавные буквы (например, B вместо b), цифры или язык ввода.")
                        else:
                            raise pass_err
            else:
                raise e
        me = await client.get_me()
        print(f"✅ [USERBOT] Успешно авторизован аккаунт: {me.first_name} (@{me.username or me.id})!\n")

    await asyncio.gather(
        run_bot(bot),
        run_userbot_with_client(bot, client),
        run_dummy_http_server()
    )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Остановка сервера.")
