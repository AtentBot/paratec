"""Webhooks de saída: avisa o sistema do cliente quando algo acontece.

Fluxo: o `store` chama `disparar(tenant_id, evento, dados)` nos pontos em que o
evento nasce (mensagem, handoff, orçamento…) → buscamos os webhooks ATIVOS do
tenant que assinam o evento → cada entrega roda num pool de threads (best-effort,
nunca bloqueia o atendimento), com até 3 tentativas e backoff.

Segurança:
- Assinatura HMAC-SHA256 de `"{timestamp}.{corpo}"` com o segredo do webhook
  (cabeçalho `X-AtentBot-Assinatura: sha256=<hex>`); o timestamp permite ao
  receptor recusar replays antigos.
- Anti-SSRF: só HTTPS e só destinos com IP público — o serviço roda numa rede
  interna (Postgres, Evolution, n8n…). O IP é revalidado a cada entrega e
  redirecionamentos não são seguidos.
- Webhook que falha `webhook_max_falhas` vezes seguidas é desativado sozinho.
"""
from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
import logging
import secrets
import socket
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from urllib.parse import urlsplit

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from . import billing, store
from .auth import TenantCtx, current_tenant
from .settings import settings

log = logging.getLogger("atentbot.webhooks")

EVENTOS: dict[str, dict] = {
    "mensagem.recebida": {
        "grupo": "Atendimento", "label": "Mensagem recebida",
        "descricao": "O cliente enviou uma mensagem no WhatsApp.",
        "exemplo": {"thread_id": "5511999998888", "autor": "cliente", "texto": "Qual o prazo de entrega?"},
    },
    "mensagem.enviada": {
        "grupo": "Atendimento", "label": "Mensagem enviada",
        "descricao": "O agente de IA ou um atendente respondeu.",
        "exemplo": {"thread_id": "5511999998888", "autor": "agente", "texto": "Entregamos em até 5 dias úteis."},
    },
    "conversa.transferida_humano": {
        "grupo": "Atendimento", "label": "Transferida para humano",
        "descricao": "A IA foi pausada e a conversa passou para a equipe.",
        "exemplo": {"thread_id": "5511999998888", "status": "humano"},
    },
    "conversa.resolvida": {
        "grupo": "Atendimento", "label": "Conversa resolvida",
        "descricao": "A conversa foi marcada como resolvida.",
        "exemplo": {"thread_id": "5511999998888", "status": "resolvida"},
    },
    "orcamento.criado": {
        "grupo": "Vendas", "label": "Orçamento criado",
        "descricao": "O agente registrou um pedido de orçamento.",
        "exemplo": {"id": 123, "tipo": "pedido", "thread_id": "5511999998888", "cliente": "ACME Ltda",
                    "telefone": "5511999998888", "resumo": "200m de cabo de cobre 50mm²", "payload": {}},
    },
    "fila.item_criado": {
        "grupo": "Vendas", "label": "Item na fila humana",
        "descricao": "Novo pedido, entrega ou boleto aguardando a equipe.",
        "exemplo": {"id": 124, "tipo": "boleto", "thread_id": "5511999998888", "resumo": "2ª via do boleto"},
    },
    "fila.item_atualizado": {
        "grupo": "Vendas", "label": "Item da fila atualizado",
        "descricao": "Mudou o status ou o responsável de um item da fila.",
        "exemplo": {"id": 124, "tipo": "boleto", "status": "concluido", "responsavel": "Ana"},
    },
    "cliente.cadastro_completo": {
        "grupo": "Clientes", "label": "Cadastro completo",
        "descricao": "O cliente preencheu todos os dados obrigatórios.",
        "exemplo": {"telefone": "5511999998888", "razao_social": "ACME Ltda", "cnpj": "00000000000191",
                    "email": "compras@acme.com.br", "nome_contato": "João", "status": "ativo"},
    },
}

EVENTO_TESTE = "webhook.teste"
_BACKOFF = (0, 2, 10)  # espera (s) antes de cada tentativa
_TIMEOUT = 10.0


# =========================================================================
# Assinatura e validação de destino
# =========================================================================

def novo_segredo() -> str:
    return "whsec_" + secrets.token_urlsafe(32)


