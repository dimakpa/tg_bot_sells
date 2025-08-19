import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import Command
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from storage.database import init_db, get_db, close_db
from storage.categories import load_categories_from_json
from services.transaction_service import TransactionService, parse_amount
from keyboards.main import get_main_keyboard, get_quick_actions_keyboard, get_cancel_keyboard
from keyboards.categories import get_categories_keyboard, get_quick_income_keyboard, get_confirm_keyboard
from storage.models import TransactionKind
from storage.categories import get_categories_by_kind, get_subcategories, get_category_by_id
from loguru import logger
from handlers import report as report_handlers
from utils.message_utils import _send_step_message, _edit_callback_message

# Настройка логирования
logger.add("bot.log", rotation="1 day", retention="7 days", level="INFO")

# Инициализация бота и диспетчера
bot = Bot(token=settings.bot_token)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
from middlewares.db import DatabaseSessionMiddleware
# Подключаем middleware, чтобы внедрять AsyncSession в обработчики

dp.update.middleware(DatabaseSessionMiddleware())
# Роутер отчётов

dp.include_router(report_handlers.router)
from handlers import recent as recent_handlers
# Роутер последних операций

dp.include_router(recent_handlers.router)





# Состояния FSM
class TransactionStates(StatesGroup):
	waiting_for_category = State()
	waiting_for_subcategory = State()
	waiting_for_comment = State()
	waiting_for_amount = State()
	waiting_for_confirmation = State()


# Обработчики команд
@dp.message(Command("start"))
async def cmd_start(message: types.Message, session: AsyncSession):
	"""Обработчик команды /start"""
	user = message.from_user
	
	# Создаем или получаем пользователя
	transaction_service = TransactionService(session)
	await transaction_service.get_or_create_user(
		user_id=user.id,
		username=user.username,
		first_name=user.first_name,
		last_name=user.last_name
	)
	
	welcome_text = f"""
👋 Привет, {user.first_name or user.username or 'пользователь'}!

Я бот для учёта расходов и продаж. Выберите действие:
    """
	
	await message.answer(welcome_text, reply_markup=get_main_keyboard())


@dp.message(Command("help"))
async def cmd_help(message: types.Message):
	"""Обработчик команды /help"""
	help_text = """
📖 Справка по командам:

/start - Главное меню
/help - Эта справка
/undo - Отменить последнюю операцию (в течение 5 минут)
/edit_last - Редактировать последнюю операцию
/export - Быстрый экспорт отчёта

💡 Быстрые команды:
• Нажмите "💰 Трата" для записи расходов
• Нажмите "💸 Продажа" для записи доходов
• Используйте "📊 Посмотреть траты" для просмотра расходов
• Используйте "📈 Посмотреть продажи" для просмотра доходов
• Используйте "📋 Экспорт отчёта" для создания отчётов
    """
	
	await message.answer(help_text, reply_markup=get_main_keyboard())


@dp.message(Command("undo"))
async def cmd_undo(message: types.Message, session: AsyncSession):
	"""Обработчик команды /undo"""
	user_id = message.from_user.id
	transaction_service = TransactionService(session)
	
	deleted_transaction = await transaction_service.delete_last_transaction(user_id)
	
	if deleted_transaction:
		await message.answer(
			f"✅ Последняя операция отменена:\n"
			f"Сумма: {deleted_transaction.amount} {deleted_transaction.currency}\n"
			f"Категория: {deleted_transaction.category_id}"
		)
	else:
		await message.answer("❌ Не найдено операций для отмены (или прошло больше 5 минут)")


# Обработчики callback-запросов
@dp.callback_query(lambda c: c.data == "expense")
async def process_expense(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession):
	"""Обработчик выбора траты"""
	await state.set_state(TransactionStates.waiting_for_category)
	await state.update_data(kind="expense")
	
	categories = await get_categories_by_kind(session, TransactionKind.EXPENSE)
	keyboard = get_categories_keyboard(categories, "expense")
	await callback.message.edit_text(
		"💰 Выберите категорию траты:",
		reply_markup=keyboard
	)


@dp.callback_query(lambda c: c.data == "income")
async def process_income(callback: types.CallbackQuery, state: FSMContext):
	"""Обработчик выбора продажи"""
	await state.set_state(TransactionStates.waiting_for_category)
	await state.update_data(kind="income")
	
	keyboard = get_quick_income_keyboard()
	await callback.message.edit_text(
		"💸 Выберите тип продажи:",
		reply_markup=keyboard
	)


