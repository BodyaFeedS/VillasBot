import aiosqlite
import logging
import re
from datetime import datetime
import config

DB_PATH = "villas.db"


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

        # Таблица для закладок / избранного
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
            "INSERT OR IGNORE INTO users (user_id, max_price, exchange_limit, created_at) VALUES (?, ?, ?, ?)",
            (user_id, max_price_val, ex_limit_val, datetime.now().isoformat())
        )
        await db.commit()


async def get_user_max_price(user_id: int) -> int:
    """Возвращает текущую установленную максимальную цену аренды для пользователя."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT max_price FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            if row and row[0] is not None:
                try:
                    return int(row[0])
                except (ValueError, TypeError):
                    return config.MAX_PRICE
            return config.MAX_PRICE


async def get_user_exchange_limit(user_id: int) -> int:
    """Возвращает текущий установленный лимит суммы для обмена валют/крипты."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT exchange_limit FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            if row and row[0] is not None:
                try:
                    return int(row[0])
                except (ValueError, TypeError):
                    return config.DEFAULT_EXCHANGE_LIMIT
            return config.DEFAULT_EXCHANGE_LIMIT


async def update_user_max_price(user_id: int, max_price: int):
    """Обновляет персональный фильтр цены аренды для пользователя."""
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
    Предотвращает пересылку и дублирование повторяющихся сообщений!
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
    Сохраняет пост в БД, если его ещё нет в базе для данной категории и если текст не является дубликатом.
    """
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


async def get_latest_villas(category: str = "rent_paphos", max_price: int = 600, limit: int = 15) -> list[dict]:
    """
    Возвращает сохраненные записи, отфильтрованные по категории и по максимальной цене / сумме обмена.
    """
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
            params = (category, limit)
        elif category == "currency_exchange":
            query = """
                SELECT id, channel, post_id, price, text, url, category, created_at
                FROM villas
                WHERE category = ? AND (price <= ? OR price = 0)
                ORDER BY id DESC
                LIMIT ?
            """
            params = (category, max_price, limit)
        else:
            query = """
                SELECT id, channel, post_id, price, text, url, category, created_at
                FROM villas
                WHERE category = ? AND price <= ?
                ORDER BY id DESC
                LIMIT ?
            """
            params = (category, max_price, limit)

        async with db.execute(query, params) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]


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
        async with db.execute(query, (user_id, limit)) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]


async def search_villas(query: str, max_price: int = 50000, limit: int = 25) -> list[dict]:
    """
    Поиск по ключевым словам в тексте объявлений.
    Если запрос не содержит слов 'продам'/'продажа'/'купить'/'sale', ищем только в аренде (rent_paphos) с фильтром price <= max_price!
    Исключает попадание продажи недвижимости в результаты поиска аренды!
    """
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        query_lower = query.lower()
        is_sale_query = any(kw in query_lower for kw in ("продам", "продаж", "купить", "sale", "прода"))

        if is_sale_query:
            sql = """
                SELECT id, channel, post_id, price, text, url, category, created_at
                FROM villas
                WHERE text LIKE ? AND category = 'sale_villa'
                ORDER BY id DESC
                LIMIT ?
            """
            params = (f"%{query}%", limit)
        else:
            sql = """
                SELECT id, channel, post_id, price, text, url, category, created_at
                FROM villas
                WHERE text LIKE ? AND category = 'rent_paphos' AND price <= ?
                ORDER BY id DESC
                LIMIT ?
            """
            params = (f"%{query}%", max_price, limit)

        async with db.execute(sql, params) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]
