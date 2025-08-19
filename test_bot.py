#!/usr/bin/env python3
"""
Тестовый скрипт для проверки работы бота
"""

import asyncio
from decimal import Decimal
from storage.database import init_db, get_db
from storage.categories import load_categories_from_json
from storage.models import TransactionKind, Transaction
from services.transaction_service import TransactionService
from loguru import logger


async def test_database():
    """Тестирование базы данных"""
    logger.info("Тестирование базы данных...")
    
    # Инициализируем базу данных
    await init_db()
    logger.info("✅ База данных инициализирована")
    
    # Загружаем категории
    async for session in get_db():
        await load_categories_from_json(session)
        break
    
    logger.info("✅ Категории загружены")
    
    # Проверяем, что категории загружены
    from storage.categories import get_categories_by_kind
    
    async for session in get_db():
        expense_categories = await get_categories_by_kind(session, TransactionKind.EXPENSE)
        income_categories = await get_categories_by_kind(session, TransactionKind.INCOME)
        
        logger.info(f"✅ Загружено категорий расходов: {len(expense_categories)}")
        logger.info(f"✅ Загружено категорий доходов: {len(income_categories)}")
        
        # Выводим несколько категорий для проверки
        logger.info("Примеры категорий расходов:")
        for cat in expense_categories[:3]:
            logger.info(f"  - {cat.name} (ID: {cat.id})")
        
        logger.info("Примеры категорий доходов:")
        for cat in income_categories[:3]:
            logger.info(f"  - {cat.name} (ID: {cat.id})")
        
        break


async def test_create_transactions():
    """Тест: создаём доход и расход и убеждаемся, что записи появляются в БД"""
    from sqlalchemy import select
    
    async for session in get_db():
        service = TransactionService(session)
        user_id = 999999999  # тестовый user id
        await service.get_or_create_user(user_id=user_id, username="tester")
        
        # создаём доход (категория 103 "Мёд 1 л")
        income_tx = await service.create_transaction(
            user_id=user_id,
            kind=TransactionKind.INCOME,
            category_id=103,
            subcategory_id=None,
            amount=Decimal("700.00"),
            comment="test income"
        )
        assert income_tx.id is not None and income_tx.id > 0
        assert income_tx.amount == Decimal("700.00")
        
        # создаём расход (категория 36 "Подарки", подкатегория 40 "Другое")
        expense_tx = await service.create_transaction(
            user_id=user_id,
            kind=TransactionKind.EXPENSE,
            category_id=36,
            subcategory_id=40,
            amount=Decimal("50.00"),
            comment="test expense"
        )
        assert expense_tx.id is not None and expense_tx.id > 0
        assert expense_tx.amount == Decimal("50.00")
        
        # проверяем, что всего 2 записи для пользователя
        result = await session.execute(select(Transaction).where(Transaction.user_id == user_id))
        rows = result.scalars().all()
        assert len(rows) >= 2
        logger.info(f"✅ Создано транзакций пользователя {user_id}: {len(rows)} (id: {[t.id for t in rows]})")
        break


async def main():
    """Главная функция тестирования"""
    logger.info("🧪 Начинаем тестирование...")
    
    try:
        await test_database()
        await test_create_transactions()
        logger.info("✅ Все тесты прошли успешно!")
    except Exception as e:
        logger.error(f"❌ Ошибка при тестировании: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())
