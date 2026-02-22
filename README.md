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

## Если на сервере только ОДНА консоль

Это нормальная ситуация. Делайте так:

1) Запуск в фоне (чтобы консоль не занималась):

```bash
cd /root/tmp_sk/yandex_site_checker
. .venv/bin/activate
nohup uvicorn app.main:app --host 0.0.0.0 --port 8000 > /tmp/app.log 2>&1 &
```

2) Проверка в этой же консоли:

```bash
curl -i http://127.0.0.1:8000/
```

3) Если не отвечает, смотрите лог:

```bash
tail -n 80 /tmp/app.log
```

Останавливать процесс при необходимости:

```bash
pkill -f "uvicorn app.main:app"
```

## Проверка с Windows PowerShell

В PowerShell команда `curl` — это не Linux curl. Используйте `curl.exe`:

```powershell
curl.exe -i http://45.8.98.114:8000/
```


## Если на `127.0.0.1:8000` приходит `404 Not Found`
Это значит, что на порту 8000 уже висит **чужой процесс**, а не это приложение.

Сделайте так (в этой же консоли):

```bash
ss -lntp | grep :8000
pkill -f "uvicorn app.main:app"
cd /root/tmp_sk/yandex_site_checker
. .venv/bin/activate
nohup uvicorn app.main:app --host 0.0.0.0 --port 8000 > /tmp/app.log 2>&1 &
curl -i http://127.0.0.1:8000/
```

Если снова не 200 — покажите лог:

```bash
tail -n 80 /tmp/app.log
```

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


## Что делать прямо сейчас (чтобы Tilda заработала)
1. Поднимите сервер и не закрывайте процесс (или запустите через `nohup`).
2. Убедитесь, что сайт доступен по HTTPS-домену (Tilda не отправляет webhook на HTTP).
3. В Tilda откройте: **Настройки сайта → Формы → Webhook**.
4. Вставьте URL:
   - `https://ВАШ_ДОМЕН/webhook/tilda`
5. Нажмите «Сохранить» — Tilda сразу отправит `test=test`.
6. Успех = сервер вернул `200` и тело `ok`.

Быстрая проверка с Windows PowerShell:
```powershell
curl.exe -X POST https://ВАШ_ДОМЕН/webhook/tilda -d "test=test"
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
