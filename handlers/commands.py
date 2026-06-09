"""
Обработчики основных команд и логики активации.

Активация по одноразовым кодам:
1. Пользователь пишет боту → бот просит код доступа.
2. Пользователь присылает код (формат WRN-XXX-XXX-XXX-XXX).
3. Бот ищет код в базе:
   - код свободен  → активируем, привязываем код к этому Telegram ID.
   - код занят им же → впускаем (повторный вход с того же аккаунта).
   - код занят другим → отказ.
   - кода нет        → отказ.
4. После активации юзер узнаётся по Telegram ID и заходит без кода.
"""
from aiogram import Router, F
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

import texts
from models import database as db

router = Router()


@router.message(Command("start"))
async def cmd_start(message: Message, command: CommandObject) -> None:
    """
    /start без аргументов — приветствие/активация.
    /start рассылки WB 200 — запуск функции (если активирован).
    """
    await db.ensure_user(message.from_user.id, message.from_user.username)

    args = command.args  # всё, что после /start

    if args:
        if not await db.is_activated(message.from_user.id):
            await message.answer(texts.NEED_ACTIVATION)
            return
        await _handle_function_launch(message, args)
        return

    if await db.is_activated(message.from_user.id):
        await message.answer(texts.ALREADY_ACTIVATED)
        await message.answer(texts.ABOUT)
    else:
        await message.answer(texts.GREETING)


async def _handle_function_launch(message: Message, args: str) -> None:
    """Разбирает строку запуска функции. Сейчас поддержан только сценарий рассылки."""
    parts = args.split()

    if len(parts) >= 3 and parts[0].lower() in ("рассылки", "рассылка", "mailing"):
        platform = parts[1]
        try:
            limit = int(parts[2])
        except ValueError:
            await message.answer(texts.MAILING_BAD_FORMAT)
            return
        await message.answer(texts.mailing_accepted(platform=platform, limit=limit))
        return

    await message.answer(texts.MAILING_BAD_FORMAT)


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(texts.HELP)


@router.message(Command("stats"))
async def cmd_stats(message: Message) -> None:
    if not await db.is_activated(message.from_user.id):
        await message.answer(texts.NEED_ACTIVATION)
        return
    await message.answer(texts.stats_message())


@router.message(F.text)
async def handle_text(message: Message) -> None:
    """
    Любой текст без команды.
    - Если юзер не активирован — считаем это попыткой ввести код доступа.
    - Если активирован — пока заглушка (на Этапе 2 здесь будет ИИ).
    """
    await db.ensure_user(message.from_user.id, message.from_user.username)

    if await db.is_activated(message.from_user.id):
        # Активирован, но это просто текст — ИИ ещё не подключён.
        await message.answer(texts.AI_NOT_READY)
        return

    # Не активирован — пробуем введённый текст как код доступа.
    result = await db.try_activate_with_code(message.from_user.id, message.text)

    if result == "ok":
        await message.answer(texts.TOKEN_OK)
        await message.answer(texts.ABOUT)
    elif result == "used_by_you":
        # Тот же юзер вводит свой же код повторно — просто впускаем.
        await message.answer(texts.ALREADY_ACTIVATED)
        await message.answer(texts.ABOUT)
    elif result == "used":
        await message.answer(texts.CODE_USED_BY_OTHER)
    else:  # not_found
        await message.answer(texts.TOKEN_WRONG)
