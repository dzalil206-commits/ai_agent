"""
Конфигурация бота. Все настройки берутся из .env файла.
"""
import os
from dataclasses import dataclass

from dotenv import load_dotenv

# 1) .env рядом с проектом (локальный запуск).
load_dotenv()
# 2) BotHost: папка /app СТИРАЕТСЯ при синхронизации с GitHub, а /app/data
#    сохраняется. Держи .env в /app/data — он переживёт обновления кода.
#    (уже загруженные переменные НЕ перезаписываются — /app/.env главнее)
_DATA_DIR = os.getenv("DATA_DIR", "/app/data")
load_dotenv(os.path.join(_DATA_DIR, ".env"))


def _resolve_db_path(raw: str) -> str:
    """
    Относительный путь БД кладём в DATA_DIR, если он существует (BotHost):
    /app/bot.db стирается при синхронизации, /app/data/bot.db — нет.
    Локально (нет /app/data) поведение прежнее: файл рядом с ботом.
    """
    if os.path.isabs(raw):
        return raw
    if os.path.isdir(_DATA_DIR):
        return os.path.join(_DATA_DIR, raw)
    return raw


@dataclass
class Config:
    bot_token: str
    db_path: str
    # --- ИИ (Claude API) ---
    anthropic_api_key: str | None   # нет ключа → ИИ-режимы отключены, бот работает
    anthropic_base_url: str | None  # адрес API реселлера; пусто = официальный Anthropic
    ai_model: str
    ai_max_tokens: int
    ai_daily_limit: int             # запросов к ИИ на юзера в день
    proxy_url: str | None           # http://user:pass@host:port или socks5://...


def load_config() -> Config:
    bot_token = os.getenv("BOT_TOKEN")
    placeholders = {
        "сюда_вставь_токен_бота",
        "ВСТАВЬ_СЮДА_ТОКЕН_ОТ_BOTFATHER",
    }
    if not bot_token or bot_token in placeholders:
        raise RuntimeError(
            "BOT_TOKEN не задан. Открой файл .env и впиши токен от @BotFather "
            "вместо ВСТАВЬ_СЮДА_ТОКЕН_ОТ_BOTFATHER."
        )

    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if api_key in ("", "ВСТАВЬ_СЮДА_КЛЮЧ_ANTHROPIC"):
        api_key = None

    return Config(
        bot_token=bot_token,
        db_path=_resolve_db_path(os.getenv("DB_PATH", "bot.db")),
        anthropic_api_key=api_key,
        anthropic_base_url=os.getenv("ANTHROPIC_BASE_URL", "").strip() or None,
        ai_model=os.getenv("AI_MODEL", "claude-3-5-sonnet-20241022"),
        ai_max_tokens=int(os.getenv("AI_MAX_TOKENS", "2000")),
        ai_daily_limit=int(os.getenv("AI_DAILY_LIMIT", "50")),
        proxy_url=os.getenv("PROXY_URL", "").strip() or None,
    )


config = load_config()
