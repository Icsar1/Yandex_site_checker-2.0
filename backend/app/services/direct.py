from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from app.services.keywords import batch_keywords


BatchCallback = Callable[[int, int], Awaitable[None] | None]


class DirectError(Exception):
    """Base error for Yandex Direct forecast automation."""


class CaptchaOrAuthError(DirectError):
    """Captcha or authentication redirect was detected."""


class DirectTimeoutError(DirectError):
    """Forecast results did not appear before timeout."""


class DirectForecastClient:
    def __init__(
        self,
        storage_state_path: str,
        forecast_url: str,
        headless: bool = True,
        timeout_ms: int = 45000,
    ) -> None:
        self.storage_state_path = storage_state_path
        self.forecast_url = forecast_url
        self.headless = headless
        self.timeout_ms = timeout_ms

    async def forecast_batch(self, keywords: list[str], region_id: int) -> list[dict]:
        if len(keywords) > 100:
            raise ValueError("forecast_batch accepts no more than 100 keywords")
        if not keywords:
            return []

        try:
            from playwright.async_api import TimeoutError as PlaywrightTimeoutError
            from playwright.async_api import async_playwright
        except ModuleNotFoundError as exc:
            raise DirectError("Playwright is not installed") from exc

        playwright = await async_playwright().start()
        browser: Any | None = None
        context: Any | None = None

        try:
            browser = await playwright.chromium.launch(headless=self.headless)
            context_kwargs = self._context_kwargs()
            context = await browser.new_context(**context_kwargs)
            context.set_default_timeout(self.timeout_ms)
            page = await context.new_page()

            response = await page.goto(
                self.forecast_url,
                wait_until="domcontentloaded",
                timeout=self.timeout_ms,
            )
            await self._raise_if_auth_or_captcha(page, response)

            await self._set_region(page, region_id)
            await self._fill_keywords(page, keywords)
            await self._click_calculate(page)

            try:
                await self._wait_for_results(page)
            except PlaywrightTimeoutError as exc:
                if await self._is_auth_or_captcha(page):
                    raise CaptchaOrAuthError("Captcha or auth redirect detected") from exc
                raise DirectTimeoutError("Timed out waiting for forecast results") from exc

            await self._raise_if_auth_or_captcha(page)
            results = await self._parse_results(page)
            if not results:
                raise DirectTimeoutError("Forecast results table was not found")

            await self._save_storage_state(context)
            return results
        finally:
            if context is not None:
                await context.close()
            if browser is not None:
                await browser.close()
            await playwright.stop()

    async def forecast_keywords(
        self,
        keywords: list[dict],
        region_id: int,
        batch_size: int = 100,
        on_batch: BatchCallback | None = None,
    ) -> list[dict]:
        batches = batch_keywords(keywords, batch_size)
        total_batches = len(batches)
        forecast: list[dict] = []

        for batch_index, batch in enumerate(batches, start=1):
            batch_result = await self.forecast_batch(
                [str(keyword["phrase"]) for keyword in batch],
                region_id,
            )
            forecast.extend(batch_result)
            await _maybe_call_batch_callback(on_batch, batch_index, total_batches)

        return forecast

    def _context_kwargs(self) -> dict[str, str]:
        storage_state = Path(self.storage_state_path)
        if storage_state.exists():
            return {"storage_state": str(storage_state)}
        return {}

    async def _set_region(self, page: Any, region_id: int) -> None:
        region_value = str(region_id)
        locator = page.locator("input#geo.b-region-selector__geo")
        try:
            if await locator.count() > 0:
                await self._set_input_value(locator, region_value)
                return
        except Exception:
            pass
        for selector in (
            "input[name='geo']",
            "input[id='geo']",
        ):
            loc = page.locator(selector).first
            try:
                if await loc.count() > 0:
                    await self._set_input_value(loc, region_value)
                    return
            except Exception:
                continue

    async def _set_input_value(self, locator: Any, value: str) -> None:
        await locator.evaluate(
            """
            (el, v) => {
                el.value = v;
                el.dispatchEvent(new Event('input', { bubbles: true }));
                el.dispatchEvent(new Event('change', { bubbles: true }));
            }
            """,
            value,
        )

    async def _fill_keywords(self, page: Any, keywords: list[str]) -> None:
        keyword_text = "\n".join(keywords)
        for selector in (
            "textarea#ad-words",
            "textarea[name='phrases']",
            "textarea.b-word-suggestions__phrases",
        ):
            locator = page.locator(selector).first
            try:
                if await locator.count() == 0:
                    continue
                await locator.fill(keyword_text, timeout=5000)
                return
            except Exception:
                continue
        raise DirectError("Keyword input was not found on Direct forecast page")

    async def _click_calculate(self, page: Any) -> None:
        for selector in (
            "input.b-advanced-forecast__submit-button",
            "input[type='submit'][value*='Посчитать']",
            "input[type='submit'][value*='Рассчитать']",
        ):
            locator = page.locator(selector).first
            try:
                if await locator.count() == 0:
                    continue
                await locator.click(timeout=5000)
                return
            except Exception:
                continue
        raise DirectError("Calculate button was not found on Direct forecast page")

    async def _wait_for_results(self, page: Any) -> None:
        await page.wait_for_function(
            """
            () => {
                var t = document.querySelector('table.js-result-table');
                if (!t) return false;
                var cell = t.querySelector('.js-requests-cell');
                return cell && /\\d/.test(cell.textContent);
            }
            """,
            timeout=self.timeout_ms,
        )

    async def _parse_results(self, page: Any) -> list[dict]:
        all_tables = await page.evaluate("""() => {
            var rt = document.querySelector('table.js-result-table');
            var tables = rt ? [rt] : Array.from(document.querySelectorAll('table'));
            return tables.map(function(table) {
                return Array.from(table.querySelectorAll('tr')).map(function(row) {
                    return Array.from(row.querySelectorAll('th, td')).map(function(cell) {
                        return cell.innerText.trim();
                    });
                });
            });
        }""")

        for table_rows in all_tables:
            header_mapping: dict[str, int] | None = None
            header_row_index = -1

            for row_index, values in enumerate(table_rows):
                mapping = _map_headers(values)
                if {"phrase", "impressions", "clicks", "spending"}.issubset(mapping):
                    header_mapping = mapping
                    header_row_index = row_index
                    break

            if header_mapping is None:
                continue

            parsed: list[dict] = []
            for row_index in range(header_row_index + 1, len(table_rows)):
                item = _parse_result_row_direct(table_rows[row_index], header_mapping)
                if item is not None:
                    parsed.append(item)

            if parsed:
                return parsed

        return []

    async def _raise_if_auth_or_captcha(self, page: Any, response: Any | None = None) -> None:
        if await self._is_auth_or_captcha(page, response):
            raise CaptchaOrAuthError("Captcha or auth redirect detected")

    async def _is_auth_or_captcha(self, page: Any, response: Any | None = None) -> bool:
        if response is not None:
            response_url = str(getattr(response, "url", "") or "").lower()
            if "passport" in response_url:
                return True

            status = int(getattr(response, "status", 0) or 0)
            headers = getattr(response, "headers", {}) or {}
            location = str(headers.get("location", "")).lower()
            if 300 <= status < 400 and "passport" in location:
                return True

        page_url = str(getattr(page, "url", "") or "").lower()
        if "passport" in page_url:
            return True

        captcha_selector = (
            "[class*='captcha'], [id*='captcha'], "
            "[class*='Captcha'], [id*='Captcha'], "
            "iframe[src*='captcha'], iframe[src*='smartcaptcha']"
        )
        try:
            if await page.locator(captcha_selector).count() > 0:
                return True
        except Exception:
            return False

        return False

    async def _save_storage_state(self, context: Any) -> None:
        storage_state = Path(self.storage_state_path)
        storage_state.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = storage_state.with_name(f"{storage_state.name}.tmp")
        await context.storage_state(path=str(tmp_path))
        tmp_path.replace(storage_state)


