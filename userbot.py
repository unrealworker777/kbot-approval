# -*- coding: utf-8 -*-
"""
Юзербот на личном аккаунте Константина (Telethon).

- Авто-реакции на посты в отслеживаемых каналах — низкий риск, без одобрения.
- Комментарии к постам, ответы в чатах и в ЛС — генерируются черновиком и
  ВСЕГДА ждут одобрения через approval_bot.py, прежде чем реально уйдут.

Важно про риск бана: использование Telegram API для автоматизации личного
аккаунта формально не приветствуется правилами Telegram. Здесь каждое
текстовое действие проходит через ручное одобрение — это не спам-паттерн,
но полностью исключить риск нельзя.
"""

import asyncio

from telethon import TelegramClient, events
from telethon.tl.functions.messages import GetDiscussionMessageRequest, SendReactionRequest
from telethon.tl.types import ReactionEmoji

import config
import draft
import pending

client = TelegramClient("konstantin_session", config.TELEGRAM_API_ID, config.TELEGRAM_API_HASH)

# main.py подставляет сюда approval_bot.notify до старта опроса
approval_notifier = None


async def start():
    await client.start(phone=config.TELEGRAM_PHONE)
    me = await client.get_me()
    print(f"Юзербот запущен как {me.first_name} (id={me.id})")

    # Регистрируем хендлеры ЯВНО и только если списки заданы — иначе пустой
    # список превращался бы в «слушать вообще всё» и лайкать везде.
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


async def on_channel_post(event):
    # интересуют только посты в каналах (broadcast), не сообщения в супергруппах
    if not event.is_channel or event.is_group:
        return
    text = event.raw_text or ""
    if not text.strip():
        return

    # авто-реакция — не текст, низкий риск, без одобрения
    try:
        await client(SendReactionRequest(
            peer=await event.get_input_chat(),
            msg_id=event.id,
            reaction=[ReactionEmoji(emoticon=config.AUTO_REACT_EMOJI)],
        ))
    except Exception as e:
        print(f"Не удалось поставить реакцию: {e}")

    draft_text = await asyncio.to_thread(draft.generate_draft, "comment", text)
    action = pending.add(pending.PendingAction(
        kind="comment", chat_id=event.chat_id, reply_to_msg_id=event.id,
        context_text=text, draft_text=draft_text,
    ))
    await _notify(action)


async def on_chat_message(event):
    if event.out:
        return  # свои сообщения игнорируем
    reply = await event.get_reply_message()
    if not reply or not reply.out:
        return  # реагируем только на ответы НА сообщения Константина
    text = event.raw_text or ""
    if not text.strip():
        return

    draft_text = await asyncio.to_thread(draft.generate_draft, "chat_reply", text)
    action = pending.add(pending.PendingAction(
        kind="chat_reply", chat_id=event.chat_id, reply_to_msg_id=event.id,
        context_text=text, draft_text=draft_text,
    ))
    await _notify(action)


async def on_private_message(event):
    if event.out:
        return
    text = event.raw_text or ""
    if not text.strip():
        return

    # приватность: по умолчанию не трогаем переписки с контактами (семья, текущие
    # клиенты) — их содержимое не уходит в API. Только холодные входящие.
    if config.DM_HANDLING == "non_contacts":
        sender = await event.get_sender()
        if getattr(sender, "contact", False):
            return

    draft_text = await asyncio.to_thread(draft.generate_draft, "dm_reply", text)
    action = pending.add(pending.PendingAction(
        kind="dm_reply", chat_id=event.chat_id, reply_to_msg_id=event.id,
        context_text=text, draft_text=draft_text,
    ))
    await _notify(action)


async def send_action(action: pending.PendingAction, text: str):
    """Реально отправляет одобренный (или заменённый) текст от имени Константина."""
    if action.kind == "comment":
        # Комментарий к посту канала уходит НЕ в сам канал, а в привязанную
        # группу обсуждений — ответом на авто-форвард поста туда.
        disc = await client(GetDiscussionMessageRequest(
            peer=action.chat_id, msg_id=action.reply_to_msg_id))
        if not disc.messages:
            raise RuntimeError(
                "У канала нет группы обсуждений — комментарий оставить нельзя.")
        top = disc.messages[0]
        await client.send_message(top.peer_id, text, reply_to=top.id)
    elif action.kind == "dm_reply":
        await client.send_message(action.chat_id, text)
    else:  # chat_reply
        await client.send_message(action.chat_id, text, reply_to=action.reply_to_msg_id)
