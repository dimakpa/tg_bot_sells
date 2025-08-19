from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import sessionmaker
from .models import Base
from config import settings
import aiosqlite


# Создаем движок для базы данных
if settings.database_url.startswith("sqlite"):
    # Для SQLite используем aiosqlite
    engine = create_async_engine(
        settings.database_url.replace("sqlite+aiosqlite://", "sqlite+aiosqlite://"),
        echo=False,
        future=True
    )
else:
    # Для PostgreSQL используем asyncpg
    engine = create_async_engine(
        settings.database_url,
        echo=False,
        future=True
    )

# Создаем фабрику сессий
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)


async def get_db() -> AsyncSession:
    """Получить сессию базы данных"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db():
    """Инициализировать базу данных"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db():
    """Закрыть соединение с базой данных"""
    await engine.dispose()
