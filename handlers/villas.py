import logging
import html
from aiogram import Router, F, Bot
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
import database as db
import config
from parser import notify_users
from ai_classifier import classify_post_smart as classify_post
from ai_classifier import is_paphos_location, is_apartment_only
from datetime import datetime

router = Router()


class SearchState(StatesGroup):
    waiting_for_keyword = State()


def format_villa_card_with_kb(v: dict, category: str) -> tuple[str, InlineKeyboardMarkup]:
    date_str = ""
    if v.get("created_at"):
        try:
            dt = datetime.fromisoformat(v["created_at"])
            date_str = dt.strftime("%d.%m.%Y %H:%M")
        except Exception:
            date_str = ""

    price_str = f"{v['price']:,} €".replace(",", " ")
    price_label = "💰 Стоимость:"

    raw_snippet = v['text'][:300].strip()
    if len(v['text']) > 300:
        raw_snippet += "..."
    text_snippet = html.escape(raw_snippet)

    header_line = f"📍 @{v['channel']} • {date_str}" if date_str else f"📍 @{v['channel']}"
    text = (
        f"{header_line}\n"
        f"<b>{price_label} {price_str}</b>\n\n"
        f"{text_snippet}\n\n"
        f"👉 <a href='{v['url']}'>Перейти к объявлению</a>\n"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❤️ В Избранное", callback_data=f"fav_{v['id']}")]
    ])
    return text, kb


@router.callback_query(F.data.startswith("fav_"))
async def on_favorite_click(callback: CallbackQuery):
    try:
        villa_id = int(callback.data.split("_")[1])
        added = await db.add_favorite(callback.from_user.id, villa_id)
        if added:
            await callback.answer("✅ Добавлено в Избранное!", show_alert=False)
        else:
            await callback.answer("⭐ Уже сохранено в Избранном!", show_alert=False)
    except Exception:
        await callback.answer("Ошибка при добавлении.", show_alert=False)


@router.message(F.text == "⭐ Мое Избранное")
async def show_favorites(message: Message):
    villas = await db.get_user_favorites(message.from_user.id, limit=20)
    villas = [
        v for v in villas
        if is_paphos_location(v.get("text", "")) and not is_apartment_only(v.get("text", ""))
    ][:15]
    if not villas:
        await message.answer(
            "У вас пока нет сохраненных объявлений Пафоса.\n"
            "Нажимайте кнопку <b>«❤️ В Избранное»</b> под любым объявлением, чтобы добавить его сюда.",
            parse_mode="HTML"
        )
        return
    await message.answer("⭐ <b>Ваши избранные объявления (Пафос):</b>", parse_mode="HTML")
    for v in villas:
        text, kb = format_villa_card_with_kb(v, v.get("category", ""))
        await message.answer(text, reply_markup=kb, parse_mode="HTML", disable_web_page_preview=True)


@router.message(F.text == "🔍 Поиск по словам")
async def ask_search_keyword(message: Message, state: FSMContext):
    await message.answer(
        "🔍 <b>Поиск по ключевым словам и ценам (Пафос)</b>\n\n"
        "Вы можете ввести:\n"
        "• Любую цену в евро (например: <code>3000</code> или <code>5000</code>) — бот покажет все виллы в аренду до этой суммы!\n"
        "• Район или особенности (например: <code>Тала</code>, <code>Корал Бэй</code>, <code>бассейн</code>, <code>4 спальни</code>).\n\n"
        "Напишите ваш запрос ниже:",
        parse_mode="HTML"
    )
    await state.set_state(SearchState.waiting_for_keyword)


@router.message(SearchState.waiting_for_keyword)
async def process_search_keyword(message: Message, state: FSMContext):
    query = (message.text or "").strip()
    if not query:
        await message.answer("Пожалуйста, введите запрос для поиска:")
        return

    await state.clear()
    villas = await db.search_villas(query, max_price=50000, limit=30)
    villas = [
        v for v in villas
        if is_paphos_location(v.get("text", "")) and not is_apartment_only(v.get("text", ""))
    ][:15]
    if not villas:
        await message.answer(
            f"❌ По запросу <b>«{html.escape(query)}»</b> в Пафосе ничего не найдено.\n"
            "Попробуйте другое слово или район.",
            parse_mode="HTML"
        )
        return

    await message.answer(f"🔍 <b>Результаты поиска по запросу «{html.escape(query)}» (Пафос):</b>", parse_mode="HTML")
    for v in villas:
        text, kb = format_villa_card_with_kb(v, v.get("category", ""))
        await message.answer(text, reply_markup=kb, parse_mode="HTML", disable_web_page_preview=True)