@dp.callback_query(lambda c: c.data.startswith("expense_category:") or c.data.startswith("income_category:"))
async def process_category_selection(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession):
	"""Обработчик выбора категории"""
	category_id = int(callback.data.split(":")[1])
	data = await state.get_data()
	
	# Получаем категорию
	category = await get_category_by_id(session, category_id)
	if not category:
		await callback.answer("❌ Категория не найдена")
		return
	
	# Проверяем, есть ли подкатегории
	subcategories = await get_subcategories(session, category_id)
	
	if subcategories:
		# Есть подкатегории - переходим к их выбору
		await state.set_state(TransactionStates.waiting_for_subcategory)
		await state.update_data(category_id=category_id, category_name=category.name)
		
		keyboard = get_categories_keyboard(subcategories, "subcategory")
		await callback.message.edit_text(f"📂 Выберите подкатегорию для '{category.name}':", reply_markup=keyboard)
	else:
		# Нет подкатегорий - переходим к комментарию
		await state.set_state(TransactionStates.waiting_for_comment)
		await state.update_data(
			category_id=category_id,
			category_name=category.name,
			subcategory_id=None,
			subcategory_name=None
		)
		
		await _edit_callback_message(
			callback,
			state,
			f"💬 Введите комментарий к операции '{category.name}' (или отправьте '-' для пропуска):",
			reply_markup=get_cancel_keyboard()
		)


@dp.callback_query(lambda c: c.data.startswith("quick_income:"))
async def process_quick_income(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession):
	"""Обработчик быстрого выбора дохода"""
	category_id = int(callback.data.split(":")[1])
	data = await state.get_data()
	
	# Получаем категорию
	category = await get_category_by_id(session, category_id)
	if not category:
		await callback.answer("❌ Категория не найдена")
		return
	
	await state.set_state(TransactionStates.waiting_for_comment)
	await state.update_data(
		category_id=category_id,
		category_name=category.name,
		subcategory_id=None,
		subcategory_name=None
	)
	await _edit_callback_message(
		callback,
		state,
		f"💬 Введите комментарий к операции '{category.name}' (или отправьте '-' для пропуска):",
		reply_markup=get_cancel_keyboard()
	)


@dp.callback_query(lambda c: c.data.startswith("subcategory_category:"))
async def process_subcategory_selection(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession):
	"""Обработчик выбора подкатегории"""
	subcategory_id = int(callback.data.split(":")[1])
	data = await state.get_data()
	
	# Получаем подкатегорию
	subcategory = await get_category_by_id(session, subcategory_id)
	if not subcategory:
		await callback.answer("❌ Подкатегория не найдена")
		return
	
	await state.set_state(TransactionStates.waiting_for_comment)
	await state.update_data(
		subcategory_id=subcategory_id,
		subcategory_name=subcategory.name
	)
	
	await _edit_callback_message(
		callback,
		state,
        f"💬 Введите комментарий к операции '{data['category_name']} → {subcategory.name}' (или отправьте '-' для пропуска):",
        reply_markup=get_cancel_keyboard()
    )


@dp.message(TransactionStates.waiting_for_comment)
async def process_comment(message: types.Message, state: FSMContext):
	"""Обработчик ввода комментария"""
	comment = message.text.strip()
	if comment == "-":
		comment = None
	
	await state.update_data(comment=comment)
	await state.set_state(TransactionStates.waiting_for_amount)
	
	# Удаляем сообщение пользователя
	try:
		await message.delete()
	except Exception:
		pass
	
	await _send_step_message(
		message.chat.id,
		bot,
		state, 
		"💰 Введите сумму:",
		reply_markup=get_cancel_keyboard()
	)


@dp.message(TransactionStates.waiting_for_amount)
async def process_amount(message: types.Message, state: FSMContext):
	"""Обработчик ввода суммы"""
	# Удаляем сообщение пользователя
	try:
		await message.delete()
	except Exception:
		pass
	
	amount = parse_amount(message.text)
	
	if amount is None:
		await _send_step_message(
			message.chat.id,
			bot,
			state,
			"❌ Неверный формат суммы. Попробуйте снова (например: 1000, 1 500, 2.50):",
			reply_markup=get_cancel_keyboard()
		)
		return
	
	if amount <= 0:
		await _send_step_message(
			message.chat.id,
			bot,
			state,
			"❌ Сумма должна быть больше нуля. Попробуйте снова:",
			reply_markup=get_cancel_keyboard()
		)
		return
	
	data = await state.get_data()
	await state.update_data(amount=amount)
	
	# Формируем текст для подтверждения
	kind_text = "трата" if data['kind'] == 'expense' else "доход"
	category_text = data['category_name']
	if data.get('subcategory_name'):
		category_text += f" → {data['subcategory_name']}"
	
	comment_text = f"\n💬 Комментарий: {data.get('comment', 'не указан')}" if data.get('comment') else "\n💬 Комментарий: не указан"
	
	confirm_text = f"""
📋 Подтвердите операцию:

💰 Тип: {kind_text}
📂 Категория: {category_text}
💵 Сумма: {amount} RUB{comment_text}

Всё верно?
    """
	
	await state.set_state(TransactionStates.waiting_for_confirmation)
	await _send_step_message(message.chat.id, bot, state, confirm_text, reply_markup=get_confirm_keyboard("transaction"))


