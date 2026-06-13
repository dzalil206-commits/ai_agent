from aiogram import Router, F
from aiogram.types import CallbackQuery

import states
import texts
from keyboards import main_menu, platforms_menu, back_to_menu
from services import ai

router = Router()

PLATFORM_NAMES = {
    "platform_wb":  "Wildberries",
    "platform_ozon": "OZON",
    "platform_tg":  "Telegram",
}


@router.callback_query(F.data == "menu_back")
async def cb_back(call: CallbackQuery) -> None:
    ai.clear_mode(call.from_user.id)
    states.clear_awaiting_code(call.from_user.id)
    await call.message.edit_text(texts.ABOUT, reply_markup=main_menu())


@router.callback_query(F.data == "menu_change_tariff")
async def cb_change_tariff(call: CallbackQuery) -> None:
    ai.clear_mode(call.from_user.id)            # выходим из ИИ-режима
    states.set_awaiting_code(call.from_user.id)  # следующий текст = новый токен
    await call.message.edit_text(texts.CHANGE_TARIFF_PROMPT, reply_markup=back_to_menu())


@router.callback_query(F.data == "menu_mailings")
async def cb_mailings(call: CallbackQuery) -> None:
    await call.message.edit_text(texts.SELECT_PLATFORM, reply_markup=platforms_menu())


@router.callback_query(F.data.in_({"platform_wb", "platform_ozon", "platform_tg"}))
async def cb_platform(call: CallbackQuery) -> None:
    platform = PLATFORM_NAMES[call.data]
    await call.message.edit_text(
        texts.mailing_accepted(platform=platform, limit=200),
        reply_markup=back_to_menu(),
    )


@router.callback_query(F.data == "menu_stats")
async def cb_stats(call: CallbackQuery) -> None:
    await call.message.edit_text(texts.STATS_STUB, reply_markup=back_to_menu())


@router.callback_query(F.data == "menu_ai_clients")
async def cb_ai_clients(call: CallbackQuery) -> None:
    if not ai.is_configured():
        await call.message.edit_text(texts.AI_NOT_CONFIGURED, reply_markup=back_to_menu())
        return
    ai.set_mode(call.from_user.id, "sales")
    await call.message.edit_text(texts.AI_CLIENTS_ON, reply_markup=back_to_menu())


@router.callback_query(F.data == "menu_ai_assistant")
async def cb_ai_assistant(call: CallbackQuery) -> None:
    if not ai.is_configured():
        await call.message.edit_text(texts.AI_NOT_CONFIGURED, reply_markup=back_to_menu())
        return
    ai.set_mode(call.from_user.id, "assistant")
    await call.message.edit_text(texts.AI_ASSISTANT_ON, reply_markup=back_to_menu())
