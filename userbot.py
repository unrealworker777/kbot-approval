# -*- coding: utf-8 -*-
"""
Юзербот на личном аккаунте Константина (Telethon).
Реакции — сразу. Тексты — только после одобрения через approval_bot.py.
"""

import asyncio
from datetime import datetime, timezone

from telethon import TelegramClient, events
from telethon.tl.functions.messages import GetDiscussionMessageRequest, SendReactionRequest
from telethon.tl.types import ReactionEmoji

import config
import draft
import pending

client = TelegramClient("konstantin_session", config.TELEGRAM_API_ID, config.TELEGRAM_API_HASH)

approval_notifier = None

_START_TS = None
_ME_ID = None


async def start():
    global _START_TS, _ME_ID
    await client.start(phone=config.TELEGRAM_PHONE)
    me = await client.get_me()
    _ME_ID = me.id
    _START_TS = datetime.now(timezone.utc)
    print(f"Юзербот запущен как {me.first_name} (id={me.id})")

    if config.MONITORED_CHANNELS:
        client.add_event_handler(
            on_channel_post, events.NewMessage(chats=config.MONITORED_CHANNELS))
        print(f"Слежу за каналами: {', '.join(config.MONITORED_CHANNELS)}")
    else:
        print("MONITORED_CHANNELS пуст — каналы не отслеживаются.")

    if config.MONITORED_CHATS:
        client.add_event_handler(
            on_chat_message, events.NewMessage(chats=config.MONITORED_CHATS))
        print(f"Слежу за чатами: {', '.join(config.MONITORED_CHATS)}")
    else:
        print("MONITORED_CHATS пуст — чаты не отслеживаются.")

    if config.DM_HANDLING != "off":
        client.add_event_handler(
            on_private_message, events.NewMessage(incoming=True, func=lambda e: e.is_private))
        print(f"Обработка ЛС: {config.DM_HANDLING}")
    else:
        print("DM_HANDLING=off — личка не обрабатывается.")


async def _notify(action: pending.PendingAction):
    if approval_notifier is not None:
        await approval_notifier(action)
    else:
        print(f"[Нет approval_notifier] Черновик {action.id}: {action.draft_text}")


def _is_old(event):
    d = getattr(event.message, "date", None)
    return _START_TS is not None and d is not None and d < _START_TS


async def _skip_sender(event):
    if _ME_ID is not None and getattr(event, "sender_id", None) == _ME_ID:
        return True
    sender = await event.get_sender()
    if getattr(sender, "bot", False):
        return True
    return False


async def _msg_link(event):
    """Ссылка на оригинальный пост/сообщение: t.me/username/id или t.me/c/short/id."""
    try:
        chat = await event.get_chat()
        uname = getattr(chat, "username", None)
        if uname:
            return f"https://t.me/{uname}/{event.id}"
        cid = event.chat_id
        if cid is not None and str(cid).startswith("-100"):
            return f"https://t.me/c/{str(cid)[4:]}/{event.id}"
    except Exception:
        pass
    return ""


def _meaningless(text):
    """True, если отвечать нет смысла: короткое «спасибо/ок/👍» и т.п."""
    t = (text or "").strip().lower()
    cleaned = t.strip(" .!?)(-—…,")
    if not cleaned:
        return True
    if cleaned in config.STOP_REPLIES:
        return True
    if len(cleaned) < config.MIN_MEANINGFUL_LEN:
        first = cleaned.split()[0] if cleaned.split() else cleaned
        if first in config.STOP_REPLIES:
            return True
    return False


async def on_channel_post(event):
    if not event.is_channel or event.is_group:
        return
    if _is_old(event):
        return
    text = event.raw_text or ""
    if not text.strip():
        return

    try:
        await client(SendReactionRequest(
            peer=await event.get_input_chat(),
            msg_id=event.id,
            reaction=[ReactionEmoji(emoticon=config.AUTO_REACT_EMOJI)],
        ))
    except Exception as e:
        print(f"Не удалось поставить реакцию: {e}")

    draft_text = await asyncio.to_thread(draft.generate_draft, "comment", text)
    link = await _msg_link(event)
    action = pending.add(pending.PendingAction(
        kind="comment", chat_id=event.chat_id, reply_to_msg_id=event.id,
        context_text=text, draft_text=draft_text, link=link,
    ))
    await _notify(action)


async def on_chat_message(event):
    if event.out:
        return
    if _is_old(event) or await _skip_sender(event):
        return
    reply = await event.get_reply_message()
    if not reply or not reply.out:
        return
    text = event.raw_text or ""
    if not text.strip() or _meaningless(text):
        return

    draft_text = await asyncio.to_thread(draft.generate_draft, "chat_reply", text)
    link = await _msg_link(event)
    action = pending.add(pending.PendingAction(
        kind="chat_reply", chat_id=event.chat_id, reply_to_msg_id=event.id,
        context_text=text, draft_text=draft_text, link=link,
    ))
    await _notify(action)


async def on_private_message(event):
    if event.out:
        return
    if _is_old(event) or await _skip_sender(event):
        return
    text = event.raw_text or ""
    if not text.strip() or _meaningless(text):
        return

    if config.DM_HANDLING == "non_contacts":
        sender = await event.get_sender()
        if getattr(sender, "contact", False):
            return

    draft_text = await asyncio.to_thread(draft.generate_draft, "dm_reply", text)
    link = await _msg_link(event)
    action = pending.add(pending.PendingAction(
        kind="dm_reply", chat_id=event.chat_id, reply_to_msg_id=event.id,
        context_text=text, draft_text=draft_text, link=link,
    ))
    await _notify(action)


async def send_action(action: pending.PendingAction, text: str):
    if action.kind == "comment":
        disc = await client(GetDiscussionMessageRequest(
            peer=action.chat_id, msg_id=action.reply_to_msg_id))
        if not disc.messages:
            raise RuntimeError("У канала нет группы обсуждений — комментарий оставить нельзя.")
        top = disc.messages[0]
        await client.send_message(top.peer_id, text, reply_to=top.id)
    elif action.kind == "dm_reply":
        await client.send_message(action.chat_id, text)
    else:
        await client.send_message(action.chat_id, text, reply_to=action.reply_to_msg_id)
