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
import logging

import anthropic
from aiogram import Router, F
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

import texts
from config import config
from keyboards import main_menu
from models import database as db
from services import ai

logger = logging.getLogger(__name__)

TG_MESSAGE_LIMIT = 4000  # лимит Telegram 4096, берём с запасом

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
        ai.clear_mode(message.from_user.id)  # /start = выход из ИИ-режима в меню
        await message.answer(texts.ALREADY_ACTIVATED)
        await message.answer(texts.ABOUT, reply_markup=main_menu())
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


async def _handle_ai_chat(message: Message) -> None:
    """Текст от активированного юзера → ответ ИИ (если выбран режим)."""
    user_id = message.from_user.id

    mode = ai.get_mode(user_id)
    if mode is None:
        await message.answer(texts.AI_NOT_READY)
        return

    if not ai.is_configured():
        await message.answer(texts.AI_NOT_CONFIGURED)
        return

    if await db.ai_usage_today(user_id) >= config.ai_daily_limit:
        await message.answer(texts.AI_LIMIT_REACHED)
        return

    await message.bot.send_chat_action(message.chat.id, "typing")

    try:
        answer = await ai.ask(user_id, mode, message.text)
    except anthropic.AuthenticationError as e:
        logger.error("Claude API 401 AuthenticationError: %s", e)
        await message.answer(texts.AI_NOT_CONFIGURED)
        return
    except anthropic.NotFoundError as e:
        logger.error("Claude API 404 NotFoundError (модель не найдена?): %s", e)
        await message.answer(texts.AI_ERROR)
        return
    except anthropic.APIStatusError as e:
        logger.error("Claude API HTTP %s: %s", e.status_code, e.message)
        await message.answer(texts.AI_ERROR)
        return
    except anthropic.APIConnectionError as e:
        logger.error("Claude API ConnectionError (сеть/base_url?): %s", e)
        await message.answer(texts.AI_ERROR)
        return
    except anthropic.APIError as e:
        logger.error("Claude API неизвестная ошибка (%s): %s", type(e).__name__, e)
        await message.answer(texts.AI_ERROR)
        return

    await db.ai_usage_increment(user_id)

    if not answer:
        await message.answer(texts.AI_REFUSED)
        return

    # Telegram не принимает сообщения длиннее 4096 символов — режем.
    for start in range(0, len(answer), TG_MESSAGE_LIMIT):
        await message.answer(answer[start:start + TG_MESSAGE_LIMIT])


@router.message(F.text)
async def handle_text(message: Message) -> None:
    """
    Любой текст без команды.
    - Если юзер не активирован — считаем это попыткой ввести код доступа.
    - Если активирован — отвечает ИИ в выбранном режиме.
    """
    await db.ensure_user(message.from_user.id, message.from_user.username)

    if await db.is_activated(message.from_user.id):
        await _handle_ai_chat(message)
        return

    # Не активирован — пробуем введённый текст как код доступа.
    result = await db.try_activate_with_code(message.from_user.id, message.text)

    if result == "ok":
        await message.answer(texts.TOKEN_OK)
        await message.answer(texts.ABOUT, reply_markup=main_menu())
    elif result == "used_by_you":
        await message.answer(texts.ALREADY_ACTIVATED)
        await message.answer(texts.ABOUT, reply_markup=main_menu())
    elif result == "used":
        await message.answer(texts.CODE_USED_BY_OTHER)
    else:  # not_found
        await message.answer(texts.TOKEN_WRONG)
