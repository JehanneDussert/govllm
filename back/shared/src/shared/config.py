from functools import lru_cache
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class GatewaySettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")
    litellm_api_key: str
    litellm_base_url: str
    redis_url: str
    default_model: str
    ab_models: list[str]
    allowed_origins: list[str]

    @field_validator("ab_models", "allowed_origins", mode="before")
    @classmethod
    def parse_list(cls, v: str | list) -> list[str]:
        if isinstance(v, str):
            return [item.strip() for item in v.split(",")]
        return v


class ObservabilitySettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")
    langfuse_public_key: str
    langfuse_secret_key: str
    langfuse_host: str
    prometheus_url: str
    grafana_url: str
    grafana_service_token: str
    ab_models: list[str]
    allowed_origins: list[str]

    @field_validator("ab_models", "allowed_origins", mode="before")
    @classmethod
    def parse_list(cls, v: str | list) -> list[str]:
        if isinstance(v, str):
            return [item.strip() for item in v.split(",")]
        return v


class EvaluationSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")
    litellm_base_url: str
    litellm_api_key: str
    langfuse_public_key: str
    langfuse_secret_key: str
    langfuse_host: str
    redis_url: str
    ab_models: list[str]
    eval_interval_seconds: int
    allowed_origins: list[str]

    @field_validator("ab_models", "allowed_origins", mode="before")
    @classmethod
    def parse_list(cls, v: str | list) -> list[str]:
        if isinstance(v, str):
            return [item.strip() for item in v.split(",")]
        return v


@lru_cache
def get_gateway_settings() -> GatewaySettings:
    return GatewaySettings()


@lru_cache
def get_observability_settings() -> ObservabilitySettings:
    return ObservabilitySettings()


@lru_cache
def get_evaluation_settings() -> EvaluationSettings:
    return EvaluationSettings()