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
-- Clientes (cadastro por número de WhatsApp = telefone)
-- status: 'pendente' (cadastro incompleto) | 'ativo' (todos os campos obrigatórios)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS customers (
    telefone      TEXT PRIMARY KEY,
    razao_social  TEXT,
    cnpj          TEXT,
    email         TEXT,
    nome_contato  TEXT,
    status        TEXT NOT NULL DEFAULT 'pendente'
                    CHECK (status IN ('pendente', 'ativo')),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_customers_status ON customers(status);
CREATE INDEX IF NOT EXISTS idx_customers_cnpj   ON customers(cnpj);

-- opt-out de promoções/broadcast (cliente pediu para não receber)
ALTER TABLE customers ADD COLUMN IF NOT EXISTS opt_out BOOLEAN NOT NULL DEFAULT false;

-- ---------------------------------------------------------------------------
-- Broadcasts (campanhas de mensagem/promoção em massa)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS broadcasts (
    id            BIGSERIAL PRIMARY KEY,
    texto         TEXT NOT NULL,
    total         INTEGER NOT NULL DEFAULT 0,   -- destinatários alvo
    enviados      INTEGER NOT NULL DEFAULT 0,
    falhas        INTEGER NOT NULL DEFAULT 0,
    status        TEXT NOT NULL DEFAULT 'enviando'
                    CHECK (status IN ('enviando', 'concluido', 'erro')),
    criado_por    TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_broadcasts_created ON broadcasts(created_at DESC);

-- banner/imagem opcional da campanha (caminho relativo em /media, servido
-- pelo agent-service). NULL = campanha só de texto.
ALTER TABLE broadcasts ADD COLUMN IF NOT EXISTS imagem TEXT;

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

-- Instância Evolution (número de WhatsApp) pela qual a conversa chegou. Define
-- qual AGENTE atende (ver tabela agents) e por qual número a resposta humana
-- deve sair. NULL = fluxo legado de número único (instância padrão).
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS instancia TEXT;

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

-- Notas internas do atendente (role 'nota'): não vão ao cliente.
ALTER TABLE messages DROP CONSTRAINT IF EXISTS messages_role_check;
ALTER TABLE messages ADD CONSTRAINT messages_role_check
    CHECK (role IN ('cliente', 'agente', 'humano', 'nota'));

-- Atendente responsável pela conversa.
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS responsavel TEXT;

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

-- ---------------------------------------------------------------------------
-- Equipe de vendas (vendedores humanos que recebem alertas de handoff)
-- Quando o agente registra um orçamento (queue_items tipo 'pedido'), os
-- vendedores ATIVOS recebem um alerta no WhatsApp para assumir a conversa.
-- telefone: número no formato aceito pela Evolution (ex: 5511999998888).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sellers (
    id          BIGSERIAL PRIMARY KEY,
    nome        TEXT NOT NULL,
    telefone    TEXT NOT NULL,
    email       TEXT,
    ativo       BOOLEAN NOT NULL DEFAULT true,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_sellers_ativo ON sellers(ativo);

-- ---------------------------------------------------------------------------
-- Agentes de atendimento (multi-agente por número de WhatsApp)
-- Cada agente tem uma PERSONA (instruções próprias) e um conjunto de
-- CAPACIDADES (grupos de ferramentas: catalogo, pedidos, entrega, boletos,
-- conhecimento). Fica amarrado a UMA instância Evolution (número de WhatsApp):
-- ao chegar uma mensagem por aquele número, é este agente que responde.
-- Ex.: "Financeiro" -> boletos; "Comercial" -> catalogo+pedidos; "Logística"
-- -> entrega. Sem agente para a instância, cai no fluxo padrão (todas as tools).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS agents (
    id           BIGSERIAL PRIMARY KEY,
    nome         TEXT NOT NULL,
    descricao    TEXT,
    instancia    TEXT,                          -- nome da instância Evolution amarrada
    persona      TEXT,                          -- instruções extras / tom deste agente
    capacidades  TEXT[] NOT NULL DEFAULT '{}',  -- ex: {catalogo,pedidos,entrega,boletos,conhecimento}
    ativo        BOOLEAN NOT NULL DEFAULT true,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Uma instância (número) só pode ser atendida por um agente. Índice único
-- parcial: permite vários agentes SEM instância amarrada (rascunhos).
CREATE UNIQUE INDEX IF NOT EXISTS idx_agents_instancia
    ON agents(instancia) WHERE instancia IS NOT NULL;

-- Agente PADRÃO (catch-all): atende todo número que não tem agente próprio.
-- É editável pelo analista (persona/capacidades) mas não pode ser removido nem
-- amarrado a um número. Só pode haver um (índice único parcial).
ALTER TABLE agents ADD COLUMN IF NOT EXISTS is_default BOOLEAN NOT NULL DEFAULT false;
CREATE UNIQUE INDEX IF NOT EXISTS idx_agents_default ON agents(is_default) WHERE is_default;

-- Semeia o agente padrão (idempotente): persona vazia + todas as capacidades =
-- reproduz o prompt base histórico (ATENDENTE_PROMPT). Só insere se ainda não há.
INSERT INTO agents (nome, descricao, persona, capacidades, ativo, is_default)
SELECT 'Agente padrão',
       'Atende todos os números que não têm um agente próprio.',
       NULL,
       ARRAY['catalogo','pedidos','entrega','boletos','conhecimento'],
       true, true
WHERE NOT EXISTS (SELECT 1 FROM agents WHERE is_default);

-- ===========================================================================
-- MULTI-TENANT SaaS (AtentBot) — contas, sessões, assinaturas, isolamento.
-- Tudo idempotente e guardado (roda no startup, ver store.ensure_schema).
-- Paratec vira o tenant #1: os dados de produção existentes são backfilled
-- para ele, então a produção continua funcionando durante a migração.
-- Ver plano: joyful-zooming-sphinx.
-- ===========================================================================

-- 1) Tenants (cada cliente pagante = 1 tenant) --------------------------------
CREATE TABLE IF NOT EXISTS tenants (
    id                 BIGSERIAL PRIMARY KEY,
    slug               TEXT NOT NULL UNIQUE,
    nome               TEXT NOT NULL,
    status             TEXT NOT NULL DEFAULT 'ativa'
                          CHECK (status IN ('ativa','suspensa','cancelada')),
    stripe_customer_id TEXT UNIQUE,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Semeia o tenant #1 (Paratec) = dados de produção atuais.
INSERT INTO tenants (slug, nome)
SELECT 'paratec', 'Paratec'
WHERE NOT EXISTS (SELECT 1 FROM tenants WHERE slug = 'paratec');

-- 2) Usuários (login de aplicação; 1+ por tenant) ----------------------------
CREATE TABLE IF NOT EXISTS users (
    id            BIGSERIAL PRIMARY KEY,
    tenant_id     BIGINT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    email         TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    nome          TEXT,
    role          TEXT NOT NULL DEFAULT 'owner' CHECK (role IN ('owner','agente')),
    ativo         BOOLEAN NOT NULL DEFAULT true,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- email é o identificador de login: único global (case-insensitive).
CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email ON users(lower(email));
CREATE INDEX IF NOT EXISTS idx_users_tenant ON users(tenant_id);

-- 3) Sessões (cookie opaco; guardamos só o SHA-256 do token) ------------------
CREATE TABLE IF NOT EXISTS sessions (
    id           BIGSERIAL PRIMARY KEY,
    user_id      BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash   TEXT NOT NULL UNIQUE,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at   TIMESTAMPTZ NOT NULL,
    last_seen_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_sessions_expires ON sessions(expires_at);

-- 4) Assinaturas (1 por tenant; espelha o Stripe) ----------------------------
CREATE TABLE IF NOT EXISTS subscriptions (
    id                     BIGSERIAL PRIMARY KEY,
    tenant_id              BIGINT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    stripe_subscription_id TEXT UNIQUE,
    stripe_customer_id     TEXT,
    plan                   TEXT CHECK (plan IN ('essencial','profissional','escala')),
    stripe_price_id        TEXT,
    status                 TEXT NOT NULL DEFAULT 'incomplete',
    cancel_at_period_end   BOOLEAN NOT NULL DEFAULT false,
    current_period_end     TIMESTAMPTZ,
    created_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at             TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_subscriptions_tenant   ON subscriptions(tenant_id);
CREATE INDEX        IF NOT EXISTS idx_subscriptions_customer ON subscriptions(stripe_customer_id);

-- 4b) Pesquisa de cancelamento (5 perguntas + relato do cliente) --------------
CREATE TABLE IF NOT EXISTS cancellation_feedback (
    id          BIGSERIAL PRIMARY KEY,
    tenant_id   BIGINT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    respostas   JSONB,                 -- as 5 respostas (chave->valor)
    comentario  TEXT,                  -- relato livre do cliente
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_cancel_fb_tenant ON cancellation_feedback(tenant_id, created_at DESC);

-- 5) Mapa instância WhatsApp -> tenant (resolução no caminho /chat) -----------
CREATE TABLE IF NOT EXISTS instances (
    instancia  TEXT PRIMARY KEY,
    tenant_id  BIGINT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_instances_tenant ON instances(tenant_id);

-- 6) Idempotência dos webhooks do Stripe -------------------------------------
CREATE TABLE IF NOT EXISTS stripe_events (
    id          TEXT PRIMARY KEY,
    type        TEXT,
    received_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 6c) Suporte: chamados dos clientes (abertura + acompanhamento) -------------
CREATE TABLE IF NOT EXISTS tickets (
    id          BIGSERIAL PRIMARY KEY,
    tenant_id   BIGINT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    user_id     BIGINT REFERENCES users(id) ON DELETE SET NULL,
    assunto     TEXT NOT NULL,
    categoria   TEXT NOT NULL DEFAULT 'duvida'
                  CHECK (categoria IN ('duvida','problema_tecnico','cobranca','sugestao','outro')),
    prioridade  TEXT NOT NULL DEFAULT 'normal'
                  CHECK (prioridade IN ('baixa','normal','alta')),
    status      TEXT NOT NULL DEFAULT 'aberto'
                  CHECK (status IN ('aberto','em_andamento','resolvido','fechado')),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_tickets_tenant ON tickets(tenant_id, status, created_at DESC);

CREATE TABLE IF NOT EXISTS ticket_mensagens (
    id          BIGSERIAL PRIMARY KEY,
    ticket_id   BIGINT NOT NULL REFERENCES tickets(id) ON DELETE CASCADE,
    tenant_id   BIGINT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    autor       TEXT NOT NULL CHECK (autor IN ('cliente','suporte')),
    corpo       TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_ticket_msgs ON ticket_mensagens(ticket_id, created_at);

-- 6b) Medição de consumo pay-per-use por tenant (tokens) ---------------------
-- Fonte do "quanto mais dados, mais cobramos": cada indexação (embeddings) e
-- cada resposta do agente (LLM) registra tokens estimados + custo em BRL.
-- Hoje é medir/mostrar; a cobrança automática (Stripe metered) liga depois.
CREATE TABLE IF NOT EXISTS usage_events (
    id             BIGSERIAL PRIMARY KEY,
    tenant_id      BIGINT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    tipo           TEXT NOT NULL,            -- 'rag_ingest_documento' | 'rag_ingest_catalogo' | 'chat'
    tokens         BIGINT NOT NULL DEFAULT 0,
    custo_estimado NUMERIC(12,4) NOT NULL DEFAULT 0,   -- BRL
    meta           JSONB,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_usage_tenant_created ON usage_events(tenant_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_usage_tenant_tipo    ON usage_events(tenant_id, tipo);

-- 7) Coluna tenant_id nas tabelas operacionais -------------------------------
-- Adiciona com DEFAULT transitório = id da Paratec, para o código antigo (ainda
-- sem tenant) seguir inserindo válido durante o overlap do rolling deploy do
-- Swarm. O NOT NULL / remoção do default fica p/ um deploy de cleanup posterior.
DO $$
DECLARE
    pid  BIGINT;
    t    TEXT;
    tbls TEXT[] := ARRAY['customers','broadcasts','conversations','messages',
                         'events','queue_items','sellers','agents'];
BEGIN
    SELECT id INTO pid FROM tenants WHERE slug = 'paratec';
    FOREACH t IN ARRAY tbls LOOP
        EXECUTE format('ALTER TABLE %I ADD COLUMN IF NOT EXISTS tenant_id BIGINT REFERENCES tenants(id)', t);
        EXECUTE format('ALTER TABLE %I ALTER COLUMN tenant_id SET DEFAULT %L', t, pid);
        EXECUTE format('UPDATE %I SET tenant_id = %L WHERE tenant_id IS NULL', t, pid);
    END LOOP;
END $$;

-- 8) Chaves primárias compostas (chave natural colide entre tenants) ---------
-- customers: (telefone) -> (tenant_id, telefone)
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_constraint
               WHERE conname = 'customers_pkey' AND conrelid = 'customers'::regclass
                 AND array_length(conkey,1) = 1) THEN
        ALTER TABLE customers DROP CONSTRAINT customers_pkey;
        ALTER TABLE customers ADD PRIMARY KEY (tenant_id, telefone);
    END IF;
END $$;

-- conversations: (thread_id) -> (tenant_id, thread_id) + recria a FK de messages
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_constraint
               WHERE conname = 'messages_thread_id_fkey' AND conrelid = 'messages'::regclass) THEN
        ALTER TABLE messages DROP CONSTRAINT messages_thread_id_fkey;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_constraint
               WHERE conname = 'conversations_pkey' AND conrelid = 'conversations'::regclass
                 AND array_length(conkey,1) = 1) THEN
        ALTER TABLE conversations DROP CONSTRAINT conversations_pkey;
        ALTER TABLE conversations ADD PRIMARY KEY (tenant_id, thread_id);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                   WHERE conname = 'messages_conv_fkey' AND conrelid = 'messages'::regclass) THEN
        ALTER TABLE messages ADD CONSTRAINT messages_conv_fkey
            FOREIGN KEY (tenant_id, thread_id)
            REFERENCES conversations(tenant_id, thread_id) ON DELETE CASCADE;
    END IF;