@router.message(F.text == "🏡 Продажа вилл (Пафос)")
async def show_villas_sale(message: Message):
    villas = await db.get_latest_villas(category="sale_villa", max_price=20000000, limit=30)
    villas = [
        v for v in villas
        if is_paphos_location(v.get("text", "")) and not is_apartment_only(v.get("text", ""))
    ][:15]
    if not villas:
        await message.answer(
            "В настоящий момент объявлений по продаже вилл в Пафосе нет.\n"
            "Как только появится подходящее предложение, бот сразу пришлёт уведомление.",
            parse_mode="HTML"
        )
        return

    cards_kb = [format_villa_card_with_kb(v, "sale_villa") for v in villas]
    header = "🏡 <b>Продажа вилл в Пафосе</b>\n<i>Актуальные предложения:</i>"
    await message.answer(header, parse_mode="HTML")
    for card, kb in cards_kb:
        await message.answer(card, reply_markup=kb, parse_mode="HTML", disable_web_page_preview=True)


@router.message(F.text.in_({"🏢 Аренда вилл Пафос", "Аренда вилл Пафос", "🏢 Аренда вилл (Пафос)", "🏢 Аренда вилл", "🏢 Аренда вилл и квартир", "🏢 Аренда до указанной цены"}))
async def show_villas_rent(message: Message):
    villas = await db.get_latest_villas(category="rent_paphos", max_price=50000, limit=30)
    villas = [
        v for v in villas
        if is_paphos_location(v.get("text", "")) and not is_apartment_only(v.get("text", ""))
    ][:15]
    if not villas:
        await message.answer(
            "Сейчас нет актуальных объявлений по аренде вилл и домов в Пафосе.\n"
            "Мы уведомим вас сразу же после появления подходящих вариантов.",
            parse_mode="HTML"
        )
        return

    cards_kb = [format_villa_card_with_kb(v, "rent_paphos") for v in villas]
    header = "🏢 <b>Аренда вилл в Пафосе</b>\n<i>Свежие варианты:</i>"
    await message.answer(header, parse_mode="HTML")
    for card, kb in cards_kb:
        await message.answer(card, reply_markup=kb, parse_mode="HTML", disable_web_page_preview=True)


@router.message(F.text == "❓ Помощь")
async def show_help(message: Message):
    help_text = (
        "<b>Справочная информация</b>\n\n"
        "Бот автоматически отслеживает новые публикации в профильных каналах Кипра и строго отбирает виллы и дома в Пафосе (без квартир):\n\n"
        "• <b>🏡 Продажа вилл (Пафос)</b> — виллы и дома на продажу в Пафосе\n"
        "• <b>🏢 Аренда вилл Пафос</b> — свежие объявления аренды вилл и домов в Пафосе\n"
        "• <b>⭐ Мое Избранное</b> — просмотр сохраненных объявлений\n"
        "• <b>🔍 Поиск по словам</b> — поиск по ключевым словам или максимальной цене\n\n"
        "<i>Также вы можете в любой момент написать в чат любое число (например: <b>3000</b> или <b>5000</b>) или слово, чтобы быстро найти подходящие варианты!</i>"
    )
    await message.answer(help_text, parse_mode="HTML")


@router.message(F.text)
async def global_text_search(message: Message):
    """
    Глобальный обработчик:
    1. Если пользователь написал число (например '3000' или '5000'), показываем аренду вилл с ценой до этого лимита!
    2. Если пользователь написал слова (например 'Аренда вилла Пафос', 'Тала', 'бассейн'), выполняем умный поиск!
    """
    query = (message.text or "").strip()
    if not query:
        return

    villas = await db.search_villas(query, max_price=50000, limit=30)
    villas = [
        v for v in villas
        if is_paphos_location(v.get("text", "")) and not is_apartment_only(v.get("text", ""))
    ][:15]
    if not villas:
        await message.answer(
            f"❌ По запросу <b>«{html.escape(query)}»</b> в Пафосе ничего не найдено.\n"
            "Попробуйте другое слово или укажите другую сумму.",
            parse_mode="HTML"
        )
        return

    if query.isdigit():
        header_text = f"🔍 <b>Аренда вилл в Пафосе с бюджетом до {int(query):,} €:</b>".replace(",", " ")
    else:
        header_text = f"🔍 <b>Результаты поиска по запросу «{html.escape(query)}» (Пафос):</b>"

    await message.answer(header_text, parse_mode="HTML")
    for v in villas:
        text, kb = format_villa_card_with_kb(v, v.get("category", ""))
        await message.answer(text, reply_markup=kb, parse_mode="HTML", disable_web_page_preview=True)
