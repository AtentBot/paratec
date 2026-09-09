"""API HTTP do serviço de agentes — chamada pelo N8N (fluxo do WhatsApp)
e pela tela administrativa (endpoints /catalog, /conversas, /fila, /metrics)."""
import asyncio
import base64
import csv
import io
import json
import logging
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, File, HTTPException, Query, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import catalog, evolution, realtime, store
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
    # Permite publicar eventos SSE a partir de código síncrono (threadpool).
    realtime.broker.bind_loop(asyncio.get_running_loop())
    yield


app = FastAPI(title="Paratec Agent Service", version="0.1.0", lifespan=lifespan)

# Diretório dos banners/imagens de promoções (montado em /media). Persistir com
# um volume Docker em `/app/media` para o histórico manter as miniaturas.
MEDIA_DIR = Path(settings.media_dir) if settings.media_dir else Path(__file__).resolve().parents[1] / "media"
MEDIA_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/media", StaticFiles(directory=str(MEDIA_DIR)), name="media")

# Tipos de imagem aceitos no upload de banner.
_IMAGE_MIMES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}


def _media_file(nome: str) -> Path:
    """Resolve um arquivo dentro de MEDIA_DIR barrando path traversal."""
    p = (MEDIA_DIR / Path(nome).name).resolve()
    if p.parent != MEDIA_DIR.resolve():
        raise HTTPException(status_code=400, detail="caminho de mídia inválido")
    return p

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
    segmento: str = "todos"
    criado_por: str | None = None
    # Banner opcional (caminho relativo /media/<arquivo> devolvido pelo upload).
    imagem: str | None = None
    # Destinatários escolhidos manualmente na tela. Quando presente (não vazio),
    # tem prioridade sobre `segmento`.
    telefones: list[str] | None = None


class NotaRequest(BaseModel):
    texto: str
    autor: str | None = None


class AtribuirRequest(BaseModel):
    responsavel: str | None = None


class BotRequest(BaseModel):
    ativo: bool


class VendedorCreate(BaseModel):
    nome: str
    telefone: str
    email: str | None = None
    ativo: bool = True


class VendedorUpdate(BaseModel):
    nome: str | None = None
    telefone: str | None = None
    email: str | None = None
    ativo: bool | None = None


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
def conversas(
    status: str | None = None,
    q: str | None = None,
    limit: int = Query(100, ge=1, le=500),
):
    return store.list_conversations(status, q, limit)


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


@app.post("/conversas/{thread_id}/bot")
def bot(thread_id: str, req: BotRequest):
    """Liga/desliga a resposta automática da IA nesta conversa (toggle do painel).
    ativo=false pausa a IA (atendimento humano); ativo=true devolve à IA."""
    c = store.set_bot(thread_id, req.ativo)
    if c is None:
        raise HTTPException(status_code=404, detail="conversa não encontrada")
    return c


@app.post("/conversas/{thread_id}/ler")
def marcar_lida(thread_id: str):
    """Zera o contador de não-lidas (quando o atendente abre a conversa)."""
    c = store.marcar_lida(thread_id)
    if c is None:
        raise HTTPException(status_code=404, detail="conversa não encontrada")
    return c


@app.get("/conversas/{thread_id}/stream")
async def stream(thread_id: str, request: Request):
    """Push em tempo real (SSE): emite um evento sempre que uma mensagem é
    gravada nesta conversa. O navegador, ao receber, revalida a conversa/lista.
    Envia keep-alives periódicos e encerra quando o cliente desconecta."""

    async def gen():
        q = await realtime.broker.subscribe(thread_id)
        try:
            # abre o stream imediatamente (evita buffering do proxy no 1º byte)
            yield ": ok\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    data = await asyncio.wait_for(q.get(), timeout=20)
                    yield f"data: {json.dumps(data)}\n\n"
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"  # comentário SSE mantém a conexão viva
        finally:
            realtime.broker.unsubscribe(thread_id, q)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # desliga buffering em proxies (nginx)
        },
    )


