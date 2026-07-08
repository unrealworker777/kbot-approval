# -*- coding: utf-8 -*-
"""
Генерация черновика ответа в стиле Константина через Claude API.

Функция синхронная — в userbot.py её вызывают через asyncio.to_thread(...),
чтобы сетевой запрос не блокировал event loop.
"""

from pathlib import Path

import anthropic

import config

_client = anthropic.Anthropic()  # берёт ANTHROPIC_API_KEY из окружения или профиль `ant auth login`

SYSTEM_TEMPLATE = """Ты помогаешь Константину быстро отвечать в Telegram — комментарии под постами,
реплики в чатах и личные сообщения.

Пиши строго от первого лица, как будто это сам Константин. Никогда не подписывайся и не упоминай,
что ты ассистент или ИИ — это черновик, который Константин лично прочитает и одобрит перед отправкой.

Вот описание его стиля общения — используй как основу тона и манеры:
{style_profile}

Правила:
- Один короткий вариант ответа, без "или" и перечисления вариантов.
- Без канцелярита и излишней вежливости, если это не в его стиле.
- Не выдумывай факты о жизни Константина, которых нет в контексте.
- Если это комментарий к посту — 1-3 предложения, уместные под чужим постом.
- Если это личное сообщение или реплика в чате — продолжай тему, которую поднял собеседник.
- Если собеседник прямо спрашивает, бот ли это / ИИ ли это — верни ровно строку [FLAG_HUMAN]
  и ничего больше (на такое ответит живой человек)."""

KIND_HINT = {
    "comment": "Комментарий под постом в канале",
    "chat_reply": "Ответ в общем чате (собеседник ответил на твоё сообщение)",
    "dm_reply": "Личное сообщение (собеседник написал в ЛС)",
}


def _load_style_profile():
    path = Path(config.STYLE_PROFILE_PATH)
    if path.exists():
        return path.read_text(encoding="utf-8")
    return "Пиши дружелюбно, живо, короткими предложениями, без канцелярита."


def generate_draft(kind, context_text, extra_instruction=None):
    """kind: 'comment' | 'chat_reply' | 'dm_reply'. Возвращает строку-черновик."""
    system = SYSTEM_TEMPLATE.format(style_profile=_load_style_profile())

    parts = [
        f"Тип: {KIND_HINT.get(kind, kind)}",
        f"Сообщение собеседника / пост:\n{context_text}",
    ]
    if extra_instruction:
        parts.append(f"Дополнительная инструкция от Константина: {extra_instruction}")
    parts.append("Напиши только текст ответа, без пояснений и кавычек вокруг него.")

    try:
        response = _client.messages.create(
            model=config.DRAFT_MODEL,
            max_tokens=400,
            system=system,
            messages=[{"role": "user", "content": "\n\n".join(parts)}],
        )
        return "".join(b.text for b in response.content if b.type == "text").strip()
    except Exception as e:
        # не роняем хендлер — вернём метку, человек напишет сам
        return f"[Ошибка генерации черновика: {e}]"
