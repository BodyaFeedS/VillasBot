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


class PriceState(StatesGroup):
    waiting_for_price = State()


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
        "🔍 <b>Поиск по ключевым словам (Пафос)</b>\n\n"
        "Введите любое слово или фразу для поиска по виллам Пафоса (например: <code>вилла</code>, <code>аренда виллы</code>, <code>бассейн</code>, <code>титул</code>, <code>4 спальни</code>):",
        parse_mode="HTML"
    )
    await state.set_state(SearchState.waiting_for_keyword)


@router.message(SearchState.waiting_for_keyword)
async def process_search_keyword(message: Message, state: FSMContext):
    query = (message.text or "").strip()
    if not query or len(query) < 2:
        await message.answer("Пожалуйста, введите минимум 2 символа для поиска:")
        return

    await state.clear()
    user_max = await db.get_user_max_price(message.from_user.id)
    villas = await db.search_villas(query, max_price=user_max, limit=30)
    villas = [
        v for v in villas
        if is_paphos_location(v.get("text", "")) and not is_apartment_only(v.get("text", ""))
    ][:15]
    if not villas:
        await message.answer(
            f"❌ По запросу <b>«{html.escape(query)}»</b> (с ценой аренды до <b>{user_max} €</b>) в Пафосе ничего не найдено.\n"
            "Попробуйте другое слово или увеличьте лимит в меню <b>«💰 Изменить цену аренды»</b>.",
            parse_mode="HTML"
        )
        return

    await message.answer(f"🔍 <b>Результаты поиска по запросу «{html.escape(query)}» (Пафос, цена до {user_max} €):</b>", parse_mode="HTML")
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


@router.message(F.text.in_({"🏢 Аренда вилл (Пафос)", "🏢 Аренда вилл", "🏢 Аренда вилл и квартир", "🏢 Аренда до указанной цены"}))
async def show_villas_rent(message: Message):
    user_max = await db.get_user_max_price(message.from_user.id)
    villas = await db.get_latest_villas(category="rent_paphos", max_price=user_max, limit=30)
    villas = [
        v for v in villas
        if is_paphos_location(v.get("text", "")) and not is_apartment_only(v.get("text", ""))
    ][:15]
    if not villas:
        await message.answer(
            f"Сейчас нет объявлений по аренде вилл и домов в Пафосе в пределах <b>{user_max} €</b>.\n"
            "Мы уведомим вас сразу же после появления подходящих вариантов.",
            parse_mode="HTML"
        )
        return

    cards_kb = [format_villa_card_with_kb(v, "rent_paphos") for v in villas]
    header = f"🏢 <b>Аренда вилл в Пафосе</b> (бюджет до {user_max} €)\n<i>Свежие варианты:</i>"
    await message.answer(header, parse_mode="HTML")
    for card, kb in cards_kb:
        await message.answer(card, reply_markup=kb, parse_mode="HTML", disable_web_page_preview=True)


@router.message(F.text == "💰 Изменить цену аренды")
async def ask_rent_price_limit(message: Message, state: FSMContext):
    current = await db.get_user_max_price(message.from_user.id)
    await message.answer(
        f"Ваш текущий лимит по аренде: <b>{current} €</b>.\n\n"
        "Укажите новую максимальную стоимость в евро (целым числом):",
        parse_mode="HTML"
    )
    await state.set_state(PriceState.waiting_for_price)


@router.message(PriceState.waiting_for_price)
async def process_rent_price_limit(message: Message, state: FSMContext):
    if not message.text or not message.text.isdigit():
        await message.answer("Пожалуйста, введите корректное число в евро (например: 600 или 1000):")
        return

    new_price = int(message.text)
    if new_price < 100 or new_price > 50000:
        await message.answer("Сумма должна быть в диапазоне от 100 до 50 000 €. Попробуйте ещё раз:")
        return

    await db.update_user_max_price(message.from_user.id, new_price)
    await state.clear()
    await message.answer(
        f"Лимит для аренды вилл успешно обновлён: <b>{new_price} €</b>.\n"
        "Теперь будут показываться варианты аренды вилл в пределах этой суммы.",
        parse_mode="HTML"
    )


@router.message(F.text == "❓ Помощь")
async def show_help(message: Message):
    help_text = (
        "<b>Справочная информация</b>\n\n"
        "Бот автоматически отслеживает новые публикации в профильных каналах Кипра и строго отбирает виллы и дома в Пафосе (без квартир):\n\n"
        "• <b>🏡 Продажа вилл (Пафос)</b> — виллы и дома на продажу в Пафосе\n"
        "• <b>🏢 Аренда вилл (Пафос)</b> — аренда вилл и домов в пределах вашего бюджета в Пафосе\n"
        "• <b>⭐ Мое Избранное</b> — просмотр сохраненных объявлений\n"
        "• <b>🔍 Поиск по словам</b> — поиск по ключевым словам в базе\n\n"
        "<i>Также вы можете в любой момент написать слово или фразу в чат, чтобы быстро найти нужное объявление!</i>"
    )
    await message.answer(help_text, parse_mode="HTML")


@router.message(F.text)
async def global_text_search(message: Message):
    """
    Глобальный обработчик: если пользователь просто написал слово в чат (например 'вилла', 'аренда', 'бассейн'),
    автоматически ищем по базе объявлений с учетом фильтра по максимальной цене аренды!
    """
    query = (message.text or "").strip()
    if len(query) < 2:
        return

    user_max = await db.get_user_max_price(message.from_user.id)
    villas = await db.search_villas(query, max_price=user_max, limit=30)
    villas = [
        v for v in villas
        if is_paphos_location(v.get("text", "")) and not is_apartment_only(v.get("text", ""))
    ][:15]
    if not villas:
        await message.answer(
            f"❌ По запросу <b>«{html.escape(query)}»</b> (с ценой аренды до <b>{user_max} €</b>) в Пафосе ничего не найдено.\n"
            "Попробуйте другое слово или увеличьте лимит в меню <b>«💰 Изменить цену аренды»</b>.",
            parse_mode="HTML"
        )
        return

    await message.answer(f"🔍 <b>Результаты поиска по слову «{html.escape(query)}» (Пафос, цена до {user_max} €):</b>", parse_mode="HTML")
    for v in villas:
        text, kb = format_villa_card_with_kb(v, v.get("category", ""))
        await message.answer(text, reply_markup=kb, parse_mode="HTML", disable_web_page_preview=True)
