from aiogram import Router, types
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime
from typing import List, Dict, Any, Iterable

from storage.models import Transaction, TransactionKind, Category
from keyboards.main import get_main_keyboard
from aiogram.exceptions import TelegramBadRequest
from services.transaction_service import TransactionService

router = Router()


async def _safe_edit_text(message: types.Message, text: str, reply_markup: types.InlineKeyboardMarkup) -> None:
	try:
		await message.edit_text(text, reply_markup=reply_markup)
	except TelegramBadRequest as e:
		if "message is not modified" in str(e):
			return
		raise


async def _fetch_recent(
	session: AsyncSession,
	user_id: int,
	kind: str | None,
	offset: int,
	limit: int = 10,
) -> List[Transaction]:
	query = select(Transaction).where(Transaction.user_id == user_id)
	if kind in {TransactionKind.EXPENSE.value, TransactionKind.INCOME.value}:
		query = query.where(Transaction.kind == TransactionKind(kind))
	query = query.order_by(Transaction.effective_at.desc()).offset(offset).limit(limit)
	res = await session.execute(query)
	return list(res.scalars().all())


async def _category_map_for(transactions: List[Transaction], session: AsyncSession) -> Dict[int, str]:
	ids: set[int] = set()
	for t in transactions:
		ids.add(t.category_id)
		if t.subcategory_id:
			ids.add(t.subcategory_id)
	if not ids:
		return {}
	res = await session.execute(select(Category.id, Category.name).where(Category.id.in_(ids)))
	return {row.id: row.name for row in res.all()}


def _format_list(transactions: List[Transaction], cat_map: Dict[int, str]) -> str:
	if not transactions:
		return "Пока нет операций."
	lines: List[str] = []
	for t in transactions:
		date_str = t.effective_at.strftime("%d.%m %H:%M")
		kind_emoji = "💰" if t.kind == TransactionKind.EXPENSE else "💸"
		cat = cat_map.get(t.category_id, str(t.category_id))
		sub = f" → {cat_map.get(t.subcategory_id, '')}" if t.subcategory_id else ""
		comment = f"\n   💬 {t.comment}" if t.comment else ""
		lines.append(f"ID {t.id} • {date_str} {kind_emoji} {t.amount:.2f} {t.currency} — {cat}{sub}{comment}")
	return "\n".join(lines)


def _with_delete_buttons(scope: str, offset: int, items: List[Transaction]) -> types.InlineKeyboardMarkup:
	rows: list[list[types.InlineKeyboardButton]] = []
	rows.append([
		types.InlineKeyboardButton(text="Траты", callback_data="recent:expense:0"),
		types.InlineKeyboardButton(text="Продажи", callback_data="recent:income:0"),
		types.InlineKeyboardButton(text="Все", callback_data="recent:all:0"),
	])
	for t in items:
		rows.append([
			types.InlineKeyboardButton(text=f"Удалить {t.id}", callback_data=f"tx:del:{t.id}:{scope}:{offset}")
		])
	nav: list[types.InlineKeyboardButton] = []
	if offset > 0:
		prev_off = max(0, offset-10)
		nav.append(types.InlineKeyboardButton(text="← Назад", callback_data=f"recent:{scope}:{prev_off}"))
	if len(items) == 10:
		nav.append(types.InlineKeyboardButton(text="Вперёд →", callback_data=f"recent:{scope}:{offset+10}"))
	if nav:
		rows.append(nav)
	rows.append([types.InlineKeyboardButton(text="Меню", callback_data="main_menu")])
	return types.InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(lambda c: c.data == "recent_transactions")
async def recent_all(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession):
	offset = 0
	items = await _fetch_recent(session, callback.from_user.id, None, offset)
	cmap = await _category_map_for(items, session)
	text = "🕐 Последние операции (последние 10):\n\n" + _format_list(items, cmap)
	kb = _with_delete_buttons("all", offset, items)
	await _safe_edit_text(callback.message, text, kb)
	await callback.answer()


