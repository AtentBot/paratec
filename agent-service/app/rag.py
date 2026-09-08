"""RAG / base de conhecimento (pgvector dedicado).

Isolado do Postgres operacional: usa um banco vetorial próprio
(settings.vector_*). Se não configurado, tudo vira no-op — o agente segue
funcionando sem a base. Embeddings via Gemini (text-embedding-004, 768 dims).
"""
from __future__ import annotations

import io
import logging
import re
from functools import lru_cache

from .settings import settings

log = logging.getLogger("paratec.rag")
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


def ensure_schema() -> None:
    with _pool().connection() as conn:
        conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        conn.execute(
            f"""CREATE TABLE IF NOT EXISTS knowledge_chunks (
                    id         BIGSERIAL PRIMARY KEY,
                    source     TEXT NOT NULL,
                    titulo     TEXT,
                    content    TEXT NOT NULL,
                    embedding  vector({DIM}),
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )"""
        )
        # 3072 dims excede o limite do índice ivfflat/hnsw (2000); a base é
        # pequena, então usamos busca exata (sequential scan) — rápida o bastante.


def status() -> dict:
    if not settings.rag_enabled:
        return {"enabled": False}
    try:
        with _pool().connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT count(*) AS n, count(DISTINCT source) AS fontes FROM knowledge_chunks")
                r = cur.fetchone()
        return {"enabled": True, "chunks": r["n"], "fontes": r["fontes"]}
    except Exception as e:  # pragma: no cover
        return {"enabled": True, "erro": str(e)}


def _chunks_catalogo() -> list[dict]:
    """Um trecho por produto: título + descrição + variantes (SKU/material/dim)."""
    from .db import query as pg_query  # Postgres operacional (catálogo)

    prods = pg_query(
        "SELECT id, title, COALESCE(description,'') AS description, slug FROM products ORDER BY id"
    )
    out = []
    for p in prods:
        vs = pg_query(
            """SELECT sku, material, dimensions, attributes, description
                 FROM product_variants WHERE product_id = %s ORDER BY sku""",
            (p["id"],),
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


def ingest_catalogo() -> dict:
    """(Re)constrói a base a partir do catálogo. Recria a tabela (garante a
    dimensão atual do embedding) e repopula."""
    with _pool().connection() as conn:
        conn.execute("DROP TABLE IF EXISTS knowledge_chunks")
    ensure_schema()
    chunks = _chunks_catalogo()
    emb = _embeddings()
    vecs = emb.embed_documents([c["content"] for c in chunks])
    with _pool().connection() as conn:
        conn.execute("DELETE FROM knowledge_chunks WHERE source = 'catalogo'")
        with conn.cursor() as cur:
            for c, v in zip(chunks, vecs):
                cur.execute(
                    "INSERT INTO knowledge_chunks (source, titulo, content, embedding) "
                    "VALUES (%s, %s, %s, %s::vector)",
                    (c["source"], c["titulo"], c["content"], _vec(v)),
                )
    return {"ingeridos": len(chunks), "fonte": "catalogo"}


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


def ingest_documento(nome: str, data: bytes, content_type: str | None = None) -> dict:
    """Extrai texto de um documento (PDF/txt/md), chunk + embed + grava.
    A fonte é o nome do arquivo (reenviar substitui a fonte)."""
    ensure_schema()
    texto = _extrair_texto(nome, data, content_type)
    partes = _chunk_text(texto)
    if not partes:
        return {"fonte": nome, "chunks": 0, "aviso": "nenhum texto extraído"}
    vecs = _embeddings().embed_documents(partes)
    with _pool().connection() as conn:
        conn.execute("DELETE FROM knowledge_chunks WHERE source = %s", (nome,))
        with conn.cursor() as cur:
            for i, (parte, v) in enumerate(zip(partes, vecs)):
                cur.execute(
                    "INSERT INTO knowledge_chunks (source, titulo, content, embedding) "
                    "VALUES (%s, %s, %s, %s::vector)",
                    (nome, f"{nome} · trecho {i + 1}", parte, _vec(v)),
                )
    return {"fonte": nome, "chunks": len(partes)}


def listar_fontes() -> list[dict]:
    with _pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT source, count(*) AS chunks, max(created_at) AS atualizado "
                "FROM knowledge_chunks GROUP BY source ORDER BY source"
            )
            return cur.fetchall()


def remover_fonte(source: str) -> int:
    with _pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM knowledge_chunks WHERE source = %s", (source,))
            return cur.rowcount


def buscar(pergunta: str, k: int = 4) -> list[dict]:
    """Busca semântica: retorna os k trechos mais próximos da pergunta."""
    if not settings.rag_enabled:
        return []
    qv = _vec(_embeddings().embed_query(pergunta))
    with _pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT titulo, content, 1 - (embedding <=> %s::vector) AS score
                     FROM knowledge_chunks
                    ORDER BY embedding <=> %s::vector LIMIT %s""",
                (qv, qv, k),
            )
            return cur.fetchall()
