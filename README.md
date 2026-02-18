# Wordstat Media Planner

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

Требования реализованы:
- принимает `application/x-www-form-urlencoded` и `application/json`;
- `test=test` возвращает `200 OK` и тело `ok`;
- отвечает быстро (обработчик без тяжелых операций).

### Проверка webhook (curl)

Form-urlencoded:

```bash
curl -X POST http://localhost:8000/webhook/tilda \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "test=test"
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
