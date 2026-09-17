"""API pública REST (integrações) — chaves por tenant com escopos.

Dois routers:
- `router_v1` (`/v1/*`): a API consumida por sistemas externos (ERP, CRM, BI…).
  Autentica por chave (`Authorization: Bearer atb_...` ou `X-API-Key`). Cada
  chave pertence a UM tenant e só enxerga os dados dele; cada endpoint exige um
  escopo (permissão por feature).
- `router_gestao` (`/integracoes/*` e `/admin/integracoes/*`): o painel cria,
  edita, rotaciona e revoga chaves e consulta o log de auditoria.

Camadas de segurança aplicadas a toda chamada /v1 (ver `_autenticar`):
chave com hash SHA-256 (texto puro exibido uma única vez) → revogação/validade →
tenant ativo → allowlist de IP/CIDR → rate limit por chave → escopo → assinatura
ativa. Toda chamada identificada fica no `api_request_log` (auditoria).
"""
from __future__ import annotations

import hashlib
import ipaddress
import secrets
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from . import billing, catalog, evolution, store
from .auth import TenantCtx, current_admin, current_tenant
from .settings import settings
from .validators import cnpj_valido, email_valido, so_digitos

KEY_PREFIX = "atb_live_"

# Escopos = permissões por feature. `grupo` organiza a tela; `escrita` marca
# escopos que alteram dados ou disparam ações (destacados no painel).
ESCOPOS: dict[str, dict] = {
    "catalogo:ler":     {"grupo": "Catálogo", "label": "Consultar catálogo", "escrita": False,
                         "descricao": "Produtos, variantes e categorias."},
    "clientes:ler":     {"grupo": "Clientes", "label": "Consultar clientes", "escrita": False,
                         "descricao": "Cadastros feitos via WhatsApp."},
    "clientes:escrever": {"grupo": "Clientes", "label": "Criar/atualizar clientes", "escrita": True,
                          "descricao": "Sincroniza cadastros vindos do seu ERP/CRM."},
    "conversas:ler":    {"grupo": "Atendimento", "label": "Consultar conversas", "escrita": False,
                         "descricao": "Conversas e histórico de mensagens."},
    "mensagens:enviar": {"grupo": "Atendimento", "label": "Enviar mensagens", "escrita": True,
                         "descricao": "Envia mensagem no WhatsApp numa conversa existente."},
    "fila:ler":         {"grupo": "Fila e orçamentos", "label": "Consultar fila humana", "escrita": False,
                         "descricao": "Pedidos, entregas e boletos aguardando a equipe."},
    "fila:escrever":    {"grupo": "Fila e orçamentos", "label": "Atualizar fila", "escrita": True,
                         "descricao": "Muda status/responsável de itens da fila."},
    "orcamentos:ler":   {"grupo": "Fila e orçamentos", "label": "Consultar orçamentos", "escrita": False,
                         "descricao": "Pedidos de orçamento registrados pelo agente."},
    "metricas:ler":     {"grupo": "Métricas", "label": "Métricas e relatórios", "escrita": False,
                         "descricao": "Indicadores do dashboard e resumo por período."},
}

_FILA_STATUS = {"novo", "andamento", "concluido"}
_FILA_TIPOS = {"pedido", "entrega", "boleto"}


# =========================================================================
# Chaves
# =========================================================================

def gerar_chave() -> tuple[str, str, str]:
    """Nova chave → (texto_puro, prefixo_visível, sha256)."""
    chave = KEY_PREFIX + secrets.token_urlsafe(32)
    return chave, chave[: len(KEY_PREFIX) + 6], hash_chave(chave)


def hash_chave(chave: str) -> str:
    return hashlib.sha256(chave.encode("utf-8")).hexdigest()


def normalizar_ips(ips: list[str] | None) -> list[str]:
    """Valida IPs/CIDRs da allowlist (422 se inválido). Vazio = qualquer IP."""
    out: list[str] = []
    for bruto in ips or []:
        v = (bruto or "").strip()
        if not v:
            continue
        try:
            out.append(str(ipaddress.ip_network(v, strict=False)))
        except ValueError:
            raise HTTPException(422, f"IP/CIDR inválido: {v}")
    return sorted(set(out))


