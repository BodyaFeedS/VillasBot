import asyncio
import logging
import html
import re
import aiohttp
from bs4 import BeautifulSoup
from aiogram import Bot
import config
import database as db
from ai_classifier import classify_post_smart as classify_post


async def fetch_channel_posts(session: aiohttp.ClientSession, channel: str, before_id: int | None = None) -> list[dict]:
    """
    Парсит публичную веб-страницу канала Telegram.
    Поддерживает как виджетную страницу t.me/s/, так и обычную страницу t.me/
    """
    url = f"https://t.me/s/{channel}"
    params = {}
    if before_id:
        params["before"] = str(before_id)
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    async with session.get(url, params=params, headers=headers, timeout=10) as resp:
        if resp.status != 200:
            logging.warning(f"Канал @{channel} вернул статус {resp.status}")
            return []
        html_content = await resp.text()

    soup = BeautifulSoup(html_content, "html.parser")
    posts = []

    messages = soup.select(".tgme_widget_message")
    if not messages:
        messages = soup.select(".tgme_channel_info, .tgme_page, [data-post]")

    for msg in messages:
        try:
            post_link_el = msg.select_one(".tgme_widget_message_date") or msg.select_one("a[href*='/']")
            if not post_link_el:
                continue
            post_url = post_link_el.get("href", "")
            post_id_match = re.search(r"/(\d+)$", post_url)
            if not post_id_match:
                continue
            post_id = int(post_id_match.group(1))

            text_el = msg.select_one(".tgme_widget_message_text") or msg.select_one(".message_text, p")
            if not text_el:
                continue
            text = text_el.get_text(separator="\n").strip()
            if not text:
                continue

            posts.append({
                "id": post_id,
                "url": post_url,
                "text": text,
                "channel": channel
            })
        except Exception as e:
            logging.debug(f"Ошибка парсинга поста в @{channel}: {e}")

    return posts


async def notify_users(bot: Bot, villa_data: dict, category: str, price: int):
    """
    Рассылает новое объявление всем подписчикам в естественном человеческом формате.
    """
    users = await db.get_all_users()
    title_map = {
        "sale_villa": "🏡 Продажа виллы (Пафос)",
        "rent_paphos": "🏢 Аренда жилья (Пафос)",
        "currency_exchange": "💱 Обмен валют"
    }
    title = title_map.get(category, "Новое объявление")
    price_str = f"{price:,} €".replace(",", " ") if category != "currency_exchange" else f"{price:,}".replace(",", " ")
    price_label = "💰 Стоимость:" if category != "currency_exchange" else "💰 Сумма:"

    raw_snippet = villa_data["text"][:350].strip()
    if len(villa_data["text"]) > 350:
        raw_snippet += "..."
    text_snippet = html.escape(raw_snippet)

    for user_id in users:
        try:
            if category == "rent_paphos":
                user_limit = await db.get_user_max_price(user_id)
                if price > user_limit:
                    continue
            elif category == "currency_exchange":
                exchange_limit = await db.get_user_exchange_limit(user_id)
                if price > exchange_limit:
                    continue

            msg_text = (
                f"<b>{title}</b>\n"
                f"📍 Источник: @{villa_data['channel']}\n\n"
                f"<b>{price_label} {price_str}</b>\n\n"
                f"{text_snippet}\n\n"
                f"👉 <a href='{villa_data['url']}'>Перейти к объявлению</a>"
            )
            await bot.send_message(
                chat_id=user_id,
                text=msg_text,
                parse_mode="HTML",
                disable_web_page_preview=True
            )
        except Exception as e:
            logging.debug(f"Не удалось отправить сообщение пользователю {user_id}: {e}")


async def check_channels_once(bot: Bot, session: aiohttp.ClientSession):
    for channel in config.CHANNELS:
        ch_clean = channel.strip()
        if not ch_clean:
            continue
        try:
            posts = await fetch_channel_posts(session, ch_clean)
            for post in posts:
                matches = await classify_post(post["text"], channel=ch_clean)
                for cat, price in matches:
                    is_new = await db.add_villa(
                        channel=ch_clean,
                        post_id=post["id"],
                        price=price,
                        text=post["text"],
                        url=post["url"],
                        category=cat
                    )
                    if is_new:
                        await notify_users(bot, post, cat, price)
        except Exception as e:
            logging.error(f"Ошибка при проверке канала @{ch_clean}: {e}")


async def start_monitoring(bot: Bot):
    logging.info("Мониторинг каналов запущен...")
    async with aiohttp.ClientSession() as session:
        while True:
            try:
                await check_channels_once(bot, session)
            except Exception as e:
                logging.error(f"Ошибка в цикле мониторинга: {e}")
            await asyncio.sleep(config.CHECK_INTERVAL)
