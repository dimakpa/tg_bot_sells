from datetime import datetime
from decimal import Decimal
from typing import Optional
from sqlalchemy import (
    BigInteger, Integer, String, DateTime, Numeric, Text,
    ForeignKey, Enum, JSON, Index, Boolean
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
import json
import enum


class Base(DeclarativeBase):
    pass


class TransactionKind(str, enum.Enum):
    EXPENSE = "expense"
    INCOME = "income"


class User(Base):
    __tablename__ = "users"
    
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    username: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    first_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    last_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    timezone: Mapped[str] = mapped_column(String(50), default="Europe/Moscow")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    transactions = relationship("Transaction", back_populates="user")


class Category(Base):
    __tablename__ = "categories"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    kind: Mapped[TransactionKind] = mapped_column(Enum(TransactionKind), nullable=False)
    parent_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("categories.id"), nullable=True)
    
    # Relationships
    parent = relationship("Category", remote_side=[id], back_populates="children")
    children = relationship("Category", back_populates="parent")
    transactions = relationship("Transaction", foreign_keys="Transaction.category_id", back_populates="category")
    subcategory_transactions = relationship("Transaction", foreign_keys="Transaction.subcategory_id", back_populates="subcategory")


class Transaction(Base):
    __tablename__ = "transactions"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)
    kind: Mapped[TransactionKind] = mapped_column(Enum(TransactionKind), nullable=False)
    category_id: Mapped[int] = mapped_column(Integer, ForeignKey("categories.id"), nullable=False)
    subcategory_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("categories.id"), nullable=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="RUB")
    comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    effective_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    meta: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    
    # Relationships
    user = relationship("User", back_populates="transactions")
    category = relationship("Category", foreign_keys=[category_id], back_populates="transactions")
    subcategory = relationship("Category", foreign_keys=[subcategory_id], back_populates="subcategory_transactions")


# Indexes
Index("idx_transactions_user_created", Transaction.user_id, Transaction.created_at)
Index("idx_transactions_kind_category", Transaction.kind, Transaction.category_id)
Index("idx_categories_kind", Category.kind)
Index("idx_categories_parent", Category.parent_id)
