"""
Работа с базой данных (SQLite через aiosqlite).

Таблицы:
- users          — пользователи Telegram, флаг активации и тариф
- access_codes   — одноразовые коды доступа; тариф зашит в префиксе кода
- ai_usage       — дневной счётчик ИИ-запросов
- mailing_usage  — месячный счётчик рассылок
- sessions       — задел под учёт рассылок (Этап 4)

Логика кодов:
- код одноразовый: при активации привязывается к user_id (used_by)
- повторно тот же код использовать нельзя
- тариф определяется по префиксу кода (STD-/PRO-/BIZ-/PREM-/MAST-)
- активированный юзер узнаётся по Telegram ID и заходит без повторного ввода
"""
import aiosqlite

import tariffs
from config import config


async def _ensure_column(db, table: str, column: str, decl: str) -> None:
    """Добавляет колонку, если её ещё нет (миграция старых баз без простоя)."""
    async with db.execute(f"PRAGMA table_info({table})") as cursor:
        cols = {row[1] for row in await cursor.fetchall()}
    if column not in cols:
        await db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")


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
                tariff      TEXT,
                created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS access_codes (
                code        TEXT PRIMARY KEY,
                tariff      TEXT,
                used_by     INTEGER,
                used_at     TIMESTAMP
            )
            """
        )
        # Месячный счётчик рассылок (лимит зависит от тарифа).
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS mailing_usage (
                user_id     INTEGER NOT NULL,
                month       TEXT NOT NULL,
                count       INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (user_id, month)
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
        # Учёт ИИ-запросов (дневной лимит на юзера).
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS ai_usage (
                user_id     INTEGER NOT NULL,
                day         TEXT NOT NULL,
                count       INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (user_id, day)
            )
            """
        )
        # Миграция старых баз: добавляем колонку tariff, если её ещё нет.
        await _ensure_column(db, "users", "tariff", "TEXT")
        await _ensure_column(db, "access_codes", "tariff", "TEXT")
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
    Тариф каждого кода определяется по его префиксу (STD-/PRO-/BIZ-/PREM-/MAST-).
    Уже существующие коды игнорируются. Возвращает, сколько добавлено.
    """
    async with aiosqlite.connect(config.db_path) as db:
        before = (await (await db.execute("SELECT COUNT(*) FROM access_codes")).fetchone())[0]
        await db.executemany(
            "INSERT OR IGNORE INTO access_codes (code, tariff) VALUES (?, ?)",
            [(c, tariffs.tariff_for_code(c)) for c in codes],
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
            "SELECT used_by, tariff FROM access_codes WHERE code = ?", (code,)
        ) as cursor:
            row = await cursor.fetchone()

        if row is None:
            return "not_found"

        used_by, tariff = row

        if used_by is not None:
            if used_by == user_id:
                return "used_by_you"
            return "used"

        # Тариф мог не записаться у легаси-кодов — добираем из префикса.
        tariff = tariff or tariffs.tariff_for_code(code)

        # Старый код юзера (если был) — после смены тарифа его стираем.
        async with db.execute(
            "SELECT code_used FROM users WHERE user_id = ?", (user_id,)
        ) as cursor:
            prev = await cursor.fetchone()
        old_code = prev[0] if prev else None

        # Код свободен — привязываем к юзеру, активируем и ставим тариф.
        await db.execute(
            "UPDATE access_codes SET used_by = ?, used_at = CURRENT_TIMESTAMP WHERE code = ?",
            (user_id, code),
        )
        await db.execute(
            "UPDATE users SET activated = 1, code_used = ?, tariff = ? WHERE user_id = ?",
            (code, tariff, user_id),
        )

        # Стираем старый код юзера (если это была реальная смена на другой код).
        if old_code and old_code != code:
            await db.execute(
                "DELETE FROM access_codes WHERE code = ? AND used_by = ?",
                (old_code, user_id),
            )

        await db.commit()
        return "ok"


async def get_user_tariff(user_id: int) -> str:
    """Ключ тарифа юзера. Если не задан (легаси) — тариф по умолчанию."""
    async with aiosqlite.connect(config.db_path) as db:
        async with db.execute(
            "SELECT tariff FROM users WHERE user_id = ?", (user_id,)
        ) as cursor:
            row = await cursor.fetchone()
    return (row[0] if row and row[0] else tariffs.DEFAULT_TARIFF)


# ---------- Учёт ИИ-запросов ----------

async def ai_usage_today(user_id: int) -> int:
    """Сколько ИИ-запросов юзер сделал сегодня (по UTC)."""
    async with aiosqlite.connect(config.db_path) as db:
        async with db.execute(
            "SELECT count FROM ai_usage WHERE user_id = ? AND day = date('now')",
            (user_id,),
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0


async def ai_usage_increment(user_id: int) -> None:
    """Увеличивает счётчик ИИ-запросов юзера за сегодня."""
    async with aiosqlite.connect(config.db_path) as db:
        await db.execute(
            """
            INSERT INTO ai_usage (user_id, day, count) VALUES (?, date('now'), 1)
            ON CONFLICT (user_id, day) DO UPDATE SET count = count + 1
            """,
            (user_id,),
        )
        await db.commit()


# ---------- Учёт рассылок (месячный лимит) ----------

async def mailing_usage_month(user_id: int) -> int:
    """Сколько рассылок юзер отправил в текущем месяце (UTC, YYYY-MM)."""
    async with aiosqlite.connect(config.db_path) as db:
        async with db.execute(
            "SELECT count FROM mailing_usage WHERE user_id = ? AND month = strftime('%Y-%m','now')",
            (user_id,),
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0


async def mailing_usage_add(user_id: int, n: int = 1) -> None:
    """Увеличивает месячный счётчик рассылок юзера на n."""
    async with aiosqlite.connect(config.db_path) as db:
        await db.execute(
            """
            INSERT INTO mailing_usage (user_id, month, count)
            VALUES (?, strftime('%Y-%m','now'), ?)
            ON CONFLICT (user_id, month) DO UPDATE SET count = count + ?
            """,
            (user_id, n, n),
        )
        await db.commit()


def _find_codes_file():
    """Ищет access_codes.txt: постоянная папка BotHost (/app/data), потом проект."""
    import os

    candidates = [
        os.path.join(os.getenv("DATA_DIR", "/app/data"), "access_codes.txt"),
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "access_codes.txt"),
        os.path.join(os.getcwd(), "access_codes.txt"),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "access_codes.txt"),
    ]
    return next((p for p in candidates if os.path.exists(p)), None)


async def sync_codes_from_file() -> int:
    """
    Домерживает коды из access_codes.txt в базу при КАЖДОМ старте.
    Новые коды добавляются, существующие игнорируются (INSERT OR IGNORE),
    использованные коды не трогаются. Возвращает, сколько добавлено.

    Это позволяет докидывать новые тарифные коды (STD-/PRO-/BIZ-/PREM-/MAST-)
    в уже работающую базу — просто обнови файл и перезапусти бота.
    """
    path = _find_codes_file()
    if path is None:
        return 0

    with open(path, "r", encoding="utf-8") as f:
        codes = [line.strip() for line in f if line.strip()]

    if not codes:
        return 0

    return await load_codes(codes)


async def load_codes_if_empty() -> int:
    """Совместимость: первичная загрузка кодов, если база пуста."""
    if await codes_count() > 0:
        return 0
    return await sync_codes_from_file()
