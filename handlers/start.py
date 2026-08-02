from aiogram import Router, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.filters import CommandStart
import database as db

router = Router()


def get_main_keyboard() -> ReplyKeyboardMarkup:
    """Создание основного меню с удобными кнопками (строго виллы в Пафосе)."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="🏡 Продажа вилл (Пафос)"),
                KeyboardButton(text="🏢 Аренда вилл Пафос")
            ],
            [
                KeyboardButton(text="💰 Фильтр цены аренды"),
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
        "• <b>💰 Фильтр цены аренды</b> — установить лимит бюджета для аренды\n"
        "• <b>⭐ Мое Избранное</b> — ваши сохранённые объявления\n"
        "• <b>🔍 Поиск по словам</b> — поиск по ключевым словам или максимальной цене\n\n"
        "<i>Выберите интересующий раздел в меню ниже или напишите любое слово или число (например «5000» или «Тала») в чат для быстрого поиска:</i>"
    )

    await message.answer(
        text=text,
        reply_markup=get_main_keyboard(),
        parse_mode="HTML"
    )
