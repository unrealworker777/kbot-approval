# -*- coding: utf-8 -*-
"""
Отдельный официальный Telegram-бот (Bot API, через @BotFather) — шлёт
Константину в личку черновик + оригинальное сообщение с кнопками
Одобрить / Заменить / Пропустить. Реально отправляет текст только userbot.py,
и только после явного нажатия «Одобрить» (или после присланной замены).
"""

import html

from aiogram import Bot, Dispatcher, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

import config
import pending
import userbot

bot = Bot(token=config.APPROVAL_BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

CONTEXT_LIMIT = 1500  # чтобы карточка не превысила лимит Telegram в 4096 символов

KIND_LABEL = {
    "comment": "💬 Комментарий к посту",
    "chat_reply": "👥 Ответ в чате",
    "dm_reply": "✉️ Личное сообщение",
}


class EditState(StatesGroup):
    waiting_text = State()


def _keyboard(action_id):
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Одобрить", callback_data=f"approve:{action_id}"),
        InlineKeyboardButton(text="✏️ Заменить", callback_data=f"edit:{action_id}"),
        InlineKeyboardButton(text="🚫 Пропустить", callback_data=f"skip:{action_id}"),
    ]])


def _esc(text, limit=None):
    """HTML-экранирование + опциональная обрезка (в постах бывают < > & и длинные тексты)."""
    text = text or ""
    if limit and len(text) > limit:
        text = text[:limit] + "…"
    return html.escape(text)


def _card_text(action: pending.PendingAction, status: str = ""):
    label = KIND_LABEL.get(action.kind, action.kind)
    card = (f"{label}\n\n"
            f"<b>Сообщение:</b>\n{_esc(action.context_text, CONTEXT_LIMIT)}\n\n"
            f"<b>Черновик ответа:</b>\n{_esc(action.draft_text)}")
    if status:
        card += f"\n\n{status}"
    return card


async def notify(action: pending.PendingAction):
    await bot.send_message(
        config.APPROVAL_CHAT_ID,
        _card_text(action),
        reply_markup=_keyboard(action.id),
        parse_mode="HTML",
    )


@dp.callback_query(F.data.startswith("approve:"))
async def cb_approve(cq: CallbackQuery):
    action_id = cq.data.split(":", 1)[1]
    action = pending.pop(action_id)
    if not action:
        await cq.answer("Уже обработано или устарело.")
        return
    try:
        await userbot.send_action(action, action.draft_text)
    except Exception as e:
        await cq.message.edit_text(
            _card_text(action, f"⚠️ <b>Ошибка отправки:</b> {_esc(str(e))}"), parse_mode="HTML")
        await cq.answer("Ошибка отправки")
        return
    await cq.message.edit_text(_card_text(action, "✅ <b>Отправлено.</b>"), parse_mode="HTML")
    await cq.answer("Отправлено")


@dp.callback_query(F.data.startswith("skip:"))
async def cb_skip(cq: CallbackQuery):
    action_id = cq.data.split(":", 1)[1]
    action = pending.pop(action_id)
    if action:
        await cq.message.edit_text(_card_text(action, "🚫 <b>Пропущено.</b>"), parse_mode="HTML")
    await cq.answer("Пропущено")


@dp.callback_query(F.data.startswith("edit:"))
async def cb_edit(cq: CallbackQuery, state: FSMContext):
    action_id = cq.data.split(":", 1)[1]
    action = pending.get(action_id)
    if not action:
        await cq.answer("Уже обработано или устарело.")
        return
    await state.set_state(EditState.waiting_text)
    await state.update_data(action_id=action_id)
    await cq.message.answer("Пришли свой текст следующим сообщением — отправлю его вместо черновика.")
    await cq.answer()


@dp.message(EditState.waiting_text)
async def on_edit_text(message: Message, state: FSMContext):
    data = await state.get_data()
    action = pending.pop(data.get("action_id"))
    await state.clear()
    if not action:
        await message.answer("Этот черновик уже неактуален (одобрен/пропущен раньше).")
        return
    try:
        await userbot.send_action(action, message.text)
    except Exception as e:
        await message.answer(f"⚠️ Ошибка отправки: {e}")
        return
    await message.answer("✅ Отправлено твоим текстом.")


async def start_polling():
    await dp.start_polling(bot)
