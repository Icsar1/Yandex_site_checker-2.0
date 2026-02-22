# Wordstat Media Planner

FastAPI-приложение для медиаплана **только по данным Wordstat API**.

## Быстрый запуск (одна серверная консоль)
```bash
cd /root/tmp_sk/yandex_site_checker
python3 -m venv --copies .venv
. .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Откройте `.env` и заполните минимум:
```env
WORDSTAT_OAUTH_TOKEN=ваш_токен
```

Запуск в фоне (чтобы эта же консоль осталась для проверок):
```bash
nohup uvicorn app.main:app --host 0.0.0.0 --port 8000 > /tmp/app.log 2>&1 &
```

Проверка в этой же консоли:
```bash
curl -i http://127.0.0.1:8000/
```

Ожидается `HTTP/1.1 200 OK`.

Если не `200`:
```bash
tail -n 80 /tmp/app.log
```

## Ошибка при `git commit` и `git push origin work`
Если видите ошибки `Author identity unknown` и `src refspec work does not match any`, выполните:

```bash
cd /root/tmp_sk/yandex_site_checker

# 1) Один раз настроить имя и email для git на сервере
git config --global user.name "Ваше Имя"
git config --global user.email "you@example.com"

# 2) Убедиться, что вы на ветке work (или создать её)
git checkout -B work

# 3) Закоммитить
git add .
git commit -m "merge: resolve conflicts with main"

# 4) Первый push ветки work на origin
git push -u origin work
```

Если `work` не нужна, можно пушить текущую ветку так:

```bash
git push -u origin HEAD
```

## Если приходит 404 на `/`
Обычно это значит, что на порту `8000` запущен другой процесс.

```bash
ss -lntp | grep :8000
pkill -f "uvicorn app.main:app" || true
cd /root/tmp_sk/yandex_site_checker
. .venv/bin/activate
nohup uvicorn app.main:app --host 0.0.0.0 --port 8000 > /tmp/app.log 2>&1 &
curl -i http://127.0.0.1:8000/
```

## Если в файлах появились маркеры конфликта Git
Это следы неудачного merge. Быстрое восстановление:

```bash
cd /root/tmp_sk/yandex_site_checker
git reset --hard HEAD
git clean -fd
git pull --ff-only
```

## Быстрый фикс 404 (одной командой)
Если на `http://127.0.0.1:8000/` получаете `{"detail":"Not Found"}`, запустите:

```bash
bash scripts/recover_404.sh
```

Скрипт:
- гасит процесс на порту `8000`;
- поднимает **именно этот** проект через `python -m uvicorn --app-dir ... app.main:app`;
- сразу печатает HTTP-статус и хвост лога.

## Структура проекта

```
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

- `WORDSTAT_OAUTH_TOKEN` — OAuth-токен (обязательно).
- `WORDSTAT_API_KEY` — API-ключ (обязательно).
- `WORDSTAT_BASE_URL` — базовый URL API.
- `WORDSTAT_ENDPOINT` — endpoint Wordstat.
- `WORDSTAT_TIMEOUT_SECONDS` — таймаут API-запроса.
- `REQUEST_LOG_LEVEL` — уровень логирования.
- `DEBUG` — режим отладки.

## Webhook Tilda
Endpoint:
- `POST /webhook/tilda`

Поведение:
- `test=test` → `200 OK` и тело `ok`.
- Поддерживает `application/x-www-form-urlencoded` и `application/json`.
- Для Tilda обязателен HTTPS URL.

Проверка:
```bash
curl -X POST http://127.0.0.1:8000/webhook/tilda \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "test=test"
```

## Проверка из Windows PowerShell
Используйте `curl.exe` (не алиас `curl`):

```powershell
curl.exe -i http://45.8.98.114:8000/
curl.exe -X POST https://ВАШ_ДОМЕН/webhook/tilda -d "test=test"
```

## Автообновление с Git на сервере (чтобы тянулось само)

Сделайте это **один раз** на самом сервере:

```bash
cd /root/tmp_sk/yandex_site_checker
bash scripts/install_autoupdate_cron.sh /root/tmp_sk/yandex_site_checker main
```

Что будет дальше:
- каждую минуту сервер проверяет `origin/main`;
- если есть новые коммиты — делает `git reset --hard origin/main`;
- обновляет зависимости `pip install -r requirements.txt`;
- перезапускает приложение и проверяет `http://127.0.0.1:8000/`.

Проверка, что автообновление включено:
```bash
crontab -l | grep update_from_git.sh
```

Лог автообновления:
```bash
tail -n 100 /tmp/wordstat_deploy.log
```

Ручной запуск обновления прямо сейчас:
```bash
bash scripts/update_from_git.sh /root/tmp_sk/yandex_site_checker main
```

## Локальный запуск

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # заполните WORDSTAT_API_KEY
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Откройте: `http://localhost:8000`

## Запуск тестов и линтеров

```bash
pytest
ruff check .
black --check .
```

## Production: варианты деплоя (без nginx и с nginx)

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

> Для webhook Tilda **обязательно HTTPS**.

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
