from aiogram import Router, F
from aiogram.types import CallbackQuery

import texts
from keyboards import main_menu, platforms_menu, back_to_menu

router = Router()

PLATFORM_NAMES = {
    "platform_wb":  "Wildberries",
    "platform_ozon": "OZON",
    "platform_tg":  "Telegram",
}


@router.callback_query(F.data == "menu_back")
async def cb_back(call: CallbackQuery) -> None:
    await call.message.edit_text(texts.MAIN_MENU, reply_markup=main_menu())


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
    await call.message.edit_text(texts.AI_CLIENTS_STUB, reply_markup=back_to_menu())


@router.callback_query(F.data == "menu_ai_assistant")
async def cb_ai_assistant(call: CallbackQuery) -> None:
    await call.message.edit_text(texts.AI_ASSISTANT_STUB, reply_markup=back_to_menu())
