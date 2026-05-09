# Admin README

Краткая инструкция для добавления новых треков через `/admin`.

## 1) Что подготовить заранее

- Доступ админа в `.env`/Railway: `ADMIN_IDS=<your_telegram_id,...>`.
- Stripe ключ:
  - `STRIPE_API_KEY` (предпочтительно), или
  - `STRIPE_SECRET_KEY`.
- Файл обложки в PNG/JPG (рекомендуется квадрат 3000x3000 или 2000x2000).
- Исходный звук в WAV для мастеринга.
- Текст описания трека на английском языке (1-3 абзаца).
- Цена:
  - USD (например, `16`)
  - SEK (например, `169`).

## 2) Подготовка MP3 из WAV в Audacity (точно по шагам)

1. Открой WAV в Audacity.
2. Нормализуй громкость (по желанию): `Effect -> Normalize`.
3. Экспорт:
   - `File -> Export -> Export as MP3`.
   - Bitrate Mode: `Constant`.
   - Quality: `320 kbps`.
   - Channel Mode: `Joint Stereo`.
4. Имя файла делай понятным (по названию трека), без случайных символов.
5. Проверь длительность и что файл нормально воспроизводится.

## 3) Как добавить трек через `/admin`

1. В Telegram напиши боту `/admin`.
2. Нажми `➕ Add New Track`.
3. По шагам отправь:
   - Title
   - Description
   - USD price
   - SEK price
   - Cover image (JPG/PNG)
   - MP3 (как Document)
4. Бот автоматически:
   - сохранит cover в `covers/`,
   - сохранит mp3 в `songs/`,
   - обновит `file_ids.json`,
   - создаст в Stripe: Product, Price USD, Price SEK, Payment Link USD, Payment Link SEK.
5. Проверь preview и нажми `✅ Confirm & Save`.

## 4) Что проверять после добавления

- В `/admin -> 📋 View All Tracks` появился новый трек.
- В карточке трека есть обе ссылки Stripe (USD и SEK).
- Трек виден в витрине/miniapp после деплоя.
- Тестовая покупка проходит (в test mode), webhook не падает.

## 5) SALES_LOG и статистика

- Продажи пишутся в `sales_log.json`.
- Бесплатные выдачи (`FREE`) тоже логируются.
- В `/admin -> 📊 Sales Statistics` доступны:
  - Today / This week / This month / All time,
  - топ треков,
  - последние 7 дней,
  - счётчик free downloads.

### Опционально: синхронизация `SALES_LOG_JSON` в Railway Variables

Включается только если нужно:

- `ENABLE_SALES_LOG_RAILWAY_SYNC=1`
- `RAILWAY_API_TOKEN`
- `RAILWAY_PROJECT_ID`
- `RAILWAY_ENVIRONMENT_ID`
- `RAILWAY_SERVICE_ID`

Если эти переменные не заданы, лог продолжает штатно работать через `sales_log.json`.

## 6) Мини-runbook (deploy / rollback / диагностика)

### Deploy

1. Commit + push.
2. Deploy Worker (bot polling) и Web (Flask API) в Railway.
3. Проверить логи:
   - Worker: есть `Application started` / polling без `409 Conflict`.
   - Web: webhook отвечает без 500.

### Rollback

1. В Railway выбрать предыдущий успешный deployment.
2. Перезапустить Worker и Web.
3. Проверить `/admin` и покупку тестового трека.

### Диагностика

- `/admin` не отвечает:
  - проверь, что polling запущен только в одном инстансе,
  - проверь `ADMIN_IDS`.
- Не создаются Stripe ссылки:
  - проверь `STRIPE_API_KEY`/`STRIPE_SECRET_KEY`,
  - проверь логи Worker при шаге `Add MP3`.
- Пустая статистика:
  - проверь webhook `checkout.session.completed`,
  - проверь, что `sales_log.json` обновляется.
