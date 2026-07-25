from __future__ import annotations

from pydantic import SecretStr

from app.config import Settings


def test_settings_loads_from_env_vars(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DOMAIN", "example.test")
    monkeypatch.setenv("MOCK_YANDEX", "false")
    monkeypatch.setenv("CONCURRENCY", "7")
    monkeypatch.setenv("WORDSTAT_API_KEY", "env-secret-value")

    settings = Settings()

    assert settings.APP_ENV == "test"
    assert settings.DOMAIN == "example.test"
    assert settings.MOCK_YANDEX is False
    assert settings.CONCURRENCY == 7
    assert settings.WORDSTAT_API_KEY.get_secret_value() == "env-secret-value"


def test_secret_fields_do_not_leak_values() -> None:
    secret_value = "very-sensitive-secret"
    settings = Settings(
        ADMIN_PASSWORD=SecretStr(secret_value),
        SESSION_SECRET=SecretStr(secret_value),
    )

    assert secret_value not in repr(settings)
    assert secret_value not in str(settings.ADMIN_PASSWORD)
    assert secret_value not in str(settings.SESSION_SECRET)


def test_mock_yandex_defaults_to_true(monkeypatch) -> None:
    monkeypatch.delenv("MOCK_YANDEX", raising=False)

    assert Settings(_env_file=None).MOCK_YANDEX is True
