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
                KeyboardButton(text="🏢 Аренда вилл и квартир")
            ],
            [
                KeyboardButton(text="💱 Обмен валют"),
                KeyboardButton(text="⭐ Мое Избранное")
            ],
            [
                KeyboardButton(text="🔍 Поиск по словам"),
                KeyboardButton(text="💰 Изменить цену аренды")
            ],
            [
                KeyboardButton(text="💰 Изменить цену обмена"),
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
    exchange_limit = await db.get_user_exchange_limit(user_id)
    exchange_str = f"{exchange_limit:,}".replace(",", " ")

    text = (
        "👋 <b>Каталог недвижимости и обмена валют (Пафос)</b>\n\n"
        "Бот отслеживает новые публикации в профильных каналах и отбирает объявления по направлениям:\n\n"
        "• <b>Продажа вилл</b> — дома и виллы в Пафосе\n"
        f"• <b>Аренда вилл и квартир</b> — варианты в пределах <b>{user_limit} €</b>\n"
        f"• <b>Обмен валют</b> — предложения с лимитом до <b>{exchange_str}</b>\n\n"
        "<i>Выберите интересующий раздел в меню ниже или напишите любое слово в чат для поиска:</i>"
    )

    await message.answer(
        text=text,
        reply_markup=get_main_keyboard(),
        parse_mode="HTML"
    )
