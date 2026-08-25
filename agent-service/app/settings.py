"""Configuração do serviço de agentes (lida do ambiente / .env)."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Postgres (mesmo banco do catálogo)
    pghost: str = "localhost"
    pgport: int = 5432
    pgdatabase: str = "paratec"
    pguser: str = "postgres"
    pgpassword: str = ""

    # LLM (Google Gemini). Default = flash (rápido/barato p/ alto volume);
    # troque para gemini-2.5-pro (mais capaz) se preferir.
    google_api_key: str = ""
    llm_model: str = "gemini-2.5-flash"

    # Servidor
    app_host: str = "0.0.0.0"
    app_port: int = 8000

    @property
    def pg_dsn(self) -> str:
        return (
            f"host={self.pghost} port={self.pgport} dbname={self.pgdatabase} "
            f"user={self.pguser} password={self.pgpassword}"
        )


settings = Settings()
