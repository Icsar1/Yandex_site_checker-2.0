# SEO Lead Analyzer (VPS-first)

Сервис для VPS, который:
- принимает заявку в API,
- делает SEO-экспресс анализ,
- выдает ссылку на отчет,
- удаляет отчет через 3 дня.

## С чего начать (без Tilda)

Сначала просто подними сервис на VPS и проверь, что он работает.

### 1) Запуск

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### 2) Проверка здоровья сервиса

Открой:

`http://<VPS_IP>:8000/health`

Должен вернуться JSON со статусом `ok`.

### 3) Создание тестового отчета (вручную)

```bash
curl -X POST http://<VPS_IP>:8000/lead/seo \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Иван",
    "phone": "+79990000000",
    "email": "mail@example.com",
    "site_url": "https://example.com"
  }'
```

В ответе придет `report_url`.

### 4) Открытие отчета

Открой `report_url` в браузере.

---

## Когда VPS уже работает, подключаем Tilda

В Tilda нужно будет отправлять POST-запрос на:

`http://<VPS_IP>:8000/lead/seo`

(Потом заменишь на домен/HTTPS, когда будет готово.)

---

## Пример env

```env
APP_BASE_URL=http://<VPS_IP>:8000
REPORT_TTL_HOURS=72
DB_PATH=seo_reports.db

# mock | yandex_hybrid | russian_seo
SEO_DATA_PROVIDER=mock

YANDEX_WEBMASTER_TOKEN=
YANDEX_DIRECT_TOKEN=
YANDEX_METRICA_TOKEN=
TOPVISOR_API_KEY=
```


### Webhook для Tilda

Если форма в Tilda отправляет вебхук, можно использовать отдельный endpoint:

`POST /webhook/tilda`

Поддерживаются `application/json`, `application/x-www-form-urlencoded` и `multipart/form-data` payload-ы.
Обязательные поля: `name`, `phone`, `email`, `site_url` (для сайта также принимаются `site`, `website`, `url`).
При невалидных или неполных данных endpoint возвращает `422`.

## API

- `GET /health` — проверка, что сервис жив.
- `POST /lead/seo` — создать SEO-отчет.
- `POST /webhook/tilda` — принять вебхук из Tilda и создать SEO-отчет.
- `GET /r/{report_id}` — страница отчета.
