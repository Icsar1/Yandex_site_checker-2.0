from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.wordstat_client import WordstatAPIError, WordstatKeyword


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_validation_error_for_empty_required_fields(client: TestClient) -> None:
    response = client.post(
        "/generate",
        data={"niche": " ", "region": " ", "monthly_budget": "", "campaign_goal": ""},
    )
    assert response.status_code == 400
    assert "Ошибка валидации" in response.text


def test_api_error_is_shown_to_user(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    mock = AsyncMock(side_effect=WordstatAPIError("Сервис недоступен"))
    monkeypatch.setattr("app.main.wordstat_client.get_keywords", mock)

    response = client.post("/generate", data={"niche": "ремонт", "region": "Москва"})
    assert response.status_code == 502
    assert "Ошибка Wordstat API" in response.text


def test_successful_pdf_generation(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    mock = AsyncMock(
        return_value=[
            WordstatKeyword(phrase="ремонт квартиры", frequency=5000, match_type="broad"),
            WordstatKeyword(phrase="дизайн интерьера", frequency=1200, match_type="phrase"),
        ]
    )
    monkeypatch.setattr("app.main.wordstat_client.get_keywords", mock)

    response = client.post(
        "/generate",
        data={
            "niche": "ремонт",
            "region": "Москва",
            "monthly_budget": "100000",
            "campaign_goal": "Лиды",
        },
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content.startswith(b"%PDF")
