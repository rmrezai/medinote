from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "MediNote API"
    database_url: str = "postgresql+psycopg://medinote:medinote@db:5432/medinote"
    environment: str = "development"
    test_bypass_auth: bool = False
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173,http://localhost:8080,http://127.0.0.1:8080"
    session_hours: int = 12
    enable_api_docs: bool = True
    immutable_store_path: str = "/tmp/medinote-immutable"
    default_retention_days: int = 2555
    retention_encryption_key_hex: str = ""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]


settings = Settings()
