import re
import os
import json
import logging
import aiohttp
import config

MIN_PRICE_THRESHOLD = 150
MAX_STORE_PRICE = 20000


def normalize_prices_in_text(text: str) -> str:
    """
    Нормализует цены, записанные через запятую или пробел:
    €1,350 -> €1350
    €4,300 -> €4300
    1,350 € -> 1350 €
    1 350 € -> 1350 €
    от 1,000 -> от 1000
    """
    def repl_comma(m):
        return m.group(1) + m.group(2)
    return re.sub(r'\b(\d{1,3})[,_ ](\d{3})\b', repl_comma, text)


def is_other_city(text: str) -> bool:
    """
    Проверяет, что объявление относится к ЛЮБОМУ ДРУГОМУ городу Кипра (Не Пафос):
    Лимасол, Лимассол, Ларнака, Никосия, Айя-Напа, Протарас, Фамагуста, Кирения,
    а также популярные районы Лимасола (Агиос Тихонас, Гермасойя, Муттаяка и др.).
    """
    text_lower = text.lower()
    other_cities = [
        "лимассол", "лимасол", "лимасоле", "лимассоле", "limassol", "limasol",
        "#лимасол", "#лимассол", "агиос тихонас", "agios tychonas",
        "гермасой", "germasogeia", "мутаяк", "mouttagiaka", "пиргос", "pyrgos",
        "парекклис", "parekklisia", "ороклин", "oroklini", "пила", "pyla",
        "ларнак", "ларнаке", "larnac", "#ларнака",
        "никоси", "никосие", "nicosi", "#никосия",
        "айя-нап", "ayia", "#айянапа",
        "протарас", "protaras", "#протарас",
        "фамагуст", "famagust", "кирени", "kyrenia"
    ]
    return any(city in text_lower for city in other_cities)


def is_paphos_location(text: str) -> bool:
    """
    Строгая проверка: объявление должно относиться исключительно к Пафосу или его пригородам
    и НЕ содержать упоминаний других городов или районов Лимасола/Ларнаки/Никосии.
    """
    if is_other_city(text):
        return False

    text_lower = text.lower()
    paphos_keywords = [
        "пафос", "paphos", "pafos", "#пафос", "#paphos",
        "тала", "tala", "хлорак", "chlorak", "пейя", "pegeia", "peyia",
        "кония", "konia", "емба", "emba", "киссонерг", "kissonerg",
        "аргак", "като пафос", "цада", "tsada", "героскипу", "geroskipou",
        "епископи", "полис", "polis", "афродита", "aphrodite",
        "корал бэй", "coral bay", "mandria", "мандрия", "анавита",
        "куклия", "kouklia", "пейе", "тале", "хлораке"
    ]
    return any(kw in text_lower for kw in paphos_keywords)


def is_seeking_housing(text: str) -> bool:
    """
    Отсеивает объявления, где люди ИЩУТ жильё в аренду/покупку:
    сниму, ищу, ищем, нужна квартира...
    """
    text_lower = text.lower()
    seek_terms = [
        "сниму", "снимем", "снимет", "#сниму",
        "ищу ", "ищу\n", "ищем ", "ищет ", "#ищу", "#ищем",
        "поиск жилья", "нужна квартира", "нужны апартаменты",
        "нужно жилье", "нужно жильё", "кто сдаст", "кто сдает",
        "сним.", "looking for", "wanted to rent"
    ]
    return any(term in text_lower for term in seek_terms)


def is_apartment_only(text: str) -> bool:
    """
    Отсеивает объявления, где сдаются/продаются исключительно квартиры, апартаменты или студии
    (без упоминания вилл, домов, коттеджей или таунхаусов).
    """
    text_lower = text.lower()
    flat_words = [
        "квартир", "апартамент", "студи", "flat", "apartment", "studio",
        "#квартира", "#апартаменты", "#студия",
        "1-комн", "2-комн", "3-комн", "однокомнат", "двухкомнат", "трехкомнат"
    ]
    villa_words = [
        "вилл", "дом", "коттедж", "особняк", "villa", "house",
        "таунхаус", "townhouse", "бунгало", "мезонет", "#вилла", "#дом"
    ]
    has_flat = any(fw in text_lower for fw in flat_words)
    has_villa = any(vw in text_lower for vw in villa_words)
    return has_flat and not has_villa


def is_property_for_sale(text: str) -> bool:
    """
    100% гарантированная проверка, что объявление о ПРОДАЖЕ недвижимости (а не аренда!):
    1. Если указана любая цена >= 15 000 € -> это ПРОДАЖА!
    2. Ключевые слова продажи: продам, продажа, продается, рассрочка, без ндс, vat, титул...
    """
    text_norm = normalize_prices_in_text(text)
    text_lower = text_norm.lower()

    all_numbers = re.findall(r'\b(\d{5,8})\b', text_lower)
    for num_str in all_numbers:
        try:
            val = int(num_str)
            if val >= 15000:
                return True
        except ValueError:
            pass

    sale_keywords = [
        "продам", "продается", "продаётся", "продажа", "продаже", "продаю", "продаж", "продад", "продаем", "продаём",
        "купить", "покупк", "купи", "собственност", "застройщик", "вложение", "инвестиц",
        "for sale", "selling", "#продам", "#продажа",
        "рассрочк", "без ндс", "с ндс", "vat", "титул", "титульный",
        "предлагается эксклюзивная вилла"
    ]
    return any(kw in text_lower for kw in sale_keywords)