def assinar(segredo: str, timestamp: int, corpo: bytes) -> str:
    mac = hmac.new(segredo.encode(), f"{timestamp}.".encode() + corpo, hashlib.sha256)
    return "sha256=" + mac.hexdigest()


def _ip_bloqueado(ip: str) -> bool:
    addr = ipaddress.ip_address(ip)
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped:
        addr = addr.ipv4_mapped
    return not addr.is_global or addr.is_multicast


def resolver_destino(url: str) -> tuple[str | None, str | None]:
    """Valida o destino e devolve (ip_para_pin, motivo).

    - motivo != None  -> destino recusado (não entregar).
    - (ip, None)       -> ok; conecte PINANDO esse IP já validado (fecha o
                          DNS-rebinding/TOCTOU: nada de re-resolver na hora).
    - (None, None)     -> ok sem pin (modo dev: rede privada liberada).
    """
    try:
        partes = urlsplit(url)
    except ValueError:
        return None, "URL inválida"
    if partes.scheme != "https":
        return None, "use uma URL https://"
    if not partes.hostname:
        return None, "URL sem host"
    if partes.username or partes.password:
        return None, "não inclua usuário/senha na URL"
    if settings.webhook_permitir_rede_privada:
        return None, None  # dev: sem checagem de IP e sem pin
    try:
        infos = socket.getaddrinfo(partes.hostname, partes.port or 443, type=socket.SOCK_STREAM)
    except (socket.gaierror, UnicodeError):
        return None, "não foi possível resolver o host"
    ips = [i[4][0] for i in infos]
    if not ips or any(_ip_bloqueado(ip) for ip in ips):
        return None, "destino em rede privada/interna não é permitido"
    # Todos os IPs resolvidos são públicos: fixa o 1º para a conexão.
    return ips[0], None


def validar_destino(url: str) -> str | None:
    """Só o motivo (None se aceitável). Usado na validação em tempo de cadastro."""
    return resolver_destino(url)[1]


# =========================================================================
# Entrega
# =========================================================================

try:  # pin de IP opcional: se a API interna do httpcore mudar, cai p/ sem-pin
    from httpcore._backends.sync import SyncBackend as _SyncBackend

    class _PinnedBackend(_SyncBackend):
        """Disca sempre no IP fixado; a camada TLS acima continua usando o
        hostname da URL para SNI e verificação de certificado."""
        def __init__(self, ip: str) -> None:
            self._ip = ip
            super().__init__()

        def connect_tcp(self, host, port, timeout=None, local_address=None,
                        socket_options=None):
            return super().connect_tcp(self._ip, port, timeout=timeout,
                                       local_address=local_address,
                                       socket_options=socket_options)

    _PIN_OK = True
except Exception:  # pragma: no cover
    _PIN_OK = False


def _post(url: str, corpo: bytes, headers: dict, pin_ip: str | None = None) -> httpx.Response:
    if pin_ip and _PIN_OK:
        transport = httpx.HTTPTransport(verify=True)
        try:
            transport._pool._network_backend = _PinnedBackend(pin_ip)
        except Exception:  # pragma: no cover — nunca quebrar a entrega pelo pin
            transport = None
        if transport is not None:
            with httpx.Client(transport=transport, timeout=_TIMEOUT) as c:
                return c.post(url, content=corpo, headers=headers, follow_redirects=False)
    return httpx.post(url, content=corpo, headers=headers, timeout=_TIMEOUT,
                      follow_redirects=False)


def envelope(tenant_id: int, evento: str, dados: dict, evento_id: str | None = None) -> dict:
    return {
        "id": evento_id or f"evt_{uuid.uuid4().hex}",
        "evento": evento,
        "criado_em": datetime.now(timezone.utc).isoformat(),
        "tenant_id": tenant_id,
        "dados": dados,
    }


