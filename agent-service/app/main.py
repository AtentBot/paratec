"""API HTTP do serviço de agentes — chamada pelo N8N (fluxo do WhatsApp)
e pela tela administrativa (endpoints /catalog, /conversas, /fila, /metrics)."""
import csv
import io
import logging
import time
from contextlib import asynccontextmanager

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from . import catalog, evolution, store
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


class ResponderRequest(BaseModel):
    texto: str


class BroadcastRequest(BaseModel):
    texto: str
    criado_por: str | None = None


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


@app.post("/conversas/{thread_id}/resolver")
def resolver(thread_id: str):
    c = store.resolver_conversation(thread_id)
    if c is None:
        raise HTTPException(status_code=404, detail="conversa não encontrada")
    return c


@app.post("/conversas/{thread_id}/reabrir")
def reabrir(thread_id: str):
    c = store.reabrir_conversation(thread_id)
    if c is None:
        raise HTTPException(status_code=404, detail="conversa não encontrada")
    return c


@app.post("/conversas/{thread_id}/responder")
def responder_conversa(thread_id: str, req: ResponderRequest):
    """Envia uma resposta HUMANA ao cliente pelo WhatsApp (Evolution) e registra
    no histórico. thread_id = número do WhatsApp."""
    texto = req.texto.strip()
    if not texto:
        raise HTTPException(status_code=422, detail="texto vazio")
    if store.get_conversation(thread_id) is None:
        raise HTTPException(status_code=404, detail="conversa não encontrada")
    try:
        evolution.enviar_texto(thread_id, texto)
    except evolution.EvolutionError as e:
        raise HTTPException(status_code=503, detail=str(e))
    store.add_message(thread_id, "humano", texto)
    store.set_status(thread_id, "humano")
    return store.get_conversation(thread_id)


# --- Clientes (tela adm) ---------------------------------------------------

@app.get("/clientes")
def clientes(status: str | None = None, limit: int = Query(200, ge=1, le=1000)):
    return store.list_customers(status, limit)


@app.get("/clientes/{telefone}")
def cliente(telefone: str):
    c = store.get_customer(telefone)
    if c is None:
        raise HTTPException(status_code=404, detail="cliente não encontrado")
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


# --- Exportações CSV -------------------------------------------------------

def _csv(filename: str, colunas: list[str], linhas: list[dict]) -> Response:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(colunas)
    for r in linhas:
        w.writerow([r.get(c, "") for c in colunas])
    return Response(
        content=buf.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/clientes.csv")
def clientes_csv(status: str | None = None):
    cols = ["telefone", "razao_social", "cnpj", "email", "nome_contato",
            "status", "created_at"]
    return _csv("clientes.csv", cols, store.list_customers(status, 100000))


@app.get("/fila.csv")
def fila_csv(tipo: str | None = None, status: str | None = None):
    cols = ["id", "tipo", "status", "cliente", "telefone", "resumo",
            "responsavel", "created_at"]
    return _csv("fila.csv", cols, store.list_queue(tipo, status))


# --- Orçamentos (comercial) — pedidos de orçamento gerados pelo agente ------

@app.get("/orcamentos")
def orcamentos(status: str | None = None):
    return store.list_queue("pedido", status)


# --- Broadcast (envio em massa de promoções) --------------------------------

def _run_broadcast(bid: int, texto: str, dests: list[dict]) -> None:
    """Worker: envia a todos com throttle (anti-bloqueio). Roda em background."""
    for c in dests:
        try:
            evolution.enviar_texto(c["telefone"], texto)
            store.bump_broadcast(bid, enviados=1)
        except Exception as e:  # pragma: no cover
            logging.getLogger("paratec").warning("broadcast %s falhou p/ %s: %s",
                                                  bid, c.get("telefone"), e)
            store.bump_broadcast(bid, falhas=1)
        time.sleep(settings.broadcast_throttle_seconds)
    store.finish_broadcast(bid, "concluido")


@app.post("/broadcast")
def broadcast(req: BroadcastRequest, bg: BackgroundTasks):
    texto = req.texto.strip()
    if not texto:
        raise HTTPException(status_code=422, detail="texto vazio")
    if not settings.evolution_configured:
        raise HTTPException(status_code=503, detail="Evolution API não configurada")
    dests = store.customers_para_broadcast()
    if not dests:
        raise HTTPException(status_code=422, detail="nenhum cliente elegível (ativo/sem opt-out)")
    bid = store.create_broadcast(texto, len(dests), req.criado_por)
    bg.add_task(_run_broadcast, bid, texto, dests)
    return {"id": bid, "total": len(dests), "status": "enviando"}


@app.get("/broadcasts")
def broadcasts():
    return store.list_broadcasts()


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
