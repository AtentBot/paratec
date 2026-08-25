-- Schema do catalogo Paratec (nucleo, sem dependencias de extensao)
-- Executar: psql "$DATABASE_URL" -f db/schema.sql
-- Idempotente: pode rodar varias vezes.
-- A base de conhecimento vetorial (RAG dos agentes) fica em db/schema_vector.sql
-- e depende da extensao pgvector (ainda nao provisionada neste servidor).

-- ---------------------------------------------------------------------------
-- Categorias (taxonomia categoria-de-produto do WordPress)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS categories (
    id          SERIAL PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE,
    slug        TEXT UNIQUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- Produtos (familia de produto = 1 post 'produto' do WordPress)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS products (
    id            INTEGER PRIMARY KEY,            -- id do post no WordPress
    slug          TEXT NOT NULL UNIQUE,
    title         TEXT NOT NULL,
    description   TEXT,                            -- intro/descricao da familia
    image_url     TEXT,
    source_url    TEXT,
    featured      BOOLEAN NOT NULL DEFAULT false,  -- "Produtos em Destaque"
    raw_text      TEXT,                            -- texto limpo da pagina (fallback p/ agentes)
    wp_modified   TIMESTAMPTZ,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- N:N produto <-> categoria
CREATE TABLE IF NOT EXISTS product_categories (
    product_id   INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    category_id  INTEGER NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
    PRIMARY KEY (product_id, category_id)
);

-- ---------------------------------------------------------------------------
-- Variantes (SKU concreto: PRT-101, etc.)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS product_variants (
    id           SERIAL PRIMARY KEY,
    product_id   INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    sku          TEXT,                    -- ex: PRT-101 (normalizado)
    material     TEXT,                    -- ex: Latao Niquelado, Inox, Aluminio
    dimensions   TEXT,                    -- ex: 300mm
    attributes   TEXT,                    -- ex: "1 descida"
    description  TEXT,
    raw_text     TEXT,
    extracted_by TEXT,                    -- 'heuristic' | 'llm'
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_variants_product ON product_variants(product_id);
CREATE INDEX IF NOT EXISTS idx_variants_sku     ON product_variants(sku);

-- Identidade da variante = produto + sku + dimensao + atributos.
-- (COALESCE porque UNIQUE trata NULLs como distintos por padrao.)
CREATE UNIQUE INDEX IF NOT EXISTS uq_variant_identity ON product_variants
    (product_id, coalesce(sku,''), coalesce(dimensions,''), coalesce(attributes,''));

-- Busca textual (fallback / hibrida) usando full-text search nativo do PG.
CREATE INDEX IF NOT EXISTS idx_products_title_fts
    ON products USING gin (to_tsvector('portuguese', title));
CREATE INDEX IF NOT EXISTS idx_variants_sku_lower
    ON product_variants (lower(sku));
