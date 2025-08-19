from aiogram import Router, types
from sqlalchemy.ext.asyncio import AsyncSession
from aiogram.fsm.context import FSMContext
from datetime import datetime, timedelta
from services.report_service import ReportService
from storage.models import TransactionKind
from keyboards.main import get_main_keyboard
from loguru import logger

# Импортируем функцию для правильного управления сообщениями
from utils.message_utils import _edit_callback_message, _send_step_message

router = Router()


@router.callback_query(lambda c: c.data.startswith("export:"))
async def handle_export(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession):
	# formats:
	# export:expense:days
	# export:income:days
	# export:income:days:aggregation  where aggregation in {detail,by_category,by_subcategory,overall}
	parts = callback.data.split(":")
	_, kind_str, days_str, *rest = parts
	days = int(days_str)
	aggregation = rest[0] if rest else None
	kind = TransactionKind.EXPENSE if kind_str == "expense" else TransactionKind.INCOME
	
	end = datetime.utcnow()
	start = end - timedelta(days=days)
	service = ReportService(session)
	xlsx_path, png_paths, summary = await service.build_report(
		user_id=callback.from_user.id,
		kind=kind,
		start_date=start,
		end_date=end,
		aggregation=aggregation,
	)
	
	title = 'Траты' if kind == TransactionKind.EXPENSE else 'Продажи'
	caption_base = f"Отчёт: {title}\nСумма: {summary['total']:.2f}, операций: {summary['count']}"
	
	await callback.message.answer_document(
		document=types.FSInputFile(str(xlsx_path)),
		caption=caption_base + "\nФормат: Excel"
	)
	# отправляем PNG(и)
	for p in png_paths:
		await callback.message.answer_document(
			document=types.FSInputFile(str(p)),
			caption=caption_base + "\nФормат: PNG"
		)
	
	# Удаляем старое меню с выбором отчетов
	data = await state.get_data()
	prev_id = data.get("last_bot_message_id")
	if prev_id:
		try:
			await callback.bot.delete_message(callback.message.chat.id, prev_id)
		except Exception:
			pass
	
	await callback.message.answer("Готово. Главное меню:", reply_markup=get_main_keyboard())
	await callback.answer("Готово")


@router.callback_query(lambda c: c.data == "export_report")
async def export_menu(callback: types.CallbackQuery, state: FSMContext):
	text = "📋 Экспорт отчёта: выберите тип"
	from aiogram.utils.keyboard import InlineKeyboardBuilder
	kb = InlineKeyboardBuilder()
	kb.row(
		types.InlineKeyboardButton(text="Траты 30д", callback_data="export:expense:30:detail"),
		types.InlineKeyboardButton(text="Продажи 30д", callback_data="export:income:30:detail"),
	)
	kb.row(
		types.InlineKeyboardButton(text="Траты: кат.", callback_data="export:expense:30:by_category"),
		types.InlineKeyboardButton(text="Продажи: кат.", callback_data="export:income:30:by_category"),
	)
	kb.row(
		types.InlineKeyboardButton(text="Траты: подкат.", callback_data="export:expense:30:by_subcategory"),
		types.InlineKeyboardButton(text="Продажи: подкат.", callback_data="export:income:30:by_subcategory"),
	)
	kb.row(
		types.InlineKeyboardButton(text="Траты: секции", callback_data="export:expense:30:by_category_sections"),
		types.InlineKeyboardButton(text="Траты: итого", callback_data="export:expense:30:overall"),
	)
	kb.row(
		types.InlineKeyboardButton(text="Продажи: итого", callback_data="export:income:30:overall"),
	)
	await _edit_callback_message(callback, state, text, reply_markup=kb.as_markup()) 