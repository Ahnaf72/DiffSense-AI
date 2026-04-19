from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment / .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── App ──
    app_name: str = "DiffSense-AI"
    app_env: str = "development"
    debug: bool = False
    log_level: str = "INFO"

    # ── CORS ──
    cors_origins: str = ""  # comma-separated, e.g. "http://localhost:3000,https://app.example.com"

    # ── Server ──
    host: str = "0.0.0.0"
    port: int = 8000

    # ── Database (Supabase) ──
    database_url: str = ""
    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_service_key: str = ""
    supabase_project_ref: str = ""
    supabase_cli_path: str = "supabase"  # just "supabase" if on PATH, or full path

    # ── Auth ──
    secret_key: str = ""  # MUST be set in .env — app will refuse to start if empty/default
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Validate critical settings
        if self.is_production and not self.secret_key:
            raise ValueError("SECRET_KEY must be set in production environment")
        if self.is_production and self.secret_key and len(self.secret_key) < 32:
            raise ValueError("SECRET_KEY must be at least 32 characters in production")

    # ── Storage ──
    upload_dir: str = "uploads"

    # ── Celery / Redis ──
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = ""   # defaults to redis_url if empty
    celery_result_backend: str = ""  # defaults to redis_url if empty

    # ── Embedding model ──
    embedding_model_name: str = "all-MiniLM-L6-v2"
    embedding_device: str = "cpu"  # "cpu" or "cuda"

    # ── Scoring weights (must sum to 1.0, will be normalized if not) ──
    scoring_weight_plagiarism: float = 0.6
    scoring_weight_paraphrase: float = 0.3
    scoring_weight_semantic: float = 0.1

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def cors_origin_list(self) -> list[str]:
        """Parse CORS_ORIGINS into a list."""
        if not self.cors_origins:
            return []
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
