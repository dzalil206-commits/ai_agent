"""
Конфигурация бота. Все настройки берутся из .env файла.
"""
import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass
class Config:
    bot_token: str
    db_path: str
    # --- ИИ (Claude API) ---
    anthropic_api_key: str | None   # нет ключа → ИИ-режимы отключены, бот работает
    ai_model: str
    ai_max_tokens: int
    ai_daily_limit: int             # запросов к ИИ на юзера в день


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
        db_path=os.getenv("DB_PATH", "bot.db"),
        anthropic_api_key=api_key,
        ai_model=os.getenv("AI_MODEL", "claude-opus-4-8"),
        ai_max_tokens=int(os.getenv("AI_MAX_TOKENS", "2000")),
        ai_daily_limit=int(os.getenv("AI_DAILY_LIMIT", "50")),
    )


config = load_config()
