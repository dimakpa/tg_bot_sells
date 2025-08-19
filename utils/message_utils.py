from aiogram import Bot, types
from aiogram.fsm.context import FSMContext


async def _send_step_message(chat_id: int, bot_obj: Bot, state: FSMContext, text: str, reply_markup: types.InlineKeyboardMarkup | types.ReplyKeyboardMarkup | None = None) -> types.Message:
	"""Удаляет предыдущее бот-сообщение шага (если есть) и отправляет новое, сохраняя его ID в FSM."""
	data = await state.get_data()
	prev_id = data.get("last_bot_message_id")
	if prev_id:
		try:
			await bot_obj.delete_message(chat_id, prev_id)
		except Exception:
			pass
	msg = await bot_obj.send_message(chat_id, text, reply_markup=reply_markup)
	await state.update_data(last_bot_message_id=msg.message_id)
	return msg


async def _edit_callback_message(callback: types.CallbackQuery, state: FSMContext, text: str, reply_markup: types.InlineKeyboardMarkup | types.ReplyKeyboardMarkup | None = None) -> types.Message:
	"""Редактирует callback-сообщение и сохраняет его ID в FSM для последующего удаления."""
	await callback.message.edit_text(text, reply_markup=reply_markup)
	await state.update_data(last_bot_message_id=callback.message.message_id)
	return callback.message 