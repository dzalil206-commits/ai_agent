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

    return Config(
        bot_token=bot_token,
        db_path=os.getenv("DB_PATH", "bot.db"),
    )


config = load_config()