def ip_permitido(ip: str | None, permitidos: list[str]) -> bool:
    if not permitidos:
        return True
    if not ip:
        return False
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return any(addr in ipaddress.ip_network(n, strict=False) for n in permitidos)


def ip_cliente(request: Request) -> str | None:
    """IP de origem. Em produção a cadeia é Traefik → Next → agent; o Traefik
    (sem forwardedHeaders.insecure) sobrescreve o X-Forwarded-For recebido,
    então o 1º item é o cliente real."""
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else None


def _extrair_chave(request: Request) -> str | None:
    authz = request.headers.get("authorization") or ""
    if authz.lower().startswith("bearer "):
        return authz[7:].strip() or None
    return (request.headers.get("x-api-key") or "").strip() or None


# --- Rate limit (janela deslizante de 60s por chave, em memória) -----------
# O serviço roda com 1 réplica; com várias réplicas, mover p/ Redis.

class _RateLimiter:
    def __init__(self) -> None:
        self._hits: dict[int, deque] = {}
        self._lock = threading.Lock()

    def consumir(self, key_id: int, limite: int) -> tuple[bool, int, int]:
        """→ (permitido, restantes, segundos_até_liberar)."""
        agora = time.monotonic()
        with self._lock:
            q = self._hits.setdefault(key_id, deque())
            while q and agora - q[0] >= 60:
                q.popleft()
            if len(q) >= limite:
                return False, 0, max(1, int(60 - (agora - q[0])) + 1)
            q.append(agora)
            return True, limite - len(q), 0

    def limpar(self) -> None:
        with self._lock:
            self._hits.clear()


rate_limiter = _RateLimiter()
_ultimo_touch: dict[int, float] = {}


@dataclass
class ApiCtx:
    tenant_id: int
    key_id: int
    nome: str
    prefixo: str
    escopos: list[str] = field(default_factory=list)
    rate_limit_min: int = 60


def _autenticar(request: Request) -> ApiCtx:
    chave = _extrair_chave(request)
    if not chave:
        raise HTTPException(401, "informe a chave em 'Authorization: Bearer <chave>'",
                            headers={"WWW-Authenticate": "Bearer"})
    k = store.get_api_key_by_hash(hash_chave(chave))
    if not k:
        raise HTTPException(401, "chave de API inválida", headers={"WWW-Authenticate": "Bearer"})

    ctx = ApiCtx(tenant_id=int(k["tenant_id"]), key_id=int(k["id"]), nome=k["nome"],
                 prefixo=k["prefixo"], escopos=list(k["escopos"] or []),
                 rate_limit_min=int(k["rate_limit_min"]))
    # A partir daqui a chamada é atribuível a um tenant → entra na auditoria.
    request.state.api_ctx = ctx

    if k.get("revoked_at"):
        raise HTTPException(401, "chave de API revogada")
    if k.get("expires_at") and k["expires_at"] <= datetime.now(timezone.utc):
        raise HTTPException(401, "chave de API expirada")
    if (k.get("tenant_status") or "ativa") != "ativa":
        raise HTTPException(403, "conta suspensa")

    ip = ip_cliente(request)
    if not ip_permitido(ip, list(k.get("ips_permitidos") or [])):
        raise HTTPException(403, "IP de origem não autorizado para esta chave")

    ok, restantes, espera = rate_limiter.consumir(ctx.key_id, ctx.rate_limit_min)
    request.state.api_rate = (ctx.rate_limit_min, restantes)
    if not ok:
        raise HTTPException(429, "limite de requisições por minuto excedido",
                            headers={"Retry-After": str(espera)})

    agora = time.monotonic()
    if agora - _ultimo_touch.get(ctx.key_id, 0) > 30:  # evita UPDATE a cada chamada
        _ultimo_touch[ctx.key_id] = agora
        try:
            store.touch_api_key(ctx.key_id, ip)
        except Exception:  # pragma: no cover
            pass
    return ctx


