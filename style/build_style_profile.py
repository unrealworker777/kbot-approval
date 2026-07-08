# -*- coding: utf-8 -*-
"""
Разовый скрипт: анализирует примеры сообщений Константина и составляет
краткое описание его стиля общения (style_profile.md) — оно потом
подставляется в системный промпт при генерации черновиков ответов.

Запуск:
    python style/build_style_profile.py style/examples

В style/examples положи .txt файлы с примерами (см. convert_telegram_export.py
для конвертации экспорта Telegram Desktop, либо просто вставь текст руками).
"""

import sys
from pathlib import Path

import anthropic

SYSTEM = """Ты — лингвист-аналитик. Тебе дают примеры сообщений одного человека (Константина) —
из переписок, комментариев, транскриптов уроков. Составь краткое, но ёмкое ОПИСАНИЕ ЕГО СТИЛЯ
общения в Telegram (не пересказ содержания, а именно манера речи), которое потом будет
использоваться как системная инструкция для языковой модели, пишущей ЗА него черновики ответов.

Опиши:
- Общий тон (дружелюбный / ироничный / деловой и т.д.), уровень формальности.
- Характерные слова-паразиты, любимые фразы, обращения к собеседнику.
- Длину предложений, пунктуацию (много ли многоточий, восклицаний, эмодзи — и каких именно).
- Как он обычно начинает и заканчивает сообщения.
- Чего он никогда не делает (например: не извиняется, не использует канцелярит, не пишет "Здравствуйте").

Не включай в описание содержание конкретных сообщений (темы, имена, детали) — только манеру речи,
её нужно уметь применить к любой новой теме."""


def main(sources_dir):
    src = Path(sources_dir)
    texts = [f.read_text(encoding="utf-8", errors="ignore") for f in src.glob("*.txt")]
    if not texts:
        print(f"В папке {src} нет .txt файлов с примерами. Ничего не сделано.")
        return

    combined = "\n\n---\n\n".join(texts)
    combined = combined[:120000]  # грубый предохранитель от огромных выгрузок

    client = anthropic.Anthropic()
    response = client.messages.create(
        model="claude-opus-4-8",
        max_tokens=2000,
        system=SYSTEM,
        output_config={"effort": "high"},
        messages=[{"role": "user", "content": combined}],
    )
    profile = "".join(b.text for b in response.content if b.type == "text").strip()

    out = Path(__file__).parent / "style_profile.md"
    out.write_text(profile, encoding="utf-8")
    print(f"Готово: {out}\n\n--- Превью ---\n{profile[:600]}")


if __name__ == "__main__":
    folder = sys.argv[1] if len(sys.argv) > 1 else str(Path(__file__).parent / "examples")
    main(folder)
