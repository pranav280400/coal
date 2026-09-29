"""Typed application settings loaded from environment variables (12-factor).

Every secret is a ``SecretStr`` so it is never printed in logs or reprs. In
``production`` the settings object refuses to start with insecure defaults.
"""

from __future__ import annotations

import base64
import binascii
from functools import lru_cache
from typing import Annotated, Any, Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

_INSECURE_MARKERS = ("change-me", "changeme", "insecure", "dev-only")


def _split_csv(value: object) -> object:
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return value


class Settings(BaseSettings):
    """Settings loaded from the environment.

    ``_strip_comment_values`` below defends against a sharp edge in Docker Compose's
    ``env_file`` parser: it strips an inline ``#`` comment only when the value is
    non-empty, so a line such as ``TEMPORAL_API_KEY=      # optional`` arrives as the
    literal string ``"# optional"``. Left alone that silently enables features nobody
    configured. Treat any value that begins with ``#`` as unset.
    """

    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ------------------------------------------------------------------ app
    app_name: str = "Lumen"
    environment: Literal["development", "staging", "production", "test"] = "development"
    debug: bool = False
    log_level: str = "INFO"
    log_json: bool = True
    api_prefix: str = "/api/v1"
    public_web_url: str = "http://localhost:3000"
    public_api_url: str = "http://localhost:8000"
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:3000"]
    )
    trusted_proxy_count: int = 1

    # ------------------------------------------------------------- database
    database_url: SecretStr = SecretStr(
        "postgresql+asyncpg://cmg:cmg-dev-only-password@localhost:5432/coalminegov"
    )
    db_pool_size: int = 10
    db_max_overflow: int = 20
    db_echo: bool = False

    # ---------------------------------------------------------------- redis
    redis_url: SecretStr = SecretStr("redis://localhost:6379/0")
    dashboard_cache_ttl_seconds: int = 300

    # ---------------------------------------------------------------- kafka
    kafka_bootstrap_servers: str = "localhost:9094"
    kafka_security_protocol: Literal["PLAINTEXT", "SSL", "SASL_PLAINTEXT", "SASL_SSL"] = (
        "PLAINTEXT"
    )
    kafka_sasl_mechanism: str | None = None
    kafka_sasl_username: str | None = None
    kafka_sasl_password: SecretStr | None = None
    kafka_ssl_cafile: str | None = None
    kafka_client_id: str = "coalminegov"
    kafka_topic_domain_events: str = "cmg.domain-events"
    kafka_topic_field_events: str = "cmg.field-events"
    kafka_topic_dlq: str = "cmg.dlq"
    kafka_topic_partitions: int = 6
    kafka_replication_factor: int = 1

    # --------------------------------------------------------------- qdrant
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: SecretStr | None = None
    qdrant_collection: str = "cmg_knowledge"

    # ------------------------------------------------- LLM gateway (LiteLLM)
    llm_base_url: str = "http://localhost:4000/v1"
    llm_api_key: SecretStr = SecretStr("sk-cmg-dev-only-litellm-key")
    llm_chat_model: str = "cmg-chat"
    llm_embedding_model: str = "cmg-embed"
    embedding_dim: int = 1024
    llm_timeout_seconds: float = 120.0
    llm_max_tokens: int = 1024
    llm_temperature: float = 0.2
    rag_top_k: int = 6

    # ------------------------------------------------------------- temporal
    temporal_host: str = "localhost:7233"
    temporal_namespace: str = "default"
    temporal_task_queue: str = "cmg-main"
    temporal_tls_cert_path: str | None = None
    temporal_tls_key_path: str | None = None
    temporal_api_key: SecretStr | None = None
    worker_metrics_port: int = 9464
    consumer_metrics_port: int = 9465
    # Also sizes the worker's activity thread pool (see app/workflows/worker.py).
    worker_max_concurrent_activities: int = 16

    # ----------------------------------------------------------------- auth
    jwt_secret_key: SecretStr = SecretStr("dev-only-insecure-jwt-secret-change-me-0123456789")
    jwt_algorithm: str = "HS256"
    jwt_issuer: str = "coalminegov"
    jwt_audience: str = "coalminegov-api"
    access_token_ttl_minutes: int = 15
    refresh_token_ttl_days: int = 7
    pii_encryption_key: SecretStr = SecretStr("ZGV2LW9ubHktaW5zZWN1cmUta2V5LWNoYW5nZS1tZSE=")
    password_reset_ttl_minutes: int = 30
    password_min_length: int = 10
    login_max_attempts: int = 5
    login_lockout_minutes: int = 15
    rate_limit_per_minute: int = 300
    rate_limit_auth_per_minute: int = 20

    # --------------------------------------------------- SSO (OpenID Connect)
    sso_enabled: bool = False
    sso_provider_name: str = "Government SSO"
    sso_issuer_url: str | None = None
    sso_client_id: str | None = None
    sso_client_secret: SecretStr | None = None
    sso_redirect_uri: str = "http://localhost:3000/api/auth/sso/callback"
    sso_scopes: str = "openid profile email"
    sso_auto_provision: bool = False
    sso_default_role: Literal["mine_official", "corporate", "regulator", "contractor"] = (
        "regulator"
    )
    sso_allowed_email_domains: Annotated[list[str], NoDecode] = Field(default_factory=list)

    # ------------------------------------------------ object storage (S3 API)
    s3_endpoint_url: str | None = "http://localhost:9000"
    s3_public_endpoint_url: str | None = None
    s3_region: str = "ap-south-1"
    s3_access_key_id: str = "cmg-minio"
    s3_secret_access_key: SecretStr = SecretStr("cmg-minio-dev-only-secret")
    s3_bucket: str = "cmg-files"
    s3_force_path_style: bool = True
    s3_presign_ttl_seconds: int = 900
    max_upload_mb: int = 25

    # -------------------------------------------------------- notifications
    email_enabled: bool = False
    smtp_host: str = "localhost"
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: SecretStr | None = None
    smtp_from: str = "Lumen <no-reply@lumen.example>"
    smtp_starttls: bool = True
    smtp_use_tls: bool = False

    sms_provider: Literal["none", "twilio", "msg91"] = "none"
    twilio_account_sid: str | None = None
    twilio_auth_token: SecretStr | None = None
    twilio_from_number: str | None = None
    msg91_auth_key: SecretStr | None = None
    msg91_template_id: str | None = None

    vapid_public_key: str | None = None
    vapid_private_key: SecretStr | None = None
    vapid_subject: str = "mailto:admin@coalminegov.example"

    # --------------------------------------------- governance / AI tuning
    compliance_reminder_days: Annotated[list[int], NoDecode] = Field(
        default_factory=lambda: [7, 3, 1]
    )
    sla_critical_hours: int = 4
    sla_high_hours: int = 24
    sla_medium_hours: int = 72
    sla_low_hours: int = 168
    max_escalation_level: int = 3
    recurring_violation_threshold: int = 3
    recurring_violation_window_days: int = 30
    geofence_radius_km: float = 15.0
    high_risk_threshold: float = 70.0
    report_timezone: str = "Asia/Kolkata"

    # ------------------------------------------------------------ bootstrap
    bootstrap_admin_email: str | None = None
    bootstrap_admin_username: str = "admin"
    bootstrap_admin_password: SecretStr | None = None

    # ------------------------------------------------------------ validators
    @model_validator(mode="before")
    @classmethod
    def _strip_comment_values(cls, data: Any) -> Any:
        """Treat a value that is only an inline comment as unset (see class docstring).

        The key is dropped rather than set to ``None`` so the field's declared default
        applies — ``None`` would fail validation on non-optional fields such as
        ``smtp_host``.
        """
        if isinstance(data, dict):
            return {
                k: v
                for k, v in data.items()
                if not (isinstance(v, str) and v.lstrip().startswith("#"))
            }
        return data

    @field_validator("cors_origins", "sso_allowed_email_domains", mode="before")
    @classmethod
    def _csv_str(cls, value: object) -> object:
        return _split_csv(value)

    @field_validator("compliance_reminder_days", mode="before")
    @classmethod
    def _csv_int(cls, value: object) -> object:
        parsed = _split_csv(value)
        if isinstance(parsed, list):
            return sorted({int(v) for v in parsed}, reverse=True)
        return parsed

    @model_validator(mode="after")
    def _production_guards(self) -> Settings:
        if self.environment != "production":
            return self
        problems: list[str] = []
        secrets = {
            "JWT_SECRET_KEY": self.jwt_secret_key.get_secret_value(),
            "PII_ENCRYPTION_KEY": self.pii_encryption_key.get_secret_value(),
            "DATABASE_URL": self.database_url.get_secret_value(),
            "LLM_API_KEY": self.llm_api_key.get_secret_value(),
            "S3_SECRET_ACCESS_KEY": self.s3_secret_access_key.get_secret_value(),
        }
        try:
            secrets["PII_ENCRYPTION_KEY (decoded)"] = base64.urlsafe_b64decode(
                secrets["PII_ENCRYPTION_KEY"]
            ).decode("utf-8", "ignore")
        except (ValueError, binascii.Error):
            problems.append("PII_ENCRYPTION_KEY is not valid url-safe base64")
        for name, value in secrets.items():
            if any(marker in value.lower() for marker in _INSECURE_MARKERS):
                problems.append(f"{name} still uses a development default")
        if len(self.jwt_secret_key.get_secret_value()) < 32:
            problems.append("JWT_SECRET_KEY must be at least 32 characters")
        if self.debug:
            problems.append("DEBUG must be false in production")
        if any(o.startswith("http://") and "localhost" not in o for o in self.cors_origins):
            problems.append("CORS_ORIGINS must use https in production")
        if self.sso_enabled and not (self.sso_issuer_url and self.sso_client_id):
            problems.append("SSO_ENABLED requires SSO_ISSUER_URL and SSO_CLIENT_ID")
        if problems:
            raise ValueError("Unsafe production configuration: " + "; ".join(problems))
        return self

    # --------------------------------------------------------------- helpers
    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    def sla_hours_for(self, severity: str) -> int:
        return {
            "critical": self.sla_critical_hours,
            "high": self.sla_high_hours,
            "medium": self.sla_medium_hours,
        }.get(severity, self.sla_low_hours)


@lru_cache
def get_settings() -> Settings:
    return Settings()