END $$;

-- 9) Agente padrão: um por tenant (antes era único global) --------------------
DROP INDEX IF EXISTS idx_agents_default;
CREATE UNIQUE INDEX IF NOT EXISTS idx_agents_default_tenant
    ON agents(tenant_id) WHERE is_default;

-- 10) Índices compostos por tenant p/ as queries mais quentes -----------------
CREATE INDEX IF NOT EXISTS idx_conversations_tenant_updated ON conversations(tenant_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_customers_tenant_status      ON customers(tenant_id, status);
CREATE INDEX IF NOT EXISTS idx_queue_tenant_status          ON queue_items(tenant_id, status);
CREATE INDEX IF NOT EXISTS idx_events_tenant_created        ON events(tenant_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_messages_tenant_thread       ON messages(tenant_id, thread_id, created_at);

-- 11) Semeia o mapa instância -> tenant a partir dos dados existentes ---------
DO $$
DECLARE pid BIGINT;
BEGIN
    SELECT id INTO pid FROM tenants WHERE slug = 'paratec';
    INSERT INTO instances (instancia, tenant_id)
    SELECT DISTINCT instancia, pid FROM conversations WHERE instancia IS NOT NULL
    ON CONFLICT (instancia) DO NOTHING;
    INSERT INTO instances (instancia, tenant_id)
    SELECT DISTINCT instancia, pid FROM agents WHERE instancia IS NOT NULL
    ON CONFLICT (instancia) DO NOTHING;
END $$;

-- 12) Assinatura "cortesia" da Paratec: enforcement nunca bloqueia a produção -
DO $$
DECLARE pid BIGINT;
BEGIN
    SELECT id INTO pid FROM tenants WHERE slug = 'paratec';
    INSERT INTO subscriptions (tenant_id, plan, status, current_period_end)
    SELECT pid, 'escala', 'active', now() + interval '100 years'
    WHERE NOT EXISTS (SELECT 1 FROM subscriptions WHERE tenant_id = pid);