@app.post("/conversas/{thread_id}/nota")
def add_nota(thread_id: str, req: NotaRequest):
    if store.get_conversation(thread_id) is None:
        raise HTTPException(status_code=404, detail="conversa não encontrada")
    texto = req.texto.strip()
    if not texto:
        raise HTTPException(status_code=422, detail="texto vazio")
    store.add_note(thread_id, texto, req.autor)
    return store.get_conversation(thread_id)


@app.post("/conversas/{thread_id}/atribuir")
def atribuir(thread_id: str, req: AtribuirRequest):
    c = store.set_responsavel(thread_id, req.responsavel)
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


# --- Equipe de vendas (tela adm) -------------------------------------------

@app.get("/vendedores")
def vendedores(ativo: bool | None = None):
    return store.list_sellers(only_ativo=bool(ativo))


@app.post("/vendedores")
def vendedor_criar(req: VendedorCreate):
    nome = req.nome.strip()
    telefone = "".join(ch for ch in req.telefone if ch.isdigit())
    if not nome:
        raise HTTPException(status_code=422, detail="informe o nome do vendedor")
    if len(telefone) < 10:
        raise HTTPException(status_code=422, detail="WhatsApp inválido (use DDD + número)")
    return store.create_seller(nome, telefone, req.email, req.ativo)


@app.patch("/vendedores/{seller_id}")
def vendedor_atualizar(seller_id: int, req: VendedorUpdate):
    telefone = req.telefone
    if telefone is not None:
        telefone = "".join(ch for ch in telefone if ch.isdigit())
        if len(telefone) < 10:
            raise HTTPException(status_code=422, detail="WhatsApp inválido (use DDD + número)")
    v = store.update_seller(seller_id, req.nome, telefone, req.email, req.ativo)
    if v is None:
        raise HTTPException(status_code=404, detail="vendedor não encontrado")
    return v


@app.delete("/vendedores/{seller_id}")
def vendedor_remover(seller_id: int):
    if not store.delete_seller(seller_id):
        raise HTTPException(status_code=404, detail="vendedor não encontrado")
    return {"removido": seller_id}


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


# --- Relatórios (por período) ----------------------------------------------

@app.get("/relatorios/resumo")
def relatorios_resumo(desde: str, ate: str):
    return store.relatorio_resumo(desde, ate)


@app.get("/relatorios/conversas.csv")
def relatorios_conversas_csv(desde: str, ate: str):
    cols = ["thread_id", "cliente", "telefone", "status", "especialista",
            "responsavel", "created_at", "updated_at"]
    return _csv(f"relatorio-conversas-{desde}_a_{ate}.csv", cols,
                store.relatorio_conversas(desde, ate))


# --- RAG / base de conhecimento --------------------------------------------

@app.get("/rag/status")
def rag_status():
    from . import rag
    return rag.status()


@app.post("/rag/ingest")
def rag_ingest():
    """(Re)constrói a base de conhecimento a partir do catálogo."""
    from . import rag
    if not settings.rag_enabled:
        raise HTTPException(status_code=503, detail="RAG não configurado (VECTOR_HOST)")
    try:
        return rag.ingest_catalogo()
    except Exception as e:  # pragma: no cover
        raise HTTPException(status_code=500, detail=f"falha no ingest: {e}")


@app.post("/rag/upload")
async def rag_upload(file: UploadFile = File(...)):
    """Ingere um documento (PDF/txt/md) na base de conhecimento."""
    from . import rag
    if not settings.rag_enabled:
        raise HTTPException(status_code=503, detail="RAG não configurado (VECTOR_HOST)")
    data = await file.read()
    if not data:
        raise HTTPException(status_code=422, detail="arquivo vazio")
    try:
        return rag.ingest_documento(file.filename or "documento", data, file.content_type)
    except Exception as e:  # pragma: no cover
        raise HTTPException(status_code=500, detail=f"falha no upload: {e}")


@app.get("/rag/fontes")
def rag_fontes():
    from . import rag
    if not settings.rag_enabled:
        return []
    return rag.listar_fontes()


@app.delete("/rag/fontes/{source}")
def rag_remover_fonte(source: str):
    from . import rag
    removidos = rag.remover_fonte(source)
    return {"fonte": source, "removidos": removidos}


# --- Orçamentos (comercial) — pedidos de orçamento gerados pelo agente ------

