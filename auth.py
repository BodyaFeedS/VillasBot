import os
import asyncio
from dotenv import load_dotenv
from telethon import TelegramClient, errors
import config

load_dotenv()

API_ID = int(os.getenv("API_ID", config.API_ID))
API_HASH = os.getenv("API_HASH", config.API_HASH)


async def authorize():
    print("=============================================")
    print("🔑 АВТОРИЗАЦИЯ ЮЗЕРБОТА В TELEGRAM (С 2FA)")
    print("=============================================")
    client = TelegramClient("userbot_session", API_ID, API_HASH)
    await client.connect()

    if not await client.is_user_authorized():
        phone = input("📱 Введите номер телефона (например: +7999... или +380...): ").strip()
        await client.send_code_request(phone)
        code = input("💬 Введите код подтверждения из Telegram: ").strip()
        try:
            await client.sign_in(phone=phone, code=code)
        except errors.SessionPasswordNeededError:
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

    me = await client.get_me()
    print("=============================================")
    print(f"✅ Успешно авторизован аккаунт: {me.first_name} (@{me.username or me.id})")
    print("📁 Файл сессии userbot_session.session успешно создан и сохранён!")
    print("=============================================")
    await client.disconnect()


if __name__ == "__main__":
    try:
        asyncio.run(authorize())
    except (KeyboardInterrupt, SystemExit):
        print("\n❌ Авторизация отменена.")
    except Exception as e:
        print(f"\n❌ Ошибка авторизации: {e}")