def exigir_escopo(escopo: str | None = None):
    """Dependency: autentica a chave e (opcionalmente) exige um escopo."""
    if escopo is not None and escopo not in ESCOPOS:  # erro de programação
        raise ValueError(f"escopo desconhecido: {escopo}")

    def dep(request: Request) -> ApiCtx:
        ctx = _autenticar(request)
        if escopo and escopo not in ctx.escopos:
            raise HTTPException(403, f"a chave não tem o escopo '{escopo}'")
        if not billing.assinatura_ativa(ctx.tenant_id):
            raise HTTPException(402, "subscription_required")
        return ctx

    return dep


def instalar(app: FastAPI) -> None:
    """Registra os routers e o middleware de auditoria/cabeçalhos de rate limit."""

    @app.middleware("http")
    async def _auditoria_api(request: Request, call_next):
        if not request.url.path.startswith("/v1/"):
            return await call_next(request)
        inicio = time.perf_counter()
        response = await call_next(request)
        ctx: ApiCtx | None = getattr(request.state, "api_ctx", None)
        rate = getattr(request.state, "api_rate", None)
        if rate:
            response.headers["X-RateLimit-Limit"] = str(rate[0])
            response.headers["X-RateLimit-Remaining"] = str(rate[1])
        if ctx:
            ms = int((time.perf_counter() - inicio) * 1000)
            try:
                await run_in_threadpool(
                    store.log_api_request, ctx.tenant_id, ctx.key_id, request.method,
                    request.url.path, response.status_code, ms, ip_cliente(request),
                )
            except Exception:  # pragma: no cover — auditoria não derruba a chamada
                pass
        return response

    app.include_router(router_v1)
    app.include_router(router_gestao)


# =========================================================================
# API pública /v1
# =========================================================================

router_v1 = APIRouter(prefix="/v1", tags=["API pública v1"])


class ClienteUpsert(BaseModel):
    razao_social: str | None = None
    cnpj: str | None = None
    email: str | None = None
    nome_contato: str | None = None


class MensagemEnvio(BaseModel):
    texto: str = Field(min_length=1, max_length=4096)
    pausar_ia: bool = True  # como no painel: resposta humana pausa o bot


class FilaAtualizacao(BaseModel):
    status: str | None = None
    responsavel: str | None = None


def _telefone(v: str) -> str:
    t = so_digitos(v)
    if not 10 <= len(t) <= 15:
        raise HTTPException(422, "telefone inválido (use DDI+DDD+número, só dígitos)")
    return t


@router_v1.get("/me")
def v1_me(ctx: ApiCtx = Depends(exigir_escopo())):
    """Identifica a chave (útil p/ testar a integração)."""
    t = store.get_tenant(ctx.tenant_id) or {}
    return {
        "tenant": {"id": ctx.tenant_id, "nome": t.get("nome"), "slug": t.get("slug")},
        "chave": {"id": ctx.key_id, "nome": ctx.nome, "prefixo": ctx.prefixo,
                  "escopos": ctx.escopos, "rate_limit_min": ctx.rate_limit_min},
    }


# --- Catálogo -------------------------------------------------------------

@router_v1.get("/catalogo/produtos")
def v1_produtos(q: str | None = None, categoria: str | None = None,
                limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
                ctx: ApiCtx = Depends(exigir_escopo("catalogo:ler"))):
    items = catalog.listar_produtos(ctx.tenant_id, q, categoria, limit, offset)
    return {"items": items, "limit": limit, "offset": offset}


@router_v1.get("/catalogo/produtos/{identificador}")
def v1_produto(identificador: str, ctx: ApiCtx = Depends(exigir_escopo("catalogo:ler"))):
    p = catalog.detalhes_produto(ctx.tenant_id, identificador)
    if p is None:
        raise HTTPException(404, "produto não encontrado")
    return p


