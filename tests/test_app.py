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
    # main branch returns 400 for validation errors
    assert response.status_code == 400
    assert "Ошибка валидации" in response.text


def test_api_error_is_shown_to_user(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    mock = AsyncMock(side_effect=WordstatAPIError("Сервис недоступен"))
    monkeypatch.setattr("app.main.wordstat_client.get_keywords", mock)

    response = client.post(
        "/generate",
        data={
            "niche": "test",
            "region": "test",
            "monthly_budget": "100",
            "campaign_goal": "test",
        },
    )
    assert response.status_code == 502
    assert "Ошибка Wordstat API: Сервис недоступен" in response.text


def test_successful_generation(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    mock_keywords = [WordstatKeyword(phrase="test phrase", frequency=100)]
    mock = AsyncMock(return_value=mock_keywords)
    monkeypatch.setattr("app.main.wordstat_client.get_keywords", mock)

    response = client.post(
        "/generate",
        data={
            "niche": "test",
            "region": "test",
            "monthly_budget": "1000",
            "campaign_goal": "test",
        },
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"


def test_tilda_webhook_test_payload(client: TestClient) -> None:
    response = client.post(
        "/webhook/tilda",
        data={"test": "test"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert response.status_code == 200
    assert response.text == "ok"


def test_tilda_webhook_json_payload(client: TestClient) -> None:
    response = client.post(
        "/webhook/tilda",
        json={"test": "test"},
    )
    assert response.status_code == 200
    assert response.text == "ok"
