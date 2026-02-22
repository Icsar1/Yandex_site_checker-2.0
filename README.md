# Wordstat Media Planner
 codex/create-web-app-for-media-plan-using-yandex-api-isv5zt
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

## Если видите в файлах `<<<<<<<`, `=======`, `>>>>>>>`
Это не "мои символы" и не код приложения. Это метки **Git-конфликта** после неудачного merge.

Как быстро починить:

```bash
cd /root/tmp_sk/yandex_site_checker
git status
git reset --hard HEAD
git clean -fd
git pull --ff-only
```

Проверка, что меток больше нет:

```bash
rg -n "<<<<<<<|=======|>>>>>>>" || echo "ok: conflict markers not found"
```

Дальше снова запускайте приложение как обычно.

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
=======
Веб-приложение на FastAPI для формирования медиаплана **только на базе Яндекс Wordstat API**.

## Возможности
- Форма ввода ниши, региона, бюджета и цели кампании.
- Получение ключевых фраз и частотностей через Wordstat API.
- Расчет сводных метрик:
  - общее число ключей;
  - суммарная частотность;
  - средняя частотность;
  - распределение бюджета по приоритетам (при наличии бюджета).
- Экспорт отчета в PDF (ReportLab).
- Webhook для Tilda: `POST /webhook/tilda`.
- Явная обработка ошибок API без моков/фолбэков в прод-логике.

## Структура проекта

```text
app/main.py
app/services/wordstat_client.py
app/services/media_plan.py
app/services/pdf_export.py
templates/index.html
static/styles.css
tests/test_app.py
```

## Переменные окружения
Создайте `.env` на основе `.env.example`:

- `WORDSTAT_API_KEY` — API-ключ (обязательно).
- `WORDSTAT_BASE_URL` — базовый URL API.
- `WORDSTAT_ENDPOINT` — endpoint Wordstat.
- `WORDSTAT_TIMEOUT_SECONDS` — таймаут API-запроса.
- `REQUEST_LOG_LEVEL` — уровень логирования.
- `DEBUG` — режим отладки.

## Локальный запуск

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# заполните WORDSTAT_API_KEY
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Откройте: `http://localhost:8000`

## Запуск тестов и линтеров

```bash
pytest
ruff check .
black --check .
```

## Webhook для Tilda
Endpoint: `POST /webhook/tilda`

Реализовано с учетом требований Tilda:
- принимает `application/x-www-form-urlencoded` и `application/json`;
- сразу после подключения Tilda отправляет `test=test` (POST), обработчик возвращает `200 OK` и тело `ok`;
- обработчик легковесный и отвечает быстро (в пределах 5 секунд);
- поддерживается HTTPS-требование на уровне инфраструктуры (TLS-терминация);
- Tilda при недоступности webhook может делать повторные попытки отправки (по документации: еще 2 попытки с интервалом около минуты).

Что обычно приходит от Tilda в payload:
- поля формы (`Name`, `Email`, `Phone` и т.д., либо кастомные имена);
- служебные поля вроде `tranid` (ID заявки) и `formid` (ID блока);
- опционально `COOKIES`, если включена передача cookie в настройках Tilda;
- опционально API-ключ (если настроен в Tilda) — в POST-поле или заголовке.

### Проверка webhook (curl)

Form-urlencoded (проверка test-хука):

```bash
curl -X POST http://localhost:8000/webhook/tilda \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "test=test"
```

Form-urlencoded (пример payload заявки):

```bash
curl -X POST http://localhost:8000/webhook/tilda \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "Name=Иван&Email=test%40email.com&Phone=0123456789&tranid=467251:8442970&formid=form48844953"
```

JSON:

```bash
curl -X POST http://localhost:8000/webhook/tilda \
  -H "Content-Type: application/json" \
  -d '{"test":"test"}'
```

## Пример запроса генерации медиаплана

```bash
curl -X POST http://localhost:8000/generate \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "niche=ремонт+квартир&region=Москва&monthly_budget=120000&campaign_goal=Лиды" \
  -o media_plan_wordstat.pdf
```

## Production: варианты деплоя (без nginx и с nginx)


### Когда nginx не нужен
Для небольшого приложения nginx не обязателен. Можно запустить только `gunicorn` (или `uvicorn`) и открыть порт сервера напрямую.

Это нормально для простого VPS-сценария, если вам не нужны дополнительные возможности reverse proxy.

### 1) gunicorn

```bash
pip install gunicorn

gunicorn app.main:app \
  -k uvicorn.workers.UvicornWorker \
  -b 127.0.0.1:8000 \
  -w 2
```

### 2) nginx (опционально, как reverse proxy)
Пример server-блока:

```nginx
server {
    listen 443 ssl;
    server_name your-domain.example;

    ssl_certificate /etc/letsencrypt/live/your-domain.example/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-domain.example/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

> Для webhook Tilda **обязательно HTTPS**. HTTPS можно обеспечить как через nginx + сертификат, так и через любой другой TLS-терминатор (например, Caddy или Cloudflare Tunnel).

### 3) systemd unit
`/etc/systemd/system/wordstat-planner.service`:

```ini
[Unit]
Description=Wordstat Media Planner
After=network.target

[Service]
User=www-data
Group=www-data
WorkingDirectory=/opt/wordstat-planner
EnvironmentFile=/opt/wordstat-planner/.env
ExecStart=/opt/wordstat-planner/.venv/bin/gunicorn app.main:app -k uvicorn.workers.UvicornWorker -b 127.0.0.1:8000 -w 2
Restart=always

[Install]
WantedBy=multi-user.target
```

Далее:

```bash
sudo systemctl daemon-reload
sudo systemctl enable wordstat-planner
sudo systemctl start wordstat-planner
sudo systemctl status wordstat-planner
```

## Важные ограничения
- Используются только данные Wordstat API.
- Если API недоступен/вернул ошибку — пользователю показывается понятное сообщение на русском.
- В прод-логике отсутствуют моки, случайные значения и fallback-оценки.
main