async def _maybe_call_batch_callback(
    on_batch: BatchCallback | None,
    batch_index: int,
    total_batches: int,
) -> None:
    if on_batch is None:
        return
    result = on_batch(batch_index, total_batches)
    if inspect.isawaitable(result):
        await result


async def _row_text_values(row: Any) -> list[str]:
    cells = row.locator("th,td")
    cell_count = await cells.count()
    values: list[str] = []
    for cell_index in range(cell_count):
        text = await cells.nth(cell_index).inner_text()
        values.append(text.strip())
    return values


def _map_headers(values: list[Any]) -> dict[str, int]:
    mapping: dict[str, int] = {}
    normalized_values = [_normalize_header(v) for v in values]
    for index, normalized in enumerate(normalized_values):
        if not normalized:
            continue
        for field, aliases in _HEADER_ALIASES.items():
            if field not in mapping and normalized in aliases:
                mapping[field] = index
                break
    for index, normalized in enumerate(normalized_values):
        if not normalized:
            continue
        for field, aliases in _HEADER_ALIASES.items():
            if field not in mapping and any(alias in normalized for alias in aliases):
                mapping[field] = index
                break
    return mapping


def _field_for_header(value: Any) -> str | None:
    normalized = _normalize_header(value)
    if not normalized:
        return None

    for field, aliases in _HEADER_ALIASES.items():
        if normalized in aliases:
            return field
    for field, aliases in _HEADER_ALIASES.items():
        if any(alias in normalized for alias in aliases):
            return field
    return None