@router_v1.get("/catalogo/categorias")
def v1_categorias(ctx: ApiCtx = Depends(exigir_escopo("catalogo:ler"))):
    return {"items": catalog.listar_categorias(ctx.tenant_id)}


# --- Clientes -------------------------------------------------------------

@router_v1.get("/clientes")
def v1_clientes(status: str | None = Query(None, pattern="^(pendente|ativo)$"),
                limit: int = Query(100, ge=1, le=1000),
                ctx: ApiCtx = Depends(exigir_escopo("clientes:ler"))):
    return {"items": store.list_customers(ctx.tenant_id, status, limit)}


@router_v1.get("/clientes/{telefone}")
def v1_cliente(telefone: str, ctx: ApiCtx = Depends(exigir_escopo("clientes:ler"))):
    c = store.get_customer(ctx.tenant_id, _telefone(telefone))
    if c is None:
        raise HTTPException(404, "cliente não encontrado")
    return c


@router_v1.put("/clientes/{telefone}")
def v1_cliente_upsert(telefone: str, body: ClienteUpsert,
                      ctx: ApiCtx = Depends(exigir_escopo("clientes:escrever"))):
    """Cria ou atualiza (parcialmente) o cadastro do cliente."""
    dados = body.model_dump(exclude_none=True)
    if "cnpj" in dados and not cnpj_valido(dados["cnpj"]):
        raise HTTPException(422, "CNPJ inválido")
    if "cnpj" in dados:
        dados["cnpj"] = so_digitos(dados["cnpj"])
    if "email" in dados and not email_valido(dados["email"]):
        raise HTTPException(422, "e-mail inválido")
    return store.upsert_customer(ctx.tenant_id, _telefone(telefone), **dados)


# --- Conversas ------------------------------------------------------------

@router_v1.get("/conversas")
def v1_conversas(status: str | None = None, q: str | None = None,
                 limit: int = Query(100, ge=1, le=500),
                 ctx: ApiCtx = Depends(exigir_escopo("conversas:ler"))):
    return {"items": store.list_conversations(ctx.tenant_id, status, q, limit)}


@router_v1.get("/conversas/{thread_id}")
def v1_conversa(thread_id: str, ctx: ApiCtx = Depends(exigir_escopo("conversas:ler"))):
    c = store.get_conversation(ctx.tenant_id, thread_id)
    if c is None:
        raise HTTPException(404, "conversa não encontrada")
    return c


@router_v1.post("/conversas/{thread_id}/mensagens", status_code=201)
def v1_enviar_mensagem(thread_id: str, body: MensagemEnvio,
                       ctx: ApiCtx = Depends(exigir_escopo("mensagens:enviar"))):
    """Envia mensagem no WhatsApp em uma conversa JÁ existente do tenant
    (não permite abrir conversa fria com números arbitrários — anti-spam)."""
    texto = body.texto.strip()
    if not texto:
        raise HTTPException(422, "texto vazio")
    conv = store.get_conversation(ctx.tenant_id, thread_id)
    if conv is None:
        raise HTTPException(404, "conversa não encontrada")
    try:
        evolution.enviar_texto(thread_id, texto, instancia=conv.get("instancia"))
    except evolution.EvolutionError as e:
        raise HTTPException(503, str(e))
    store.add_message(ctx.tenant_id, thread_id, "humano", texto)
    if body.pausar_ia:
        store.set_status(ctx.tenant_id, thread_id, "humano")
    return {"enviado": True, "thread_id": thread_id}


# --- Fila humana / orçamentos ---------------------------------------------

@router_v1.get("/fila")
def v1_fila(tipo: str | None = None, status: str | None = None,
            ctx: ApiCtx = Depends(exigir_escopo("fila:ler"))):
    if tipo and tipo not in _FILA_TIPOS:
        raise HTTPException(422, f"tipo inválido (use {', '.join(sorted(_FILA_TIPOS))})")
    if status and status not in _FILA_STATUS:
        raise HTTPException(422, f"status inválido (use {', '.join(sorted(_FILA_STATUS))})")
    return {"items": store.list_queue(ctx.tenant_id, tipo, status)}


