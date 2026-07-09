# Пошаговая инструкция: развёртывание kbot-approval

От нуля до работающего сервиса на VPS. Делай по порядку.

---

## 0. Что собрать заранее

- **VPS** на Ubuntu (Timeweb Cloud, самого дешёвого тарифа 1 CPU / 1 GB хватит).
- **Доступ к Telegram-аккаунту Константина** — на него придёт код входа.
- **Anthropic API-ключ** — console.anthropic.com → API Keys. Это ОТДЕЛЬНЫЙ
  billing от подписки Max; пополни небольшой баланс (на Haiku уходят копейки).

---

## 1. Залить код на GitHub

Создай на github.com **пустой** репозиторий `kbot-approval` (без README), потом локально:

```
cd kbot-approval
git remote add origin https://github.com/unrealworker777/kbot-approval.git
git push -u origin main
```

При push GitHub спросит логин и personal access token (не пароль).

---

## 2. Telegram API ID / HASH

1. Зайди на https://my.telegram.org под номером Константина.
2. **API development tools** → создай приложение (название любое).
3. Скопируй `api_id` и `api_hash`.

---

## 3. Бот-одобрятор + кто получает карточки

1. В Telegram напиши **@BotFather** → `/newbot` → задай имя → скопируй **token**.
2. Реши, кто жмёт «Одобрить» — Константин или ты. Узнай numeric ID этого
   человека у **@userinfobot** — это `APPROVAL_CHAT_ID`.
3. **Обязательно:** этот человек должен один раз написать новому боту любое
   сообщение в личку — иначе бот не сможет написать первым.

---

## 4. Anthropic API-ключ

console.anthropic.com → **API Keys** → Create Key → пополни баланс.

---

## 5. Поднять VPS

Timeweb Cloud → создать сервер → **Ubuntu 24.04** → получи IP и root-пароль.

```
ssh root@ТВОЙ_IP
apt update && apt install -y python3 python3-venv python3-pip git
```

---

## 6. Клонировать и поставить зависимости

```
cd /opt
git clone https://github.com/unrealworker777/kbot-approval.git
cd kbot-approval
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

---

## 7. Заполнить .env

```
cp .env.example .env
nano .env
```

Впиши всё из шагов 2–4, плюс каналы и чаты (юзернеймы **без `@`**, через запятую).
Сохранить в nano: `Ctrl+O` → `Enter` → `Ctrl+X`.

---

## 8. Собрать голос Константина (без этого черновики будут нейтральные)

1. Положи реальные сообщения Константина в `style/examples/`:
   - экспорт Telegram Desktop (JSON) →
     `python style/convert_telegram_export.py result.json "Имя как в Telegram" style/examples/telegram_1.txt`
   - или вручную вставь 20–50 его сообщений в `style/examples/manual.txt`.
2. Запусти:
   ```
   python style/build_style_profile.py style/examples
   ```
3. Открой `style/style_profile.md` — там должно быть описание манеры, а не заглушка.

---

## 9. Первый запуск — вход в Telegram (интерактивно, из этой же папки!)

```
python main.py
```

- Telethon попросит **код** — он придёт в Telegram на аккаунт Константина. Введи.
- Если на аккаунте включён облачный пароль (2FA) — введи и его.
- Увидишь «Юзербот запущен как …». Рядом появится `konstantin_session.session`.
- **Проверь**: кинь тестовый пост в отслеживаемый канал или ответь на сообщение
  Константина в чате → боту-одобрятору придёт карточка. Нажми Одобрить / Заменить / Пропустить.
- Останови `Ctrl+C`. Сессия сохранена — код больше не спросит.

---

## 10. Запустить как сервис (работает всегда, сам поднимается после ребута)

Создай файл `/etc/systemd/system/kbot.service`:

```ini
[Unit]
Description=kbot-approval
After=network.target

[Service]
WorkingDirectory=/opt/kbot-approval
ExecStart=/opt/kbot-approval/.venv/bin/python main.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Включить:

```
systemctl daemon-reload
systemctl enable --now kbot
systemctl status kbot       # должно быть active (running)
journalctl -u kbot -f       # логи вживую
```

---

## Управление потом

- Логи: `journalctl -u kbot -f`
- Рестарт: `systemctl restart kbot`
- Обновить код: `cd /opt/kbot-approval && git pull && systemctl restart kbot`
- Стоп: `systemctl stop kbot`

---

## Важно

- Первый вход (шаг 9) делай **вручную по SSH** — сервис в шаге 10 стартуй только
  после того, как `.session` создан, иначе systemd не сможет ввести код.
- Не гони объёмы: юзербот-автоматизация против правил Telegram; ручное одобрение
  снижает риск, но при аномальной активности аккаунт можно словить в ограничения.
- `.env` и `.session` в `.gitignore` — не коммить их.
