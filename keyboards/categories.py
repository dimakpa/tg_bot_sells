from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from storage.models import Category


def get_categories_keyboard(categories: list[Category], action: str) -> InlineKeyboardMarkup:
    """Клавиатура для выбора категорий"""
    builder = InlineKeyboardBuilder()
    
    for category in categories:
        builder.row(
            InlineKeyboardButton(
                text=category.name,
                callback_data=f"{action}_category:{category.id}"
            )
        )
    
    builder.row(
        InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")
    )
    
    return builder.as_markup()


def get_quick_income_keyboard() -> InlineKeyboardMarkup:
    """Быстрая клавиатура для продаж"""
    builder = InlineKeyboardBuilder()
    
    builder.row(
        InlineKeyboardButton(text="🍯 Мёд 3 л", callback_data="quick_income:102"),
        InlineKeyboardButton(text="🍯 Мёд 1 л", callback_data="quick_income:103")
    )
    
    builder.row(
        InlineKeyboardButton(text="🍯 Мёд 0.5 л", callback_data="quick_income:104"),
        InlineKeyboardButton(text="🍯 Соты", callback_data="quick_income:105")
    )
    
    builder.row(
        InlineKeyboardButton(text="💰 Другое доход", callback_data="income_category:101")
    )
    
    builder.row(
        InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")
    )
    
    return builder.as_markup()


def get_confirm_keyboard(action: str, data: str) -> InlineKeyboardMarkup:
    """Клавиатура подтверждения"""
    builder = InlineKeyboardBuilder()
    
    builder.row(
        InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"{action}_confirm:{data}"),
        InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")
    )
    
    return builder.as_markup()
