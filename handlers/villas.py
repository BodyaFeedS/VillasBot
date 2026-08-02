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

# Кэш результатов поиска для поштучного просмотра (пагинации)
USER_SEARCH_CACHE: dict[int, list[dict]] = {}


class SearchState(StatesGroup):
    waiting_for_keyword = State()


class FilterState(StatesGroup):
    waiting_for_rent_price = State()


async def show_villa_card(target, user_id: int, index: int = 0, edit: bool = False):
    """
    Показывает одно объявление в виде аккуратной карточки с кнопками:
    «❤️ В Избранное», «👉 Открыть оригинал», «⬅️ Назад», «➡️ Дальше (X/Y)».
    """
    villas = USER_SEARCH_CACHE.get(user_id, [])
    if not villas:
        text = "Список закончился. Выберите раздел в меню для нового поиска!"
        if edit and isinstance(target, CallbackQuery):
            await target.message.edit_text(text)
        elif isinstance(target, Message):
            await target.answer(text)
        return

    total = len(villas)
    index = index % total
    v = villas[index]

    date_str = ""
    if v.get("created_at"):
        try:
            dt = datetime.fromisoformat(v["created_at"])
            date_str = dt.strftime("%d.%m.%Y %H:%M")
        except Exception:
            date_str = ""

    price_str = f"{v['price']:,} €".replace(",", " ")
    price_label = "💰 Стоимость:"

    raw_snippet = v['text'][:350].strip()
    if len(v['text']) > 350:
        raw_snippet += "..."
    text_snippet = html.escape(raw_snippet)

    header_line = f"📍 @{v['channel']} • {date_str}" if date_str else f"📍 @{v['channel']}"

    card_text = (
        f"<b>[ {index + 1} из {total} ]</b>\n"
        f"{header_line}\n"
        f"<b>{price_label} {price_str}</b>\n\n"
        f"{text_snippet}\n\n"
        f"👉 <a href='{v['url']}'>Перейти к объявлению</a>\n"
    )

    next_idx = (index + 1) % total
    prev_idx = (index - 1) % total

    buttons = [
        [
            InlineKeyboardButton(text="❤️ В Избранное", callback_data=f"fav_{v['id']}"),
            InlineKeyboardButton(text="👉 Открыть оригинал", url=v['url'])
        ]
    ]
    if total > 1:
        buttons.append([
            InlineKeyboardButton(text="⬅️ Назад", callback_data=f"page_{prev_idx}"),
            InlineKeyboardButton(text=f"➡️ Дальше ({next_idx + 1}/{total})", callback_data=f"page_{next_idx}")
        ])

    kb = InlineKeyboardMarkup(inline_keyboard=buttons)

    if edit and isinstance(target, CallbackQuery):
        try:
            await target.message.edit_text(card_text, reply_markup=kb, parse_mode="HTML", disable_web_page_preview=True)
        except Exception:
            await target.message.delete()
            await target.message.answer(card_text, reply_markup=kb, parse_mode="HTML", disable_web_page_preview=True)
    elif isinstance(target, Message):
        await target.answer(card_text, reply_markup=kb, parse_mode="HTML", disable_web_page_preview=True)
    elif isinstance(target, CallbackQuery):
        await target.message.answer(card_text, reply_markup=kb, parse_mode="HTML", disable_web_page_preview=True)


@router.callback_query(F.data.startswith("page_"))
async def on_page_click(callback: CallbackQuery):
    try:
        idx = int(callback.data.split("_")[1])
        await show_villa_card(callback, callback.from_user.id, index=idx, edit=True)
        await callback.answer()
    except Exception as e:
        logging.error(f"Page click error: {e}")
        await callback.answer("Ошибка переключения страницы.")


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


@router.message(F.text.in_({"💰 Фильтр цены аренды", "💰 Изменить цену аренды"}))
async def ask_rent_price(message: Message, state: FSMContext):
    user_id = message.from_user.id
    current_limit = await db.get_user_max_price(user_id)
    await message.answer(
        f"💰 <b>Настройка бюджета для аренды вилл в Пафосе</b>\n\n"
        f"Ваш текущий лимит стоимости аренды: <b>{current_limit:,} €</b> в месяц.\n\n"
        f"Укажите новую максимальную стоимость аренды (целым числом в евро, например: <code>3000</code> или <code>5000</code>):".replace(",", " "),
        parse_mode="HTML"
    )
    await state.set_state(FilterState.waiting_for_rent_price)


@router.message(FilterState.waiting_for_rent_price)
async def process_rent_price(message: Message, state: FSMContext):
    val_str = (message.text or "").strip()
    if not val_str.isdigit():
        await message.answer("Пожалуйста, введите целое число (например 3000):")
        return
    new_limit = int(val_str)
    user_id = message.from_user.id
    await db.update_user_max_price(user_id, new_limit)
    await state.clear()
    await message.answer(
        f"✅ <b>Лимит для аренды вилл успешно обновлён: {new_limit:,} € в месяц!</b>\n\n"
        f"Показываю актуальные варианты аренды в пределах этой суммы:".replace(",", " "),
        parse_mode="HTML"
    )
    villas = await db.get_latest_villas("rent_paphos", max_price=new_limit, limit=50)
    if not villas:
        await message.answer("Пока нет вариантов в пределах этой суммы, но мы сообщим, как только они появятся!")
        return
    USER_SEARCH_CACHE[user_id] = villas
    await message.answer(f"Нашёл <b>{len(villas)}</b> вариантов. Показываю по одному.", parse_mode="HTML")
    await show_villa_card(message, user_id, index=0)


