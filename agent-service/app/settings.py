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

    # LLM (Google Gemini). Default = alias flash-latest (aponta sempre pro flash
    # atual, à prova de deprecação); troque para gemini-pro-latest (mais capaz).
    google_api_key: str = ""
    llm_model: str = "gemini-flash-latest"

    # Servidor
    app_host: str = "0.0.0.0"
    app_port: int = 8000

    # Origens liberadas p/ CORS (tela adm). CSV no env CORS_ORIGINS.
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def pg_dsn(self) -> str:
        return (
            f"host={self.pghost} port={self.pgport} dbname={self.pgdatabase} "
            f"user={self.pguser} password={self.pgpassword}"
        )


settings = Settings()
