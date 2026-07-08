# -*- coding: utf-8 -*-
"""Конфигурация — читает .env. Скопируй .env.example в .env и заполни."""

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

# ANTHROPIC_API_KEY можно не задавать, если сделан `ant auth login` —
# тогда клиент Anthropic подхватит профиль автоматически.

MONITORED_CHANNELS = _split("MONITORED_CHANNELS")
MONITORED_CHATS = _split("MONITORED_CHATS")

AUTO_REACT_EMOJI = os.environ.get("AUTO_REACT_EMOJI", "👍")
STYLE_PROFILE_PATH = os.environ.get("STYLE_PROFILE_PATH", "style/style_profile.md")

# Как обрабатывать входящие ЛС:
#   off          — не готовить черновики на личку вообще
#   non_contacts — только от тех, кого НЕТ в контактах (холодные входящие / лиды)
#                  → переписки с семьёй/текущими клиентами не уходят в API
#   all          — на все входящие ЛС
DM_HANDLING = os.environ.get("DM_HANDLING", "non_contacts").strip().lower()

# Модель для черновиков (Haiku — быстро и дёшево для потоковых коротких ответов)
DRAFT_MODEL = os.environ.get("DRAFT_MODEL", "claude-haiku-4-5-20251001")
