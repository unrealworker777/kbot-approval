# -*- coding: utf-8 -*-
"""
consult.py — ИИ-ассистент для личных сообщений аккаунта «Эксперт КРТ».
Человек написал в личку → ассистент ведёт короткий деловой диалог, выясняет
consult.py — ИИ-ассистент для личных сообщений аккаунта «Эксперт КРТ».

Человек написал в личку → ассистент ведёт короткий деловой диалог, выясняет
задачу и участок, собирает телефон и удобное время, оформляет заявку на созвон
и создаёт лид в Битрикс24. По факту оформления дёргает колбэк (юзербот шлёт
карточку менеджеру).

Личка работает АВТОНОМНО: одобрение на каждую реплику не требуется.
Комментарии и ответы в чатах по-прежнему идут через approval_bot.

Клиент Anthropic берётся так же, как в draft.py — через SDK, поэтому работает
и с ANTHROPIC_API_KEY в .env, и с профилем `ant auth login`.
"""

import asyncio
import json
import logging
import os
import sqlite3
import urllib.error
import urllib.request
from datetime import datetime, timezone

import anthropic

import config

log = logging.getLogger("consult")

_client = anthropic.Anthropic()   # как в draft.py

CONSULT_DB     = os.environ.get("CONSULT_DB", "consult.db")
CONSULT_MODEL  = os.environ.get("CONSULT_MODEL", config.DRAFT_MODEL)

BITRIX_WEBHOOK_URL    = os.environ.get("BITRIX_WEBHOOK_URL", "").strip()
BITRIX_SOURCE_ID      = os.environ.get("BITRIX_SOURCE_ID", "").strip()
BITRIX_ASSIGNED_BY_ID = os.environ.get("BITRIX_ASSIGNED_BY_ID", "").strip()

MAX_TOOL_LOOPS = 5
HISTORY_LIMIT  = 30

# ─────────────────────────── ПРОМПТ (правится здесь) ───────────────────────────

CONSULT_SYSTEM = os.environ.get("CONSULT_SYSTEM", """\
Ты — ассистент Константина Пороцкого, основателя Института проектного менеджмента (ИПМ).
ИПМ занимается девелопментом: КРТ, ИЖС, градостроительная документация, финмодель,
проектное финансирование.

В ПЕРВОМ ответе обязательно представься: ты ассистент, помогаешь разобраться с запросом
и записать на разбор проекта к эксперту. Не выдавай себя за Константина. Если спросят
прямо, бот ты или человек, отвечай честно, что ассистент.

Задача: в коротком деловом диалоге собрать заявку на созвон с экспертом. Нужно выяснить:
1) какая задача (КРТ, ИЖС, финмодель, градостроительная документация, другое);
2) участок: спроси кадастровый номер, а если его нет, то локацию, и на какой стадии проект;
3) телефон для связи;
4) когда удобно созвониться.

Стиль (это личные сообщения, не письмо):
- Пиши коротко, 1-3 предложения. Без списков, без заголовков, без разметки.
- Один вопрос за раз. Не вываливай всё сразу.
- Говори прямо и по-деловому: «У вас есть кадастровый номер участка?», а не обтекаемо.
- Если кадастровый номер есть, попроси прислать его прямо в чат, чтобы эксперт
  посмотрел участок до созвона.
- Обращайся на «вы». Не используй тире, заменяй на запятую или двоеточие.

Инструменты:
- Как узнаёшь новый факт, вызывай save_qualification (можно частями).
- Как только есть телефон И удобное время, сразу вызывай book_meeting. Не переспрашивай
  то, что уже назвали. Если телефон и время пришли в одном сообщении, оформляй сразу.
- Отсутствие кадастрового номера не мешает записи: оформляй по локации.
- После book_meeting поблагодари и скажи, что эксперт свяжется в указанное время.
  Повторно встречу не назначай.

Ограничения:
- Не выдумывай за клиента. Не знаешь, спроси.
- Не называй конкретные цены и сроки по проекту: это определит эксперт на созвоне.
- Если спрашивают что-то за рамками (юридическая консультация, стоимость работ),
  скажи, что этот вопрос разберёт эксперт на созвоне, и веди к записи.
""")

