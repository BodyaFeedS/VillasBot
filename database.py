import aiosqlite
import logging
import re
from datetime import datetime
import config

DB_PATH = "villas.db"


async def clean_non_paphos_and_exchange():
    """
    Удаляет из базы старые записи, которые не относятся к Пафосу, являются обменом валют
    или являются обычными квартирами/апартаментами (не виллами).
    """
    from ai_classifier import is_paphos_location, is_apartment_only
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM villas WHERE category = 'currency_exchange'")
        async with db.execute("SELECT id, text FROM villas") as cursor:
            rows = await cursor.fetchall()
            ids_to_delete = []
            for row_id, text in rows:
                if not is_paphos_location(text) or is_apartment_only(text):
                    ids_to_delete.append(row_id)
            for rid in ids_to_delete:
                await db.execute("DELETE FROM villas WHERE id = ?", (rid,))
                await db.execute("DELETE FROM favorites WHERE villa_id = ?", (rid,))
        await db.commit()
    logging.info(f"✅ [DATABASE] База очищена. Удалено записей чужих городов, валюты и квартир: {len(ids_to_delete)}")


async def init_db():
    """Инициализация таблиц базы данных SQLite (вечная история, пользователи и избранное)."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                max_price INTEGER DEFAULT 600,
                exchange_limit INTEGER DEFAULT 50000,
                created_at TEXT
            )
        """)
        try:
            await db.execute("ALTER TABLE users ADD COLUMN max_price INTEGER DEFAULT 600")
        except Exception:
            pass
        try:
            await db.execute("ALTER TABLE users ADD COLUMN exchange_limit INTEGER DEFAULT 50000")
        except Exception:
            pass

        await db.execute("""
            CREATE TABLE IF NOT EXISTS villas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel TEXT NOT NULL,
                post_id INTEGER NOT NULL,
                price INTEGER NOT NULL,
                text TEXT NOT NULL,
                url TEXT NOT NULL,
                category TEXT DEFAULT 'rent_paphos',
                created_at TEXT NOT NULL,
                UNIQUE(channel, post_id, category)
            )
        """)
        try:
            await db.execute("ALTER TABLE villas ADD COLUMN category TEXT DEFAULT 'rent_paphos'")
        except Exception:
            pass

        await db.execute("""
            CREATE TABLE IF NOT EXISTS favorites (
                user_id INTEGER NOT NULL,
                villa_id INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (user_id, villa_id)
            )
        """)

        await db.commit()
    logging.info("База данных SQLite успешно инициализирована.")
    try:
        await clean_non_paphos_and_exchange()
    except Exception as e:
        logging.warning(f"Ошибка очистки базы: {e}")


async def add_user(user_id: int, max_price: int = config.MAX_PRICE, exchange_limit: int = config.DEFAULT_EXCHANGE_LIMIT):
    """Добавляет пользователя в базу для отправки уведомлений."""
    try:
        max_price_val = int(max_price)
    except (ValueError, TypeError):
        max_price_val = config.MAX_PRICE

    try:
        ex_limit_val = int(exchange_limit)
    except (ValueError, TypeError):
        ex_limit_val = config.DEFAULT_EXCHANGE_LIMIT

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT OR IGNORE INTO users (user_id, max_price, exchange_limit, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (user_id, max_price_val, ex_limit_val, datetime.now().isoformat())
        )
        await db.commit()


async def get_user_max_price(user_id: int) -> int:
    """Возвращает максимальную цену аренды, установленную пользователем."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT max_price FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            if row and row[0]:
                try:
                    return int(row[0])
                except (ValueError, TypeError):
                    pass
            return config.MAX_PRICE


async def get_user_exchange_limit(user_id: int) -> int:
    """Возвращает максимальную сумму/лимит обмена, установленный пользователем."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT exchange_limit FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            if row and row[0]:
                try:
                    return int(row[0])
                except (ValueError, TypeError):
                    pass
            return config.DEFAULT_EXCHANGE_LIMIT


async def update_user_max_price(user_id: int, max_price: int):
    """Обновляет максимальную цену аренды для конкретного пользователя."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO users (user_id, max_price, exchange_limit, created_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET max_price = excluded.max_price
            """,
            (user_id, max_price, config.DEFAULT_EXCHANGE_LIMIT, datetime.now().isoformat())
        )
        await db.commit()


