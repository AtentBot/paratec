-- Base de conhecimento vetorial (RAG dos agentes) — DEPENDE DE pgvector.
-- Aplicar SOMENTE apos provisionar a extensao no servidor:
--   - servidor gerenciado: instalar o pacote pgvector no host do Postgres
--     (ex: apt install postgresql-15-pgvector) e depois CREATE EXTENSION;
--   - alternativa: subir um Postgres com pgvector via Docker
--     (imagem pgvector/pgvector:pg15) — ver docker-compose.
--
-- Executar: psql "$DATABASE_URL" -f db/schema_vector.sql

CREATE EXTENSION IF NOT EXISTS vector;

-- Cada chunk aponta para o produto de origem.
-- Dimensao 1536 = compativel com varios modelos de embedding; ajuste se preciso.
CREATE TABLE IF NOT EXISTS knowledge_chunks (
    id          SERIAL PRIMARY KEY,
    product_id  INTEGER REFERENCES products(id) ON DELETE CASCADE,
    content     TEXT NOT NULL,
    embedding   vector(1536),
    metadata    JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_knowledge_embedding
    ON knowledge_chunks USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);
