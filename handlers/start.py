from aiogram import Router, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, WebAppInfo
from aiogram.filters import CommandStart
import database as db
import config

router = Router()


def get_main_keyboard() -> ReplyKeyboardMarkup:
    """Создание основного меню с удобными кнопками, включая Telegram Mini App."""
    webapp_btn = (
        KeyboardButton(text="📱 Каталог (Mini App)", web_app=WebAppInfo(url=config.WEBAPP_URL))
        if config.WEBAPP_URL and config.WEBAPP_URL.startswith("https://")
        else KeyboardButton(text="📱 Каталог (Mini App)")
    )

    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="🏡 Продажа вилл (Пафос)"),
                KeyboardButton(text="🏢 Аренда вилл Пафос")
            ],
            [
                webapp_btn,
                KeyboardButton(text="⭐ Мое Избранное")
            ],
            [
                KeyboardButton(text="🔍 Поиск по словам"),
                KeyboardButton(text="❓ Помощь")
            ]
        ],
        resize_keyboard=True
    )


@router.message(CommandStart())
async def cmd_start(message: Message):
    user_id = message.from_user.id
    await db.add_user(user_id)

    text = (
        "👋 <b>Каталог вилл — Пафос и пригороды</b>\n\n"
        "Бот отслеживает новые публикации в профильных каналах и строго отбирает объявления только по виллам и домам в Пафосе:\n\n"
        "• <b>🏡 Продажа вилл (Пафос)</b> — виллы, дома и коттеджи на продажу в Пафосе\n"
        "• <b>🏢 Аренда вилл Пафос</b> — актуальные предложения по аренде вилл и домов в Пафосе\n"
        "• <b>📱 Каталог (Mini App)</b> — интерактивный каталог в формате веб-приложения Telegram\n"
        "• <b>⭐ Мое Избранное</b> — ваши сохранённые объявления\n\n"
        "<i>Выберите интересующий раздел в меню ниже или напишите любое слово или число (например «5000» или «Тала») в чат для быстрого поиска:</i>"
    )

    await message.answer(
        text=text,
        reply_markup=get_main_keyboard(),
        parse_mode="HTML"
    )


@router.message(F.text == "📱 Каталог (Mini App)")
async def on_webapp_button_click(message: Message):
    if config.WEBAPP_URL and config.WEBAPP_URL.startswith("https://"):
        await message.answer(
            f"🌐 Откройте наш каталог по ссылке: <a href='{config.WEBAPP_URL}'>Paphos Villas Mini App</a>",
            parse_mode="HTML"
        )
    else:
        await message.answer(
            "🌐 <b>Telegram Mini App — Каталог вилл Пафоса</b>\n\n"
            "Приложение готово в папке <code>webapp/</code>! Чтобы кнопка открывала Mini App прямо внутри Telegram:\n\n"
            "1. В файле <code>.env</code> на Render укажите HTTPS-адрес вашего сервера:\n"
            "<code>WEBAPP_URL=https://ваше-имя-на-render.com/webapp/index.html</code>\n"
            "2. А пока вы можете открыть файл <code>webapp/index.html</code> в браузере на компьютере или телефоне!",
            parse_mode="HTML"
        )