@router.message(F.text == "⭐ Мое Избранное")
async def show_favorites(message: Message):
    user_id = message.from_user.id
    villas = await db.get_user_favorites(user_id, limit=30)
    if not villas:
        await message.answer(
            "У вас пока нет сохраненных объявлений Пафоса.\n"
            "Нажимайте кнопку <b>«❤️ В Избранное»</b> под любым объявлением, чтобы добавить его сюда.",
            parse_mode="HTML"
        )
        return
    USER_SEARCH_CACHE[user_id] = villas
    await message.answer(f"⭐ Нашёл <b>{len(villas)}</b> избранных объявлений. Показываю по одному:", parse_mode="HTML")
    await show_villa_card(message, user_id, index=0)


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
    user_id = message.from_user.id
    user_max = await db.get_user_max_price(user_id)
    villas = await db.search_villas(query, max_price=user_max, limit=50)
    if not villas:
        await message.answer(
            f"❌ По запросу <b>«{html.escape(query)}»</b> в Пафосе ничего не найдено.\n"
            "Попробуйте другое слово или район.",
            parse_mode="HTML"
        )
        return

    USER_SEARCH_CACHE[user_id] = villas
    await message.answer(f"🔍 Нашёл <b>{len(villas)}</b> вариантов по запросу «{html.escape(query)}». Показываю по одному:", parse_mode="HTML")
    await show_villa_card(message, user_id, index=0)


@router.message(F.text == "🏡 Продажа вилл (Пафос)")
async def show_villas_sale(message: Message):
    user_id = message.from_user.id
    villas = await db.get_latest_villas(category="sale_villa", max_price=50000000, limit=50)
    if not villas:
        await message.answer(
            "В настоящий момент объявлений по продаже вилл в Пафосе нет.\n"
            "Как только появится подходящее предложение, бот сразу пришлёт уведомление.",
            parse_mode="HTML"
        )
        return

    USER_SEARCH_CACHE[user_id] = villas
    await message.answer(f"🏡 Нашёл <b>{len(villas)}</b> вариантов продажи вилл в Пафосе. Показываю по одному:", parse_mode="HTML")
    await show_villa_card(message, user_id, index=0)


@router.message(F.text.in_({"🏢 Аренда вилл Пафос", "Аренда вилл Пафос", "🏢 Аренда вилл (Пафос)", "🏢 Аренда вилл", "🏢 Аренда вилл и квартир"}))
async def show_villas_rent(message: Message):
    user_id = message.from_user.id
    user_max = await db.get_user_max_price(user_id)
    villas = await db.get_latest_villas(category="rent_paphos", max_price=user_max, limit=50)
    if not villas:
        # Попробуем без ограничения цены, если с фильтром 0 вариантов
        villas_all = await db.get_latest_villas(category="rent_paphos", max_price=50000, limit=50)
        if villas_all:
            USER_SEARCH_CACHE[user_id] = villas_all
            await message.answer(
                f"ℹ️ С бюджетом до {user_max:,} € вариантов нет, поэтому показываю все свежие виллы (нашёл <b>{len(villas_all)}</b> вариантов). Показываю по одному:".replace(",", " "),
                parse_mode="HTML"
            )
            await show_villa_card(message, user_id, index=0)
            return

        await message.answer(
            "Сейчас нет актуальных объявлений по аренде вилл и домов в Пафосе.\n"
            "Мы уведомим вас сразу же после появления подходящих вариантов.",
            parse_mode="HTML"
        )
        return

    USER_SEARCH_CACHE[user_id] = villas
    await message.answer(f"🏢 Нашёл <b>{len(villas)}</b> вариантов аренды вилл в Пафосе (до {user_max:,} €). Показываю по одному:".replace(",", " "), parse_mode="HTML")
    await show_villa_card(message, user_id, index=0)


@router.message(F.text == "❓ Помощь")
async def show_help(message: Message):
    help_text = (
        "<b>Справочная информация</b>\n\n"
        "Бот автоматически отслеживает новые публикации в профильных каналах Кипра и строго отбирает виллы и дома в Пафосе (без квартир):\n\n"
        "• <b>🏡 Продажа вилл (Пафос)</b> — виллы и дома на продажу в Пафосе\n"
        "• <b>🏢 Аренда вилл Пафос</b> — свежие объявления аренды вилл и домов в Пафосе\n"
        "• <b>💰 Фильтр цены аренды</b> — установить персональный лимит бюджета для аренды\n"
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

    user_id = message.from_user.id
    user_max = await db.get_user_max_price(user_id)
    villas = await db.search_villas(query, max_price=user_max, limit=50)
    if not villas:
        await message.answer(
            f"❌ По запросу <b>«{html.escape(query)}»</b> в Пафосе ничего не найдено.\n"
            "Попробуйте другое слово или укажите другую сумму.",
            parse_mode="HTML"
        )
        return

    USER_SEARCH_CACHE[user_id] = villas

    if query.isdigit():
        header_text = f"🔍 Нашёл <b>{len(villas)}</b> вилл в аренду в пределах <b>{int(query):,} €</b>. Показываю по одному:".replace(",", " ")
    else:
        header_text = f"🔍 Нашёл <b>{len(villas)}</b> вариантов по запросу «{html.escape(query)}». Показываю по одному:"

    await message.answer(header_text, parse_mode="HTML")
    await show_villa_card(message, user_id, index=0)
