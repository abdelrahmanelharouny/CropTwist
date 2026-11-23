"""Environment-driven intelligence and provider settings.

Provider secrets are optional until deployment supplies them. Field data is
never sent to an external model by default; operators must explicitly review
provider data-handling terms and enable the relevant privacy gates.
"""
from __future__ import annotations

from functools import lru_cache
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AISettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CROPTWIST_", env_file=".env", extra="ignore")

    # Legacy internal bridge remains an explicit opt-in compatibility adapter;
    # it is not part of the default provider priority.
    llm_bridge_url: str = "http://127.0.0.1:3035"
    llm_enabled: bool = True
    llm_timeout_seconds: float = Field(default=20.0, gt=0, le=120)
    llm_temperature: float = Field(default=0.3, ge=0, le=2)
    llm_bridge_token: SecretStr = SecretStr("")
    llm_connect_timeout_seconds: float = Field(default=5.0, gt=0, le=30)
    llm_max_retries: int = Field(default=1, ge=0, le=3)
    llm_max_tokens: int = Field(default=1200, ge=1, le=8192)
    llm_max_concurrent: int = Field(default=4, ge=1, le=64)
    llm_latency_budget_seconds: float = Field(default=20.0, gt=0, le=180)
    llm_cb_failure_threshold: int = Field(default=3, ge=1, le=20)
    llm_cb_recovery_seconds: float = Field(default=30.0, gt=0, le=3600)
    llm_cb_half_open_attempts: int = Field(default=1, ge=1, le=10)
    narrative_cache_ttl_seconds: float = Field(default=24 * 3600.0, ge=0, le=30 * 86400)
    narrative_cache_max_entries: int = Field(default=256, ge=0, le=10000)
    advisor_history_turns: int = Field(default=6, ge=0, le=20)
    ai_conversation_retention_days: int = Field(default=365, ge=0, le=3650)
    supported_locales: tuple[str, ...] = ("en", "ar")

    # Exact requested defaults. Keys are SecretStr and are never returned by
    # health/status endpoints or included in logs.
    gemini_api_key: SecretStr = SecretStr("")
    gemini_model: str = "gemini-3.8-flash"
    groq_api_key: SecretStr = SecretStr("")
    groq_model: str = "openai/gpt-oss-120b"
    openrouter_api_key: SecretStr = SecretStr("")
    openrouter_model: str = "nvidia/nemotron-3.5-super-vl:free"

    # Local-only inference for private field/farmer context. Ollama must bind
    # to loopback; remote hosts are rejected rather than treated as private.
    ollama_enabled: bool = False
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen3:4b-instruct-2507-q4_K_M"
    ollama_num_ctx: int = Field(default=8192, ge=2048, le=16384)
    ollama_keep_alive: str = Field(default="5m", min_length=1, max_length=16)
    # OpenRouter is the preferred hosted provider; Groq is the sole configured
    # fallback for now. Gemini is deliberately deferred; Ollama stays disabled.
    llm_provider_order: str = "openrouter,groq"

    ai_provider_timeout_seconds: float = Field(default=25.0, gt=0, le=120)
    ai_provider_connect_timeout_seconds: float = Field(default=5.0, gt=0, le=30)
    ai_provider_max_retries: int = Field(default=1, ge=0, le=3)
    ai_provider_max_concurrent: int = Field(default=4, ge=1, le=64)
    # Leave at least one second below the AI tool's hard 50-second deadline.
    ai_provider_chain_timeout_seconds: float = Field(default=45.0, gt=0, le=49)
    ai_provider_max_response_bytes: int = Field(default=2_000_000, ge=1024, le=8_000_000)
    ai_provider_max_stream_frame_bytes: int = Field(default=262_144, ge=256, le=1_000_000)
    ai_provider_max_output_chars: int = Field(default=64_000, ge=1, le=2_000_000)
    ai_provider_cb_failure_threshold: int = Field(default=3, ge=1, le=20)
    ai_provider_cb_recovery_seconds: float = Field(default=30.0, gt=0, le=3600)
    ai_provider_max_backoff_seconds: float = Field(default=2.0, ge=0, le=10)

    # A deployment owner must review provider privacy/retention terms before
    # allowing farm-sensitive content to leave the CropTwist boundary. The
    # OpenRouter free endpoint has an additional, provider-specific gate.
    ai_allow_field_data_to_providers: bool = False
    openrouter_allow_field_data: bool = False
    ai_knowledge_allow_documents_to_embedding_provider: bool = False
    ai_knowledge_allow_queries_to_embedding_provider: bool = False
    ai_knowledge_embedding_enabled: bool = False
    ai_knowledge_embedding_model: str = "intfloat/multilingual-e5-small"
    ai_knowledge_embedding_cache_dir: str = ""

    # Retrieval and feedback operational limits. No default corpus is bundled.
    ai_knowledge_max_document_chars: int = Field(default=200_000, ge=1000, le=2_000_000)
    ai_knowledge_chunk_chars: int = Field(default=1200, ge=200, le=4000)
    ai_knowledge_chunk_overlap_chars: int = Field(default=160, ge=0, le=1000)
    ai_knowledge_max_results: int = Field(default=5, ge=1, le=20)
    ai_feedback_retention_days: int = Field(default=365, ge=30, le=3650)
    ai_trace_retention_days: int = Field(default=90, ge=7, le=3650)

    @field_validator("llm_provider_order")
    @classmethod
    def validate_provider_order(cls, value: str) -> str:
        allowed = {"ollama", "gemini", "groq", "openrouter", "legacy-llm-bridge"}
        names = [part.strip().lower() for part in value.split(",") if part.strip()]
        if not names or len(names) != len(set(names)) or any(name not in allowed for name in names):
            raise ValueError("llm_provider_order must be a unique comma-separated list of registered providers")
        return ",".join(names)

    @field_validator("ollama_base_url")
    @classmethod
    def validate_ollama_base_url(cls, value: str) -> str:
        try:
            parsed = urlsplit(value.strip())
            port = parsed.port
        except (AttributeError, ValueError):
            raise ValueError("ollama_base_url must be a valid loopback HTTP URL") from None
        if (
            parsed.scheme != "http"
            or parsed.hostname not in {"localhost", "127.0.0.1", "::1"}
            or (port is not None and not 1 <= port <= 65535)
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path not in ("", "/")
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("ollama_base_url must target a loopback HTTP host only")
        return value.strip().rstrip("/")

    @field_validator("ollama_model")
    @classmethod
    def validate_ollama_model(cls, value: str) -> str:
        value = value.strip()
        if not value or len(value) > 160 or any(ord(char) < 32 for char in value):
            raise ValueError("Ollama model identifier is invalid")
        return value

    @field_validator("gemini_model", "groq_model", "openrouter_model")
    @classmethod
    def validate_model_identifier(cls, value: str) -> str:
        value = value.strip()
        if not value or len(value) > 160 or any(ord(char) < 32 for char in value):
            raise ValueError("provider model identifier is invalid")
        return value

    @property
    def provider_order(self) -> tuple[str, ...]:
        return tuple(self.llm_provider_order.split(","))


@lru_cache
def get_ai_settings() -> AISettings:
    return AISettings()


ai_settings = get_ai_settings()
