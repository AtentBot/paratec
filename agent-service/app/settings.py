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
    # Memória da conversa: "memory" (padrão, em processo) | "postgres" (durável).
    checkpointer: str = "memory"

    # Servidor
    app_host: str = "0.0.0.0"
    app_port: int = 8000

    # Origens liberadas p/ CORS (tela adm). CSV no env CORS_ORIGINS.
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    # Evolution API (envio de WhatsApp de saída pelo painel). Vazio = desabilitado.
    evolution_api_url: str = ""       # ex: http://evolution-api:8080
    evolution_api_key: str = ""
    evolution_instance: str = "paratec"

    # Intervalo entre envios no broadcast (anti-bloqueio do WhatsApp).
    broadcast_throttle_seconds: float = 4.0

    # RAG / base de conhecimento (pgvector dedicado). vector_host vazio = desabilitado.
    vector_host: str = ""
    vector_port: int = 5432
    vector_db: str = "rag"
    vector_user: str = "postgres"
    vector_password: str = ""
    embedding_model: str = "models/gemini-embedding-001"  # 3072 dims

    @property
    def rag_enabled(self) -> bool:
        return bool(self.vector_host)

    @property
    def vector_dsn(self) -> str:
        return (
            f"host={self.vector_host} port={self.vector_port} dbname={self.vector_db} "
            f"user={self.vector_user} password={self.vector_password} "
            f"keepalives=1 keepalives_idle=30 keepalives_interval=10 keepalives_count=5"
        )

    @property
    def evolution_configured(self) -> bool:
        return bool(self.evolution_api_url and self.evolution_api_key)

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def pg_dsn(self) -> str:
        # keepalives TCP evitam que a rede overlay do Swarm derrube conexões ociosas.
        return (
            f"host={self.pghost} port={self.pgport} dbname={self.pgdatabase} "
            f"user={self.pguser} password={self.pgpassword} "
            f"keepalives=1 keepalives_idle=30 keepalives_interval=10 keepalives_count=5"
        )


settings = Settings()
