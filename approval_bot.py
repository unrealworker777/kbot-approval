# -*- coding: utf-8 -*-
"""
Бот-одобрятор (Bot API, @BotFather). Шлёт Константину карточку с черновиком
и кнопками. Реально отправляет текст только userbot.py — после одобрения.
"""

import asyncio
import html

from aiogram import Bot, Dispatcher, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

import config
import draft
import pending
import userbot

bot = Bot(token=config.APPROVAL_BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

CONTEXT_LIMIT = 1500

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
        InlineKeyboardButton(text="🔁 Другие варианты", callback_data=f"more:{action_id}"),
        InlineKeyboardButton(text="🚫 Пропустить", callback_data=f"skip:{action_id}"),
    ]])


def _variants_keyboard(action_id):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Вариант 1", callback_data=f"pick:{action_id}:0"),
         InlineKeyboardButton(text="✅ Вариант 2", callback_data=f"pick:{action_id}:1")],
        [InlineKeyboardButton(text="🔁 Ещё 2 варианта", callback_data=f"more:{action_id}"),
         InlineKeyboardButton(text="✏️ Свой текст", callback_data=f"edit:{action_id}")],
        [InlineKeyboardButton(text="🚫 Пропустить", callback_data=f"skip:{action_id}")],
    ])


def _esc(text, limit=None):
    text = text or ""
    if limit and len(text) > limit:
        text = text[:limit] + "…"
    return html.escape(text)


def _link_line(action):
    return f"\n\n🔗 <a href=\"{action.link}\">Открыть оригинал</a>" if getattr(action, "link", "") else ""


def _card_text(action: pending.PendingAction, status: str = ""):
    label = KIND_LABEL.get(action.kind, action.kind)
    card = (f"{label}\n\n"
            f"<b>Сообщение:</b>\n{_esc(action.context_text, CONTEXT_LIMIT)}\n\n"
            f"<b>Черновик ответа:</b>\n{_esc(action.draft_text)}")
    card += _link_line(action)
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


@dp.callback_query(F.data.startswith("more:"))
async def cb_more(cq: CallbackQuery):
    action_id = cq.data.split(":", 1)[1]
    action = pending.get(action_id)
    if not action:
        await cq.answer("Уже обработано или устарело.")
        return
    await cq.answer("Готовлю 2 варианта…")
    already = [action.draft_text] + list(action.variants)
    variants = await asyncio.to_thread(
        draft.generate_variants, action.kind, action.context_text, 2, already)
    action.variants = variants
    label = KIND_LABEL.get(action.kind, action.kind)
    txt = (f"{label}\n\n"
           f"<b>Сообщение:</b>\n{_esc(action.context_text, CONTEXT_LIMIT)}\n\n"
           f"<b>Вариант 1:</b>\n{_esc(variants[0])}\n\n"
           f"<b>Вариант 2:</b>\n{_esc(variants[1])}")
    txt += _link_line(action)
    await cq.message.answer(txt, reply_markup=_variants_keyboard(action_id), parse_mode="HTML")


@dp.callback_query(F.data.startswith("pick:"))
async def cb_pick(cq: CallbackQuery):
    _, action_id, idx = cq.data.split(":")
    action = pending.get(action_id)
    if not action or not action.variants:
        await cq.answer("Уже обработано или устарело.")
        return
    try:
        text = action.variants[int(idx)]
    except (IndexError, ValueError):
        await cq.answer("Вариант не найден.")
        return
    await cq.answer()
    try:
        await userbot.send_action(action, text)
    except Exception as e:
        await cq.message.answer(f"⚠️ <b>Ошибка отправки:</b> {_esc(str(e))}", parse_mode="HTML")
        return
    pending.pop(action_id)
    await cq.message.edit_reply_markup(reply_markup=None)
    await cq.message.answer(f"✅ <b>Отправлен вариант {int(idx) + 1}.</b>", parse_mode="HTML")


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
