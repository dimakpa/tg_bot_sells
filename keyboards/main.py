from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder


def get_main_keyboard() -> InlineKeyboardMarkup:
    """Главная клавиатура"""
    builder = InlineKeyboardBuilder()
    
    builder.row(
        InlineKeyboardButton(text="💰 Трата", callback_data="expense"),
        InlineKeyboardButton(text="💸 Продажа", callback_data="income")
    )
    
    builder.row(
        InlineKeyboardButton(text="📊 Посмотреть траты", callback_data="view_expenses"),
        InlineKeyboardButton(text="📈 Посмотреть продажи", callback_data="view_incomes")
    )
    
    builder.row(
        InlineKeyboardButton(text="🕐 Последние операции", callback_data="recent_transactions"),
        InlineKeyboardButton(text="📋 Экспорт отчёта", callback_data="export_report")
    )
    
    return builder.as_markup()


def get_quick_actions_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура быстрых действий после операции"""
    builder = InlineKeyboardBuilder()
    
    builder.row(
        InlineKeyboardButton(text="➕ Ещё", callback_data="add_another"),
        InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")
    )
    
    return builder.as_markup()


def get_cancel_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура отмены"""
    builder = InlineKeyboardBuilder()
    
    builder.row(
        InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")
    )
    
    return builder.as_markup()