CONSULT_TOOLS = [
    {
        "name": "save_qualification",
        "description": "Сохранить факты о клиенте и его проекте. Вызывай по мере "
                       "поступления информации, можно частично.",
        "input_schema": {
            "type": "object",
            "properties": {
                "has_plot": {"type": "string", "description": "Есть ли участок: да / нет / не ясно"},
                "plot":     {"type": "string", "description": "Кадастровый номер или локация"},
                "stage":    {"type": "string", "description": "Стадия проекта"},
                "task":     {"type": "string", "description": "Задача: КРТ / ИЖС / финмодель / другое"},
                "phone":    {"type": "string", "description": "Телефон для связи"},
            },
        },
    },
    {
        "name": "book_meeting",
        "description": "Оформить заявку на созвон с экспертом. Вызывай только когда есть "
                       "телефон и удобное время.",
        "input_schema": {
            "type": "object",
            "properties": {
                "preferred_time": {"type": "string", "description": "Когда клиенту удобно"},
                "phone":          {"type": "string", "description": "Телефон для связи"},
                "summary":        {"type": "string", "description": "Краткое резюме запроса для эксперта"},
            },
            "required": ["preferred_time", "phone", "summary"],
        },
    },
]

# ─────────────────────────── БД ───────────────────────────

def _now():
    return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self, path=CONSULT_DB):
        self.path = path
        self._init()

    def _conn(self):
        c = sqlite3.connect(self.path)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA journal_mode=WAL")
        return c

    def _init(self):
        with self._conn() as c:
            c.executescript("""
            CREATE TABLE IF NOT EXISTS consult_leads (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                peer_id        INTEGER UNIQUE,
                username       TEXT,
                name           TEXT,
                q_task         TEXT,
                q_has_plot     TEXT,
                q_plot         TEXT,
                q_stage        TEXT,
                q_phone        TEXT,
                q_pref_time    TEXT,
                meeting_booked INTEGER DEFAULT 0,
                bitrix_lead_id INTEGER,
                status         TEXT DEFAULT 'new',
                created_at     TEXT,
                updated_at     TEXT
            );
            CREATE TABLE IF NOT EXISTS consult_dialog (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                peer_id    INTEGER,
                role       TEXT,
                content    TEXT,
                created_at TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_cd_peer ON consult_dialog(peer_id);
            """)

    def get(self, peer_id):
        with self._conn() as c:
            return c.execute("SELECT * FROM consult_leads WHERE peer_id=?", (peer_id,)).fetchone()

    def get_or_create(self, peer_id, username, name):
        row = self.get(peer_id)
        if row:
            return row
        with self._conn() as c:
            c.execute("INSERT INTO consult_leads(peer_id,username,name,status,created_at,updated_at) "
                      "VALUES(?,?,?,?,?,?)", (peer_id, username, name, "new", _now(), _now()))
        return self.get(peer_id)

    def update(self, peer_id, **fields):
        if not fields:
            return
        fields["updated_at"] = _now()
        cols = ", ".join(f"{k}=?" for k in fields)
        with self._conn() as c:
            c.execute(f"UPDATE consult_leads SET {cols} WHERE peer_id=?",
                      (*fields.values(), peer_id))

    def add_msg(self, peer_id, role, content):
        with self._conn() as c:
            c.execute("INSERT INTO consult_dialog(peer_id,role,content,created_at) VALUES(?,?,?,?)",
                      (peer_id, role, content, _now()))

    def history(self, peer_id, limit=HISTORY_LIMIT):
        with self._conn() as c:
            rows = c.execute("SELECT role,content FROM consult_dialog WHERE peer_id=? "
                             "ORDER BY id DESC LIMIT ?", (peer_id, limit)).fetchall()
        return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]

    def has_dialog(self, peer_id):
        with self._conn() as c:
            r = c.execute("SELECT 1 FROM consult_dialog WHERE peer_id=? LIMIT 1", (peer_id,)).fetchone()
        return r is not None

# ─────────────────────────── БИТРИКС ───────────────────────────

