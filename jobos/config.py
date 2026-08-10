"""JOBOS configuration — loads from environment, typed via Pydantic Settings."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSettings(BaseSettings):
    """PostgreSQL connection settings."""

    model_config = SettingsConfigDict(env_prefix="JOBOS_DB_")

    host: str = "localhost"
    port: int = 5432
    user: str = "jobos"
    password: str = "jobos_dev"
    name: str = "jobos"
    min_pool_size: int = 5
    max_pool_size: int = 20

    @property
    def dsn(self) -> str:
        return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.name}"


class VaultSettings(BaseSettings):
    """KMS and encryption settings."""

    model_config = SettingsConfigDict(env_prefix="JOBOS_VAULT_")

    # KMS provider: 'aws' | 'gcp' | 'local' (local = dev-only, uses a static key)
    kms_provider: str = "local"
    # For local dev only — a hex-encoded 32-byte key
    local_master_key_hex: str = (
        "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
    )
    # AWS KMS
    aws_kms_key_id: str = ""
    aws_region: str = "ap-south-1"
    # GCP KMS
    gcp_kms_key_name: str = ""
    # Read from the top-level JOBOS_ENVIRONMENT (not JOBOS_VAULT_ENVIRONMENT)
    # so the vault can refuse dev-only key material in production.
    environment: str = Field(default="development", validation_alias="JOBOS_ENVIRONMENT")

    @property
    def environment_is_production(self) -> bool:
        return self.environment.strip().lower() == "production"


class LLMSettings(BaseSettings):
    """LLM routing settings via LiteLLM."""

    model_config = SettingsConfigDict(env_prefix="JOBOS_LLM_")

    # Platform trial credits — used for onboarding T+0 before tenant adds keys
    platform_groq_key: str = ""
    platform_openrouter_key: str = ""

    # Default models (can be overridden per-tenant via BYOK)
    tailoring_model: str = "groq/llama-3.3-70b-versatile"
    entailment_model: str = "nvidia_nim/meta/llama-3.1-70b-instruct"
    # Local ONNX model — no API key, no quota, no network at inference time.
    # Set to a litellm route (e.g. 'cloudflare/@cf/baai/bge-base-en-v1.5') to
    # use a hosted provider instead; EMBEDDING_DIM must then match its width.
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    embedding_local: bool = True


class ComposioSettings(BaseSettings):
    """Composio SDK settings."""

    model_config = SettingsConfigDict(env_prefix="JOBOS_COMPOSIO_")

    api_key: str = ""


class LinkedInPolicy(BaseSettings):
    """LinkedIn rate limits and safety policy — even on the official API."""

    model_config = SettingsConfigDict(env_prefix="JOBOS_LINKEDIN_")

    posts_per_day: int = 1
    comments_per_day_min: int = 6
    comments_per_day_max: int = 12
    likes_per_day_min: int = 10
    likes_per_day_max: int = 25
    min_gap_minutes: int = 11
    jitter_max_minutes: int = 40
    active_window_start_hour: int = 8  # IST
    active_window_end_hour: int = 22  # IST
    weekend_volume_multiplier: float = 0.4
    ceiling_utilization_max: float = 0.70
    skip_day_probability: float = 0.15
    comment_structural_similarity_max: float = 0.40


class EmailPolicy(BaseSettings):
    """Email sending safety policy."""

    model_config = SettingsConfigDict(env_prefix="JOBOS_EMAIL_")

    max_per_day: int = 25
    min_gap_seconds: int = 45
    jitter_max_seconds: int = 90
    max_burst_per_hour: int = 6
    bounce_rate_circuit_breaker: float = 0.02
    template_variation_min: float = 0.30


class SafetySettings(BaseSettings):
    """Global circuit breaker thresholds."""

    model_config = SettingsConfigDict(env_prefix="JOBOS_SAFETY_")

    # Global breakers
    entailment_failure_rate_5m: float = 0.15
    outbox_failure_rate_5m: float = 0.25
    tier_gate_drop_rate_floor: float = 0.15
    p95_llm_latency_ms: int = 30_000

    # Per-tenant breakers
    consecutive_failures_max: int = 3
    entailment_failures_per_day_max: int = 5

    # Shadow mode
    shadow_mode_days: int = 7


class Settings(BaseSettings):
    """Root settings — aggregates all subsystem configs."""

    model_config = SettingsConfigDict(
        env_prefix="JOBOS_",
        env_nested_delimiter="__",
    )

    # App metadata
    app_name: str = "JOBOS"
    debug: bool = False
    environment: str = Field(default="development")  # development | staging | production

    # Subsystem configs
    db: DatabaseSettings = Field(default_factory=DatabaseSettings)
    vault: VaultSettings = Field(default_factory=VaultSettings)
    llm: LLMSettings = Field(default_factory=LLMSettings)
    composio: ComposioSettings = Field(default_factory=ComposioSettings)
    linkedin: LinkedInPolicy = Field(default_factory=LinkedInPolicy)
    email: EmailPolicy = Field(default_factory=EmailPolicy)
    safety: SafetySettings = Field(default_factory=SafetySettings)


# Singleton — import this everywhere
settings = Settings()
