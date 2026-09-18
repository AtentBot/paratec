"""RAG / base de conhecimento (pgvector dedicado), ISOLADA POR TENANT.

Cada cliente (tenant) tem sua própria base: os agentes só recuperam trechos do
próprio tenant. Fica num banco vetorial próprio (settings.vector_*), separado do
Postgres operacional. Se não configurado, tudo vira no-op — o agente segue
funcionando sem a base. Embeddings via Gemini (gemini-embedding-001, 3072 dims).

O banco vetorial NÃO tem a tabela `tenants` (fica no Postgres operacional), então
`tenant_id` aqui é só o inteiro do tenant (sem FK); o isolamento é por filtro.
"""
from __future__ import annotations

import io
import logging
import re
from functools import lru_cache

from .settings import settings

log = logging.getLogger("atentbot.rag")
DIM = 3072  # gemini-embedding-001


@lru_cache(maxsize=1)
def _pool():
    from psycopg_pool import ConnectionPool
    from psycopg.rows import dict_row

    pool = ConnectionPool(
        settings.vector_dsn,
        min_size=1,
        max_size=3,
        kwargs={"row_factory": dict_row},
        open=True,
    )
    return pool


@lru_cache(maxsize=1)
def _embeddings():
    from langchain_google_genai import GoogleGenerativeAIEmbeddings

    return GoogleGenerativeAIEmbeddings(
        model=settings.embedding_model, google_api_key=settings.google_api_key
    )


def _vec(v: list[float]) -> str:
    return "[" + ",".join(f"{x:.7f}" for x in v) + "]"


def _estimar_tokens(textos: list[str]) -> int:
    """Estimativa de tokens (~4 caracteres por token) para a medição de consumo."""
    return sum(len(t or "") for t in textos) // 4


def _registrar_consumo(tenant_id: int, tipo: str, textos: list[str], meta: dict) -> dict:
    """Mede os tokens de embedding e registra o consumo (custo interno; a
    indexação não é cobrada do cliente). Best-effort."""
    tokens = _estimar_tokens(textos)
    try:
        from . import billing

        return billing.registrar_consumo(tenant_id, tipo, tokens, {**meta, "tokens": tokens})
    except Exception as e:  # pragma: no cover
        log.warning("registro de consumo falhou: %s", e)
        return {"tokens": tokens, "custo_estimado": settings.custo_tokens(tipo, tokens)}


def _default_tenant_id() -> int:
    """Id do tenant de fallback (Paratec) para backfill dos chunks legados."""
    try:
        from . import store

        t = store.get_tenant_by_slug(settings.default_tenant_slug)
        return int(t["id"]) if t else 1
    except Exception:  # pragma: no cover
        return 1


def ensure_schema() -> None:
    with _pool().connection() as conn:
        conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        conn.execute(
            f"""CREATE TABLE IF NOT EXISTS knowledge_chunks (
                    id         BIGSERIAL PRIMARY KEY,
                    tenant_id  BIGINT,
                    source     TEXT NOT NULL,
                    titulo     TEXT,
                    content    TEXT NOT NULL,
                    embedding  vector({DIM}),
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )"""
        )
        # Migração p/ bases existentes (sem tenant_id): adiciona a coluna e faz
        # backfill dos chunks legados para o tenant Paratec.
        conn.execute("ALTER TABLE knowledge_chunks ADD COLUMN IF NOT EXISTS tenant_id BIGINT")
        conn.execute(
            "UPDATE knowledge_chunks SET tenant_id = %s WHERE tenant_id IS NULL",
            (_default_tenant_id(),),
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_kc_tenant ON knowledge_chunks(tenant_id)")
        # 3072 dims excede o limite do índice ivfflat/hnsw (2000); as bases são
        # pequenas, então usamos busca exata por tenant (rápida o bastante).


def status(tenant_id: int) -> dict:
    if not settings.rag_enabled:
        return {"enabled": False}
    try:
        with _pool().connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT count(*) AS n, count(DISTINCT source) AS fontes "
                    "FROM knowledge_chunks WHERE tenant_id = %s",
                    (tenant_id,),
                )
                r = cur.fetchone()
        return {"enabled": True, "chunks": r["n"], "fontes": r["fontes"]}
    except Exception as e:  # pragma: no cover
        return {"enabled": True, "erro": str(e)}


def _chunks_catalogo(tenant_id: int) -> list[dict]:
    """Um trecho por produto DO TENANT: título + descrição + variantes."""
    from .db import query as pg_query  # Postgres operacional (catálogo)

    prods = pg_query(
        "SELECT id, title, COALESCE(description,'') AS description, slug "
        "FROM products WHERE tenant_id = %s ORDER BY id",
        (tenant_id,),
    )
    out = []
    for p in prods:
        vs = pg_query(
            """SELECT sku, material, dimensions, attributes, description
                 FROM product_variants WHERE tenant_id = %s AND product_id = %s ORDER BY sku""",
            (tenant_id, p["id"]),
        )
        linhas = []
        for v in vs:
            partes = [v.get("sku")]
            for campo in ("material", "dimensions", "attributes", "description"):
                if v.get(campo):
                    partes.append(str(v[campo]))
            linhas.append(" · ".join([x for x in partes if x]))
        corpo = f"Produto: {p['title']}.\n{p['description']}".strip()
        if linhas:
            corpo += "\nVariantes/SKUs:\n- " + "\n- ".join(linhas)
        out.append({"source": "catalogo", "titulo": p["title"], "content": corpo})
    return out