def extract_rental_price(text: str, max_price: int = MAX_STORE_PRICE) -> int | None:
    """
    Точное извлечение стоимости АРЕНДЫ вилл и домов в евро.
    """
    text_norm = normalize_prices_in_text(text)
    text_lower = text_norm.lower()

    patterns = [
        r'(?:€|eur|евро|euro)\s*#?(\d{2,5})',
        r'#?(\d{2,5})\s*(?:€|eur|евро|euro|е\b|евр)',
        r'#?до\s*(?:€|eur|евро|euro)?\s*#?(\d{2,5})',
        r'цена\s*(?:-|=|:)?\s*#?(\d{2,5})',
        r'#€(\d{2,5})',
        r'#(\d{2,5})€',
        r'\b(\d{2,5})\s*(?:в месяц|за месяц|/мес|/month|в мес|мес|в сутки|за ночь|посуточно|/ночь|/сутки|сутки|ночь)'
    ]
    found_prices = []
    invalid_words = ("кв.м", "кв. м", "кв м", "m2", "м2", "метро", "участок", "площад", "соток", "$", "usd", "баксов", "доллар", "этаж")

    for pat in patterns:
        matches = re.findall(pat, text_lower)
        for m in matches:
            try:
                val = int(m)
                if 50 <= val <= max_price:
                    idx = text_lower.find(str(val))
                    start_sub = max(0, idx - 25)
                    end_sub = min(len(text_lower), idx + 25)
                    context_str = text_lower[start_sub:end_sub]
                    if not any(w in context_str for w in invalid_words):
                        found_prices.append(val)
            except ValueError:
                pass

    if not found_prices:
        all_nums = re.findall(r'\b(\d{2,5})\b', text_lower)
        for m in all_nums:
            try:
                val = int(m)
                if 50 <= val <= min(max_price, 15000):
                    idx = text_lower.find(str(val))
                    start_sub = max(0, idx - 25)
                    end_sub = min(len(text_lower), idx + 25)
                    context_str = text_lower[start_sub:end_sub]
                    if not any(w in context_str for w in invalid_words) and "202" not in str(val):
                        found_prices.append(val)
            except ValueError:
                pass

    if found_prices:
        return min(found_prices)
    return None


def extract_sale_price(text: str) -> int:
    text_norm = normalize_prices_in_text(text)
    text_lower = text_norm.lower()
    all_numbers = re.findall(r'\b(\d{5,8})\b', text_lower)
    prices = []
    for num_str in all_numbers:
        try:
            val = int(num_str)
            if 50000 <= val <= 50000000:
                prices.append(val)
        except ValueError:
            pass
    return max(prices) if prices else 0


def is_sale_villa_paphos(text: str) -> bool:
    """
    #Продам #Вилла #Пафос (строго Пафос и пригороды, без Лимасола, Ларнаки и без обычных квартир!).
    """
    if is_seeking_housing(text) or not is_paphos_location(text) or is_apartment_only(text):
        return False

    text_lower = text.lower()
    if not is_property_for_sale(text):
        return False

    villa_keywords = [
        "вилл", "дом", "коттедж", "особняк", "villa", "house", "#вилла"
    ]
    return any(kw in text_lower for kw in villa_keywords)


def is_rent_paphos(text: str, max_price: int = MAX_STORE_PRICE) -> tuple[bool, int | None]:
    """
    #аренда #вилла #пафос (строго аренда ВИЛЛ и ДОМОВ в Пафосе, БЕЗ КВАРТИР!).
    Если это продажа (is_property_for_sale == True) или квартира (is_apartment_only == True), объявление отсеивается!
    """
    if is_property_for_sale(text) or is_seeking_housing(text) or not is_paphos_location(text) or is_apartment_only(text):
        return False, None

    text_lower = text.lower()

    rent_keywords = [
        "аренд", "сдам", "сдаем", "сдаём", "сдается", "сдаётся", "сдаю", "сдать",
        "rent", "for rent", "letting", "долгосрок", "посуточно", "за ночь", "в сутки", "за сутки",
        "на сутки", "/ночь", "/сутки", "per night", "на месяц", "#аренда",
        "вилл", "дом", "коттедж", "особняк", "villa", "house", "таунхаус", "townhouse", "бунгало"
    ]
    has_rent = any(kw in text_lower for kw in rent_keywords)
    price = extract_rental_price(text, max_price=max_price)

    if price is not None and price <= max_price and (has_rent or "nedvizhka" in text_lower):
        return True, price

    return False, None


def classify_post_nlp(text: str, channel: str = "", max_price: int = MAX_STORE_PRICE) -> list[tuple[str, int]]:
    """
    Классифицирует публикации строго на ВИЛЛЫ и ДОМА в Пафосе (без квартир!):
    1) rent_paphos (аренда вилл и домов в Пафосе)
    2) sale_villa (продажа вилл и домов в Пафосе)
    """
    matched = []

    is_rent, rent_price = is_rent_paphos(text, max_price=max_price)
    if is_rent and rent_price is not None:
        matched.append(("rent_paphos", rent_price))

    if is_sale_villa_paphos(text):
        price = extract_sale_price(text)
        matched.append(("sale_villa", price))

    return matched


async def classify_post_smart(text: str, channel: str = "") -> list[tuple[str, int]]:
    return classify_post_nlp(text, channel, max_price=MAX_STORE_PRICE)
