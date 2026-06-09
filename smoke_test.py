"""
Smoke-тест: проверяет, что бот собирается и вся логика работает
БЕЗ реального обращения к Telegram API.
Запуск: python smoke_test.py
"""
import asyncio
import os
import tempfile

# 1) Подставляем валидный по формату тестовый токен и временную БД
#    ДО импорта проекта (config падает на плейсхолдере).
os.environ["BOT_TOKEN"] = "123456789:AAEhBOweik9ai2o4V4Vr2NjfM7890abcdef"
_tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_tmp.close()
os.environ["DB_PATH"] = _tmp.name

import config            # noqa: E402
from models import database as db   # noqa: E402
import texts             # noqa: E402
from handlers.commands import router  # noqa: E402
from aiogram import Bot, Dispatcher  # noqa: E402


def check(name, cond):
    print(f"  [{'OK ' if cond else 'FAIL'}] {name}")
    assert cond, f"ПРОВАЛЕН ТЕСТ: {name}"


async def main():
    print("== 1. Конфиг ==")
    check("токен загружен из окружения", config.config.bot_token.startswith("123456789:"))
    check("db_path = временный файл", config.config.db_path.endswith(".db"))

    print("== 2. Инициализация БД ==")
    await db.init_db()
    check("init_db не падает", True)
    check("кодов в пустой базе = 0", await db.codes_count() == 0)

    print("== 3. Загрузка кодов ==")
    test_codes = ["WRN-AAA-BBB-CCC-DDD", "WRN-EEE-FFF-GGG-HHH", "WRN-111-222-333-444"]
    added = await db.load_codes(test_codes)
    check("добавлено 3 кода", added == 3)
    check("повторная загрузка игнорит дубли", await db.load_codes(test_codes) == 0)
    check("всего кодов = 3", await db.codes_count() == 3)

    print("== 4. Пользователи и активация ==")
    USER_A, USER_B = 1001, 2002
    await db.ensure_user(USER_A, "alice")
    check("новый юзер не активирован", await db.is_activated(USER_A) is False)

    r1 = await db.try_activate_with_code(USER_A, "WRN-AAA-BBB-CCC-DDD")
    check("свободный код -> 'ok'", r1 == "ok")
    check("после активации is_activated=True", await db.is_activated(USER_A) is True)

    r2 = await db.try_activate_with_code(USER_A, "wrn-aaa-bbb-ccc-ddd")  # тот же код, нижний регистр
    check("свой же код повторно -> 'used_by_you'", r2 == "used_by_you")

    await db.ensure_user(USER_B, "bob")
    r3 = await db.try_activate_with_code(USER_B, "WRN-AAA-BBB-CCC-DDD")
    check("чужой занятый код -> 'used'", r3 == "used")
    check("юзер B остался не активирован", await db.is_activated(USER_B) is False)

    r4 = await db.try_activate_with_code(USER_B, "WRN-ZZZ-ZZZ-ZZZ-ZZZ")
    check("несуществующий код -> 'not_found'", r4 == "not_found")

    print("== 5. Тексты ==")
    check("GREETING не пустой", bool(texts.GREETING))
    check("mailing_accepted рендерит платформу/лимит",
          "WB" in texts.mailing_accepted("WB", 200) and "200" in texts.mailing_accepted("WB", 200))
    check("stats_message рендерит числа", "5 / 200" in texts.stats_message(5, 200, 3))

    print("== 6. Сборка бота (валидация токена aiogram) ==")
    bot = Bot(token=config.config.bot_token)
    dp = Dispatcher()
    dp.include_router(router)
    check("Bot создан, токен прошёл валидацию формата", bot is not None)
    check("роутер с хендлерами подключён", len(dp.sub_routers) == 1)
    await bot.session.close()

    print("\nВСЕ ПРОВЕРКИ ПРОЙДЕНЫ ✅")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    finally:
        try:
            os.unlink(os.environ["DB_PATH"])
        except OSError:
            pass
