from typing import Dict, List
from dataclasses import dataclass
from hashlib import md5

from app.config import settings


@dataclass
class ProviderResult:
    critical_errors: List[str]
    demand_score: int
    competitors: List[Dict[str, str]]
    recommendations: List[str]


class BaseSeoDataProvider:
    async def collect(self, site_url: str) -> ProviderResult:
        raise NotImplementedError


class MockSeoDataProvider(BaseSeoDataProvider):
    """Легкая оффлайн-заглушка для демо/разработки без внешних API."""

    async def collect(self, site_url: str) -> ProviderResult:
        website_hash = int(md5(site_url.encode("utf-8")).hexdigest(), 16)
        demand_score = 35 + website_hash % 66

        return ProviderResult(
            critical_errors=[
                "Нет явного Title/Description на части страниц",
                "Медленная загрузка мобильной версии",
                "Не настроены расширенные сниппеты (schema.org)",
            ],
            demand_score=demand_score,
            competitors=[
                {
                    "domain": "competitor-a.ru",
                    "gap": "Больше посадочных страниц под коммерческие запросы",
                },
                {"domain": "competitor-b.ru", "gap": "Выше видимость по инфозапросам"},
                {"domain": "competitor-c.ru", "gap": "Сильнее ссылочный профиль"},
            ],
            recommendations=[
                "Собрать и кластеризовать семантику по коммерческим и информационным интентам",
                "Оптимизировать ключевые страницы под E-E-A-T и коммерческие факторы",
                "Ускорить Core Web Vitals и внедрить технический мониторинг",
                "Сделать контент-план и усилить внутреннюю перелинковку",
            ],
        )


class YandexHybridProvider(BaseSeoDataProvider):
    """
    Контур реального решения:
    - Yandex Webmaster API: техошибки, индексирование.
    - Yandex Metrica API: поведенка/конверсионные сигналы.
    - Direct API: НЕ полноценный SEO-аудит, только косвенно про спрос/семантику.
    - Для сравнения с конкурентами обычно нужен внешний SEO/serp-провайдер.

    Сейчас безопасно fallback-имся на mock-логику, если интеграции не включены.
    """

    async def collect(self, site_url: str) -> ProviderResult:
        # TODO: подключить реальные вызовы, когда будут токены и выбран внешний SEO API.
        # Примерно:
        # webmaster_issues = await self._fetch_webmaster(site_url)
        # metrica_signals = await self._fetch_metrica(site_url)
        # demand = await self._fetch_direct_demand(site_url)
        # competitor_gaps = await self._fetch_external_seo_competitors(site_url)
        return await MockSeoDataProvider().collect(site_url)


class RussianSeoProvider(BaseSeoDataProvider):
    """
    Российский вариант интеграции:
    - Yandex Webmaster + Yandex Metrica для данных по вашему сайту.
    - Topvisor API (или аналогичный RU-сервис) для видимости/конкурентов/позиции.

    Реальные вызовы добавляются в TODO-блоке, пока используется fallback на mock.
    """

    async def collect(self, site_url: str) -> ProviderResult:
        # TODO: примерный контур прод-интеграции:
        # webmaster_issues = await self._fetch_webmaster(site_url)
        # metrica_signals = await self._fetch_metrica(site_url)
        # topvisor_competitors = await self._fetch_topvisor_visibility(site_url)
        return await MockSeoDataProvider().collect(site_url)


def build_provider() -> BaseSeoDataProvider:
    provider_name = settings.seo_data_provider.lower().strip()
    if provider_name == "yandex_hybrid":
        return YandexHybridProvider()
    if provider_name == "russian_seo":
        return RussianSeoProvider()
    return MockSeoDataProvider()