def _bitrix_call(method, payload):
    if not BITRIX_WEBHOOK_URL:
        return None, "BITRIX_WEBHOOK_URL не задан"
    url = BITRIX_WEBHOOK_URL.rstrip("/") + "/" + method
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("content-type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode("utf-8")), None
    except urllib.error.HTTPError as e:
        return None, f"HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:300]}"
    except Exception as e:
        return None, str(e)


def _bitrix_upsert(lead, summary):
    """Создаёт или обновляет лид. Возвращает id лида или 0."""
    if not BITRIX_WEBHOOK_URL:
        log.info("Bitrix не настроен, лид не пишу")
        return 0

    comments = (
        "ЗАЯВКА НА СОЗВОН (собрана ассистентом в Telegram).\n"
        f"Задача: {lead['q_task'] or '—'}\n"
        f"Участок: {lead['q_plot'] or '—'} (есть: {lead['q_has_plot'] or '—'})\n"
        f"Стадия: {lead['q_stage'] or '—'}\n"
        f"Удобное время: {lead['q_pref_time'] or '—'}\n"
        f"Резюме: {summary}\n"
        f"Telegram: @{lead['username'] or '—'} (id {lead['peer_id']})"
    )
    phone = [{"VALUE": lead["q_phone"], "VALUE_TYPE": "WORK"}] if lead["q_phone"] else None

    if lead["bitrix_lead_id"]:
        fields = {"COMMENTS": comments}
        if phone:
            fields["PHONE"] = phone
        _, err = _bitrix_call("crm.lead.update.json",
                              {"id": lead["bitrix_lead_id"], "fields": fields})
        if err:
            log.error("Bitrix lead.update: %s", err)
        return lead["bitrix_lead_id"]

    fields = {
        "TITLE": f"Заявка из Telegram: {lead['name'] or lead['username'] or 'лид'}",
        "NAME": lead["name"] or "",
        "COMMENTS": comments,
        "SOURCE_DESCRIPTION": f"telegram-dm | @{lead['username'] or '—'}",
    }
    if phone:
        fields["PHONE"] = phone
    if BITRIX_SOURCE_ID:
        fields["SOURCE_ID"] = BITRIX_SOURCE_ID
    if BITRIX_ASSIGNED_BY_ID:
        fields["ASSIGNED_BY_ID"] = BITRIX_ASSIGNED_BY_ID

    data, err = _bitrix_call("crm.lead.add.json", {"fields": fields})
    if err:
        log.error("Bitrix lead.add: %s", err)
        return 0
    if isinstance(data, dict) and data.get("error"):
        log.error("Bitrix lead.add: %s", data)
        return 0
    try:
        return int((data or {}).get("result") or 0)
    except Exception:
        return 0

# ─────────────────────────── CLAUDE ───────────────────────────

def _claude(system, messages):
    """Синхронный вызов — из корутин зовётся через asyncio.to_thread, как draft.py."""
    return _client.messages.create(
        model=CONSULT_MODEL,
        max_tokens=1024,
        system=system,
        messages=messages,
        tools=CONSULT_TOOLS,
    )

# ─────────────────────────── КОНСУЛЬТАНТ ───────────────────────────

class Consultant:
    """on_booked(lead: dict, summary: str) — колбэк при оформлении заявки.
    Может быть обычной функцией или корутиной."""

    def __init__(self, db_path=CONSULT_DB, on_booked=None):
        self.store = Store(db_path)
        self.on_booked = on_booked

    def is_active(self, peer_id):
        """True, если с этим человеком диалог уже идёт. Нужно, чтобы userbot
        не резал короткие ответы («да», «нет», «ок») фильтром _meaningless."""
        return self.store.has_dialog(peer_id)

    # ── инструменты ──

    def _tool_save(self, peer_id, **kw):
        mapping = {"has_plot": "q_has_plot", "plot": "q_plot", "stage": "q_stage",
                   "task": "q_task", "phone": "q_phone"}
        upd = {col: kw[k] for k, col in mapping.items() if kw.get(k)}
        if upd:
            self.store.update(peer_id, **upd)
        return {"status": "saved", "saved_fields": list(upd.keys())}

    def _tool_book(self, peer_id, preferred_time, phone, summary):
        self.store.update(peer_id, q_pref_time=preferred_time, q_phone=phone,
                          meeting_booked=1, status="meeting_booked")
        lead = self.store.get(peer_id)
        lead_id = _bitrix_upsert(lead, summary)
        if lead_id and not lead["bitrix_lead_id"]:
            self.store.update(peer_id, bitrix_lead_id=lead_id)
        return {"status": "booked", "bitrix_lead_id": lead_id}

    @staticmethod
    def _known_block(lead):
        fields = {
            "задача": lead["q_task"], "участок": lead["q_plot"],
            "участок есть": lead["q_has_plot"], "стадия": lead["q_stage"],
            "телефон": lead["q_phone"], "удобное время": lead["q_pref_time"],
        }
        known = [f"{k}: {v}" for k, v in fields.items() if v]
        tail = "\nЗаявка уже оформлена, встречу повторно не назначай." if lead["meeting_booked"] else ""
        if not known:
            return "\n\nПока о клиенте ничего не известно." + tail
        return "\n\nУже известно: " + "; ".join(known) + "." + tail

    # ── основной вход ──

    async def handle_message(self, peer_id, username, full_name, text):
        """Обрабатывает входящее ЛС. Возвращает текст ответа или None."""
        text = (text or "").strip()
        if not text:
            return None

        lead = self.store.get_or_create(peer_id, username, full_name)
        if (username and username != lead["username"]) or (full_name and full_name != lead["name"]):
            self.store.update(peer_id, username=username, name=full_name)
            lead = self.store.get(peer_id)

        self.store.add_msg(peer_id, "user", text)

        system = CONSULT_SYSTEM + self._known_block(lead)
        messages = self.store.history(peer_id)

        final_text, last_text, booked, booked_summary = None, "", False, ""

        for _ in range(MAX_TOOL_LOOPS):
            try:
                resp = await asyncio.to_thread(_claude, system, messages)
            except Exception as e:
                log.exception("Claude: %s", e)
                return "Секунду, отвечу чуть позже, небольшая техническая заминка."

            content = list(resp.content or [])
            turn_text = "\n".join(getattr(b, "text", "") for b in content
                                  if getattr(b, "type", "") == "text").strip()
            if turn_text:
                last_text = turn_text
            tool_uses = [b for b in content if getattr(b, "type", "") == "tool_use"]
            log.info("consult peer=%s stop=%s tools=%s text_len=%d",
                     peer_id, resp.stop_reason, [t.name for t in tool_uses], len(turn_text))

            if resp.stop_reason == "tool_use" and tool_uses:
                messages.append({"role": "assistant", "content": content})
                results = []
                for tu in tool_uses:
                    inp = dict(tu.input or {})
                    try:
                        if tu.name == "save_qualification":
                            res = self._tool_save(peer_id, **inp)
                        elif tu.name == "book_meeting":
                            res = await asyncio.to_thread(
                                self._tool_book, peer_id,
                                inp.get("preferred_time", ""), inp.get("phone", ""),
                                inp.get("summary", ""))
                            booked, booked_summary = True, inp.get("summary", "")
                        else:
                            res = {"error": "unknown tool"}
                    except Exception as e:
                        log.exception("tool %s: %s", tu.name, e)
                        res = {"error": str(e)}
                    results.append({"type": "tool_result", "tool_use_id": tu.id,
                                    "content": json.dumps(res, ensure_ascii=False)})
                messages.append({"role": "user", "content": results})
                continue

            final_text = turn_text
            break

        if not final_text:
            final_text = last_text
        if not final_text:
            final_text = ("Спасибо, заявка оформлена, эксперт свяжется с вами в удобное время."
                          if booked else
                          "Понял вас. Расскажите чуть подробнее о задаче, и я всё оформлю.")

        self.store.add_msg(peer_id, "assistant", final_text)

        if booked and self.on_booked:
            try:
                r = self.on_booked(dict(self.store.get(peer_id)), booked_summary)
                if asyncio.iscoroutine(r):
                    await r
            except Exception as e:
                log.exception("on_booked: %s", e)

        return final_text

    @staticmethod
    def manager_card(lead, summary):
        return (
            "🔔 Новая заявка на созвон (из личных сообщений)\n\n"
            f"Задача: {lead.get('q_task') or '—'}\n"
            f"Участок: {lead.get('q_plot') or '—'} (есть: {lead.get('q_has_plot') or '—'})\n"
            f"Стадия: {lead.get('q_stage') or '—'}\n"
            f"Телефон: {lead.get('q_phone') or '—'}\n"
            f"Удобное время: {lead.get('q_pref_time') or '—'}\n"
            f"Резюме: {summary}\n"
            f"Telegram: @{lead.get('username') or '—'}"
        )
