"""
Работа с базой данных (SQLite через aiosqlite).

Таблицы:
- users         — пользователи Telegram и флаг активации
- access_codes  — 5000 одноразовых кодов доступа (формат WRN-XXXX-XXXX-XXXX-XXXX)
- sessions      — задел под учёт рассылок (Этап 4)

Логика кодов:
- код одноразовый: при активации привязывается к user_id (used_by)
- повторно тот же код использовать нельзя
- активированный юзер узнаётся по Telegram ID и заходит без повторного ввода
"""
import aiosqlite

from config import config


async def init_db() -> None:
    """Создаёт таблицы, если их ещё нет. Вызывается при старте бота."""
    async with aiosqlite.connect(config.db_path) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id     INTEGER PRIMARY KEY,
                username    TEXT,
                activated   INTEGER NOT NULL DEFAULT 0,
                code_used   TEXT,
                created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS access_codes (
                code        TEXT PRIMARY KEY,
                used_by     INTEGER,
                used_at     TIMESTAMP
            )
            """
        )
        # Задел под Этап 4 — учёт сессий рассылок.
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL,
                platform    TEXT,
                limit_count INTEGER,
                sent        INTEGER NOT NULL DEFAULT 0,
                replies     INTEGER NOT NULL DEFAULT 0,
                status      TEXT NOT NULL DEFAULT 'created',
                created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        await db.commit()


# ---------- Пользователи ----------

async def ensure_user(user_id: int, username) -> None:
    """Добавляет пользователя, если его ещё нет."""
    async with aiosqlite.connect(config.db_path) as db:
        await db.execute(
            "INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)",
            (user_id, username),
        )
        await db.commit()


async def is_activated(user_id: int) -> bool:
    async with aiosqlite.connect(config.db_path) as db:
        async with db.execute(
            "SELECT activated FROM users WHERE user_id = ?", (user_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return bool(row and row[0])


# ---------- Коды доступа ----------

async def codes_count() -> int:
    """Сколько всего кодов в базе (для проверки, загружены ли они)."""
    async with aiosqlite.connect(config.db_path) as db:
        async with db.execute("SELECT COUNT(*) FROM access_codes") as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0


async def load_codes(codes) -> int:
    """
    Загружает список кодов в базу (однократно).
    Уже существующие коды игнорируются. Возвращает, сколько добавлено.
    """
    async with aiosqlite.connect(config.db_path) as db:
        before = (await (await db.execute("SELECT COUNT(*) FROM access_codes")).fetchone())[0]
        await db.executemany(
            "INSERT OR IGNORE INTO access_codes (code) VALUES (?)",
            [(c,) for c in codes],
        )
        await db.commit()
        after = (await (await db.execute("SELECT COUNT(*) FROM access_codes")).fetchone())[0]
        return after - before


async def try_activate_with_code(user_id: int, code: str):
    """
    Пытается активировать юзера по коду.

    Возвращает кортеж (статус, сообщение_для_логики):
      "ok"          — код свободен, юзер активирован, код привязан
      "not_found"   — такого кода нет
      "used_by_you" — этот код уже привязан к ЭТОМУ же юзеру (повторный вход)
      "used"        — код уже использован ДРУГИМ юзером
    """
    code = code.strip().upper()

    async with aiosqlite.connect(config.db_path) as db:
        async with db.execute(
            "SELECT used_by FROM access_codes WHERE code = ?", (code,)
        ) as cursor:
            row = await cursor.fetchone()

        if row is None:
            return "not_found"

        used_by = row[0]

        if used_by is not None:
            if used_by == user_id:
                return "used_by_you"
            return "used"

        # Код свободен — привязываем к юзеру и активируем.
        await db.execute(
            "UPDATE access_codes SET used_by = ?, used_at = CURRENT_TIMESTAMP WHERE code = ?",
            (user_id, code),
        )
        await db.execute(
            "UPDATE users SET activated = 1, code_used = ? WHERE user_id = ?",
            (code, user_id),
        )
        await db.commit()
        return "ok"


async def load_codes_if_empty() -> int:
    """
    Если таблица кодов пуста — загружает коды из файла access_codes.txt
    (лежит рядом с проектом). Возвращает количество добавленных кодов.
    Используется для автозагрузки на хостинге при первом старте.
    """
    import os

    if await codes_count() > 0:
        return 0

    # Ищем access_codes.txt: сначала рядом с моделями, потом в рабочей директории.
    candidates = [
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "access_codes.txt"),
        os.path.join(os.getcwd(), "access_codes.txt"),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "access_codes.txt"),
    ]
    path = next((p for p in candidates if os.path.exists(p)), None)
    if path is None:
        return 0

    with open(path, "r", encoding="utf-8") as f:
        codes = [line.strip() for line in f if line.strip()]

    if not codes:
        return 0

    return await load_codes(codes)
