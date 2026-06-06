"""
Central configuration — all settings loaded from environment variables.
Pydantic-settings validates types at startup so misconfiguration fails fast.
"""
from functools import lru_cache
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── App ───────────────────────────────────────────────
    environment: str = "development"
    secret_key: str = "change_me"
    log_level: str = "INFO"
    # Stored as comma-separated string to avoid pydantic-settings v2 JSON parsing
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    @property
    def cors_origins_list(self) -> List[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    # ── Database ──────────────────────────────────────────
    database_url: str

    # ── Redis ─────────────────────────────────────────────
    redis_url: str = "redis://redis:6379/0"
    celery_broker_url: str = "redis://redis:6379/1"
    celery_result_backend: str = "redis://redis:6379/2"

    # ── API Keys ──────────────────────────────────────────
    keepa_api_key: str = ""
    anthropic_api_key: str = ""
    openai_api_key: str = ""

    # ── Amazon ────────────────────────────────────────────
    amazon_access_key: str = ""
    amazon_secret_key: str = ""
    amazon_associate_tag: str = ""

    # ── Notifications ─────────────────────────────────────
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    alert_email_to: str = ""

    # ── Scraping ──────────────────────────────────────────
    scraper_request_delay_seconds: float = 2.0
    scraper_max_concurrency: int = 3
    scraper_proxies: str = ""

    # ── Scoring / Thresholds ──────────────────────────────
    alert_score_threshold: int = 75
    min_roi_percent: float = 20.0

    # ── Dev / Testing ─────────────────────────────────────
    # When true, use synthetic Amazon data when scraping fails (no Keepa key needed)
    mock_enrichment_fallback: bool = False

    # ── Profitability assumptions ─────────────────────────
    vat_rate: float = 0.20
    fba_fulfilment_estimate_gbp: float = 3.50
    shipping_cost_per_kg_gbp: float = 0.80
    default_product_weight_kg: float = 0.5
    amazon_referral_fee_percent: float = 0.15

    @property
    def proxy_list(self) -> List[str]:
        if not self.scraper_proxies:
            return []
        return [p.strip() for p in self.scraper_proxies.split(",") if p.strip()]

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
