# -*- coding: utf-8 -*-
"""Генерация черновика ответа в стиле Константина через Claude API."""

from pathlib import Path

import anthropic

import config

_client = anthropic.Anthropic()

SYSTEM_TEMPLATE = """Ты помогаешь Константину быстро отвечать в Telegram — комментарии под постами,
реплики в чатах и личные сообщения.

Пиши строго от первого лица, как будто это сам Константин. Никогда не подписывайся и не упоминай,
что ты ассистент или ИИ — это черновик, который Константин лично прочитает и одобрит перед отправкой.

Вот описание его СТИЛЯ общения — используй как основу тона и манеры:
{style_profile}

Ниже — БАЗА ЗНАНИЙ по методологии и терминам (девелопмент, ИЖС, КРТ, 214-ФЗ).
Используй её, чтобы отвечать по существу и не путать понятия. Но это только
фактура: НЕ пересказывай её списками и слайдами, НЕ вываливай этапы целиком,
пиши коротко и живым голосом Константина.
{knowledge_base}

Правила:
- Один короткий вариант ответа, без "или" и перечисления вариантов.
- Без канцелярита и излишней вежливости, если это не в его стиле.
- Не выдумывай факты о жизни Константина, которых нет в контексте.
- Цифры экономики из базы знаний — это ОДИН пример-кейс, не универсальные нормы;
  не приводи их как норматив для любого участка.
- Если это комментарий к посту — 1-3 предложения, уместные под чужим постом.
  Где это естественно, заканчивай коротким встречным вопросом по теме поста,
  чтобы завязать диалог (как Константин: «Как это определить? …», «С чего
  начнёте — с земли или уже есть проект?»). Но НЕ притягивай вопрос силой:
  если он не к месту — обойдись без него, лучше без вопроса, чем искусственный.
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


def _load_knowledge_base():
    path = Path(config.KNOWLEDGE_BASE_PATH)
    if path.exists():
        return path.read_text(encoding="utf-8")
    return "(база знаний не задана)"


def generate_draft(kind, context_text, extra_instruction=None):
    """kind: 'comment' | 'chat_reply' | 'dm_reply'. Возвращает строку-черновик."""
    system = SYSTEM_TEMPLATE.format(
        style_profile=_load_style_profile(),
        knowledge_base=_load_knowledge_base(),
    )

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
        return f"[Ошибка генерации черновика: {e}]"


def generate_variants(kind, context_text, n=2, avoid=None):
    """Возвращает список из n РАЗНЫХ альтернативных черновиков (для кнопки «Другие варианты»)."""
    avoid = list(avoid or [])
    variants = []
    for _ in range(n):
        seen = avoid + variants
        instr = ("Дай ДРУГОЙ вариант ответа — другой заход и формулировки, "
                 "не повторяй уже предложенное.")
        if seen:
            joined = "\n---\n".join(seen)
            instr += f"\nУже были такие варианты (не повторяй их):\n{joined}"
        variants.append(generate_draft(kind, context_text, extra_instruction=instr))
    return variants
