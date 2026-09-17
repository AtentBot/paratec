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
    # A `evolution_api_key` é a chave GLOBAL da Evolution (AUTHENTICATION_API_KEY);
    # o agent-service a usa como proxy para o painel gerenciar instâncias, de modo
    # que o admin da Paratec NUNCA precise acessar a Evolution diretamente.
    evolution_api_url: str = ""       # ex: http://evolution-api:8080
    evolution_api_key: str = ""
    evolution_instance: str = "paratec"

    # Webhook para onde a Evolution deve entregar as mensagens das instâncias
    # criadas pelo painel (normalmente o webhook do N8N que chama o agente).
    # Vazio = ao conectar um número novo, NÃO configura o webhook automaticamente
    # (o admin conecta o número, mas o roteamento ao agente é feito à parte).
    evolution_webhook_url: str = ""

    # Intervalo entre envios no broadcast (anti-bloqueio do WhatsApp).
    broadcast_throttle_seconds: float = 4.0

    # URL pública do painel adm (usada no link dos alertas aos vendedores).
    panel_url: str = "https://app.atentbot.com"

    # E-mail de suporte/contato exibido ao cliente (páginas legais, tela de suporte).
    support_email: str = "contato@dewconsultoria.com.br"

    # API pública (integrações REST por tenant). Limite de chaves ativas por
    # tenant e retenção (dias) do log de auditoria das chamadas.
    api_max_chaves_por_tenant: int = 20
    api_log_retencao_dias: int = 90

    # SMTP p/ notificações por e-mail (abertura/atualização de chamados). Vazio =
    # desabilitado (chamados ficam só no painel). NÃO commitar SMTP_PASS — use
    # .env.docker (gitignored). smtp_ssl=true usa STARTTLS na 587 / SSL na 465.
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_pass: str = ""
    smtp_ssl: bool = True
    smtp_from_name: str = "AtentBot"
    smtp_from_email: str = ""
    smtp_reply_to: str = ""   # vazio = usa support_email

    @property
    def email_enabled(self) -> bool:
        return bool(self.smtp_host and self.smtp_from_email)

    @property
    def reply_to(self) -> str:
        return self.smtp_reply_to or self.support_email

    # -----------------------------------------------------------------------
    # Multi-tenant / autenticação de aplicação
    # -----------------------------------------------------------------------
    # Tenant de fallback para tráfego legado (instâncias ainda não mapeadas em
    # `instances`). É o slug do tenant semeado com os dados de produção atuais.
    default_tenant_slug: str = "paratec"
    # Cookie de sessão do painel.
    session_cookie_name: str = "atentbot_session"
    session_ttl_days: int = 30
    # Secure=false facilita o dev local em http; em produção deixe true.
    session_cookie_secure: bool = True

    # -----------------------------------------------------------------------
    # Stripe (assinatura SaaS). Vazio = billing desabilitado.
    # -----------------------------------------------------------------------
    stripe_secret_key: str = ""
    stripe_publishable_key: str = ""
    stripe_webhook_secret: str = ""
    # Price IDs (recorrentes) de cada plano, criados no dashboard do Stripe.
    stripe_price_essencial: str = ""
    stripe_price_profissional: str = ""
    stripe_price_escala: str = ""
    # URLs de retorno do Checkout (no painel/site).
    billing_success_url: str = "https://app.atentbot.com/checkout/sucesso"
    billing_cancel_url: str = "https://app.atentbot.com/checkout/cancelado"
    # Carência (dias) para assinatura em past_due antes de bloquear o acesso.
    past_due_grace_days: int = 3

    # Consumo pay-per-use por tokens (custo do Gemini + margem), em BRL por 1.000
    # tokens. Duas fontes: INDEXAÇÃO (embeddings, ao subir/reindexar documentos e
    # catálogo) e CONVERSA (LLM do agente por mensagem). Ajuste às suas tabelas.
    # Hoje o modelo é "medir e mostrar": o valor é estimado/exibido, ainda não
    # cobrado automaticamente (gancho de Stripe metered fica para depois).
    usage_preco_por_1k_tokens_embedding: float = 0.02
    usage_preco_por_1k_tokens_chat: float = 0.20

    def custo_tokens(self, tipo: str, tokens: int) -> float:
        """Custo estimado (BRL) para uma quantidade de tokens, por fonte."""
        taxa = (self.usage_preco_por_1k_tokens_embedding if tipo.startswith("rag")
                else self.usage_preco_por_1k_tokens_chat)
        return round((tokens / 1000.0) * taxa, 4)

    # Cobrança AUTOMÁTICA dos extras (Stripe Billing Meters). Vazio = desligado
    # (só medir e mostrar). Ligue criando 2 meters + 2 preços metered no Stripe
    # (ver docs/DEPLOY_SAAS.md) e preenchendo estes valores. `event_name` é o nome
    # do meter; o preço metered entra no checkout junto do plano base.
    stripe_meter_indexacao: str = ""            # event_name do meter de indexação
    stripe_meter_conversa: str = ""             # event_name do meter de conversa
    stripe_price_meter_indexacao: str = ""      # price id metered (indexação)
    stripe_price_meter_conversa: str = ""       # price id metered (conversa)

    @property
    def metered_enabled(self) -> bool:
        return bool(self.stripe_configured and self.stripe_meter_indexacao
                    and self.stripe_meter_conversa)

    def meter_event_name(self, tipo: str) -> str:
        return self.stripe_meter_conversa if tipo == "chat" else self.stripe_meter_indexacao

    @property
    def metered_price_ids(self) -> list[str]:
        return [p for p in (self.stripe_price_meter_indexacao,
                            self.stripe_price_meter_conversa) if p]

    # Diretório dos banners/imagens de promoções (servidos em /media). Vazio =
    # <agent-service>/media. Aponte para um volume Docker para persistir.
    media_dir: str = ""

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
    def stripe_configured(self) -> bool:
        return bool(self.stripe_secret_key)

    @property
    def plan_prices(self) -> dict[str, str]:
        """plano -> price id (só os planos configurados)."""
        return {
            k: v
            for k, v in {
                "essencial": self.stripe_price_essencial,
                "profissional": self.stripe_price_profissional,
                "escala": self.stripe_price_escala,
            }.items()
            if v
        }

    @property
    def price_to_plan(self) -> dict[str, str]:
        """price id -> plano (inverso de plan_prices)."""
        return {v: k for k, v in self.plan_prices.items()}

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
