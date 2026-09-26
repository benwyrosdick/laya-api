from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Laya API"
    app_env: str = "development"
    secret_key: str = "dev-insecure-change-me"
    public_base_url: str = "http://localhost:8000"

    database_url: str = "postgresql+asyncpg://laya:laya@localhost:5432/laya"

    google_client_id: str = ""
    google_client_secret: str = ""
    allow_dev_login: bool = False

    engine: str = "stub"
    # Comma-separated real runtimes to load: "laya", "lev", "kev", or "laya,lev,kev".
    # Empty follows `engine`. "stub" loads neither.
    engines: str = ""
    lev_run: str = "franckverrot/lev-350m"
    kev_run: str = "jaredpalmer/kev-0.8b"
    laya_device: str | None = None
    laya_preload: bool = True
    default_model: str = "laya-latest"

    rate_limit_rpm: int = 180
    max_questions_per_request: int = 256
    max_choice_options: int = 255
    max_score_levels: int = 10
    min_score_levels: int = 2
    session_cookie_name: str = "laya_session"

    @property
    def google_enabled(self) -> bool:
        return bool(self.google_client_id and self.google_client_secret)

    @property
    def https_only(self) -> bool:
        return self.public_base_url.lower().startswith("https://")

    @property
    def google_redirect_uri(self) -> str:
        return f"{self.public_base_url.rstrip('/')}/auth/google/callback"

    def real_runtimes(self) -> set[str]:
        raw = (self.engines or "").strip().lower()
        if not raw:
            if self.engine in {"stub", "heuristic", "fake"}:
                return set()
            if self.engine in {"both", "all"}:
                return {"laya", "lev", "kev"}
            return {self.engine.strip().lower()}
        if raw in {"stub", "none"}:
            return set()
        if raw in {"both", "all"}:
            return {"laya", "lev", "kev"}
        return {part.strip() for part in raw.split(",") if part.strip()}
