-- Schema OPERACIONAL da plataforma de atendimento Paratec.
-- Convive no mesmo banco do catálogo (db/schema.sql). Idempotente.
-- Executar: psql "$DATABASE_URL" -f db/schema_ops.sql
--
-- Estas tabelas são a fonte de verdade da tela administrativa:
--   conversations/messages -> seção Conversas
--   events                 -> métricas do Dashboard
--   queue_items            -> Fila humana (pedidos/entrega/boletos)
-- O estado interno do agente (memória por thread) é persistido à parte pelo
-- checkpointer do LangGraph (PostgresSaver cria suas próprias tabelas).

-- ---------------------------------------------------------------------------
-- Conversas (1 por thread; thread_id = número do WhatsApp)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS conversations (
    thread_id     TEXT PRIMARY KEY,
    cliente       TEXT,
    telefone      TEXT,
    status        TEXT NOT NULL DEFAULT 'ia'
                    CHECK (status IN ('ia', 'humano', 'resolvida')),
    especialista  TEXT,
    unread        INTEGER NOT NULL DEFAULT 0,
    last_preview  TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_conversations_status  ON conversations(status);
CREATE INDEX IF NOT EXISTS idx_conversations_updated ON conversations(updated_at DESC);

-- ---------------------------------------------------------------------------
-- Mensagens (histórico exibido na tela; ordem cronológica por thread)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS messages (
    id            BIGSERIAL PRIMARY KEY,
    thread_id     TEXT NOT NULL REFERENCES conversations(thread_id) ON DELETE CASCADE,
    role          TEXT NOT NULL CHECK (role IN ('cliente', 'agente', 'humano')),
    content       TEXT NOT NULL,
    especialista  TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_messages_thread ON messages(thread_id, created_at);

-- ---------------------------------------------------------------------------
-- Eventos (telemetria de atendimento -> métricas do dashboard)
-- tipo: mensagem_recebida | resposta_enviada | roteou_especialista
--       | handoff_humano | resolvida | fila_criada
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS events (
    id            BIGSERIAL PRIMARY KEY,
    thread_id     TEXT,
    tipo          TEXT NOT NULL,
    especialista  TEXT,
    meta          JSONB,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_events_created ON events(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_events_tipo    ON events(tipo);

-- ---------------------------------------------------------------------------
-- Fila humana (pedidos/orçamentos, entregas, 2ª via de boleto)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS queue_items (
    id            BIGSERIAL PRIMARY KEY,
    tipo          TEXT NOT NULL CHECK (tipo IN ('pedido', 'entrega', 'boleto')),
    thread_id     TEXT,
    cliente       TEXT,
    telefone      TEXT,
    resumo        TEXT NOT NULL,
    status        TEXT NOT NULL DEFAULT 'novo'
                    CHECK (status IN ('novo', 'andamento', 'concluido')),
    responsavel   TEXT,
    payload       JSONB,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_queue_status ON queue_items(status);
CREATE INDEX IF NOT EXISTS idx_queue_tipo   ON queue_items(tipo);
CREATE INDEX IF NOT EXISTS idx_queue_created ON queue_items(created_at DESC);
