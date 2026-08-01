from aiogram import Router
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.filters import CommandStart
import database as db

router = Router()


def get_main_keyboard() -> ReplyKeyboardMarkup:
    """Создание основного меню с удобными кнопками."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="🏡 Продажа вилл (Пафос)"),
                KeyboardButton(text="🏢 Аренда вилл (Пафос)")
            ],
            [
                KeyboardButton(text="⭐ Мое Избранное"),
                KeyboardButton(text="💰 Изменить цену аренды")
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

    user_limit = await db.get_user_max_price(user_id)

    text = (
        "👋 <b>Каталог вилл — Пафос и пригороды</b>\n\n"
        "Бот отслеживает новые публикации в профильных каналах и строго отбирает объявления только по виллам и домам в Пафосе:\n\n"
        "• <b>🏡 Продажа вилл (Пафос)</b> — виллы, дома и коттеджи на продажу в Пафосе\n"
        f"• <b>🏢 Аренда вилл (Пафос)</b> — аренда вилл и домов в Пафосе до <b>{user_limit} €</b>\n\n"
        "<i>Выберите интересующий раздел в меню ниже или напишите любое слово в чат для поиска:</i>"
    )

    await message.answer(
        text=text,
        reply_markup=get_main_keyboard(),
        parse_mode="HTML"
    )
