from decimal import Decimal
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_
from storage.models import Transaction, User, Category, TransactionKind
from storage.categories import get_category_by_id
from loguru import logger
import re


class TransactionService:
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def create_transaction(
        self,
        user_id: int,
        kind: TransactionKind,
        category_id: int,
        subcategory_id: Optional[int],
        amount: Decimal,
        comment: Optional[str] = None,
        currency: str = "RUB",
        effective_at: Optional[datetime] = None
    ) -> Transaction:
        """Создать новую транзакцию"""
        try:
            transaction = Transaction(
                user_id=user_id,
                kind=kind,
                category_id=category_id,
                subcategory_id=subcategory_id,
                amount=amount,
                currency=currency,
                comment=comment,
                effective_at=effective_at or datetime.utcnow()
            )
            
            self.session.add(transaction)
            await self.session.commit()
            await self.session.refresh(transaction)
            
            logger.info(f"Создана транзакция {transaction.id} для пользователя {user_id}")
            return transaction
            
        except Exception as e:
            logger.error(f"Ошибка при создании транзакции: {e}")
            await self.session.rollback()
            raise
    
    async def get_user_transactions(
        self,
        user_id: int,
        kind: Optional[TransactionKind] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 50
    ) -> List[Transaction]:
        """Получить транзакции пользователя"""
        query = select(Transaction).where(Transaction.user_id == user_id)
        
        if kind:
            query = query.where(Transaction.kind == kind)
        
        if start_date:
            query = query.where(Transaction.effective_at >= start_date)
        
        if end_date:
            query = query.where(Transaction.effective_at <= end_date)
        
        query = query.order_by(Transaction.effective_at.desc()).limit(limit)
        
        result = await self.session.execute(query)
        return result.scalars().all()
    
    async def get_recent_transactions(self, user_id: int, limit: int = 10) -> List[Transaction]:
        """Получить последние транзакции"""
        return await self.get_user_transactions(user_id, limit=limit)
    
    async def get_transaction_summary(
        self,
        user_id: int,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """Получить сводку по транзакциям"""
        query = select(
            Transaction.kind,
            func.sum(Transaction.amount).label('total_amount'),
            func.count(Transaction.id).label('count')
        ).where(Transaction.user_id == user_id)
        
        if start_date:
            query = query.where(Transaction.effective_at >= start_date)
        
        if end_date:
            query = query.where(Transaction.effective_at <= end_date)
        
        query = query.group_by(Transaction.kind)
        
        result = await self.session.execute(query)
        rows = result.all()
        
        summary = {
            'expense': {'total': Decimal('0'), 'count': 0},
            'income': {'total': Decimal('0'), 'count': 0}
        }
        
        for row in rows:
            kind = row.kind.value
            summary[kind]['total'] = row.total_amount
            summary[kind]['count'] = row.count
        
        return summary
    
    async def delete_last_transaction(self, user_id: int, minutes: int = 5) -> Optional[Transaction]:
        """Удалить последнюю транзакцию пользователя (если она создана в течение N минут)"""
        cutoff_time = datetime.utcnow() - timedelta(minutes=minutes)
        
        query = select(Transaction).where(
            and_(
                Transaction.user_id == user_id,
                Transaction.created_at >= cutoff_time
            )
        ).order_by(Transaction.created_at.desc()).limit(1)
        
        result = await self.session.execute(query)
        transaction = result.scalar_one_or_none()
        
        if transaction:
            await self.session.delete(transaction)
            await self.session.commit()
            logger.info(f"Удалена транзакция {transaction.id} пользователя {user_id}")
            return transaction
        
        return None
    
    async def get_or_create_user(
        self,
        user_id: int,
        username: Optional[str] = None,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None
    ) -> User:
        """Получить или создать пользователя"""
        result = await self.session.execute(
            select(User).where(User.id == user_id)
        )
        user = result.scalar_one_or_none()
        
        if not user:
            user = User(
                id=user_id,
                username=username,
                first_name=first_name,
                last_name=last_name
            )
            self.session.add(user)
            await self.session.commit()
            await self.session.refresh(user)
            logger.info(f"Создан новый пользователь {user_id}")
        
        return user

    async def delete_transaction_by_id(self, user_id: int, transaction_id: int) -> bool:
        """Удалить транзакцию по id, если она принадлежит пользователю."""
        result = await self.session.execute(
            select(Transaction).where(Transaction.id == transaction_id)
        )
        transaction = result.scalar_one_or_none()
        if not transaction:
            return False
        if transaction.user_id != user_id:
            return False
        try:
            await self.session.delete(transaction)
            await self.session.commit()
            logger.info(f"Удалена транзакция {transaction_id} пользователя {user_id}")
            return True
        except Exception as e:
            logger.error(f"Ошибка удаления транзакции {transaction_id}: {e}")
            await self.session.rollback()
            return False


def parse_amount(amount_str: str) -> Optional[Decimal]:
    """Парсить сумму из строки"""
    try:
        # Убираем пробелы и заменяем запятые на точки
        cleaned = amount_str.strip().replace(' ', '').replace(',', '.')
        
        # Проверяем, что это число
        if not re.match(r'^\d+\.?\d*$', cleaned):
            return None
        
        return Decimal(cleaned)
    except (ValueError, TypeError):
        return None
