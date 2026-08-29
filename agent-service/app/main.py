"""API HTTP do serviço de agentes — chamada pelo N8N (fluxo do WhatsApp)
e pela tela administrativa (endpoints /catalog, /conversas, /fila, /metrics)."""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from . import catalog, store
from .agents import responder
from .db import get_pool
from .settings import settings


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Garante o schema operacional (idempotente) ao subir o serviço."""
    try:
        store.ensure_schema()
    except Exception as e:  # pragma: no cover
        logging.getLogger("paratec").warning("ensure_schema falhou: %s", e)
    yield


app = FastAPI(title="Paratec Agent Service", version="0.1.0", lifespan=lifespan)

# A tela adm (Next.js) roda em outra origem; libera CORS para o painel.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    mensagem: str
    # id da conversa (ex: número do WhatsApp) — mantém o histórico por cliente
    thread_id: str = "default"
    cliente: str | None = None
    telefone: str | None = None


class ChatResponse(BaseModel):
    resposta: str


class QueueUpdate(BaseModel):
    status: str | None = None
    responsavel: str | None = None


@app.get("/health")
def health():
    try:
        with get_pool().connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT count(*) AS n FROM products")
                n = cur.fetchone()["n"]
        return {"status": "ok", "produtos": n, "model": settings.llm_model}
    except Exception as e:  # pragma: no cover
        return {"status": "degraded", "erro": str(e)}


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    resposta = responder(req.mensagem, req.thread_id, req.cliente, req.telefone)
    return ChatResponse(resposta=resposta)


# --- Conversas (tela adm) --------------------------------------------------

@app.get("/conversas")
def conversas(status: str | None = None, limit: int = Query(100, ge=1, le=500)):
    return store.list_conversations(status, limit)


@app.get("/conversas/{thread_id}")
def conversa(thread_id: str):
    c = store.get_conversation(thread_id)
    if c is None:
        raise HTTPException(status_code=404, detail="conversa não encontrada")
    return c


@app.post("/conversas/{thread_id}/assumir")
def assumir(thread_id: str):
    c = store.assumir_conversation(thread_id)
    if c is None:
        raise HTTPException(status_code=404, detail="conversa não encontrada")
    return c


# --- Fila humana (tela adm) ------------------------------------------------

@app.get("/fila")
def fila(tipo: str | None = None, status: str | None = None):
    return store.list_queue(tipo, status)


@app.patch("/fila/{item_id}")
def fila_update(item_id: int, upd: QueueUpdate):
    item = store.update_queue_item(item_id, upd.status, upd.responsavel)
    if item is None:
        raise HTTPException(status_code=404, detail="item não encontrado")
    return item


# --- Métricas (dashboard) --------------------------------------------------

@app.get("/metrics/overview")
def metrics_overview():
    return store.metrics_overview()


# --- Catálogo (consumido pela tela administrativa) -------------------------

@app.get("/catalog/stats")
def catalog_stats():
    """Totais do catálogo para os cards do dashboard."""
    return catalog.contar_totais()


@app.get("/catalog/categorias")
def catalog_categorias():
    return catalog.listar_categorias()


@app.get("/catalog/produtos")
def catalog_produtos(
    q: str | None = None,
    categoria: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    return catalog.listar_produtos(q, categoria, limit, offset)


@app.get("/catalog/produtos/{identificador}")
def catalog_produto(identificador: str):
    p = catalog.detalhes_produto(identificador)
    if p is None:
        raise HTTPException(status_code=404, detail="produto não encontrado")
    return p
