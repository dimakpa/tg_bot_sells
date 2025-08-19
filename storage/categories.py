import json
import os
from typing import List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from .models import Category, TransactionKind
from loguru import logger


async def load_categories_from_json(session: AsyncSession) -> None:
    """Загрузить категории из JSON файла"""
    categories_file = "data/categories.json"
    
    if not os.path.exists(categories_file):
        logger.warning(f"Файл категорий {categories_file} не найден")
        return
    
    try:
        with open(categories_file, 'r', encoding='utf-8') as f:
            categories_data = json.load(f)
        
        # Проверяем, есть ли уже категории в базе данных
        result = await session.execute(select(Category).limit(1))
        if result.scalar_one_or_none():
            logger.info("Категории уже загружены в базу данных")
            return
        
        # Создаем категории
        for cat_data in categories_data:
            category = Category(
                id=cat_data["id"],
                name=cat_data["name"],
                kind=TransactionKind(cat_data["kind"]),
                parent_id=cat_data.get("parent_id")
            )
            session.add(category)
        
        await session.commit()
        logger.info(f"Загружено {len(categories_data)} категорий")
        
    except Exception as e:
        logger.error(f"Ошибка при загрузке категорий: {e}")
        await session.rollback()
        raise


async def get_categories_by_kind(session: AsyncSession, kind: TransactionKind) -> List[Category]:
    """Получить категории по типу"""
    result = await session.execute(
        select(Category).where(Category.kind == kind, Category.parent_id.is_(None))
    )
    return result.scalars().all()


async def get_subcategories(session: AsyncSession, parent_id: int) -> List[Category]:
    """Получить подкатегории"""
    result = await session.execute(
        select(Category).where(Category.parent_id == parent_id)
    )
    return result.scalars().all()


async def get_category_by_id(session: AsyncSession, category_id: int) -> Category:
    """Получить категорию по ID"""
    result = await session.execute(
        select(Category).where(Category.id == category_id)
    )
    return result.scalar_one_or_none()
