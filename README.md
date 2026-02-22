# Wordstat Media Planner

Коротко: это FastAPI-приложение, которое строит медиаплан **только** по данным Wordstat API.

## Быстрый старт (5 команд)
```bash
cd /root/tmp_sk/yandex_site_checker
python3 -m venv --copies .venv
. .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Откройте `.env` и впишите токен:
```env
WORDSTAT_OAUTH_TOKEN=ваш_токен
```

Запуск:
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Проверка:
```bash
curl -i http://127.0.0.1:8000/
```
Если `HTTP/1.1 200 OK` — всё работает.

## Что умеет
- Форма на `/` (ниша, регион, бюджет, цель).
- Генерация PDF на `/generate`.
- Webhook Tilda `POST /webhook/tilda`.
- Понятные ошибки на русском, если Wordstat недоступен.

## Webhook Tilda (минимум)
- Поддерживает `application/x-www-form-urlencoded` и `application/json`.
- `test=test` возвращает `200` и `ok`.
- Для продакшена нужен HTTPS.

Проверка:
```bash
curl -X POST http://127.0.0.1:8000/webhook/tilda \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "test=test"
```

## ENV переменные
- `WORDSTAT_OAUTH_TOKEN` (обязательно)
- `WORDSTAT_BASE_URL` (по умолчанию `https://api.wordstat.yandex.net`)
- `WORDSTAT_TIMEOUT_SECONDS` (по умолчанию `10`)
- `REQUEST_LOG_LEVEL` (по умолчанию `INFO`)
- `DEBUG` (`true/false`)

## Важно
- Никаких fallback-данных: только ответ Wordstat API.
- При ошибках API пользователь получает понятное сообщение.
