"""Project settings and logger configuration."""

from __future__ import annotations

import logging
import os
from functools import cached_property
from typing import Literal, cast

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]


class DatabaseSettings(BaseModel):
    """Database connection settings grouped under ``settings.db``."""

    model_config = ConfigDict(frozen=True)

    owner_url: str
    app_url: str
    test_url: str
    staging_url: str | None = None


class AdminSettings(BaseModel):
    """SQLAdmin authentication and session settings."""

    model_config = ConfigDict(frozen=True)

    username: str
    password: SecretStr
    session_secret: SecretStr


class ApiSettings(BaseModel):
    """API authentication settings."""

    model_config = ConfigDict(frozen=True)

    bearer_token: SecretStr


class Settings(BaseSettings):
    """Typed application settings loaded from the local environment."""

    model_config = SettingsConfigDict(
        env_file=".env.local",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    db_owner_url: str = Field(validation_alias="MACRODB_OWNER_URL")
    db_app_url: str = Field(validation_alias="MACRODB_APP_URL")
    db_test_url: str = Field(validation_alias="MACRODB_TEST_URL")
    db_staging_url: str | None = Field(
        default=None,
        validation_alias="MACRODB_STAGING_URL",
    )
    admin_username: str = Field(
        default="admin",
        validation_alias="MACRODB_ADMIN_USERNAME",
    )
    admin_password: SecretStr = Field(
        default=SecretStr("change_me"),
        validation_alias="MACRODB_ADMIN_PASSWORD",
    )
    admin_session_secret: SecretStr = Field(
        default=SecretStr("change_me"),
        validation_alias="MACRODB_ADMIN_SESSION_SECRET",
    )
    api_bearer_token: SecretStr = Field(
        default=SecretStr("change_me"),
        validation_alias="MACRODB_API_BEARER_TOKEN",
    )
    fred_api_key: SecretStr | None = Field(
        default=None,
        validation_alias="FRED_API_KEY",
    )
    log_level: LogLevel = Field(
        default="INFO",
        validation_alias="MACRODB_LOG_LEVEL",
    )

    @field_validator("log_level", mode="before")
    @classmethod
    def normalize_log_level(cls, value: str | LogLevel) -> LogLevel:
        """Accept lower-case input while keeping the configured value canonical."""

        normalized = str(value).upper()
        allowed_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if normalized not in allowed_levels:
            raise ValueError(
                "MACRODB_LOG_LEVEL must be one of DEBUG, INFO, WARNING, ERROR, CRITICAL",
            )
        return cast(LogLevel, normalized)

    @cached_property
    def db(self) -> DatabaseSettings:
        return DatabaseSettings(
            owner_url=self.db_owner_url,
            app_url=self.db_app_url,
            test_url=self.db_test_url,
            staging_url=self.db_staging_url,
        )

    @cached_property
    def admin(self) -> AdminSettings:
        return AdminSettings(
            username=self.admin_username,
            password=self.admin_password,
            session_secret=self.admin_session_secret,
        )

    @cached_property
    def api(self) -> ApiSettings:
        return ApiSettings(bearer_token=self.api_bearer_token)

    def resolve_credential_ref(self, credentials_ref: str | None) -> str | None:
        """Resolve an indirect secret handle stored in the database."""

        if credentials_ref is None:
            return None
        resolved = os.getenv(credentials_ref)
        if resolved:
            return resolved
        for field_name, field_info in self.__class__.model_fields.items():
            if field_info.validation_alias != credentials_ref:
                continue
            value = getattr(self, field_name)
            if value is None:
                return None
            if isinstance(value, SecretStr):
                return value.get_secret_value()
            if isinstance(value, str) and value:
                return value
            return None
        return None


def _configure_logging(level: LogLevel) -> logging.Logger:
    logging.basicConfig(
        level=getattr(logging, level),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
    return logging.getLogger("macro_foundry")


settings = Settings()
logger = _configure_logging(settings.log_level)


__all__ = [
    "AdminSettings",
    "ApiSettings",
    "DatabaseSettings",
    "LogLevel",
    "Settings",
    "logger",
    "settings",
]
