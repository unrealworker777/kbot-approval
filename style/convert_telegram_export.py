# -*- coding: utf-8 -*-
"""
Вытаскивает сообщения ОДНОГО человека из экспорта чата Telegram Desktop
(result.json, JSON-формат экспорта) в плоский .txt — для style/build_style_profile.py.

Как получить result.json: Telegram Desktop -> открой чат/канал -> три точки
-> "Экспорт истории чата" -> формат JSON (Machine-readable JSON).

Запуск:
    python style/convert_telegram_export.py result.json "Константин Иванов" style/examples/telegram_1.txt
"""

import json
import sys
from pathlib import Path


def extract_text(msg):
    t = msg.get("text")
    if isinstance(t, str):
        return t
    if isinstance(t, list):
        parts = []
        for p in t:
            if isinstance(p, str):
                parts.append(p)
            elif isinstance(p, dict) and "text" in p:
                parts.append(str(p["text"]))
        return "".join(parts)
    return ""


def main(export_path, sender_name, out_path):
    data = json.loads(Path(export_path).read_text(encoding="utf-8"))
    lines = []
    for msg in data.get("messages", []):
        if msg.get("type") != "message":
            continue
        if msg.get("from") != sender_name:
            continue
        text = extract_text(msg).strip()
        if text:
            lines.append(text)

    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n\n".join(lines), encoding="utf-8")
    print(f"Сохранено {len(lines)} сообщений от «{sender_name}» в {out}")


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print('Использование: python convert_telegram_export.py result.json "Имя Константина в Telegram" style/examples/telegram_1.txt')
        sys.exit(1)
    main(sys.argv[1], sys.argv[2], sys.argv[3])
