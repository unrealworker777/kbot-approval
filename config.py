# -*- coding: utf-8 -*-
"""Конфигурация — читает .env."""

import os
from dotenv import load_dotenv

load_dotenv()


def _split(env_name):
    raw = os.environ.get(env_name, "")
    return [c.strip() for c in raw.split(",") if c.strip()]


TELEGRAM_API_ID = int(os.environ["TELEGRAM_API_ID"])
TELEGRAM_API_HASH = os.environ["TELEGRAM_API_HASH"]
TELEGRAM_PHONE = os.environ["TELEGRAM_PHONE"]

APPROVAL_BOT_TOKEN = os.environ["APPROVAL_BOT_TOKEN"]
APPROVAL_CHAT_ID = int(os.environ["APPROVAL_CHAT_ID"])

MONITORED_CHANNELS = _split("MONITORED_CHANNELS")
MONITORED_CHATS = _split("MONITORED_CHATS")

AUTO_REACT_EMOJI = os.environ.get("AUTO_REACT_EMOJI", "👍")
STYLE_PROFILE_PATH = os.environ.get("STYLE_PROFILE_PATH", "style/style_profile.md")
KNOWLEDGE_BASE_PATH = os.environ.get("KNOWLEDGE_BASE_PATH", "knowledge_base.md")

# off | non_contacts | all
DM_HANDLING = os.environ.get("DM_HANDLING", "non_contacts").strip().lower()

DRAFT_MODEL = os.environ.get("DRAFT_MODEL", "claude-haiku-4-5-20251001")

# Фильтр пустых сообщений: на короткие благодарности/реакции бот не отвечает.
MIN_MEANINGFUL_LEN = int(os.environ.get("MIN_MEANINGFUL_LEN", "12"))
STOP_REPLIES = _split("STOP_REPLIES") or [
    "спасибо", "спс", "ок", "окей", "хорошо", "понял", "понятно", "ясно",
    "супер", "класс", "топ", "согласен", "верно", "точно", "+", "++", "да", "нет",
    "👍", "🔥", "❤", "🙏", "👏",
]

# ── Фильтр релевантности: на что Константину есть смысл отвечать ──
FILTER_MODEL = os.environ.get("FILTER_MODEL", "claude-haiku-4-5-20251001")
TOPIC_FILTER = os.environ.get("TOPIC_FILTER", "on").strip().lower()  # on | off

RELEVANT_TOPICS = """- КРТ, договоры КРТ
- ИЖС, посёлки, малоэтажка
- земельные участки, ВРИ, ЗОУИТ
- финмодель, маржа, проектное финансирование
- градостроительные нормативы, ППТ/ПМТ
- разборы конкретных кейсов и ошибок
- изменения в законах по стройке"""

STOP_TOPICS = """- анонсы конференций и мероприятий
- реклама курсов
- объявления о продаже квартир
- новости без разбора (просто факт, нечего разбирать)
- вакансии"""
