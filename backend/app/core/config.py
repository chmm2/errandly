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

    # Neo4j (social graph — a derived read model, safe to rebuild)
    neo4j_url: str = "bolt://neo4j:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "errandly-dev"
    # Hops beyond this are treated as strangers. 4 keeps a campus-sized graph
    # traversable in single-digit milliseconds while still reaching most of it.
    social_max_hops: int = 4

    # MongoDB (chat)
    mongo_url: str = "mongodb://mongo:27017"
    mongo_db: str = "errandly"

    # Auth / JWT
    jwt_secret: str = "change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7

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

    # Escrow headroom. Shop prices move, and a runner who fronts cash must not
    # be left out of pocket because the requester's wallet was sized to an
    # estimate. A percentage of the ESTIMATED SPEND is held on top; the runner
    # fee is not part of that base, because the fee is fixed and known and
    # padding it would only lock money nobody can ever need.
    escrow_buffer_pct: float = 0.15

    # Semantic fraud channel (modules/fraud/semantics.py). Optional in every
    # sense: with no provider configured the fraud system behaves exactly as it
    # does without it.
    #   "ollama"    - a model on campus hardware; no student text leaves the
    #                 building, which matters when the evidence is notes and
    #                 reviews written by identifiable people.
    #   "anthropic" - hosted, better at the nuanced calls, kept as a reference.
    #   ""          - infer from whether an API key is present.
    llm_provider: str = ""
    anthropic_api_key: str = ""
    # host.docker.internal, not localhost: the backend runs in a container and
    # Ollama runs on the host.
    ollama_url: str = "http://host.docker.internal:11434"
    # qwen2.5:7b, not a 3B: measured on the real prompt, llama3.2:3b
    # returned reads_as_genuine=True for a history its own observations had
    # just called repetitive and suspicious. 7B separates the same pair by
    # 0.75 and reports injection attempts instead of following them.
    ollama_model: str = "qwen2.5:7b"
    semantic_analysis_enabled: bool = True
    # The review-reading channel is OFF by default because it was measured not
    # to work. Two independent runs on qwen2.5:7b separated genuine from farmed
    # rating histories by -0.9 and +2.8 points - noise either side of zero -
    # and it failed in both directions on the cases that matter: a farmed
    # history with varied wording scored 72 and was cleared, while an honest
    # runner whose friends rate without writing scored 30 and was not.
    #
    # The errand-text channel is a different question and is unaffected; it
    # separated the same kind of pair by 41.7 points.
    #
    # Kept behind a flag rather than deleted: the prompt is worth another
    # attempt, and evals/run_eval.py is where to iterate. Turn it on only when
    # the harness shows real separation.
    review_analysis_enabled: bool = False

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
