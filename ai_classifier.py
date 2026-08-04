import re
import os
import json
import logging
import aiohttp
import config

MIN_PRICE_THRESHOLD = 150
MAX_STORE_PRICE = 20000

# Строгий регулярный выражение для поиска ВИЛЛ и ДОМОВ с границами слов \b
# Чтобы слово "дом" НЕ совпадало внутри слов "видом", "рядом", "поездом", "ходом"!
VILLA_REGEX = re.compile(
    r'\b(вилл[а-я]*|дом[ауеов]*|дома|доме|домов|коттедж[а-я]*|особняк[а-я]*|таунхаус[а-я]*|бунгало|мезонет[а-я]*|villa[s]?|house[s]?|townhouse[s]?|bungalow[s]?)\b',
    re.IGNORECASE
)


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
    Епископи, а также популярные районы Лимасола/Ларнаки.
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
        "фамагуст", "famagust", "кирени", "kyrenia",
        "епископи", "episkopi", "епископие"
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
        "полис", "polis", "афродита", "aphrodite",
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
    Отсеивает объявления, где сдаются/продаются квартиры, апартаменты или студии,
    если это НЕ вилла или дом.
    Использует строгий поиск VILLA_REGEX (чтобы "дом" не совпадал внутри "видом на море" или "рядом").
    """
    text_lower = text.lower()
    flat_words = [
        "квартир", "апартамент", "студи", "flat", "apartment", "studio",
        "#квартира", "#апартаменты", "#студия",
        "1-комн", "2-комн", "3-комн", "однокомнат", "двухкомнат", "трехкомнат"
    ]
    has_flat = any(fw in text_lower for fw in flat_words)
    has_villa = bool(VILLA_REGEX.search(text_lower))
    return has_flat and not has_villa


def is_property_for_sale(text: str) -> bool:
    """
    Проверка, что объявление о ПРОДАЖЕ недвижимости (а не аренда!).
    Требует явных слов продажи или покупки, исключая аренду.
    """
    text_norm = normalize_prices_in_text(text)
    text_lower = text_norm.lower()

    rent_keywords = ["сдам", "сдается", "сдаётся", "аренд", "в аренду", "долгосрок", "посуточно"]
    if any(rk in text_lower for rk in rent_keywords):
        # Если явно сказано "сдается в аренду", это не продажа
        return False

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
    """
    Извлечение стоимости ПРОДАЖИ виллы в евро (от 50 000 до 50 000 000 €).
    Если цена продажи не найдена, возвращает 0.
    """
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


def get_villa_intent(text: str) -> str | None:
    """
    Интеллектуальная классификация категории: 'SALE' (продажа виллы) или 'RENT' (аренда виллы).
    Гарантирует 100% взаимную исключительность:
    - Аренда никогда не станет продажей.
    - Продажа никогда не станет арендой.
    """
    text_lower = text.lower()

    # 1. Сильные маркеры ПРОДАЖИ (хештеги и однозначные фразы)
    strong_sale_markers = [
        "#продам", "#продажа", "#продается", "#sale", "#forsale",
        "продам вилл", "продается вилл", "продаётся вилл", "продажа вилл",
        "продам дом", "продается дом", "продаётся дом", "продажа дом",
        "купить вилл", "купить дом", "for sale", "титул в наличии",
        "собственность от застройщика", "цена продажи"
    ]
    is_strong_sale = any(m in text_lower for m in strong_sale_markers)

    # 2. Сильные маркеры АРЕНДЫ (хештеги и однозначные фразы)
    strong_rent_markers = [
        "#аренда", "#сдам", "#сдается", "#сдаётся", "#rent", "#forrent",
        "сдам вилл", "сдается вилл", "сдаётся вилл", "аренда вилл",
        "сдам дом", "сдается дом", "сдаётся дом", "аренда дом",
        "на длительный срок", "долгосрок", "посуточно", "в месяц", "/мес", "per month"
    ]
    is_strong_rent = any(m in text_lower for m in strong_rent_markers)

    # 3. Извлекаем цены
    sale_price = extract_sale_price(text)       # числа >= 50 000
    rent_price = extract_rental_price(text)     # числа <= 15 000

    # Если есть сильный маркер продажи И нет сильного маркера аренды
    if is_strong_sale and not is_strong_rent:
        return "SALE"

    # Если есть сильный маркер аренды И нет сильного маркера продажи
    if is_strong_rent and not is_strong_sale:
        return "RENT"

    # Если в тексте указана цена >= 50 000 — это однозначно ПРОДАЖА (даже если упомянута аренда как инвестиция)
    if sale_price >= 50000:
        return "SALE"

    # Если указана цена <= 15 000 и нет большой цены продажи — это АРЕНДА
    if rent_price is not None and rent_price <= 15000:
        return "RENT"

    # Если остались общие слова
    general_sale = any(w in text_lower for w in ["продам", "продажа", "продается", "купить", "selling"])
    general_rent = any(w in text_lower for w in ["сдам", "сдается", "аренд", "долгосрок", "letting"])

    if general_sale and not general_rent:
        return "SALE"
    if general_rent and not general_sale:
        return "RENT"

    return None


def is_sale_villa_paphos(text: str) -> bool:
    """
    #Продам #Вилла #Пафос (строго Пафос и пригороды, без квартир, с использованием VILLA_REGEX).
    Использует get_villa_intent == 'SALE', чтобы аренда НИКОГДА не попала в продажу.
    """
    if is_seeking_housing(text) or not is_paphos_location(text) or is_apartment_only(text):
        return False

    if not VILLA_REGEX.search(text):
        return False

    if get_villa_intent(text) != "SALE":
        return False

    return True


def is_rent_paphos(text: str, max_price: int = MAX_STORE_PRICE) -> tuple[bool, int | None]:
    """
    #аренда #вилла #пафос (строго аренда ВИЛЛ и ДОМОВ в Пафосе, БЕЗ КВАРТИР!).
    Использует get_villa_intent == 'RENT', чтобы продажа НИКОГДА не попала в аренду.
    """
    if is_seeking_housing(text) or not is_paphos_location(text) or is_apartment_only(text):
        return False, None

    if not VILLA_REGEX.search(text):
        return False, None

    if get_villa_intent(text) != "RENT":
        return False, None

    price = extract_rental_price(text, max_price=max_price)
    actual_price = price if price is not None else 0
    if actual_price <= max_price:
        return True, actual_price

    return False, None


def classify_post_nlp(text: str, channel: str = "", max_price: int = MAX_STORE_PRICE) -> list[tuple[str, int]]:
    """
    Классифицирует публикации строго на ВИЛЛЫ и ДОМА в Пафосе (без квартир!):
    1) rent_paphos (аренда вилл и домов в Пафосе)
    2) sale_villa (продажа вилл и домов в Пафосе)
    Аренда и продажа строго взаимоисключаются.
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
    """
    Интеллектуальная классификация (с гарантией, что аренда не попадает в продажу и наоборот).
    """
    return classify_post_nlp(text, channel, max_price=MAX_STORE_PRICE)
