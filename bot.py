"""
Точка входа бота.

Работает при любом способе запуска:
    python bot.py
    python -m bot

Фикс импортов: добавляем папку этого файла в sys.path, иначе при
запуске через `python -m bot` Python не находит пакеты handlers/ и models/
и падает с ошибкой ModuleNotFoundError: No module named 'handlers'.
"""
import os
import sys

# --- ФИКС ИМПОРТОВ (должен стоять ДО импортов проекта) ---
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)
# ----------------------------------------------------------

import asyncio
import logging

from aiogram import Bot, Dispatcher

from config import config
from handlers.commands import router as commands_router
from models.database import init_db, load_codes_if_empty


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )

    await init_db()
    loaded = await load_codes_if_empty()
    if loaded:
        logging.info("Загружено кодов доступа в базу: %d", loaded)

    bot = Bot(token=config.bot_token)
    dp = Dispatcher()
    dp.include_router(commands_router)

    logging.info("Бот запущен. Ожидаю сообщения...")
    await dp.start_polling(bot, drop_pending_updates=True)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Бот остановлен.")
