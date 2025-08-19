from typing import Any, Awaitable, Callable, Dict
from aiogram import BaseMiddleware
from storage.database import AsyncSessionLocal


class DatabaseSessionMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[object, Dict[str, Any]], Awaitable[Any]],
        event: object,
        data: Dict[str, Any],
    ) -> Any:
        async with AsyncSessionLocal() as session:
            data["session"] = session
            return await handler(event, data)
