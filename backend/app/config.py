from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(ROOT / ".env", ROOT / ".env.local"), env_file_encoding="utf-8", extra="ignore"
    )
    database_url: SecretStr = SecretStr("postgresql://xresearch:change-me@127.0.0.1:55432/xresearch")
    dashscope_api_key: SecretStr = SecretStr("")
    dashscope_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    llm_model: str = "qwen-plus"
    tavily_api_key: SecretStr = SecretStr("")
    x_bearer_token: SecretStr = SecretStr("")
    massive_api_key: SecretStr = SecretStr("")
    sec_user_agent: str = ""
    app_host: str = "127.0.0.1"
    app_port: int = 8765
    app_auth_token: SecretStr = SecretStr("")
    cors_origins: list[str] = ["http://127.0.0.1:5173", "http://localhost:5173"]
    timezone: str = "Asia/Shanghai"
    massive_requests_per_minute: int = 5
    max_model_calls: int = 14
    max_tool_calls: int = 18
    max_external_requests: int = 30
    max_total_tokens: int = 60000
    max_research_rounds: int = 4
    run_timeout_seconds: int = 420
    x_sync_max_pages: int = 3
    x_page_size: int = 20
    x_search_enabled: bool = False
    approval_ttl_hours: int = 72
    http_timeout_seconds: int = 25

    @field_validator(
        "massive_requests_per_minute",
        "max_model_calls",
        "max_tool_calls",
        "max_external_requests",
        "max_total_tokens",
        "run_timeout_seconds",
    )
    @classmethod
    def positive(cls, value: int) -> int:
        if value < 1:
            raise ValueError("must be positive")
        return value

    @property
    def db_url(self) -> str:
        return self.database_url.get_secret_value().replace("postgresql+psycopg://", "postgresql://")

    @property
    def sqlalchemy_url(self) -> str:
        return self.db_url.replace("postgresql://", "postgresql+psycopg://", 1)

    def provider_status(self) -> dict:
        return {
            "dashscope": bool(self.dashscope_api_key.get_secret_value()),
            "tavily": bool(self.tavily_api_key.get_secret_value()),
            "x": bool(self.x_bearer_token.get_secret_value()),
            "massive": bool(self.massive_api_key.get_secret_value()),
            "sec": "@" in self.sec_user_agent,
        }


@lru_cache
def get_settings() -> Settings:
    return Settings()