def entregar(hook: dict, payload: dict, tentativas: int = len(_BACKOFF)) -> dict:
    """Entrega síncrona com retry; registra o resultado. Retorna o resumo."""
    corpo = json.dumps(payload, default=str, ensure_ascii=False).encode("utf-8")
    status_code: int | None = None
    erro: str | None = None
    feitas = 0
    inicio = time.perf_counter()
    for espera in _BACKOFF[:max(1, tentativas)]:
        if espera:
            time.sleep(espera)
        feitas += 1
        pin_ip, motivo = resolver_destino(hook["url"])  # resolve+valida+pina numa etapa
        if motivo:
            erro, status_code = f"destino recusado: {motivo}", None
            break  # não adianta tentar de novo
        ts = int(time.time())
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "AtentBot-Webhooks/1.0",
            "X-AtentBot-Evento": payload["evento"],
            "X-AtentBot-Entrega": payload["id"],
            "X-AtentBot-Timestamp": str(ts),
            "X-AtentBot-Assinatura": assinar(hook["segredo"], ts, corpo),
        }
        try:
            r = _post(hook["url"], corpo, headers, pin_ip=pin_ip)
            status_code, erro = r.status_code, None
            if 200 <= r.status_code < 300:
                break
            erro = f"HTTP {r.status_code}"
            if 400 <= r.status_code < 500 and r.status_code not in (408, 429):
                break  # erro do receptor: retry não resolve
        except httpx.HTTPError as e:
            status_code, erro = None, f"{type(e).__name__}: {e}"[:300]
    sucesso = status_code is not None and 200 <= status_code < 300
    ms = int((time.perf_counter() - inicio) * 1000)
    try:
        store.registrar_entrega_webhook(
            int(hook["id"]), int(hook["tenant_id"]), payload["id"], payload["evento"], payload,
            sucesso, status_code, feitas, erro, ms, settings.webhook_max_falhas,
        )
    except Exception as e:  # pragma: no cover
        log.warning("falha ao registrar entrega do webhook %s: %s", hook.get("id"), e)
    return {"sucesso": sucesso, "status_code": status_code, "erro": erro,
            "tentativas": feitas, "duracao_ms": ms}


_pool: ThreadPoolExecutor | None = None


def _executor() -> ThreadPoolExecutor:
    global _pool
    if _pool is None:
        _pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="webhook")
    return _pool


def _agendar(fn, *args) -> None:
    _executor().submit(fn, *args)


def disparar(tenant_id: int, evento: str, dados: dict) -> None:
    """Enfileira o evento p/ os webhooks assinantes. Best-effort: nunca levanta."""
    if evento not in EVENTOS:
        log.warning("evento de webhook desconhecido: %s", evento)
        return
    try:
        hooks = store.webhooks_do_evento(tenant_id, evento)
    except Exception as e:  # pragma: no cover
        log.warning("falha ao buscar webhooks (%s): %s", evento, e)
        return
    if not hooks:
        return
    payload = envelope(tenant_id, evento, dados)
    for h in hooks:
        try:
            _agendar(entregar, h, payload)
        except Exception as e:  # pragma: no cover
            log.warning("falha ao agendar webhook %s: %s", h.get("id"), e)


# =========================================================================
# Gestão (painel)
# =========================================================================

router = APIRouter(prefix="/integracoes/webhooks", tags=["Integrações (painel)"])


class WebhookCreate(BaseModel):
    url: str = Field(min_length=8, max_length=2000)
    descricao: str | None = Field(None, max_length=120)
    eventos: list[str]


class WebhookUpdate(BaseModel):
    url: str | None = Field(None, min_length=8, max_length=2000)
    descricao: str | None = Field(None, max_length=120)
    eventos: list[str] | None = None
    ativo: bool | None = None


def _exigir_owner(tenant: TenantCtx) -> None:
    if tenant.role != "owner":
        raise HTTPException(403, "apenas o responsável da conta gerencia webhooks")


def _validar_eventos(eventos: list[str]) -> list[str]:
    invalidos = [e for e in eventos if e not in EVENTOS]
    if invalidos:
        raise HTTPException(422, f"eventos inválidos: {', '.join(invalidos)}")
    if not eventos:
        raise HTTPException(422, "selecione ao menos um evento")
    return sorted(set(eventos))


def _validar_url(url: str) -> str:
    url = url.strip()
    motivo = validar_destino(url)
    if motivo:
        raise HTTPException(422, motivo)
    return url


def _hook_interno(tenant_id: int, webhook_id: int) -> dict:
    h = store.get_webhook(tenant_id, webhook_id)
    segredo = store.get_webhook_segredo(tenant_id, webhook_id)
    if h is None or segredo is None:
        raise HTTPException(404, "webhook não encontrado")
    return {**h, "segredo": segredo}