END $$;

-- 13) Isolamento do catálogo por tenant (só se as tabelas do catálogo existem;
-- em dev sem catálogo elas podem não existir). O isolamento de LEITURA é feito
-- filtrando products.tenant_id (ver catalog.py). A ingestão self-serve por
-- tenant (upload de CSV) está na seção 14 + app/ingest.py.
DO $$
DECLARE pid BIGINT;
BEGIN
    SELECT id INTO pid FROM tenants WHERE slug = 'paratec';
    IF to_regclass('public.products') IS NOT NULL THEN
        ALTER TABLE products ADD COLUMN IF NOT EXISTS tenant_id BIGINT REFERENCES tenants(id);
        EXECUTE format('ALTER TABLE products ALTER COLUMN tenant_id SET DEFAULT %L', pid);
        UPDATE products SET tenant_id = pid WHERE tenant_id IS NULL;
        CREATE INDEX IF NOT EXISTS idx_products_tenant ON products(tenant_id);
    END IF;
    IF to_regclass('public.categories') IS NOT NULL THEN
        ALTER TABLE categories ADD COLUMN IF NOT EXISTS tenant_id BIGINT REFERENCES tenants(id);
        EXECUTE format('ALTER TABLE categories ALTER COLUMN tenant_id SET DEFAULT %L', pid);
        UPDATE categories SET tenant_id = pid WHERE tenant_id IS NULL;
        ALTER TABLE categories DROP CONSTRAINT IF EXISTS categories_name_key;
        CREATE UNIQUE INDEX IF NOT EXISTS uq_categories_tenant_name ON categories(tenant_id, name);
    END IF;
    IF to_regclass('public.product_variants') IS NOT NULL THEN
        ALTER TABLE product_variants ADD COLUMN IF NOT EXISTS tenant_id BIGINT REFERENCES tenants(id);
        EXECUTE format('ALTER TABLE product_variants ALTER COLUMN tenant_id SET DEFAULT %L', pid);
        UPDATE product_variants SET tenant_id = pid WHERE tenant_id IS NULL;
        CREATE INDEX IF NOT EXISTS idx_variants_tenant ON product_variants(tenant_id);
    END IF;
    IF to_regclass('public.product_categories') IS NOT NULL THEN
        ALTER TABLE product_categories ADD COLUMN IF NOT EXISTS tenant_id BIGINT REFERENCES tenants(id);
        EXECUTE format('ALTER TABLE product_categories ALTER COLUMN tenant_id SET DEFAULT %L', pid);
        UPDATE product_categories SET tenant_id = pid WHERE tenant_id IS NULL;
    END IF;
END $$;

-- 14) Catálogo GRAVÁVEL por tenant (ingestão self-serve) ----------------------
-- products.id continua PK global (INTEGER). Produtos ingeridos por novos tenants
-- recebem id de uma SEQUÊNCIA com piso alto (acima dos ids do WordPress da
-- Paratec), evitando colisão entre tenants SEM precisar de PK composta/FKs novas.
-- slug deixa de ser único global e passa a ser único por tenant (chave do upsert
-- da importação). O scraper da Paratec segue usando o WP id (ver load_to_db.py).
DO $$
DECLARE mx BIGINT;
BEGIN
    IF to_regclass('public.products') IS NOT NULL THEN
        ALTER TABLE products DROP CONSTRAINT IF EXISTS products_slug_key;
        CREATE UNIQUE INDEX IF NOT EXISTS uq_products_tenant_slug ON products(tenant_id, slug);
        CREATE SEQUENCE IF NOT EXISTS catalog_product_id_seq;
        SELECT COALESCE(max(id), 0) INTO mx FROM products;
        PERFORM setval('catalog_product_id_seq', GREATEST(100000000, mx + 1), false);
    END IF;
END $$;
