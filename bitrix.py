# -*- coding: utf-8 -*-
"""
bitrix.py — создание лида в Битрикс24 через входящий вебхук.
URL вебхука берётся из .env (BITRIX_WEBHOOK), в код не пишем.
"""

import json
import urllib.request

import config


def create_lead(data, tg_username="", tg_name=""):
    """Создаёт лид. data — dict от consult.detect_lead(). Возвращает id лида или None."""
    if not config.BITRIX_WEBHOOK:
        print("[bitrix] BITRIX_WEBHOOK не задан — лид не создан")
        return None

    title = f"TG: {tg_name or tg_username or 'без имени'}"
    if data.get("cadastre"):
        title += f" · КН {data['cadastre']}"

    comment_lines = [
        "Источник: Telegram (ассистент ИПМ)",
        f"Username: @{tg_username}" if tg_username else "",
        f"Суть: {data.get('summary', '')}",
        f"Кадастровый номер: {data['cadastre']}" if data.get("cadastre") else "",
        f"Площадь: {data['area']}" if data.get("area") else "",
        f"Регион: {data['region']}" if data.get("region") else "",
        f"Статус: {data['status']}" if data.get("status") else "",
    ]
    fields = {
        "TITLE": title,
        "NAME": tg_name or tg_username or "Клиент из Telegram",
        "COMMENTS": "\n".join(x for x in comment_lines if x),
        "SOURCE_DESCRIPTION": "Telegram-ассистент ИПМ",
    }
    if data.get("phone"):
        fields["PHONE"] = [{"VALUE": data["phone"], "VALUE_TYPE": "WORK"}]
    if data.get("email"):
        fields["EMAIL"] = [{"VALUE": data["email"], "VALUE_TYPE": "WORK"}]

    url = config.BITRIX_WEBHOOK.rstrip("/") + "/crm.lead.add.json"
    payload = json.dumps({"fields": fields}).encode("utf-8")
    req = urllib.request.Request(
        url, data=payload, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            result = json.loads(resp.read().decode("utf-8"))
        lead_id = result.get("result")
        print(f"[bitrix] лид создан: {lead_id}")
        return lead_id
    except Exception as e:
        print(f"[bitrix] ошибка создания лида: {e}")
        return None
