-- Base de conhecimento vetorial (RAG dos agentes) — DEPENDE DE pgvector.
-- Aplicar SOMENTE apos provisionar a extensao no servidor:
--   - servidor gerenciado: instalar o pacote pgvector no host do Postgres
--     (ex: apt install postgresql-15-pgvector) e depois CREATE EXTENSION;
--   - alternativa: subir um Postgres com pgvector via Docker
--     (imagem pgvector/pgvector:pg15) — ver docker-compose.
--
-- Executar: psql "$DATABASE_URL" -f db/schema_vector.sql

-- NOTA: o schema real é criado em runtime por app/rag.py (ensure_schema) — este
-- arquivo é a referência/documentação e deve espelhá-lo. Base ISOLADA POR TENANT.

CREATE EXTENSION IF NOT EXISTS vector;

-- Cada chunk pertence a um TENANT (isolamento). Dimensão 3072 = gemini-embedding-001.
-- Banco vetorial é separado do operacional, então tenant_id NÃO tem FK aqui.
CREATE TABLE IF NOT EXISTS knowledge_chunks (
    id          BIGSERIAL PRIMARY KEY,
    tenant_id   BIGINT,
    source      TEXT NOT NULL,          -- 'catalogo' ou nome do documento enviado
    titulo      TEXT,
    content     TEXT NOT NULL,
    embedding   vector(3072),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 3072 dims excede o limite do ivfflat/hnsw (2000): sem índice ANN; a busca é
-- exata por tenant (bases pequenas). Índice por tenant acelera o filtro.
CREATE INDEX IF NOT EXISTS idx_kc_tenant ON knowledge_chunks(tenant_id);
