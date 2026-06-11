from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def main_menu() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="📦 Рассылки",                  callback_data="menu_mailings")
    builder.button(text="📊 Статистика",                callback_data="menu_stats")
    builder.button(text="💬 ИИ общение с клиентами",    callback_data="menu_ai_clients")
    builder.button(text="🤖 ИИ ассистент",              callback_data="menu_ai_assistant")
    builder.adjust(1)
    return builder.as_markup()


def platforms_menu() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="WB",       callback_data="platform_wb")
    builder.button(text="OZON",     callback_data="platform_ozon")
    builder.button(text="TELEGRAM", callback_data="platform_tg")
    builder.adjust(3)
    return builder.as_markup()


def back_to_menu() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="← Главное меню", callback_data="menu_back")
    builder.adjust(1)
    return builder.as_markup()