@router.get("/eventos")
def eventos(tenant: TenantCtx = Depends(current_tenant)):
    return {"eventos": [{"id": k, **v} for k, v in EVENTOS.items()],
            "max_webhooks": settings.webhook_max_por_tenant}


@router.get("")
def listar(tenant: TenantCtx = Depends(current_tenant)):
    return store.list_webhooks(tenant.tenant_id)


@router.post("", status_code=201)
def criar(req: WebhookCreate, tenant: TenantCtx = Depends(billing.require_active_subscription)):
    """Cria o webhook. O segredo de assinatura volta aqui (e pode ser revelado depois)."""
    _exigir_owner(tenant)
    if store.count_webhooks(tenant.tenant_id) >= settings.webhook_max_por_tenant:
        raise HTTPException(409, f"limite de {settings.webhook_max_por_tenant} webhooks atingido")
    segredo = novo_segredo()
    h = store.create_webhook(tenant.tenant_id, _validar_url(req.url),
                             (req.descricao or "").strip() or None,
                             _validar_eventos(req.eventos), segredo, tenant.user_id)
    return {**h, "segredo": segredo}


@router.patch("/{webhook_id}")
def atualizar(webhook_id: int, req: WebhookUpdate, tenant: TenantCtx = Depends(current_tenant)):
    _exigir_owner(tenant)
    h = store.update_webhook(
        tenant.tenant_id, webhook_id,
        url=_validar_url(req.url) if req.url is not None else None,
        descricao=req.descricao.strip() if req.descricao is not None else None,
        eventos=_validar_eventos(req.eventos) if req.eventos is not None else None,
        ativo=req.ativo,
    )
    if h is None:
        raise HTTPException(404, "webhook não encontrado")
    return h


@router.delete("/{webhook_id}")
def remover(webhook_id: int, tenant: TenantCtx = Depends(current_tenant)):
    _exigir_owner(tenant)
    if not store.delete_webhook(tenant.tenant_id, webhook_id):
        raise HTTPException(404, "webhook não encontrado")
    return {"removido": webhook_id}


@router.get("/{webhook_id}/segredo")
def revelar_segredo(webhook_id: int, tenant: TenantCtx = Depends(current_tenant)):
    _exigir_owner(tenant)
    return {"segredo": _hook_interno(tenant.tenant_id, webhook_id)["segredo"]}


@router.post("/{webhook_id}/rotacionar-segredo")
def rotacionar_segredo(webhook_id: int, tenant: TenantCtx = Depends(current_tenant)):
    _exigir_owner(tenant)
    segredo = novo_segredo()
    if not store.set_webhook_segredo(tenant.tenant_id, webhook_id, segredo):
        raise HTTPException(404, "webhook não encontrado")
    return {"segredo": segredo}


@router.post("/{webhook_id}/testar")
def testar(webhook_id: int, tenant: TenantCtx = Depends(billing.require_active_subscription)):
    """Envia um evento `webhook.teste` agora (1 tentativa) e devolve o resultado."""
    _exigir_owner(tenant)
    hook = _hook_interno(tenant.tenant_id, webhook_id)
    payload = envelope(tenant.tenant_id, EVENTO_TESTE,
                       {"mensagem": "Teste de webhook do AtentBot", "webhook_id": webhook_id})
    return entregar(hook, payload, tentativas=1)


@router.get("/entregas")
def entregas(webhook_id: int | None = None, limit: int = Query(25, ge=1, le=100),
             offset: int = Query(0, ge=0), tenant: TenantCtx = Depends(current_tenant)):
    return store.list_entregas_webhook(tenant.tenant_id, webhook_id, limit, offset)


@router.post("/entregas/{entrega_id}/reenviar")
def reenviar(entrega_id: int, tenant: TenantCtx = Depends(billing.require_active_subscription)):
    """Reenvia o MESMO evento (mesmo id → o receptor pode deduplicar)."""
    _exigir_owner(tenant)
    e = store.get_entrega_webhook(tenant.tenant_id, entrega_id)
    if e is None:
        raise HTTPException(404, "entrega não encontrada")
    hook = _hook_interno(tenant.tenant_id, int(e["webhook_id"]))
    return entregar(hook, e["payload"], tentativas=1)