async def update_user_exchange_limit(user_id: int, exchange_limit: int):
    """Обновляет персональный фильтр суммы/цены для обмена валют."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO users (user_id, max_price, exchange_limit, created_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET exchange_limit = excluded.exchange_limit
            """,
            (user_id, config.MAX_PRICE, exchange_limit, datetime.now().isoformat())
        )
        await db.commit()


async def get_users_for_price(price: int) -> list[int]:
    """Возвращает список ID пользователей, у которых установленный фильтр max_price >= цене виллы."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT user_id, max_price FROM users") as cursor:
            rows = await cursor.fetchall()
            valid_users = []
            for uid, mp in rows:
                try:
                    val = int(mp)
                    if val >= price:
                        valid_users.append(uid)
                except (ValueError, TypeError):
                    if config.MAX_PRICE >= price:
                        valid_users.append(uid)
            return valid_users


async def get_users_for_exchange_limit(amount: int) -> list[int]:
    """Возвращает список ID пользователей, у которых лимит обмена валют >= суммы."""
    async with aiosqlite.connect(DB_PATH) as db:
        if amount == 0:
            async with db.execute("SELECT user_id FROM users") as cursor:
                rows = await cursor.fetchall()
                return [row[0] for row in rows]
        async with db.execute("SELECT user_id, exchange_limit FROM users") as cursor:
            rows = await cursor.fetchall()
            valid_users = []
            for uid, el in rows:
                try:
                    val = int(el)
                    if val >= amount:
                        valid_users.append(uid)
                except (ValueError, TypeError):
                    if config.DEFAULT_EXCHANGE_LIMIT >= amount:
                        valid_users.append(uid)
            return valid_users


async def get_all_users() -> list[int]:
    """Возвращает список всех ID пользователей (для уведомлений о продаже вилл)."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT user_id FROM users") as cursor:
            rows = await cursor.fetchall()
            return [row[0] for row in rows]


async def is_duplicate_post(text: str, category: str) -> bool:
    """
    Проверяет, было ли уже сохранено объявление с таким же или аналогичным текстом в этой категории.
    """
    norm_new = re.sub(r'\s+', ' ', text.strip().lower())[:120]
    if len(norm_new) < 15:
        return False

    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT text FROM villas WHERE category = ? ORDER BY id DESC LIMIT 500", (category,)) as cursor:
            rows = await cursor.fetchall()
            for row in rows:
                norm_old = re.sub(r'\s+', ' ', row[0].strip().lower())[:120]
                if norm_new == norm_old:
                    return True
            return False


