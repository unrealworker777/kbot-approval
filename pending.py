# -*- coding: utf-8 -*-
"""
Хранилище черновиков, ожидающих одобрения Константином.
In-memory: при перезапуске процесса очередь очищается (незаконченные одобрения
придётся создать заново). Для личного использования достаточно; при желании
можно заменить на SQLite.

Добавлено:
- TTL — старые неотвеченные черновики автоматически выкидываются, чтобы память
  не росла бесконечно.
"""

import time
import uuid

TTL_SECONDS = 24 * 3600  # черновик живёт сутки, потом выкидывается


class PendingAction:
    def __init__(self, kind, chat_id, reply_to_msg_id, context_text, draft_text):
        self.id = uuid.uuid4().hex[:10]
        self.kind = kind  # 'comment' | 'chat_reply' | 'dm_reply'
        self.chat_id = chat_id            # для comment это id КАНАЛА (не группы обсуждений)
        self.reply_to_msg_id = reply_to_msg_id  # для comment это id ПОСТА в канале
        self.context_text = context_text
        self.draft_text = draft_text
        self.created_at = time.time()


_STORE = {}


def _purge():
    now = time.time()
    stale = [k for k, v in _STORE.items() if now - v.created_at > TTL_SECONDS]
    for k in stale:
        _STORE.pop(k, None)


def add(action: PendingAction) -> PendingAction:
    _purge()
    _STORE[action.id] = action
    return action


def get(action_id):
    return _STORE.get(action_id)


def pop(action_id):
    return _STORE.pop(action_id, None)