@router_v1.patch("/fila/{item_id}")
def v1_fila_atualizar(item_id: int, body: FilaAtualizacao,
                      ctx: ApiCtx = Depends(exigir_escopo("fila:escrever"))):
    if body.status and body.status not in _FILA_STATUS:
        raise HTTPException(422, f"status inválido (use {', '.join(sorted(_FILA_STATUS))})")
    item = store.update_queue_item(ctx.tenant_id, item_id, body.status, body.responsavel)
    if item is None:
        raise HTTPException(404, "item não encontrado")
    return item


@router_v1.get("/orcamentos")
def v1_orcamentos(status: str | None = None,
                  ctx: ApiCtx = Depends(exigir_escopo("orcamentos:ler"))):
    if status and status not in _FILA_STATUS:
        raise HTTPException(422, f"status inválido (use {', '.join(sorted(_FILA_STATUS))})")
    return {"items": store.list_queue(ctx.tenant_id, "pedido", status)}


# --- Métricas -------------------------------------------------------------

@router_v1.get("/metricas")
def v1_metricas(ctx: ApiCtx = Depends(exigir_escopo("metricas:ler"))):
    return store.metrics_overview(ctx.tenant_id)


@router_v1.get("/relatorios/resumo")
def v1_relatorio(desde: str = Query(..., pattern=r"^\d{4}-\d{2}-\d{2}$"),
                 ate: str = Query(..., pattern=r"^\d{4}-\d{2}-\d{2}$"),
                 ctx: ApiCtx = Depends(exigir_escopo("metricas:ler"))):
    return store.relatorio_resumo(ctx.tenant_id, desde, ate)


# =========================================================================
# Gestão das chaves (painel) — sessão do usuário
# =========================================================================

router_gestao = APIRouter(tags=["Integrações (painel)"])


class ChaveCreate(BaseModel):
    nome: str = Field(min_length=1, max_length=80)
    escopos: list[str]
    ips_permitidos: list[str] = []
    rate_limit_min: int = Field(60, ge=1, le=1000)
    expira_em_dias: int | None = Field(None, ge=1, le=730)


class ChaveUpdate(BaseModel):
    nome: str | None = Field(None, min_length=1, max_length=80)
    escopos: list[str] | None = None
    ips_permitidos: list[str] | None = None
    rate_limit_min: int | None = Field(None, ge=1, le=1000)


def _exigir_owner(tenant: TenantCtx) -> None:
    if tenant.role != "owner":
        raise HTTPException(403, "apenas o responsável da conta gerencia chaves de API")


def _validar_escopos(escopos: list[str]) -> list[str]:
    invalidos = [e for e in escopos if e not in ESCOPOS]
    if invalidos:
        raise HTTPException(422, f"escopos inválidos: {', '.join(invalidos)}")
    if not escopos:
        raise HTTPException(422, "selecione ao menos uma permissão")
    return sorted(set(escopos))


def _criar(tenant: TenantCtx, nome: str, escopos: list[str], ips: list[str],
           rate: int, expires_at) -> dict:
    ativas = store.api_uso_resumo(tenant.tenant_id)["chaves_ativas"]
    if ativas >= settings.api_max_chaves_por_tenant:
        raise HTTPException(409, f"limite de {settings.api_max_chaves_por_tenant} chaves ativas atingido")
    texto, prefixo, h = gerar_chave()
    k = store.create_api_key(tenant.tenant_id, nome.strip(), prefixo, h, escopos, ips,
                             rate, expires_at, tenant.user_id)
    return {**k, "chave": texto}


@router_gestao.get("/integracoes/escopos")
def gestao_escopos(tenant: TenantCtx = Depends(current_tenant)):
    return {"escopos": [{"id": k, **v} for k, v in ESCOPOS.items()],
            "max_chaves": settings.api_max_chaves_por_tenant}


