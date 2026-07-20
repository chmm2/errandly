from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration, loaded from environment / .env."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Database
    database_url: str = "postgresql+asyncpg://errandly:errandly@db:5432/errandly"

    # Redis
    redis_url: str = "redis://redis:6379/0"

    # Kafka
    kafka_bootstrap: str = "kafka:19092"
    kafka_orders_topic: str = "errandly.orders"

    # MongoDB (chat)
    mongo_url: str = "mongodb://mongo:27017"
    mongo_db: str = "errandly"

    # Auth / JWT
    jwt_secret: str = "change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7

    # Escrow ledger — the hash chain is keyed by its OWN secret, so rotating
    # jwt_secret (which would break login tokens) never invalidates the money
    # log. Change this only if you intend to re-key and re-chain the ledger.
    ledger_hmac_secret: str = "change-me-ledger"

    # Escrow fees. total held = item_total + runner_fee + convenience_fee.
    # runner_fee = clamp(base + per_km * distance_km, min, max); distance is
    # measured from the campus reference point to the drop (pickup has no
    # coordinates today — see ledger.service.compute_fees).
    fee_runner_base: float = 20.0
    fee_runner_per_km: float = 10.0
    fee_runner_min: float = 20.0
    fee_runner_max: float = 60.0
    fee_convenience_pct: float = 0.03
    fee_convenience_min: float = 5.0

    # Which payment provider backs wallet top-ups. "simulated" credits instantly
    # (demo/dev). A real UPI/Razorpay provider implements the same port later.
    payment_provider: str = "simulated"

    # Email / OTP verification
    # Leave smtp_host blank to run in dev mode: the OTP is logged (and surfaced
    # via an X-Dev-OTP header) instead of emailed. Fill these in backend/.env
    # to send for real — the password never leaves your .env.
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "Errandly <no-reply@errandly.app>"
    smtp_starttls: bool = True
    otp_ttl_minutes: int = 10
    otp_max_attempts: int = 5
    # Self-registration is restricted to this email domain (student-only).
    student_email_domain: str = "vitstudent.ac.in"

    # App
    environment: str = "development"
    cors_origins: str = "http://localhost:5173,http://localhost:3000"

    @property
    def smtp_configured(self) -> bool:
        return bool(self.smtp_host)

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