@dp.callback_query(lambda c: c.data == "transaction_confirm")
async def process_confirmation(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession):
	"""Обработчик подтверждения транзакции"""
	data = await state.get_data()
	kind = data.get('kind')
	category_id = int(data.get('category_id'))
	subcategory_id = int(data['subcategory_id']) if data.get('subcategory_id') else None
	amount = data.get('amount')
	comment = data.get('comment') or None

	if amount is None:
		await callback.answer("❌ Ошибка при обработке суммы")
		return
	
	try:
		# Создаем транзакцию
		transaction_service = TransactionService(session)
		transaction = await transaction_service.create_transaction(
			user_id=callback.from_user.id,
			kind=TransactionKind(kind),
			category_id=category_id,
			subcategory_id=subcategory_id,
			amount=amount,
			comment=comment
		)
		
		# Очищаем состояние
		await state.clear()
		
		# Отправляем подтверждение
		kind_text = "трата" if kind == 'expense' else "доход"
		await callback.message.edit_text(
			f"✅ {kind_text.capitalize()} успешно записана!\n"
			f"💰 Сумма: {amount} RUB\n"
			f"🆔 ID: {transaction.id}",
			reply_markup=get_quick_actions_keyboard()
		)
		
	except Exception as e:
		logger.error(f"Ошибка при создании транзакции: {e}")
		await callback.answer("❌ Ошибка при сохранении операции")
		await callback.message.edit_text(
			"❌ Произошла ошибка при сохранении операции. Попробуйте снова.",
			reply_markup=get_main_keyboard()
		)


@dp.callback_query(lambda c: c.data == "cancel")
async def process_cancel(callback: types.CallbackQuery, state: FSMContext):
	"""Обработчик отмены"""
	await state.clear()
	await callback.message.edit_text(
		"❌ Операция отменена",
		reply_markup=get_main_keyboard()
	)


@dp.callback_query(lambda c: c.data == "main_menu")
async def process_main_menu(callback: types.CallbackQuery, state: FSMContext):
	"""Обработчик возврата в главное меню"""
	await state.clear()
	await callback.message.edit_text(
		"🏠 Главное меню:",
		reply_markup=get_main_keyboard()
	)


@dp.callback_query(lambda c: c.data == "add_another")
async def process_add_another(callback: types.CallbackQuery, state: FSMContext):
	"""Обработчик добавления ещё одной операции"""
	await state.clear()
	await callback.message.edit_text(
		"➕ Выберите тип операции:",
		reply_markup=get_main_keyboard()
	)


# Обработчики просмотра транзакций (заглушки)
@dp.callback_query(lambda c: c.data == "export_report_disabled")
async def process_view_operations(callback: types.CallbackQuery):
	"""Обработчики просмотра операций (пока заглушки)"""
	text = "📋 Экспорт отчёта: выберите тип"
	from aiogram.utils.keyboard import InlineKeyboardBuilder
	kb = InlineKeyboardBuilder()
	kb.row(
		types.InlineKeyboardButton(text="Траты (30 дней)", callback_data="export:expense:30"),
		types.InlineKeyboardButton(text="Продажи (30 дней)", callback_data="export:income:30"),
	)
	await callback.message.edit_text(text, reply_markup=kb.as_markup())


async def main():
	"""Главная функция"""
	logger.info("Запуск бота...")
	
	# Инициализируем базу данных
	await init_db()
	
	# Загружаем категории
	async for session in get_db():
		await load_categories_from_json(session)
		break
	
	logger.info("Бот запущен!")
	
	try:
		# Удаляем возможный активный вебхук перед polling
		await bot.delete_webhook(drop_pending_updates=True)
		await dp.start_polling(bot)
	finally:
		await close_db()
		logger.info("Бот остановлен")


if __name__ == "__main__":
	asyncio.run(main())