@router_gestao.get("/integracoes/resumo")
def gestao_resumo(tenant: TenantCtx = Depends(current_tenant)):
    return store.api_uso_resumo(tenant.tenant_id)


@router_gestao.get("/integracoes/chaves")
def gestao_listar(tenant: TenantCtx = Depends(current_tenant)):
    return store.list_api_keys(tenant.tenant_id)


@router_gestao.post("/integracoes/chaves", status_code=201)
def gestao_criar(req: ChaveCreate,
                 tenant: TenantCtx = Depends(billing.require_active_subscription)):
    """Cria a chave. O texto puro (`chave`) só é devolvido AQUI."""
    _exigir_owner(tenant)
    expira = (datetime.now(timezone.utc) + timedelta(days=req.expira_em_dias)
              if req.expira_em_dias else None)
    return _criar(tenant, req.nome, _validar_escopos(req.escopos),
                  normalizar_ips(req.ips_permitidos), req.rate_limit_min, expira)


@router_gestao.patch("/integracoes/chaves/{key_id}")
def gestao_atualizar(key_id: int, req: ChaveUpdate,
                     tenant: TenantCtx = Depends(current_tenant)):
    _exigir_owner(tenant)
    k = store.update_api_key(
        tenant.tenant_id, key_id,
        nome=req.nome.strip() if req.nome else None,
        escopos=_validar_escopos(req.escopos) if req.escopos is not None else None,
        ips_permitidos=normalizar_ips(req.ips_permitidos) if req.ips_permitidos is not None else None,
        rate_limit_min=req.rate_limit_min,
    )
    if k is None:
        raise HTTPException(404, "chave não encontrada ou revogada")
    return k


@router_gestao.post("/integracoes/chaves/{key_id}/rotacionar", status_code=201)
def gestao_rotacionar(key_id: int,
                      tenant: TenantCtx = Depends(billing.require_active_subscription)):
    """Gera uma chave nova com a MESMA configuração e revoga a antiga."""
    _exigir_owner(tenant)
    antiga = store.get_api_key(tenant.tenant_id, key_id)
    if antiga is None or antiga.get("revoked_at"):
        raise HTTPException(404, "chave não encontrada ou revogada")
    store.revoke_api_key(tenant.tenant_id, key_id)
    return _criar(tenant, antiga["nome"], list(antiga["escopos"]),
                  list(antiga["ips_permitidos"]), int(antiga["rate_limit_min"]),
                  antiga.get("expires_at"))


@router_gestao.delete("/integracoes/chaves/{key_id}")
def gestao_revogar(key_id: int, tenant: TenantCtx = Depends(current_tenant)):
    """Revogação imediata (irreversível). Liberada mesmo sem assinatura ativa."""
    _exigir_owner(tenant)
    k = store.revoke_api_key(tenant.tenant_id, key_id)
    if k is None:
        raise HTTPException(404, "chave não encontrada")
    return k


@router_gestao.get("/integracoes/logs")
def gestao_logs(chave_id: int | None = None, limit: int = Query(50, ge=1, le=100),
                offset: int = Query(0, ge=0), tenant: TenantCtx = Depends(current_tenant)):
    return store.list_api_logs(tenant.tenant_id, chave_id, limit, offset)


# --- Central admin (staff, cross-tenant) ------------------------------------

@router_gestao.get("/admin/integracoes")
def admin_chaves(q: str | None = None, limit: int = Query(25, ge=1, le=100),
                 offset: int = Query(0, ge=0), _: TenantCtx = Depends(current_admin)):
    return store.admin_list_api_keys(q, limit, offset)


@router_gestao.post("/admin/integracoes/{key_id}/revogar")
def admin_revogar(key_id: int, _: TenantCtx = Depends(current_admin)):
    """Revogação de emergência (ex.: chave vazada) pela equipe AtentBot."""
    k = store.admin_revoke_api_key(key_id)
    if k is None:
        raise HTTPException(404, "chave não encontrada")
    return k