def _parse_result_row(values: list[str], mapping: dict[str, int]) -> dict | None:
    phrase_index = mapping.get("phrase")
    if phrase_index is None or phrase_index >= len(values):
        return None

    phrase = values[phrase_index].strip()
    if not phrase:
        return None

    item: dict[str, Any] = {"phrase": phrase}
    for field in _NUMERIC_FIELDS:
        index = mapping.get(field)
        item[field] = _parse_number(values[index]) if index is not None and index < len(values) else None
    return item


def _parse_result_row_direct(values: list[str], mapping: dict[str, int]) -> dict | None:
    phrase_index = mapping.get("phrase")
    if phrase_index is None or phrase_index >= len(values):
        return None

    phrase = values[phrase_index].strip()
    if not phrase or phrase.startswith("{") or phrase == "Фразы не выбраны":
        return None
    phrase = phrase.split("\n")[0].strip()
    if not phrase or phrase.lower().startswith("итого"):
        return None

    item: dict[str, Any] = {"phrase": phrase}
    for field in _NUMERIC_FIELDS:
        index = mapping.get(field)
        if index is None or index >= len(values):
            item[field] = None
            continue
        cell_text = values[index].strip()
        item[field] = _pick_traffic_value(cell_text)
    return item


def _pick_traffic_value(cell_text: str) -> int | float | None:
    _DASHES = {"-", "---", "—", "–"}
    if not cell_text or cell_text.strip() in _DASHES:
        return None
    lines = [ln.strip() for ln in cell_text.split("\n") if ln.strip() and ln.strip() not in _DASHES]
    if len(lines) <= 1:
        return _parse_number(cell_text)
    # Direct Pro: 5 sub-rows per cell for traffic volumes 100/85/62/9/5
    pick = lines[min(3, len(lines) - 1)]
    return _parse_number(pick)


def _normalize_header(value: Any) -> str:
    text = str(value or "").casefold().replace("ё", "е")
    cleaned = "".join(char if char.isalnum() else " " for char in text)
    return " ".join(cleaned.split())


def _parse_number(value: Any) -> int | float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value) if value.is_integer() else value

    text = str(value).strip()
    if not text or text in {"-", "---"}:
        return None
    text = (
        text.replace("\xa0", "")
        .replace("\u202f", "")
        .replace(" ", "")
        .replace("%", "")
        .replace("₽", "")
    )
    text = "".join(char for char in text if char.isdigit() or char in ",.-+")
    if not text or text in {"-", "+", ".", ","}:
        return None

    if "," in text and "." in text:
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    else:
        text = text.replace(",", ".")

    try:
        number = float(text)
    except ValueError:
        return None
    return int(number) if number.is_integer() else number


_NUMERIC_FIELDS = (
    "impressions",
    "clicks",
    "spending",
    "ctr",
    "avg_cpc",
    "avg_cpm",
    "avg_bid",
)

_HEADER_ALIASES = {
    "phrase": (
        "фраза",
        "фразы",
        "ключевая фраза",
    ),
    "impressions": (
        "показы",
        "прогноз показов",
    ),
    "clicks": (
        "клики",
        "прогноз кликов",
    ),
    "spending": (
        "расход",
        "прогноз расхода",
        "бюджет",
        "прогноз бюджета",
    ),
    "ctr": (
        "ctr",
        "прогноз ctr",
    ),
    "avg_cpc": (
        "ср цена клика",
        "средняя цена клика",
        "прогноз средней ставки",
        "цена клика",
        "cpc",
    ),
    "avg_cpm": (
        "cpm",
        "ср цена тысячи показов",
    ),
    "avg_bid": (
        "ср ставка",
        "средняя ставка",
        "ставка",
    ),
}