@app.get("/orcamentos")
def orcamentos(status: str | None = None):
    return store.list_queue("pedido", status)


# --- Broadcast (envio em massa de promoções) --------------------------------

def _run_broadcast(
    bid: int, texto: str, dests: list[dict], midia: dict | None = None
) -> None:
    """Worker: envia a todos com throttle (anti-bloqueio). Roda em background.

    `midia` (opcional) = {"b64", "mimetype", "filename"} para enviar um banner
    (imagem) com `texto` como legenda; sem ela, envia só texto.
    """
    for c in dests:
        try:
            if midia:
                evolution.enviar_midia(
                    c["telefone"], midia["b64"],
                    mimetype=midia["mimetype"], filename=midia["filename"], caption=texto,
                )
            else:
                evolution.enviar_texto(c["telefone"], texto)
            store.bump_broadcast(bid, enviados=1)
        except Exception as e:  # pragma: no cover
            logging.getLogger("paratec").warning("broadcast %s falhou p/ %s: %s",
                                                  bid, c.get("telefone"), e)
            store.bump_broadcast(bid, falhas=1)
        time.sleep(settings.broadcast_throttle_seconds)
    store.finish_broadcast(bid, "concluido")


@app.post("/broadcast/upload")
async def broadcast_upload(file: UploadFile = File(...)):
    """Recebe a imagem do banner e a guarda em /media. Devolve o caminho relativo."""
    mime = (file.content_type or "").lower()
    if mime not in _IMAGE_MIMES:
        raise HTTPException(status_code=422, detail="use uma imagem JPG, PNG ou WEBP")
    data = await file.read()
    if not data:
        raise HTTPException(status_code=422, detail="arquivo vazio")
    if len(data) > 5 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="imagem acima de 5 MB")
    nome = f"promo-{uuid.uuid4().hex}{_IMAGE_MIMES[mime]}"
    _media_file(nome).write_bytes(data)
    return {"arquivo": nome, "url": f"/media/{nome}", "mimetype": mime}


@app.post("/broadcast")
def broadcast(req: BroadcastRequest, bg: BackgroundTasks):
    texto = req.texto.strip()
    if not texto and not req.imagem:
        raise HTTPException(status_code=422, detail="informe um texto ou uma imagem")
    if not settings.evolution_configured:
        raise HTTPException(status_code=503, detail="Evolution API não configurada")

    # Destinatários: seleção manual tem prioridade sobre o segmento.
    if req.telefones:
        dests = store.customers_por_telefones(req.telefones)
        if not dests:
            raise HTTPException(status_code=422, detail="nenhum cliente elegível selecionado")
    else:
        dests = store.customers_para_broadcast(req.segmento)
        if not dests:
            raise HTTPException(status_code=422, detail="nenhum cliente elegível neste segmento")

    # Banner opcional: carrega o arquivo salvo no upload e prepara para envio.
    midia: dict | None = None
    imagem_ref: str | None = None
    if req.imagem:
        arquivo = req.imagem.rsplit("/", 1)[-1]  # aceita "/media/x" ou só "x"
        caminho = _media_file(arquivo)
        if not caminho.exists():
            raise HTTPException(status_code=422, detail="imagem não encontrada; reenvie o banner")
        # extensão -> mimetype (inverso de _IMAGE_MIMES)
        mimetype = next((m for m, ext in _IMAGE_MIMES.items() if ext == caminho.suffix), "image/jpeg")
        midia = {
            "b64": base64.b64encode(caminho.read_bytes()).decode("ascii"),
            "mimetype": mimetype,
            "filename": arquivo,
        }
        imagem_ref = f"/media/{arquivo}"

    bid = store.create_broadcast(texto, len(dests), req.criado_por, imagem_ref)
    bg.add_task(_run_broadcast, bid, texto, dests, midia)
    return {"id": bid, "total": len(dests), "status": "enviando"}


@app.get("/broadcasts")
def broadcasts():
    return store.list_broadcasts()


@app.get("/broadcast/segmentos")
def broadcast_segmentos():
    """Quantidade de clientes elegíveis por segmento."""
    return store.contar_segmentos()


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
