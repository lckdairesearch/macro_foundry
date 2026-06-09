from __future__ import annotations

from pydantic import SecretStr

from macro_foundry.config import Settings


def test_resolve_credential_ref_uses_loaded_settings_value() -> None:
    settings = Settings(
        MACRODB_OWNER_URL="postgresql+psycopg://owner:owner@localhost:5432/macrodb",
        MACRODB_APP_URL="postgresql+psycopg://app:app@localhost:5432/macrodb",
        MACRODB_TEST_URL="postgresql+psycopg://app:app@localhost:5432/macrodb_test",
        FRED_API_KEY="fred-from-settings",
    )

    assert settings.resolve_credential_ref("FRED_API_KEY") == "fred-from-settings"


def test_resolve_credential_ref_prefers_exported_env(monkeypatch) -> None:
    monkeypatch.setenv("FRED_API_KEY", "fred-from-env")
    settings = Settings(
        MACRODB_OWNER_URL="postgresql+psycopg://owner:owner@localhost:5432/macrodb",
        MACRODB_APP_URL="postgresql+psycopg://app:app@localhost:5432/macrodb",
        MACRODB_TEST_URL="postgresql+psycopg://app:app@localhost:5432/macrodb_test",
        fred_api_key=SecretStr("fred-from-settings"),
    )

    assert settings.resolve_credential_ref("FRED_API_KEY") == "fred-from-env"
