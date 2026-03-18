from __future__ import annotations

import asyncio
import json
import logging
import random
from pathlib import Path
from typing import Any

from playwright.async_api import Browser, BrowserContext, Error as PlaywrightError, Page, async_playwright

from app.config import settings

logger = logging.getLogger(__name__)


class DirectForecastError(Exception):
    """Base error for Yandex Direct forecast automation."""


class DirectForecastAuthError(DirectForecastError):
    """Authentication/login related issues."""


class DirectForecastParseError(DirectForecastError):
    """Unable to parse forecast result on page."""


class DirectForecaster:
    FORECAST_URL = "https://direct.yandex.ru/registered/main.pl?cmd=advancedForecast"

    def __init__(self) -> None:
        self.cookies_path = Path(settings.direct_cookies_path)
        self.login = settings.direct_login
        self.password = settings.direct_password
        self.region_default = settings.direct_default_region
        self.headless = settings.direct_headless
        self.timeout_ms = int(settings.direct_timeout_seconds * 1000)

    async def forecast(self, keywords: list[str], region: str | None = None) -> dict[str, Any]:
        cleaned_keywords = [k.strip() for k in keywords if k and k.strip()]
        if not cleaned_keywords:
            raise DirectForecastError("Список ключевых слов пуст")

        target_region = (region or self.region_default).strip()
        if not target_region:
            raise DirectForecastError("Не указан регион для прогноза")

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=self.headless)
            try:
                context = await self._build_context(browser)
                page = await context.new_page()
                page.set_default_timeout(self.timeout_ms)

                await self._open_forecast_page(page)
                await self._ensure_authenticated(page)
                await self._fill_forecast_form(page, cleaned_keywords, target_region)
                await self._submit_forecast(page)
                result = await self._extract_result(page, cleaned_keywords, target_region)
                await self._persist_cookies(context)
                return result
            finally:
                await browser.close()

    async def _build_context(self, browser: Browser) -> BrowserContext:
        context = await browser.new_context(locale="ru-RU")
        if self.cookies_path.exists():
            try:
                cookies = json.loads(self.cookies_path.read_text(encoding="utf-8"))
                if isinstance(cookies, list) and cookies:
                    await context.add_cookies(cookies)
                    logger.info("Loaded %s cookies for Direct session", len(cookies))
            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed loading Direct cookies: %s", exc)
        return context

    async def _persist_cookies(self, context: BrowserContext) -> None:
        try:
            cookies = await context.cookies()
            self.cookies_path.parent.mkdir(parents=True, exist_ok=True)
            self.cookies_path.write_text(
                json.dumps(cookies, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed saving Direct cookies: %s", exc)

    async def _open_forecast_page(self, page: Page) -> None:
        await page.goto(self.FORECAST_URL, wait_until="domcontentloaded")
        await self._human_pause()

    async def _ensure_authenticated(self, page: Page) -> None:
        if "passport.yandex" not in page.url:
            return

        if not self.login or not self.password:
            raise DirectForecastAuthError(
                "Требуется логин/пароль Яндекса (DIRECT_LOGIN, DIRECT_PASSWORD)"
            )

        await self._login(page)

    async def _login(self, page: Page) -> None:
        login_input = page.locator("input[name='login'], input[name='username']").first
        if await login_input.count() == 0:
            raise DirectForecastAuthError("Не найдено поле логина на странице авторизации")

        await login_input.fill(self.login)
        await self._human_pause()

        await self._click_first(page, ["button:has-text('Войти')", "button:has-text('Продолжить')"])
        await self._human_pause()

        password_input = page.locator("input[type='password']").first
        if await password_input.count() == 0:
            raise DirectForecastAuthError("Не найдено поле пароля на странице авторизации")
        await password_input.fill(self.password)
        await self._human_pause()

        await self._click_first(page, ["button:has-text('Войти')", "button[type='submit']"])

        await page.wait_for_url("**direct.yandex.ru/**", timeout=self.timeout_ms)
        await self._human_pause()

    async def _fill_forecast_form(self, page: Page, keywords: list[str], region: str) -> None:
        keywords_text = "\n".join(keywords)

        await self._fill_first(
            page,
            [
                "textarea[name='phrases']",
                "textarea[placeholder*='ключ']",
                "textarea",
            ],
            keywords_text,
        )
        await self._human_pause()

        await self._fill_first(
            page,
            [
                "input[name='geo']",
                "input[placeholder*='регион']",
                "input[placeholder*='Регион']",
            ],
            region,
        )
        await self._human_pause()

        await page.keyboard.press("Enter")
        await self._human_pause()

    async def _submit_forecast(self, page: Page) -> None:
        await self._click_first(
            page,
            [
                "button:has-text('Посчитать')",
                "button:has-text('Рассчитать')",
                "button:has-text('Получить прогноз')",
                "button[type='submit']",
            ],
        )
        await self._human_pause(0.9, 1.8)

    async def _extract_result(
        self,
        page: Page,
        keywords: list[str],
        region: str,
    ) -> dict[str, Any]:
        # Try to wait for any budget/result marker.
        candidates = [
            "text=/бюджет/i",
            "text=/прогноз/i",
            "text=/кликов/i",
            "text=/показов/i",
        ]
        for locator in candidates:
            try:
                await page.locator(locator).first.wait_for(timeout=7_000)
                break
            except PlaywrightError:
                continue

        raw_text = await page.inner_text("body")
        budget = self._extract_money(raw_text)
        impressions = self._extract_metric(raw_text, ["показ", "impression"])
        clicks = self._extract_metric(raw_text, ["клик", "click"])

        if budget is None and impressions is None and clicks is None:
            raise DirectForecastParseError("Не удалось распознать данные прогноза на странице")

        return {
            "source": "yandex_direct_advanced_forecast",
            "forecast_url": page.url,
            "region": region,
            "keywords": keywords,
            "metrics": {
                "budget_rub": budget,
                "impressions": impressions,
                "clicks": clicks,
            },
            "raw_excerpt": raw_text[:3000],
        }

    @staticmethod
    def _extract_money(text: str) -> float | None:
        import re

        patterns = [
            r"(?:бюджет|стоимость)[^\d]{0,20}([\d\s]+[\.,]?\d*)",
            r"([\d\s]+[\.,]?\d*)\s*(?:₽|руб)",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if not match:
                continue
            raw = match.group(1).replace(" ", "").replace(",", ".")
            try:
                return float(raw)
            except ValueError:
                continue
        return None

    @staticmethod
    def _extract_metric(text: str, keywords: list[str]) -> int | None:
        import re

        for kw in keywords:
            pattern = rf"{kw}[^\d]{{0,20}}([\d\s]{{1,20}})"
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if not match:
                continue
            raw = match.group(1).replace(" ", "")
            if raw.isdigit():
                return int(raw)
        return None

    async def _fill_first(self, page: Page, selectors: list[str], value: str) -> None:
        for selector in selectors:
            locator = page.locator(selector).first
            if await locator.count() == 0:
                continue
            try:
                await locator.click()
                await locator.fill(value)
                return
            except PlaywrightError:
                continue
        raise DirectForecastError(f"Не найдено поле для ввода (селекторы: {selectors})")

    async def _click_first(self, page: Page, selectors: list[str]) -> None:
        for selector in selectors:
            locator = page.locator(selector).first
            if await locator.count() == 0:
                continue
            try:
                await locator.click()
                return
            except PlaywrightError:
                continue
        raise DirectForecastError(f"Не найдена кнопка действия (селекторы: {selectors})")

    @staticmethod
    async def _human_pause(min_s: float = 0.25, max_s: float = 0.9) -> None:
        await asyncio.sleep(random.uniform(min_s, max_s))