async def add_villa(channel: str, post_id: int, price: int, text: str, url: str, category: str = "rent_paphos") -> bool:
    """
    Сохраняет пост в БД, если его ещё нет в базе для данной категории,
    если текст не является дубликатом, если он относится к Пафосу и если это не квартира.
    """
    from ai_classifier import is_paphos_location, is_apartment_only
    if not is_paphos_location(text) or is_apartment_only(text):
        return False

    if await is_duplicate_post(text, category):
        return False

    async with aiosqlite.connect(DB_PATH) as db:
        try:
            await db.execute(
                """
                INSERT INTO villas (channel, post_id, price, text, url, category, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (channel, post_id, price, text, url, category, datetime.now().strftime("%d.%m.%Y %H:%M"))
            )
            await db.commit()
            return True
        except aiosqlite.IntegrityError:
            return False


async def get_latest_villas(category: str = "rent_paphos", max_price: int = 50000, limit: int = 15) -> list[dict]:
    """
    Возвращает сохраненные записи, отфильтрованные по категории,
    гарантируя, что выдаются только виллы/дома из Пафоса (без квартир).
    """
    from ai_classifier import is_paphos_location, is_apartment_only
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        if category == "sale_villa":
            query = """
                SELECT id, channel, post_id, price, text, url, category, created_at
                FROM villas
                WHERE category = ?
                ORDER BY id DESC
                LIMIT ?
            """
            params = (category, limit * 4)
        else:
            query = """
                SELECT id, channel, post_id, price, text, url, category, created_at
                FROM villas
                WHERE category = ? AND price <= ?
                ORDER BY id DESC
                LIMIT ?
            """
            params = (category, max_price, limit * 4)

        async with db.execute(query, params) as cursor:
            rows = await cursor.fetchall()
            villas = [dict(row) for row in rows]
            paphos_villas = [
                v for v in villas
                if is_paphos_location(v.get("text", "")) and not is_apartment_only(v.get("text", ""))
            ]
            return paphos_villas[:limit]


async def add_favorite(user_id: int, villa_id: int) -> bool:
    """Добавляет объявление в Избранное."""
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            await db.execute(
                "INSERT INTO favorites (user_id, villa_id, created_at) VALUES (?, ?, ?)",
                (user_id, villa_id, datetime.now().strftime("%d.%m.%Y %H:%M"))
            )
            await db.commit()
            return True
        except aiosqlite.IntegrityError:
            return False


async def get_user_favorites(user_id: int, limit: int = 30) -> list[dict]:
    """Возвращает избранные объявления пользователя."""
    from ai_classifier import is_paphos_location, is_apartment_only
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        query = """
            SELECT v.id, v.channel, v.post_id, v.price, v.text, v.url, v.category, v.created_at
            FROM favorites f
            JOIN villas v ON f.villa_id = v.id
            WHERE f.user_id = ?
            ORDER BY v.id DESC
            LIMIT ?
        """
        async with db.execute(query, (user_id, limit * 2)) as cursor:
            rows = await cursor.fetchall()
            villas = [dict(row) for row in rows]
            paphos_villas = [
                v for v in villas
                if is_paphos_location(v.get("text", "")) and not is_apartment_only(v.get("text", ""))
            ]
            return paphos_villas[:limit]


async def search_villas(query: str, max_price: int = 50000, limit: int = 25) -> list[dict]:
    """
    Умный поиск по ключевым словам или ценам в текстах объявлений Пафоса.
    1. Если введено число (например '3000' или '5000'), возвращает аренду вилл с ценой <= этому числу.
    2. Если введены общие слова ('аренда вилла пафос', 'продам'), возвращает все свежие записи этой категории.
    3. Иначе проверяет вхождение каждого поискового слова в текст объявления.
    """
    from ai_classifier import is_paphos_location, is_apartment_only
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        query_clean = query.strip()
        query_lower = query_clean.lower()

        # 1. Если пользователь ввел число (например "3000" или "5000") — ищем все виллы в аренду с ценой <= числу
        if query_clean.isdigit():
            num_val = int(query_clean)
            sql = """
                SELECT id, channel, post_id, price, text, url, category, created_at
                FROM villas
                WHERE category = 'rent_paphos' AND price <= ?
                ORDER BY id DESC
                LIMIT ?
            """
            async with db.execute(sql, (num_val, limit * 4)) as cursor:
                rows = await cursor.fetchall()
                villas = [dict(row) for row in rows]
                paphos_villas = [
                    v for v in villas
                    if is_paphos_location(v.get("text", "")) and not is_apartment_only(v.get("text", ""))
                ]
                return paphos_villas[:limit]

        # 2. Определяем категорию (продажа или аренда)
        is_sale_query = any(kw in query_lower for kw in ("продам", "продаж", "купить", "sale", "прода", "покупк"))
        target_cat = "sale_villa" if is_sale_query else "rent_paphos"

        if target_cat == "sale_villa":
            sql = "SELECT id, channel, post_id, price, text, url, category, created_at FROM villas WHERE category = 'sale_villa' ORDER BY id DESC LIMIT ?"
            params = (limit * 6,)
        else:
            sql = "SELECT id, channel, post_id, price, text, url, category, created_at FROM villas WHERE category = 'rent_paphos' AND price <= ? ORDER BY id DESC LIMIT ?"
            params = (max_price, limit * 6)

        async with db.execute(sql, params) as cursor:
            rows = await cursor.fetchall()
            villas = [dict(row) for row in rows]

        # Фильтруем только Пафос и без квартир
        villas = [
            v for v in villas
            if is_paphos_location(v.get("text", "")) and not is_apartment_only(v.get("text", ""))
        ]

        # 3. Проверяем слова поискового запроса
        generic_words = {
            "аренда", "аренды", "аренду", "арендовать", "сдам", "сдаю", "сдается", "сдаётся", "rent",
            "продам", "продажа", "продаже", "продаю", "купить", "sale",
            "вилла", "виллы", "виллу", "вилл", "дом", "дома", "коттедж", "villa", "house",
            "пафос", "пафосе", "paphos", "pafos"
        }

        words = [w for w in re.findall(r'\w+', query_lower) if len(w) >= 2]
        specific_words = [w for w in words if w not in generic_words]

        if not specific_words:
            # Запрос содержал только общие слова категории и локации (например "Аренда вилла Пафос")
            return villas[:limit]

        # Иначе каждое специфичное слово должно быть в тексте
        matched_villas = []
        for v in villas:
            text_lower = (v.get("text") or "").lower()
            if all(sw in text_lower for sw in specific_words):
                matched_villas.append(v)

        return matched_villas[:limit]
