# Railway deploy guide

## 1) Что мы деплоим

Есть 2 отдельных процесса:

- `worker` — Telegram-бот (polling), команда: `python run_bot.py`
- `web` — Flask backend для Stripe webhook, команда: `python run_server.py`

Для старта продаж по Stripe ссылкам из `tracks.py` достаточно **только worker**.
`web` нужен, если используешь команду `/buy` с webhook и авто-отправкой трека после оплаты.

## 2) Быстрый план (рекомендуется)

1. Сегодня: поднять в Railway только `worker`.
2. Завтра: заполнить env (BOT_TOKEN, Stripe ключи); ссылки оплаты — в `tracks.py` (`buy_url`) и в `miniapp.html` должны совпадать при обновлении.
3. Проверить бота в Telegram.
4. Когда понадобится `/buy` через webhook — добавить второй сервис `web`.

## 3) Подготовка репозитория

В проект уже добавлено:

- `Procfile`
  - `worker: python run_bot.py`
  - `web: python run_server.py`
- `railway.json` (политика рестартов)
- `run_server.py` читает `PORT` и слушает `0.0.0.0`

## 4) Инструкция: deploy `worker` (бот)

1. Открой Railway -> **New Project** -> **Deploy from GitHub repo**.
2. Выбери этот репозиторий.
3. В сервисе открой **Settings** -> **Start Command**.
4. Укажи команду:
   - `python run_bot.py`
5. Открой **Variables** и добавь:
   - `BOT_TOKEN=...`
   - `OWNER_TELEGRAM_ID=...`
   - `AUDIO_SALES_DIR=songs`
   - `LOG_LEVEL=INFO`
   - `LOG_FILE=-` (так лог идёт в stdout Railway)
   - `STRIPE_SECRET_KEY=...` (можно добавить завтра)
   - `STRIPE_WEBHOOK_SECRET=...` (пока можно пусто)
   - `PAYMENTS_PROVIDER_TOKEN=...` (если используешь Telegram Payments)
   - `PAYMENTS_CURRENCY=USD`
   - `BACKEND_URL=...` (если используешь `/buy`; иначе можно оставить пустым)
   - `DOMAIN=...` (если используешь `/buy`; иначе можно оставить пустым)
6. Нажми **Deploy**.
7. В логах должно быть сообщение про запуск Telegram bot polling.
8. В Telegram открой бота и отправь `/start`.

## 5) Инструкция: deploy `web` (опционально, для `/buy`)

1. В том же Railway проекте создай второй сервис (**New Service**).
2. Source тот же репозиторий.
3. **Start Command**:
   - `python run_server.py`
4. Добавь переменные:
   - `BOT_TOKEN=...`
   - `STRIPE_SECRET_KEY=...`
   - `STRIPE_WEBHOOK_SECRET=whsec_...`
   - `DOMAIN=https://<railway-web-domain>`
5. После деплоя скопируй URL сервиса (например `https://xxx.up.railway.app`).
6. В `worker` сервисе выставь:
   - `BACKEND_URL=https://xxx.up.railway.app`
   - `DOMAIN=https://xxx.up.railway.app`
7. В Stripe Dashboard создай webhook endpoint:
   - `https://xxx.up.railway.app/webhook`
   - event: `checkout.session.completed`
8. Сохрани endpoint и скопируй `Signing secret` в `STRIPE_WEBHOOK_SECRET`.
9. Redeploy `web` и `worker`.

## 6) Пример env для worker

```env
BOT_TOKEN=123456:ABCDEF
OWNER_TELEGRAM_ID=123456789
AUDIO_SALES_DIR=songs
LOG_LEVEL=INFO
LOG_FILE=-
PAYMENTS_CURRENCY=USD
```

## 7) Runbook: деплой

1. Пуш в main (или рабочую ветку, если подключена к Railway).
2. Railway автоматически запускает build/deploy.
3. Проверить логи.
4. Проверить `/start` в Telegram.

## 8) Runbook: откат

1. Открой сервис в Railway -> **Deployments**.
2. Выбери предыдущий зелёный деплой.
3. Нажми **Rollback / Redeploy**.
4. Проверь логи и `/start`.

## 9) Runbook: диагностика

### Симптом: бот не отвечает

- Проверь `BOT_TOKEN`.
- Проверь, что старт-команда именно `python run_bot.py`.
- Проверь логи сервиса `worker`.

### Симптом: `/buy` не открывает оплату

- Проверь `BACKEND_URL` в `worker`.
- Проверь, что `web` сервис жив и отвечает.
- Проверь `STRIPE_SECRET_KEY`.

### Симптом: webhook 400/401

- Проверь `STRIPE_WEBHOOK_SECRET`.
- Убедись, что endpoint в Stripe точно `https://.../webhook`.
- Убедись, что событие `checkout.session.completed` включено.

### Симптом: нет аудио после оплаты

- Проверь `song_id` в metadata (из checkout session).
- Проверь наличие файла в `songs/`.
- Проверь `BOT_TOKEN` у `web` сервиса (он отправляет файл в Telegram).