def ingest_catalogo(tenant_id: int) -> dict:
    """(Re)constrói a base do catálogo DO TENANT. Reescreve APENAS a fonte
    'catalogo' desse tenant, preservando os documentos enviados manualmente."""
    ensure_schema()
    chunks = _chunks_catalogo(tenant_id)
    if not chunks:
        with _pool().connection() as conn:
            conn.execute(
                "DELETE FROM knowledge_chunks WHERE tenant_id = %s AND source = 'catalogo'",
                (tenant_id,),
            )
        return {"ingeridos": 0, "fonte": "catalogo"}
    vecs = _embeddings().embed_documents([c["content"] for c in chunks])
    with _pool().connection() as conn:
        conn.execute(
            "DELETE FROM knowledge_chunks WHERE tenant_id = %s AND source = 'catalogo'",
            (tenant_id,),
        )
        with conn.cursor() as cur:
            for c, v in zip(chunks, vecs):
                cur.execute(
                    "INSERT INTO knowledge_chunks (tenant_id, source, titulo, content, embedding) "
                    "VALUES (%s, %s, %s, %s, %s::vector)",
                    (tenant_id, c["source"], c["titulo"], c["content"], _vec(v)),
                )
    consumo = _registrar_consumo(
        tenant_id, "rag_ingest_catalogo", [c["content"] for c in chunks],
        {"fonte": "catalogo", "chunks": len(chunks)},
    )
    return {"ingeridos": len(chunks), "fonte": "catalogo", **consumo}


def _chunk_text(texto: str, size: int = 1200, overlap: int = 150) -> list[str]:
    texto = re.sub(r"[ \t]+", " ", texto).strip()
    chunks, i, n = [], 0, len(texto)
    while i < n:
        parte = texto[i : i + size].strip()
        if parte:
            chunks.append(parte)
        i += size - overlap
    return chunks


def _extrair_texto(nome: str, data: bytes, content_type: str | None) -> str:
    nome_l = (nome or "").lower()
    if nome_l.endswith(".pdf") or (content_type or "").endswith("pdf"):
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(data))
        return "\n".join((pg.extract_text() or "") for pg in reader.pages)
    return data.decode("utf-8", errors="replace")


def ingest_documento(tenant_id: int, nome: str, data: bytes, content_type: str | None = None) -> dict:
    """Extrai texto de um documento (PDF/txt/md), chunk + embed + grava NO TENANT.
    A fonte é o nome do arquivo (reenviar substitui a fonte, dentro do tenant)."""
    ensure_schema()
    texto = _extrair_texto(nome, data, content_type)
    partes = _chunk_text(texto)
    if not partes:
        return {"fonte": nome, "chunks": 0, "aviso": "nenhum texto extraído"}
    vecs = _embeddings().embed_documents(partes)
    with _pool().connection() as conn:
        conn.execute(
            "DELETE FROM knowledge_chunks WHERE tenant_id = %s AND source = %s",
            (tenant_id, nome),
        )
        with conn.cursor() as cur:
            for i, (parte, v) in enumerate(zip(partes, vecs)):
                cur.execute(
                    "INSERT INTO knowledge_chunks (tenant_id, source, titulo, content, embedding) "
                    "VALUES (%s, %s, %s, %s, %s::vector)",
                    (tenant_id, nome, f"{nome} · trecho {i + 1}", parte, _vec(v)),
                )
    consumo = _registrar_consumo(
        tenant_id, "rag_ingest_documento", partes, {"fonte": nome, "chunks": len(partes)},
    )
    return {"fonte": nome, "chunks": len(partes), **consumo}


def listar_fontes(tenant_id: int) -> list[dict]:
    with _pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT source, count(*) AS chunks, max(created_at) AS atualizado "
                "FROM knowledge_chunks WHERE tenant_id = %s GROUP BY source ORDER BY source",
                (tenant_id,),
            )
            return cur.fetchall()


def remover_fonte(tenant_id: int, source: str) -> int:
    with _pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM knowledge_chunks WHERE tenant_id = %s AND source = %s",
                (tenant_id, source),
            )
            return cur.rowcount


def buscar(pergunta: str, tenant_id: int, k: int = 4) -> list[dict]:
    """Busca semântica DENTRO DO TENANT: os k trechos mais próximos da pergunta."""
    if not settings.rag_enabled or not tenant_id:
        return []
    qv = _vec(_embeddings().embed_query(pergunta))
    with _pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT titulo, content, 1 - (embedding <=> %s::vector) AS score
                     FROM knowledge_chunks
                    WHERE tenant_id = %s
                    ORDER BY embedding <=> %s::vector LIMIT %s""",
                (qv, tenant_id, qv, k),
            )
            return cur.fetchall()
