# -*- coding: utf-8 -*-
"""
Юзербот на личном аккаунте (Telethon).
Комментарии и чаты — через одобрение. Личка — по режиму DM_MODE.
"""

import asyncio
import random
from datetime import datetime, timezone, date

from telethon import TelegramClient, events
from telethon.tl.functions.messages import GetDiscussionMessageRequest, SendReactionRequest
from telethon.tl.types import ReactionEmoji

import bitrix
import config
import consult
import draft
import pending

client = TelegramClient("konstantin_session", config.TELEGRAM_API_ID, config.TELEGRAM_API_HASH)

approval_notifier = None

_START_TS = None
_ME_ID = None

# суточный лимит исходящих в личку (защита аккаунта от бана)
_dm_day = None
_dm_count = 0


def _dm_quota_ok():
    global _dm_day, _dm_count
    today = date.today()
    if _dm_day != today:
        _dm_day, _dm_count = today, 0
    if _dm_count >= config.DM_DAILY_LIMIT:
        return False
    _dm_count += 1
    return True


async def _valid_chats(names, kind):
    """Оставляет только те юзернеймы, которые Telegram реально резолвит."""
    ok = []
    for name in names:
        try:
            await client.get_input_entity(name)
            ok.append(name)
        except Exception as e:
            print(f"[{kind}] пропускаю «{name}»: {type(e).__name__}: {e}")
    return ok


async def start():
    global _START_TS, _ME_ID
    await client.start(phone=config.TELEGRAM_PHONE)
    me = await client.get_me()
    _ME_ID = me.id
    _START_TS = datetime.now(timezone.utc)
    print(f"Юзербот запущен как {me.first_name} (id={me.id})")

    channels = await _valid_chats(config.MONITORED_CHANNELS, "каналы")
    if channels:
        client.add_event_handler(on_channel_post, events.NewMessage(chats=channels))
        print(f"Слежу за каналами ({len(channels)}): {', '.join(channels)}")
    else:
        print("Рабочих каналов нет — каналы не отслеживаются.")

    chats = await _valid_chats(config.MONITORED_CHATS, "чаты")
    if chats:
        client.add_event_handler(on_chat_message, events.NewMessage(chats=chats))
        print(f"Слежу за чатами ({len(chats)}): {', '.join(chats)}")
    else:
        print("Рабочих чатов нет — чаты не отслеживаются.")

    if config.DM_HANDLING != "off":
        client.add_event_handler(
            on_private_message, events.NewMessage(incoming=True, func=lambda e: e.is_private))
        print(f"Обработка ЛС: {config.DM_HANDLING}, режим: {config.DM_MODE}"
              + (" (АВТОНОМНО, без модерации)" if config.DM_MODE == "consult"
                 else " (через одобрение)"))
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


async def _can_comment(event):
    try:
        disc = await client(GetDiscussionMessageRequest(
            peer=event.chat_id, msg_id=event.id))
        return bool(getattr(disc, "messages", None))
    except Exception:
        return False


def _meaningless(text):
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

    if not await asyncio.to_thread(draft.is_relevant, text):
        return

    if not await _can_comment(event):
        return

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

    if not await asyncio.to_thread(draft.is_relevant, text):
        return

    draft_text = await asyncio.to_thread(draft.generate_draft, "chat_reply", text)
    link = await _msg_link(event)
    action = pending.add(pending.PendingAction(
        kind="chat_reply", chat_id=event.chat_id, reply_to_msg_id=event.id,
        context_text=text, draft_text=draft_text, link=link,
    ))
    await _notify(action)


async def _autonomous_reply(event, text):
    """Автономный контур: ассистент ИПМ отвечает сам (consult.py) + лид в Битрикс."""
    if not _dm_quota_ok():
        print("[consult] суточный лимит сообщений исчерпан — не отвечаю")
        return

    sender = await event.get_sender()
    uid = getattr(sender, "id", None)
    uname = getattr(sender, "username", "") or ""
    fname = getattr(sender, "first_name", "") or ""

    answer = await asyncio.to_thread(consult.reply, uid, text, fname)
    if not answer:
        return

    await asyncio.sleep(random.randint(config.DM_DELAY_MIN, config.DM_DELAY_MAX))
    async with client.action(event.chat_id, "typing"):
        await asyncio.sleep(min(len(answer) / 60, 6))
    await client.send_message(event.chat_id, answer)

    lead = await asyncio.to_thread(consult.detect_lead, uid)
    if lead:
        await asyncio.to_thread(bitrix.create_lead, lead, uname, fname)
        if approval_notifier is not None:
            await _notify(pending.add(pending.PendingAction(
                kind="dm_reply", chat_id=event.chat_id, reply_to_msg_id=event.id,
                context_text=f"🔔 ЛИД в Битрикс от @{uname or uid}\n{lead.get('summary','')}",
                draft_text="(лид создан автоматически, ответа не требуется)",
            )))


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

    # АВТОНОМНЫЙ контур: ассистент отвечает сам
    if config.DM_MODE == "consult":
        await _autonomous_reply(event, text)
        return

    # контур с одобрением: черновик + карточка
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
