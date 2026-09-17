"""API HTTP do serviço de agentes (AtentBot).

- `/chat` é chamado pelo N8N (fluxo do WhatsApp) — resolve o tenant pela instância.
- `/auth/*` e `/billing/*` cuidam de login e assinatura (SaaS multi-tenant).
- `/v1/*` é a API pública de integrações (chave por tenant + escopos) — ver
  app/api_publica.py.
- Os demais endpoints (painel) exigem sessão + assinatura ativa e são isolados
  por tenant: cada handler recebe `tenant` (Depends) e repassa tenant.tenant_id
  a store/catalog. Sem esse filtro, haveria vazamento entre clientes.
"""
import asyncio
import base64
import csv
import io
import json
import logging
import re
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import (
    BackgroundTasks, Depends, FastAPI, File, HTTPException, Query, Request,
    Response, UploadFile,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import (
    api_publica, auth, billing, catalog, evolution, ingest, mailer, realtime, store, webhooks,
)
from .agents import CAPACIDADES, CAPACIDADES_ORDEM, responder
from .auth import TenantCtx, current_admin, current_tenant
from .billing import require_active_subscription
from .db import get_pool
from .settings import settings


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Garante o schema operacional (idempotente) ao subir o serviço."""
    try:
        store.ensure_schema()
    except Exception as e:  # pragma: no cover
        logging.getLogger("atentbot").warning("ensure_schema falhou: %s", e)
    try:
        store.purge_api_logs(settings.api_log_retencao_dias)
        store.purge_webhook_entregas(settings.webhook_retencao_dias)
    except Exception as e:  # pragma: no cover
        logging.getLogger("atentbot").warning("purge_api_logs falhou: %s", e)
    # Permite publicar eventos SSE a partir de código síncrono (threadpool).
    realtime.broker.bind_loop(asyncio.get_running_loop())
    yield


app = FastAPI(title="AtentBot Agent Service", version="1.0.0", lifespan=lifespan)

# API pública de integrações (/v1, chaves por tenant) + gestão das chaves no painel.
api_publica.instalar(app)
app.include_router(webhooks.router)

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


# =========================================================================
# Modelos
# =========================================================================

class ChatRequest(BaseModel):
    mensagem: str
    thread_id: str = "default"
    cliente: str | None = None
    telefone: str | None = None
    instancia: str | None = None


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
    imagem: str | None = None
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


class AgenteCreate(BaseModel):
    nome: str
    descricao: str | None = None
    instancia: str | None = None
    persona: str | None = None
    capacidades: list[str] = []
    ativo: bool = True
    hiperpersonalizacao: bool = False


class AgenteUpdate(BaseModel):
    nome: str | None = None
    descricao: str | None = None
    instancia: str | None = None
    persona: str | None = None
    capacidades: list[str] | None = None
    ativo: bool | None = None
    hiperpersonalizacao: bool | None = None


class SignupRequest(BaseModel):
    empresa: str
    email: str
    senha: str
    nome: str | None = None
    plano: str | None = None   # plano escolhido na landing (segue no link do e-mail)
    whatsapp: str | None = None  # obrigatório (validado em auth.signup)


class VerificarEmailRequest(BaseModel):
    token: str


class ReenviarVerificacaoRequest(BaseModel):
    email: str
    plano: str | None = None


class WhatsappCodigoRequest(BaseModel):
    telefone: str | None = None   # troca o número do cadastro (antes de verificar)


class WhatsappVerificarRequest(BaseModel):
    codigo: str


class LoginRequest(BaseModel):
    email: str
    senha: str


class CheckoutRequest(BaseModel):
    plano: str


class CancelRequest(BaseModel):
    respostas: dict | None = None   # as 5 respostas da pesquisa
    comentario: str | None = None   # relato livre do cliente


class TicketCreate(BaseModel):
    assunto: str
    descricao: str
    categoria: str = "duvida"
    prioridade: str = "normal"


class TicketMensagem(BaseModel):
    corpo: str


class TicketStatus(BaseModel):
    status: str


class AdminSubReq(BaseModel):
    status: str
    plan: str | None = None


class AdminPlanoPrecoReq(BaseModel):
    preco: float
    aplicar_existentes: bool = False


class AdminTicketReq(BaseModel):
    status: str | None = None
    prioridade: str | None = None


class InstanciaCreate(BaseModel):
    nome: str


# =========================================================================
# Público: health + chat (n8n)
# =========================================================================

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
    # Tenant resolvido internamente pela instância (ver agents.responder).
    resposta = responder(
        req.mensagem, req.thread_id, req.cliente, req.telefone, req.instancia
    )
    return ChatResponse(resposta=resposta)


# =========================================================================
# Autenticação (sessão por cookie)
# =========================================================================

def _plano_ou_none(plano: str | None) -> str | None:
    return plano if plano in billing.PLANOS else None


@app.post("/auth/signup")
def auth_signup(req: SignupRequest):
    # Sem sessão aqui: o acesso começa só depois de confirmar o e-mail.
    res = auth.signup(req.empresa, req.email, req.senha, req.nome, _plano_ou_none(req.plano),
                      req.whatsapp)
    return {"verificacao_enviada": True, "email": res["user"]["email"]}


@app.post("/auth/verify-email")
def auth_verify_email(req: VerificarEmailRequest, response: Response):
    u = auth.verificar_email(req.token)
    auth.abrir_sessao(response, u["id"])
    return {"email": u["email"], "nome": u.get("nome"), "role": u["role"], "tenant_id": u["tenant_id"]}


@app.post("/auth/resend-verification")
def auth_resend_verification(req: ReenviarVerificacaoRequest):
    auth.reenviar_verificacao(req.email, _plano_ou_none(req.plano))
    return {"ok": True}


@app.post("/auth/whatsapp/send-code")
def auth_whatsapp_send_code(req: WhatsappCodigoRequest | None = None,
                            tenant: TenantCtx = Depends(current_tenant)):
    return auth.enviar_codigo_whatsapp(tenant, req.telefone if req else None)


@app.post("/auth/whatsapp/verify")
def auth_whatsapp_verify(req: WhatsappVerificarRequest,
                         tenant: TenantCtx = Depends(current_tenant)):
    return auth.confirmar_codigo_whatsapp(tenant, req.codigo)


@app.post("/auth/login")
def auth_login(req: LoginRequest, response: Response):
    u = auth.login(req.email, req.senha)
    auth.abrir_sessao(response, u["id"])
    return {"email": u["email"], "nome": u.get("nome"), "role": u["role"], "tenant_id": u["tenant_id"]}


@app.post("/auth/logout")
def auth_logout(request: Request, response: Response):
    auth.encerrar_sessao(request, response)
    return {"ok": True}


class TrocarSenhaReq(BaseModel):
    senha_atual: str
    senha_nova: str


@app.post("/auth/change-password")
def auth_change_password(req: TrocarSenhaReq, tenant: TenantCtx = Depends(current_tenant)):
    auth.trocar_senha(tenant.user_id, req.senha_atual, req.senha_nova)
    return {"ok": True}


@app.get("/auth/me")
def auth_me(tenant: TenantCtx = Depends(current_tenant)):
    t = store.get_tenant(tenant.tenant_id)
    return {
        "email": tenant.email,
        "nome": tenant.nome,
        "name": tenant.nome or tenant.email,   # compat com o whoami antigo
        "username": tenant.email,
        "role": tenant.role,
        "is_staff": tenant.is_staff,
        "whatsapp": tenant.whatsapp,
        # E-mail é sempre verificado aqui (sessão só existe após o link).
        "verificacoes": {"email": True, "whatsapp": tenant.whatsapp_verificado},
        "tenant": {"id": tenant.tenant_id, "nome": (t or {}).get("nome"), "slug": (t or {}).get("slug")},
        "assinatura": billing.status(tenant.tenant_id),
    }


# =========================================================================
# Billing (Stripe)
# =========================================================================

@app.get("/billing/plans")
def billing_plans():
    return billing.planos()


@app.get("/billing/status")
def billing_status(tenant: TenantCtx = Depends(current_tenant)):
    return billing.status(tenant.tenant_id)


@app.get("/billing/usage")
def billing_usage(tenant: TenantCtx = Depends(current_tenant)):
    """Consumo pay-per-use do mês (indexação + conversas)."""
    return billing.uso(tenant.tenant_id)


@app.post("/billing/checkout")
def billing_checkout(req: CheckoutRequest, tenant: TenantCtx = Depends(current_tenant)):
    if tenant.role != "owner":
        raise HTTPException(403, "apenas o responsável da conta pode assinar")
    if not tenant.whatsapp_verificado:
        raise HTTPException(403, "whatsapp_nao_verificado")
    return {"url": billing.criar_checkout(tenant, req.plano)}


@app.post("/billing/cancel")
def billing_cancel(req: CancelRequest | None = None,
                   tenant: TenantCtx = Depends(current_tenant)):
    if tenant.role != "owner":
        raise HTTPException(403, "apenas o responsável da conta pode cancelar")
    respostas = req.respostas if req else None
    comentario = req.comentario if req else None
    return billing.cancelar(tenant.tenant_id, respostas, comentario)


@app.post("/billing/reactivate")
def billing_reactivate(tenant: TenantCtx = Depends(current_tenant)):
    if tenant.role != "owner":
        raise HTTPException(403, "apenas o responsável da conta pode reativar")
    return billing.reativar(tenant.tenant_id)


@app.post("/billing/webhook")
async def billing_webhook(request: Request):
    # Corpo CRU é obrigatório p/ verificar a assinatura do Stripe.
    payload = await request.body()
    sig = request.headers.get("stripe-signature")
    return billing.processar_webhook(payload, sig)


# =========================================================================
# Suporte / Chamados (abertura + acompanhamento pelo cliente)
# Auth-only (sem exigir assinatura ativa): um cliente lapsado ainda precisa
# falar com o suporte (ex.: sobre cobrança).
# =========================================================================

_TICKET_CATEGORIAS = {"duvida", "problema_tecnico", "cobranca", "sugestao", "outro"}
_TICKET_PRIORIDADES = {"baixa", "normal", "alta"}


@app.get("/suporte/config")
def suporte_config(tenant: TenantCtx = Depends(current_tenant)):
    return {"email": settings.support_email}


@app.get("/suporte/chamados")
def suporte_listar(status: str | None = None,
                   tenant: TenantCtx = Depends(current_tenant)):
    return store.list_tickets(tenant.tenant_id, status)


@app.post("/suporte/chamados")
def suporte_criar(req: TicketCreate, tenant: TenantCtx = Depends(current_tenant)):
    assunto = req.assunto.strip()
    descricao = req.descricao.strip()
    if not assunto or not descricao:
        raise HTTPException(status_code=422, detail="informe assunto e descrição")
    if req.categoria not in _TICKET_CATEGORIAS:
        raise HTTPException(status_code=422, detail="categoria inválida")
    if req.prioridade not in _TICKET_PRIORIDADES:
        raise HTTPException(status_code=422, detail="prioridade inválida")
    t = store.create_ticket(
        tenant.tenant_id, tenant.user_id, assunto, req.categoria, req.prioridade, descricao
    )
    try:
        tn = (store.get_tenant(tenant.tenant_id) or {}).get("nome")
        mailer.notificar_novo_chamado(t, tn, tenant.email, descricao)
    except Exception:  # pragma: no cover
        pass
    return t


@app.get("/suporte/chamados/{ticket_id}")
def suporte_ver(ticket_id: int, tenant: TenantCtx = Depends(current_tenant)):
    t = store.get_ticket(tenant.tenant_id, ticket_id)
    if t is None:
        raise HTTPException(status_code=404, detail="chamado não encontrado")
    return t


@app.post("/suporte/chamados/{ticket_id}/mensagens")
def suporte_responder(ticket_id: int, req: TicketMensagem,
                      tenant: TenantCtx = Depends(current_tenant)):
    corpo = req.corpo.strip()
    if not corpo:
        raise HTTPException(status_code=422, detail="mensagem vazia")
    t = store.add_ticket_message(tenant.tenant_id, ticket_id, "cliente", corpo)
    if t is None:
        raise HTTPException(status_code=404, detail="chamado não encontrado")
    try:
        tn = (store.get_tenant(tenant.tenant_id) or {}).get("nome")
        mailer.notificar_nova_mensagem(ticket_id, t["assunto"], tn, tenant.email, corpo)
    except Exception:  # pragma: no cover
        pass
    return t


@app.patch("/suporte/chamados/{ticket_id}")
def suporte_status(ticket_id: int, req: TicketStatus,
                   tenant: TenantCtx = Depends(current_tenant)):
    # O cliente só pode fechar ou reabrir o próprio chamado.
    if req.status not in {"aberto", "fechado"}:
        raise HTTPException(status_code=422, detail="status inválido")
    t = store.set_ticket_status(tenant.tenant_id, ticket_id, req.status)
    if t is None:
        raise HTTPException(status_code=404, detail="chamado não encontrado")
    return t


# =========================================================================
# ADMIN (central da equipe Dew) — cross-tenant, protegido por current_admin.
# =========================================================================

_TICKET_STATUS = {"aberto", "em_andamento", "resolvido", "fechado"}
_SUB_STATUS = {"active", "trialing", "past_due", "unpaid", "canceled", "incomplete"}


@app.get("/admin/overview")
def admin_overview(admin: TenantCtx = Depends(current_admin)):
    return store.admin_overview()


@app.get("/admin/tenants")
def admin_tenants(q: str | None = None,
                  limit: int = Query(25, ge=1, le=100), offset: int = Query(0, ge=0),
                  admin: TenantCtx = Depends(current_admin)):
    return {"items": store.admin_list_tenants(q, limit, offset),
            "total": store.admin_count_tenants(q)}


@app.patch("/admin/tenants/{tenant_id}/assinatura")
def admin_set_sub(tenant_id: int, req: AdminSubReq,
                  admin: TenantCtx = Depends(current_admin)):
    if req.status not in _SUB_STATUS:
        raise HTTPException(status_code=422, detail="status inválido")
    if req.plan is not None and req.plan not in {"essencial", "profissional", "escala"}:
        raise HTTPException(status_code=422, detail="plano inválido")
    if not store.get_tenant(tenant_id):
        raise HTTPException(status_code=404, detail="tenant não encontrado")
    return store.admin_set_subscription(tenant_id, req.status, req.plan)


@app.get("/admin/planos")
def admin_planos(admin: TenantCtx = Depends(current_admin)):
    return billing.planos_admin()


@app.patch("/admin/planos/{plano}")
def admin_plano_preco(plano: str, req: AdminPlanoPrecoReq,
                      admin: TenantCtx = Depends(current_admin)):
    if plano not in billing.PLANOS:
        raise HTTPException(status_code=404, detail="plano não encontrado")
    if not (0 < req.preco <= 1_000_000):
        raise HTTPException(status_code=422, detail="preço inválido")
    return billing.alterar_preco(plano, req.preco, req.aplicar_existentes, admin.email)


@app.get("/admin/consumo")
def admin_consumo(q: str | None = None,
                  limit: int = Query(25, ge=1, le=100), offset: int = Query(0, ge=0),
                  admin: TenantCtx = Depends(current_admin)):
    return {"items": store.admin_usage_por_tenant(q, limit, offset),
            "totais": store.admin_usage_totais(q)}


@app.get("/admin/chamados")
def admin_chamados(status: str | None = None, prioridade: str | None = None,
                   q: str | None = None,
                   limit: int = Query(25, ge=1, le=100), offset: int = Query(0, ge=0),
                   admin: TenantCtx = Depends(current_admin)):
    return {"items": store.admin_list_tickets(status, prioridade, q, limit, offset),
            "total": store.admin_count_tickets(status, prioridade, q)}


@app.get("/admin/chamados/{ticket_id}")
def admin_chamado(ticket_id: int, admin: TenantCtx = Depends(current_admin)):
    t = store.admin_get_ticket(ticket_id)
    if t is None:
        raise HTTPException(status_code=404, detail="chamado não encontrado")
    return t


@app.post("/admin/chamados/{ticket_id}/mensagens")
def admin_responder(ticket_id: int, req: TicketMensagem,
                    admin: TenantCtx = Depends(current_admin)):
    corpo = req.corpo.strip()
    if not corpo:
        raise HTTPException(status_code=422, detail="mensagem vazia")
    t = store.admin_add_ticket_message(ticket_id, "suporte", corpo)
    if t is None:
        raise HTTPException(status_code=404, detail="chamado não encontrado")
    # Notifica o cliente por e-mail (best-effort).
    try:
        if t.get("cliente_email"):
            mailer.enviar(
                t["cliente_email"],
                f"[AtentBot] Resposta no seu chamado #{ticket_id} — {t['assunto']}",
                f"Você recebeu uma resposta da equipe de suporte:\n\n{corpo}\n\n"
                f"Acompanhe em {settings.panel_url.rstrip('/')}/suporte.",
            )
    except Exception:  # pragma: no cover
        pass
    return t


@app.patch("/admin/chamados/{ticket_id}")
def admin_ticket_update(ticket_id: int, req: AdminTicketReq,
                        admin: TenantCtx = Depends(current_admin)):
    if req.status is not None and req.status not in _TICKET_STATUS:
        raise HTTPException(status_code=422, detail="status inválido")
    if req.prioridade is not None and req.prioridade not in _TICKET_PRIORIDADES:
        raise HTTPException(status_code=422, detail="prioridade inválida")
    t = store.admin_set_ticket(ticket_id, req.status, req.prioridade)
    if t is None:
        raise HTTPException(status_code=404, detail="chamado não encontrado")
    return t


# =========================================================================
# Conversas (painel) — isoladas por tenant
# =========================================================================

@app.get("/conversas")
def conversas(
    status: str | None = None,
    q: str | None = None,
    limit: int = Query(100, ge=1, le=500),
    tenant: TenantCtx = Depends(require_active_subscription),
):
    return store.list_conversations(tenant.tenant_id, status, q, limit)


@app.get("/conversas/{thread_id}")
def conversa(thread_id: str, tenant: TenantCtx = Depends(require_active_subscription)):
    c = store.get_conversation(tenant.tenant_id, thread_id)
    if c is None:
        raise HTTPException(status_code=404, detail="conversa não encontrada")
    return c


@app.post("/conversas/{thread_id}/assumir")
def assumir(thread_id: str, tenant: TenantCtx = Depends(require_active_subscription)):
    c = store.assumir_conversation(tenant.tenant_id, thread_id)
    if c is None:
        raise HTTPException(status_code=404, detail="conversa não encontrada")
    return c


@app.post("/conversas/{thread_id}/resolver")
def resolver(thread_id: str, tenant: TenantCtx = Depends(require_active_subscription)):
    c = store.resolver_conversation(tenant.tenant_id, thread_id)
    if c is None:
        raise HTTPException(status_code=404, detail="conversa não encontrada")
    return c


@app.post("/conversas/{thread_id}/reabrir")
def reabrir(thread_id: str, tenant: TenantCtx = Depends(require_active_subscription)):
    c = store.reabrir_conversation(tenant.tenant_id, thread_id)
    if c is None:
        raise HTTPException(status_code=404, detail="conversa não encontrada")
    return c


@app.post("/conversas/{thread_id}/bot")
def bot(thread_id: str, req: BotRequest, tenant: TenantCtx = Depends(require_active_subscription)):
    """Liga/desliga a resposta automática da IA nesta conversa (toggle do painel)."""
    c = store.set_bot(tenant.tenant_id, thread_id, req.ativo)
    if c is None:
        raise HTTPException(status_code=404, detail="conversa não encontrada")
    return c


@app.post("/conversas/{thread_id}/ler")
def marcar_lida(thread_id: str, tenant: TenantCtx = Depends(require_active_subscription)):
    """Zera o contador de não-lidas (quando o atendente abre a conversa)."""
    c = store.marcar_lida(tenant.tenant_id, thread_id)
    if c is None:
        raise HTTPException(status_code=404, detail="conversa não encontrada")
    return c


@app.get("/conversas/{thread_id}/stream")
async def stream(thread_id: str, request: Request,
                 tenant: TenantCtx = Depends(require_active_subscription)):
    """Push em tempo real (SSE) por conversa. Canal namespaced por tenant."""
    canal = f"{tenant.tenant_id}:{thread_id}"

    async def gen():
        q = await realtime.broker.subscribe(canal)
        try:
            yield ": ok\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    data = await asyncio.wait_for(q.get(), timeout=20)
                    yield f"data: {json.dumps(data)}\n\n"
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
        finally:
            realtime.broker.unsubscribe(canal, q)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/conversas/{thread_id}/nota")
def add_nota(thread_id: str, req: NotaRequest,
             tenant: TenantCtx = Depends(require_active_subscription)):
    if store.get_conversation(tenant.tenant_id, thread_id) is None:
        raise HTTPException(status_code=404, detail="conversa não encontrada")
    texto = req.texto.strip()
    if not texto:
        raise HTTPException(status_code=422, detail="texto vazio")
    store.add_note(tenant.tenant_id, thread_id, texto, req.autor)
    return store.get_conversation(tenant.tenant_id, thread_id)


@app.post("/conversas/{thread_id}/atribuir")
def atribuir(thread_id: str, req: AtribuirRequest,
             tenant: TenantCtx = Depends(require_active_subscription)):
    c = store.set_responsavel(tenant.tenant_id, thread_id, req.responsavel)
    if c is None:
        raise HTTPException(status_code=404, detail="conversa não encontrada")
    return c


@app.post("/conversas/{thread_id}/responder")
def responder_conversa(thread_id: str, req: ResponderRequest,
                       tenant: TenantCtx = Depends(require_active_subscription)):
    """Envia uma resposta HUMANA ao cliente pelo WhatsApp (Evolution) e registra."""
    texto = req.texto.strip()
    if not texto:
        raise HTTPException(status_code=422, detail="texto vazio")
    conv = store.get_conversation(tenant.tenant_id, thread_id)
    if conv is None:
        raise HTTPException(status_code=404, detail="conversa não encontrada")
    try:
        evolution.enviar_texto(thread_id, texto, instancia=conv.get("instancia"))
    except evolution.EvolutionError as e:
        raise HTTPException(status_code=503, detail=str(e))
    store.add_message(tenant.tenant_id, thread_id, "humano", texto)
    store.set_status(tenant.tenant_id, thread_id, "humano")
    return store.get_conversation(tenant.tenant_id, thread_id)


# =========================================================================
# Clientes (painel)
# =========================================================================

@app.get("/clientes")
def clientes(status: str | None = None, limit: int = Query(200, ge=1, le=1000),
             tenant: TenantCtx = Depends(require_active_subscription)):
    return store.list_customers(tenant.tenant_id, status, limit)


@app.get("/clientes/{telefone}")
def cliente(telefone: str, tenant: TenantCtx = Depends(require_active_subscription)):
    c = store.get_customer(tenant.tenant_id, telefone)
    if c is None:
        raise HTTPException(status_code=404, detail="cliente não encontrado")
    return c


# =========================================================================
# Equipe de vendas (painel)
# =========================================================================

@app.get("/vendedores")
def vendedores(ativo: bool | None = None,
               tenant: TenantCtx = Depends(require_active_subscription)):
    return store.list_sellers(tenant.tenant_id, only_ativo=bool(ativo))


@app.post("/vendedores")
def vendedor_criar(req: VendedorCreate,
                   tenant: TenantCtx = Depends(require_active_subscription)):
    nome = req.nome.strip()
    telefone = "".join(ch for ch in req.telefone if ch.isdigit())
    if not nome:
        raise HTTPException(status_code=422, detail="informe o nome do vendedor")
    if len(telefone) < 10:
        raise HTTPException(status_code=422, detail="WhatsApp inválido (use DDD + número)")
    return store.create_seller(tenant.tenant_id, nome, telefone, req.email, req.ativo)


@app.patch("/vendedores/{seller_id}")
def vendedor_atualizar(seller_id: int, req: VendedorUpdate,
                       tenant: TenantCtx = Depends(require_active_subscription)):
    telefone = req.telefone
    if telefone is not None:
        telefone = "".join(ch for ch in telefone if ch.isdigit())
        if len(telefone) < 10:
            raise HTTPException(status_code=422, detail="WhatsApp inválido (use DDD + número)")
    v = store.update_seller(tenant.tenant_id, seller_id, req.nome, telefone, req.email, req.ativo)
    if v is None:
        raise HTTPException(status_code=404, detail="vendedor não encontrado")
    return v


@app.delete("/vendedores/{seller_id}")
def vendedor_remover(seller_id: int,
                     tenant: TenantCtx = Depends(require_active_subscription)):
    if not store.delete_seller(tenant.tenant_id, seller_id):
        raise HTTPException(status_code=404, detail="vendedor não encontrado")
    return {"removido": seller_id}


# =========================================================================
# WhatsApp: conexões (proxy da Evolution) — registra o mapa instância->tenant
# =========================================================================

_INSTANCIA_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{1,39}$")


def _normalizar_instancia(nome: str) -> str:
    slug = re.sub(r"[^a-z0-9_-]", "-", (nome or "").strip().lower()).strip("-")
    slug = re.sub(r"-{2,}", "-", slug)
    if not _INSTANCIA_RE.match(slug):
        raise HTTPException(
            status_code=422,
            detail="nome inválido: use 2 a 40 caracteres (letras, números, - ou _)",
        )
    return slug


def _evolution_guard():
    if not settings.evolution_configured:
        raise HTTPException(status_code=503, detail="Evolution API não configurada")


def _evolution_call(fn, *args):
    _evolution_guard()
    try:
        return fn(*args)
    except evolution.EvolutionError as e:
        raise HTTPException(status_code=502, detail=str(e))


@app.get("/whatsapp/config")
def whatsapp_config(tenant: TenantCtx = Depends(require_active_subscription)):
    return {
        "configurado": settings.evolution_configured,
        "webhook_automatico": bool(settings.evolution_webhook_url),
        "instancia_padrao": settings.evolution_instance,
    }


@app.get("/whatsapp/instancias")
def whatsapp_instancias(tenant: TenantCtx = Depends(require_active_subscription)):
    # A Evolution é compartilhada: cada tenant só vê as instâncias mapeadas a ele.
    minhas = set(store.list_instances(tenant.tenant_id))
    return [i for i in _evolution_call(evolution.listar_instancias) if i.get("nome") in minhas]


@app.post("/whatsapp/instancias")
def whatsapp_criar(req: InstanciaCreate,
                   tenant: TenantCtx = Depends(require_active_subscription)):
    """Cria uma instância, mapeia ao tenant e devolve o QR Code inicial."""
    nome = _normalizar_instancia(req.nome)
    outro = store.get_tenant_by_instancia(nome)
    if nome == auth.instancia_verificacao() or (outro is not None and outro != tenant.tenant_id):
        raise HTTPException(status_code=409, detail="este número já pertence a outra conta")
    qr = _evolution_call(evolution.criar_instancia, nome)
    store.register_instance(tenant.tenant_id, nome)
    return {"nome": nome, "qrcode": qr}


@app.get("/whatsapp/instancias/{nome}/qrcode")
def whatsapp_qrcode(nome: str, tenant: TenantCtx = Depends(require_active_subscription)):
    _guard_instancia_do_tenant(tenant.tenant_id, nome)
    return {"nome": nome, "qrcode": _evolution_call(evolution.conectar_instancia, nome)}


@app.get("/whatsapp/instancias/{nome}/status")
def whatsapp_status(nome: str, tenant: TenantCtx = Depends(require_active_subscription)):
    _guard_instancia_do_tenant(tenant.tenant_id, nome)
    return _evolution_call(evolution.status_instancia, nome)


@app.post("/whatsapp/instancias/{nome}/desconectar")
def whatsapp_desconectar(nome: str, tenant: TenantCtx = Depends(require_active_subscription)):
    _guard_instancia_do_tenant(tenant.tenant_id, nome)
    _evolution_call(evolution.desconectar_instancia, nome)
    return {"nome": nome, "estado": "desconectado"}


@app.delete("/whatsapp/instancias/{nome}")
def whatsapp_remover(nome: str, tenant: TenantCtx = Depends(require_active_subscription)):
    _guard_instancia_do_tenant(tenant.tenant_id, nome)
    _evolution_call(evolution.remover_instancia, nome)
    store.unregister_instance(tenant.tenant_id, nome)
    return {"removido": nome}


def _guard_instancia_do_tenant(tenant_id: int, nome: str) -> None:
    """Só o tenant dono opera a instância. Instâncias sem dono (de outros projetos
    na mesma Evolution) e a da plataforma ficam inacessíveis."""
    if nome == auth.instancia_verificacao() or store.get_tenant_by_instancia(nome) != tenant_id:
        raise HTTPException(status_code=404, detail="instância não encontrada")


# =========================================================================
# ADMIN — WhatsApp de verificação (número DA PLATAFORMA que envia os códigos
# do cadastro). Sincronizado por QR Code na central admin; sem webhook.
# =========================================================================

class TesteWhatsappReq(BaseModel):
    telefone: str


def _instancia_plataforma_ou_404() -> str:
    nome = auth.instancia_verificacao()
    if not nome:
        raise HTTPException(404, "nenhum número de verificação configurado")
    return nome


@app.get("/admin/whatsapp-verificacao")
def admin_wa_verif(admin: TenantCtx = Depends(current_admin)):
    do_painel = store.get_platform_setting(auth.CHAVE_INSTANCIA_VERIFICACAO)
    nome = auth.instancia_verificacao()
    out = {
        "evolution_configurada": settings.evolution_configured,
        "instancia": nome or None,
        "origem": "painel" if do_painel else ("ambiente" if nome else None),
        "estado": None, "numero": None, "perfil": None, "erro": None,
    }
    if nome and settings.evolution_configured:
        try:
            st = evolution.status_instancia(nome)
            out.update(estado=st.get("estado"), numero=st.get("numero"), perfil=st.get("perfil"))
        except evolution.EvolutionError as e:
            out["erro"] = str(e)
    return out


@app.post("/admin/whatsapp-verificacao")
def admin_wa_verif_criar(req: InstanciaCreate, admin: TenantCtx = Depends(current_admin)):
    """Cria (ou reaproveita) a instância da plataforma e devolve o QR Code."""
    _evolution_guard()
    nome = _normalizar_instancia(req.nome)
    if store.get_tenant_by_instancia(nome) is not None:
        raise HTTPException(409, "esta instância pertence a um cliente; use outro nome")
    try:
        qr = evolution.criar_instancia(nome, webhook=False)
    except evolution.EvolutionError:
        # Já existe na Evolution (ex.: reconfiguração): só pede um QR novo.
        qr = _evolution_call(evolution.conectar_instancia, nome)
    store.set_platform_setting(auth.CHAVE_INSTANCIA_VERIFICACAO, nome, admin.user_id)
    return {"nome": nome, "qrcode": qr}


@app.get("/admin/whatsapp-verificacao/qrcode")
def admin_wa_verif_qrcode(admin: TenantCtx = Depends(current_admin)):
    nome = _instancia_plataforma_ou_404()
    return {"nome": nome, "qrcode": _evolution_call(evolution.conectar_instancia, nome)}


@app.get("/admin/whatsapp-verificacao/status")
def admin_wa_verif_status(admin: TenantCtx = Depends(current_admin)):
    return _evolution_call(evolution.status_instancia, _instancia_plataforma_ou_404())


@app.post("/admin/whatsapp-verificacao/teste")
def admin_wa_verif_teste(req: TesteWhatsappReq, admin: TenantCtx = Depends(current_admin)):
    """Envia uma mensagem de teste pelo número de verificação."""
    nome = _instancia_plataforma_ou_404()
    numero = auth.normalizar_whatsapp(req.telefone)
    if not numero:
        raise HTTPException(400, "informe um WhatsApp válido com DDD")
    _evolution_call(evolution.enviar_texto, numero,
                    "AtentBot: teste do número de verificação. Está funcionando!", nome)
    return {"enviado": True, "whatsapp": numero}


@app.post("/admin/whatsapp-verificacao/desconectar")
def admin_wa_verif_desconectar(admin: TenantCtx = Depends(current_admin)):
    nome = _instancia_plataforma_ou_404()
    _evolution_call(evolution.desconectar_instancia, nome)
    return {"nome": nome, "estado": "desconectado"}


@app.delete("/admin/whatsapp-verificacao")
def admin_wa_verif_remover(admin: TenantCtx = Depends(current_admin)):
    """Remove a instância da Evolution e limpa a configuração do painel."""
    nome = store.get_platform_setting(auth.CHAVE_INSTANCIA_VERIFICACAO)
    if not nome:
        raise HTTPException(409, "o número atual vem da variável de ambiente; remova-a no servidor")
    _evolution_guard()
    try:
        evolution.remover_instancia(nome)
    except evolution.EvolutionError as e:  # já removida na Evolution: segue limpando
        logging.getLogger("atentbot").warning("remoção da instância %s falhou: %s", nome, e)
    store.set_platform_setting(auth.CHAVE_INSTANCIA_VERIFICACAO, None, admin.user_id)
    return {"removido": nome}


# =========================================================================
# Agentes (multi-agente por número) — por tenant
# =========================================================================

def _validar_capacidades(caps: list[str]) -> list[str]:
    invalidas = [c for c in caps if c not in CAPACIDADES]
    if invalidas:
        raise HTTPException(status_code=422, detail=f"capacidade(s) inválida(s): {invalidas}")
    return [c for c in CAPACIDADES_ORDEM if c in set(caps)]


@app.get("/agentes/capacidades")
def agentes_capacidades(tenant: TenantCtx = Depends(require_active_subscription)):
    return [{"chave": c, "label": CAPACIDADES[c]["label"]} for c in CAPACIDADES_ORDEM]


@app.get("/agentes")
def agentes(tenant: TenantCtx = Depends(require_active_subscription)):
    return store.list_agents(tenant.tenant_id)


@app.post("/agentes")
def agente_criar(req: AgenteCreate,
                 tenant: TenantCtx = Depends(require_active_subscription)):
    nome = (req.nome or "").strip()
    if not nome:
        raise HTTPException(status_code=422, detail="informe o nome do agente")
    caps = _validar_capacidades(req.capacidades)
    inst = (req.instancia or "").strip() or None
    if inst:
        dono = store.get_tenant_by_instancia(inst)
        if dono is not None and dono != tenant.tenant_id:
            raise HTTPException(status_code=409, detail="este número pertence a outra conta")
        if store.get_agent_by_instancia(inst):
            raise HTTPException(status_code=409, detail="este número já está atribuído a outro agente")
    try:
        agente = store.create_agent(tenant.tenant_id, nome, req.descricao, inst,
                                    req.persona, caps, req.ativo, req.hiperpersonalizacao)
    except Exception as e:
        if "idx_agents_instancia" in str(e):
            raise HTTPException(status_code=409, detail="este número já está atribuído a outro agente")
        raise
    if inst:
        store.register_instance(tenant.tenant_id, inst)
    return agente


@app.patch("/agentes/{agent_id}")
def agente_atualizar(agent_id: int, req: AgenteUpdate,
                     tenant: TenantCtx = Depends(require_active_subscription)):
    atual = store.get_agent(tenant.tenant_id, agent_id)
    if atual is None:
        raise HTTPException(status_code=404, detail="agente não encontrado")
    caps = _validar_capacidades(req.capacidades) if req.capacidades is not None else None
    limpar = req.instancia is not None and (req.instancia or "").strip() == ""
    inst = (req.instancia or "").strip() or None
    if atual.get("is_default"):
        inst = None
        limpar = False
    if inst:
        dono = store.get_tenant_by_instancia(inst)
        if dono is not None and dono != tenant.tenant_id:
            raise HTTPException(status_code=409, detail="este número pertence a outra conta")
        outro = store.get_agent_by_instancia(inst)
        if outro and outro["id"] != agent_id:
            raise HTTPException(status_code=409, detail="este número já está atribuído a outro agente")
    try:
        v = store.update_agent(
            tenant.tenant_id, agent_id,
            nome=(req.nome.strip() if req.nome else None),
            descricao=req.descricao,
            instancia=inst,
            persona=req.persona,
            capacidades=caps,
            ativo=req.ativo,
            hiperpersonalizacao=req.hiperpersonalizacao,
            limpar_instancia=limpar,
        )
    except Exception as e:
        if "idx_agents_instancia" in str(e):
            raise HTTPException(status_code=409, detail="este número já está atribuído a outro agente")
        raise
    if v is None:
        raise HTTPException(status_code=404, detail="agente não encontrado")
    if inst:
        store.register_instance(tenant.tenant_id, inst)
    return v


@app.delete("/agentes/{agent_id}")
def agente_remover(agent_id: int,
                   tenant: TenantCtx = Depends(require_active_subscription)):
    atual = store.get_agent(tenant.tenant_id, agent_id)
    if atual is None:
        raise HTTPException(status_code=404, detail="agente não encontrado")
    if atual.get("is_default"):
        raise HTTPException(status_code=400, detail="o agente padrão não pode ser removido")
    if not store.delete_agent(tenant.tenant_id, agent_id):
        raise HTTPException(status_code=404, detail="agente não encontrado")
    return {"removido": agent_id}


# =========================================================================
# Fila humana (painel)
# =========================================================================

@app.get("/fila")
def fila(tipo: str | None = None, status: str | None = None,
         tenant: TenantCtx = Depends(require_active_subscription)):
    return store.list_queue(tenant.tenant_id, tipo, status)


@app.patch("/fila/{item_id}")
def fila_update(item_id: int, upd: QueueUpdate,
                tenant: TenantCtx = Depends(require_active_subscription)):
    item = store.update_queue_item(tenant.tenant_id, item_id, upd.status, upd.responsavel)
    if item is None:
        raise HTTPException(status_code=404, detail="item não encontrado")
    return item


# =========================================================================
# Métricas (dashboard)
# =========================================================================

@app.get("/metrics/overview")
def metrics_overview(tenant: TenantCtx = Depends(require_active_subscription)):
    return store.metrics_overview(tenant.tenant_id)


@app.get("/metrics/unread")
def metrics_unread(tenant: TenantCtx = Depends(require_active_subscription)):
    return {"total": store.unread_total(tenant.tenant_id)}


# =========================================================================
# Exportações CSV
# =========================================================================

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
def clientes_csv(status: str | None = None,
                 tenant: TenantCtx = Depends(require_active_subscription)):
    cols = ["telefone", "razao_social", "cnpj", "email", "nome_contato", "status", "created_at"]
    return _csv("clientes.csv", cols, store.list_customers(tenant.tenant_id, status, 100000))


@app.get("/fila.csv")
def fila_csv(tipo: str | None = None, status: str | None = None,
             tenant: TenantCtx = Depends(require_active_subscription)):
    cols = ["id", "tipo", "status", "cliente", "telefone", "resumo", "responsavel", "created_at"]
    return _csv("fila.csv", cols, store.list_queue(tenant.tenant_id, tipo, status))


# =========================================================================
# Relatórios
# =========================================================================

@app.get("/relatorios/resumo")
def relatorios_resumo(desde: str, ate: str,
                      tenant: TenantCtx = Depends(require_active_subscription)):
    return store.relatorio_resumo(tenant.tenant_id, desde, ate)


@app.get("/relatorios/conversas.csv")
def relatorios_conversas_csv(desde: str, ate: str,
                             tenant: TenantCtx = Depends(require_active_subscription)):
    cols = ["thread_id", "cliente", "telefone", "status", "especialista",
            "responsavel", "created_at", "updated_at"]
    return _csv(f"relatorio-conversas-{desde}_a_{ate}.csv", cols,
                store.relatorio_conversas(tenant.tenant_id, desde, ate))


# =========================================================================
# RAG / base de conhecimento
# =========================================================================

@app.get("/rag/status")
def rag_status(tenant: TenantCtx = Depends(require_active_subscription)):
    from . import rag
    return rag.status(tenant.tenant_id)


@app.post("/rag/ingest")
def rag_ingest(tenant: TenantCtx = Depends(require_active_subscription)):
    from . import rag
    if not settings.rag_enabled:
        raise HTTPException(status_code=503, detail="RAG não configurado (VECTOR_HOST)")
    try:
        return rag.ingest_catalogo(tenant.tenant_id)
    except Exception as e:  # pragma: no cover
        raise HTTPException(status_code=500, detail=f"falha no ingest: {e}")


@app.post("/rag/upload")
async def rag_upload(file: UploadFile = File(...),
                     tenant: TenantCtx = Depends(require_active_subscription)):
    from . import rag
    if not settings.rag_enabled:
        raise HTTPException(status_code=503, detail="RAG não configurado (VECTOR_HOST)")
    data = await file.read()
    if not data:
        raise HTTPException(status_code=422, detail="arquivo vazio")
    try:
        return rag.ingest_documento(tenant.tenant_id, file.filename or "documento",
                                    data, file.content_type)
    except Exception as e:  # pragma: no cover
        raise HTTPException(status_code=500, detail=f"falha no upload: {e}")


@app.get("/rag/fontes")
def rag_fontes(tenant: TenantCtx = Depends(require_active_subscription)):
    from . import rag
    if not settings.rag_enabled:
        return []
    return rag.listar_fontes(tenant.tenant_id)


@app.delete("/rag/fontes/{source}")
def rag_remover_fonte(source: str,
                      tenant: TenantCtx = Depends(require_active_subscription)):
    from . import rag
    removidos = rag.remover_fonte(tenant.tenant_id, source)
    return {"fonte": source, "removidos": removidos}


# =========================================================================
# Orçamentos (comercial)
# =========================================================================

@app.get("/orcamentos")
def orcamentos(status: str | None = None,
               tenant: TenantCtx = Depends(require_active_subscription)):
    return store.list_queue(tenant.tenant_id, "pedido", status)


# =========================================================================
# Broadcast (envio em massa)
# =========================================================================

def _run_broadcast(
    tenant_id: int, bid: int, texto: str, dests: list[dict], midia: dict | None = None
) -> None:
    for c in dests:
        try:
            if midia:
                evolution.enviar_midia(
                    c["telefone"], midia["b64"],
                    mimetype=midia["mimetype"], filename=midia["filename"], caption=texto,
                )
            else:
                evolution.enviar_texto(c["telefone"], texto)
            store.bump_broadcast(tenant_id, bid, enviados=1)
        except Exception as e:  # pragma: no cover
            logging.getLogger("atentbot").warning("broadcast %s falhou p/ %s: %s",
                                                   bid, c.get("telefone"), e)
            store.bump_broadcast(tenant_id, bid, falhas=1)
        time.sleep(settings.broadcast_throttle_seconds)
    store.finish_broadcast(tenant_id, bid, "concluido")


@app.post("/broadcast/upload")
async def broadcast_upload(file: UploadFile = File(...),
                           tenant: TenantCtx = Depends(require_active_subscription)):
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
def broadcast(req: BroadcastRequest, bg: BackgroundTasks,
              tenant: TenantCtx = Depends(require_active_subscription)):
    texto = req.texto.strip()
    if not texto and not req.imagem:
        raise HTTPException(status_code=422, detail="informe um texto ou uma imagem")
    if not settings.evolution_configured:
        raise HTTPException(status_code=503, detail="Evolution API não configurada")

    if req.telefones:
        dests = store.customers_por_telefones(tenant.tenant_id, req.telefones)
        if not dests:
            raise HTTPException(status_code=422, detail="nenhum cliente elegível selecionado")
    else:
        dests = store.customers_para_broadcast(tenant.tenant_id, req.segmento)
        if not dests:
            raise HTTPException(status_code=422, detail="nenhum cliente elegível neste segmento")

    midia: dict | None = None
    imagem_ref: str | None = None
    if req.imagem:
        arquivo = req.imagem.rsplit("/", 1)[-1]
        caminho = _media_file(arquivo)
        if not caminho.exists():
            raise HTTPException(status_code=422, detail="imagem não encontrada; reenvie o banner")
        mimetype = next((m for m, ext in _IMAGE_MIMES.items() if ext == caminho.suffix), "image/jpeg")
        midia = {
            "b64": base64.b64encode(caminho.read_bytes()).decode("ascii"),
            "mimetype": mimetype,
            "filename": arquivo,
        }
        imagem_ref = f"/media/{arquivo}"

    bid = store.create_broadcast(tenant.tenant_id, texto, len(dests), req.criado_por, imagem_ref)
    bg.add_task(_run_broadcast, tenant.tenant_id, bid, texto, dests, midia)
    return {"id": bid, "total": len(dests), "status": "enviando"}


@app.get("/broadcasts")
def broadcasts(tenant: TenantCtx = Depends(require_active_subscription)):
    return store.list_broadcasts(tenant.tenant_id)


@app.get("/broadcast/segmentos")
def broadcast_segmentos(tenant: TenantCtx = Depends(require_active_subscription)):
    return store.contar_segmentos(tenant.tenant_id)


# =========================================================================
# Catálogo (painel)
# =========================================================================

@app.get("/catalog/stats")
def catalog_stats(tenant: TenantCtx = Depends(require_active_subscription)):
    return catalog.contar_totais(tenant.tenant_id)


@app.get("/catalog/categorias")
def catalog_categorias(tenant: TenantCtx = Depends(require_active_subscription)):
    return catalog.listar_categorias(tenant.tenant_id)


@app.get("/catalog/produtos")
def catalog_produtos(
    q: str | None = None,
    categoria: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    tenant: TenantCtx = Depends(require_active_subscription),
):
    return catalog.listar_produtos(tenant.tenant_id, q, categoria, limit, offset)


@app.get("/catalog/produtos/{identificador}")
def catalog_produto(identificador: str,
                    tenant: TenantCtx = Depends(require_active_subscription)):
    p = catalog.detalhes_produto(tenant.tenant_id, identificador)
    if p is None:
        raise HTTPException(status_code=404, detail="produto não encontrado")
    return p


# --- Importação self-serve do catálogo (CSV) -------------------------------

@app.get("/catalog/modelo.csv")
def catalog_modelo(tenant: TenantCtx = Depends(current_tenant)):
    """Baixa o CSV de exemplo (template) para o cliente preencher."""
    return Response(
        content=ingest.modelo_csv(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="modelo-catalogo.csv"'},
    )


@app.post("/catalog/import")
async def catalog_import(file: UploadFile = File(...),
                         tenant: TenantCtx = Depends(require_active_subscription)):
    """Importa/atualiza o catálogo do tenant a partir de um CSV."""
    data = await file.read()
    if not data:
        raise HTTPException(status_code=422, detail="arquivo vazio")
    try:
        produtos = ingest.parse_csv(data)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    try:
        return ingest.importar(tenant.tenant_id, produtos)
    except Exception as e:  # pragma: no cover
        raise HTTPException(status_code=500, detail=f"falha ao importar: {e}")


@app.delete("/catalog")
def catalog_limpar(tenant: TenantCtx = Depends(require_active_subscription)):
    """Apaga TODO o catálogo do tenant (produtos, variantes e categorias)."""
    if tenant.role != "owner":
        raise HTTPException(403, "apenas o responsável da conta pode limpar o catálogo")
    return ingest.limpar(tenant.tenant_id)
