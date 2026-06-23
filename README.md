# Wordstat Media Planner

FastAPI-приложение для медиаплана **только по данным Wordstat API**.


## Документация
- [Черновик PRD](docs/prd_draft.md) — описание продукта, целевого стека, логики работы MVP и следующих итераций.


## Docker и служебные скрипты

Запуск в Docker:
```bash
docker compose build
docker compose up -d
```

Ручной запуск без Docker:
```bash
bash scripts/start.sh
bash scripts/stop.sh
```

Установка на VPS Unix/Linux с Docker и systemd:
```bash
sudo REPO_URL=https://github.com/OWNER/REPO.git BRANCH=main bash scripts/install_vps_unix.sh /opt/wordstat-media-planner
```

Запуск тестов на Windows PowerShell:
```powershell
powershell -ExecutionPolicy Bypass -File scripts/run_tests_windows.ps1
```

## Быстрый запуск (одна серверная консоль)
```bash
cd /root/tmp_sk/yandex_site_checker
python3 -m venv --copies .venv
. .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Для корректной кириллицы в PDF установите шрифты DejaVu:
```bash
apt install -y fonts-dejavu-core
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

## Быстрый фикс 404 (одной командой)
Если на `http://127.0.0.1:8000/` получаете `{"detail":"Not Found"}`, запустите:

```bash
bash scripts/recover_404.sh
```

Скрипт:
- гасит процесс на порту `8000`;
- поднимает **именно этот** проект через `python -m uvicorn --app-dir ... app.main:app`;
- сразу печатает HTTP-статус и хвост лога.

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

## ENV
- `WORDSTAT_OAUTH_TOKEN` (обязательно)
- `WORDSTAT_BASE_URL` (`https://api.wordstat.yandex.net`)
- `WORDSTAT_TIMEOUT_SECONDS` (`10`)
- `REQUEST_LOG_LEVEL` (`INFO`)
- `DEBUG` (`false`)


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

