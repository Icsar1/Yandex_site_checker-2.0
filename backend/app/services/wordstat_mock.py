from __future__ import annotations


class MockWordstatClient:
    async def top_requests(
        self,
        query: str,
        region_ids: list[int] | None = None,
    ) -> list[dict[str, int | str]]:
        normalized_query = query.lower().strip() or "натяжные потолки"
        if "натяж" in normalized_query and "потол" in normalized_query:
            return list(_STRETCH_CEILING_KEYWORDS)

        return [
            {"phrase": f"{normalized_query} цена", "freq": 4200},
            {"phrase": f"купить {normalized_query}", "freq": 3300},
            {"phrase": f"{normalized_query} заказать", "freq": 2100},
            {"phrase": f"{normalized_query} стоимость", "freq": 1900},
            {"phrase": f"{normalized_query} под ключ", "freq": 1600},
            {"phrase": f"{normalized_query} москва", "freq": 1500},
            {"phrase": f"{normalized_query} недорого", "freq": 1200},
            {"phrase": f"{normalized_query} установка", "freq": 950},
            {"phrase": f"{normalized_query} калькулятор", "freq": 870},
            {"phrase": f"{normalized_query} отзывы", "freq": 760},
            {"phrase": f"{normalized_query} фото", "freq": 640},
            {"phrase": f"{normalized_query} видео", "freq": 420},
            {"phrase": f"{normalized_query} своими руками", "freq": 390},
            {"phrase": f"что такое {normalized_query}", "freq": 340},
            {"phrase": f"{normalized_query} вакансии", "freq": 260},
            {"phrase": f"{normalized_query} скачать каталог", "freq": 140},
        ]

    async def get_regions_tree(self) -> list[dict[str, int | str | None]]:
        return [
            {"id": 225, "name": "Россия", "parent_id": None},
            {"id": 213, "name": "Москва", "parent_id": 225},
            {"id": 2, "name": "Санкт-Петербург", "parent_id": 225},
            {"id": 35, "name": "Краснодарский край", "parent_id": 225},
            {"id": 65, "name": "Новосибирск", "parent_id": 225},
            {"id": 54, "name": "Екатеринбург", "parent_id": 225},
        ]

    async def user_info(self) -> dict[str, int]:
        return {"quota": 1000, "used": 0}


_STRETCH_CEILING_KEYWORDS: tuple[dict[str, int | str], ...] = (
    {"phrase": "натяжные потолки цена", "freq": 5200},
    {"phrase": "купить натяжные потолки", "freq": 3100},
    {"phrase": "натяжные потолки заказать", "freq": 1800},
    {"phrase": "натяжные потолки стоимость монтажа", "freq": 2400},
    {"phrase": "натяжные потолки калькулятор", "freq": 900},
    {"phrase": "натяжные потолки москва", "freq": 4500},
    {"phrase": "натяжные потолки отзывы", "freq": 1200},
    {"phrase": "натяжные потолки своими руками", "freq": 800},
    {"phrase": "натяжные потолки фото", "freq": 3500},
    {"phrase": "натяжные потолки виды", "freq": 1100},
    {"phrase": "натяжные потолки матовые", "freq": 950},
    {"phrase": "натяжные потолки глянцевые", "freq": 870},
    {"phrase": "натяжные потолки в ванную", "freq": 1300},
    {"phrase": "натяжные потолки двухуровневые", "freq": 700},
    {"phrase": "натяжные потолки бесплатно замер", "freq": 400},
    {"phrase": "натяжные потолки вакансии", "freq": 300},
    {"phrase": "натяжные потолки скачать каталог", "freq": 150},
    {"phrase": "что такое натяжные потолки", "freq": 600},
    {"phrase": "натяжные потолки недорого", "freq": 1500},
    {"phrase": "натяжные потолки с подсветкой", "freq": 850},
)