@router.callback_query(lambda c: c.data.startswith("recent:"))
async def recent_paged(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession):
	_, scope, off_str = callback.data.split(":", 2)
	offset = int(off_str)
	kind = None if scope == "all" else scope
	items = await _fetch_recent(session, callback.from_user.id, kind, offset)
	cmap = await _category_map_for(items, session)
	title = "Все" if kind is None else ("Траты" if kind==TransactionKind.EXPENSE.value else "Продажи")
	text = f"🕐 Последние операции — {title} (с {offset+1})\n\n" + _format_list(items, cmap)
	kb = _with_delete_buttons(scope, offset, items)
	await _safe_edit_text(callback.message, text, kb)
	await callback.answer()


@router.callback_query(lambda c: c.data.startswith("tx:del:"))
async def tx_delete_prompt(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession):
	# tx:del:{id}:{scope}:{offset}
	_, _, tx_id_str, scope, offset_str = callback.data.split(":", 4)
	tx_id = int(tx_id_str)
	offset = int(offset_str)
	kb = types.InlineKeyboardMarkup(inline_keyboard=[
		[
			types.InlineKeyboardButton(text="✅ Да, удалить", callback_data=f"tx:delconf:{tx_id}:{scope}:{offset}"),
			types.InlineKeyboardButton(text="❌ Отмена", callback_data=f"recent:{scope}:{offset}")
		]
	])
	await _safe_edit_text(callback.message, f"Удалить операцию ID {tx_id}?", kb)
	await callback.answer()


@router.callback_query(lambda c: c.data.startswith("tx:delconf:"))
async def tx_delete_confirm(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession):
	_, _, tx_id_str, scope, offset_str = callback.data.split(":", 4)
	tx_id = int(tx_id_str)
	offset = int(offset_str)
	service = TransactionService(session)
	ok = await service.delete_transaction_by_id(callback.from_user.id, tx_id)
	if ok:
		await callback.answer("Удалено")
	else:
		await callback.answer("Не удалось удалить", show_alert=True)
	# Обновим список
	kind = None if scope == "all" else scope
	items = await _fetch_recent(session, callback.from_user.id, kind, offset)
	cmap = await _category_map_for(items, session)
	title = "Все" if kind is None else ("Траты" if kind==TransactionKind.EXPENSE.value else "Продажи")
	text = f"🕐 Последние операции — {title} (с {offset+1})\n\n" + _format_list(items, cmap)
	kb = _with_delete_buttons(scope, offset, items)
	await _safe_edit_text(callback.message, text, kb)


@router.callback_query(lambda c: c.data == "view_expenses")
async def view_expenses(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession):
	offset = 0
	items = await _fetch_recent(session, callback.from_user.id, TransactionKind.EXPENSE.value, offset)
	cmap = await _category_map_for(items, session)
	text = "📊 Последние траты (последние 10):\n\n" + _format_list(items, cmap)
	kb = types.InlineKeyboardMarkup(inline_keyboard=[
		[
			types.InlineKeyboardButton(text="← Все", callback_data="recent:all:0"),
			types.InlineKeyboardButton(text="Продажи →", callback_data="recent:income:0"),
		],
		[
			types.InlineKeyboardButton(text="Вперёд →", callback_data="recent:expense:10") if len(items)==10 else types.InlineKeyboardButton(text="Меню", callback_data="main_menu")
		]
	])
	await _safe_edit_text(callback.message, text, kb)
	await callback.answer()


@router.callback_query(lambda c: c.data == "view_incomes")
async def view_incomes(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession):
	offset = 0
	items = await _fetch_recent(session, callback.from_user.id, TransactionKind.INCOME.value, offset)
	cmap = await _category_map_for(items, session)
	text = "📈 Последние продажи (последние 10):\n\n" + _format_list(items, cmap)
	kb = types.InlineKeyboardMarkup(inline_keyboard=[
		[
			types.InlineKeyboardButton(text="← Траты", callback_data="recent:expense:0"),
			types.InlineKeyboardButton(text="Все →", callback_data="recent:all:0"),
		],
		[
			types.InlineKeyboardButton(text="Вперёд →", callback_data="recent:income:10") if len(items)==10 else types.InlineKeyboardButton(text="Меню", callback_data="main_menu")
		]
	])
	await _safe_edit_text(callback.message, text, kb)
	await callback.answer() 