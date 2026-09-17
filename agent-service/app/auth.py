"""Autenticação de aplicação (multi-tenant) por cookie de sessão.

Cada cliente (tenant) tem um ou mais usuários. O login cria uma sessão opaca
(token aleatório); guardamos apenas o SHA-256 do token no banco. O cookie viaja
pelo proxy same-origin `/agent/*` do Next, então o painel autentica sem CORS.

Substitui o Authentik (forward-auth) que era usado na infra.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import Depends, HTTPException, Request, Response

from urllib.parse import urlencode

from . import evolution, mailer, store
from .settings import settings

log = logging.getLogger("atentbot.auth")
_ph = PasswordHasher()
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


# --- Hash de senha e token ------------------------------------------------

def hash_senha(senha: str) -> str:
    return _ph.hash(senha)


def verificar_senha(hash_: str, senha: str) -> bool:
    try:
        return _ph.verify(hash_, senha)
    except VerifyMismatchError:
        return False
    except Exception:
        return False


def _novo_token() -> str:
    return secrets.token_urlsafe(32)


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def email_valido(email: str) -> bool:
    return bool(_EMAIL_RE.match((email or "").strip()))


def normalizar_whatsapp(numero: str) -> str | None:
    """Só dígitos, com DDI. Número brasileiro sem DDI (DDD + 8/9 dígitos) ganha
    o 55. Devolve None se não parece um celular válido."""
    d = re.sub(r"\D", "", numero or "")
    if len(d) in (10, 11) and not d.startswith("55"):
        d = "55" + d
    if d.startswith("55"):
        return d if len(d) in (12, 13) else None
    return d if 10 <= len(d) <= 15 else None


def _slug(nome: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", (nome or "").lower()).strip("-") or "cliente"
    return base[:40]


# --- Sessão / cookie ------------------------------------------------------

def _set_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        settings.session_cookie_name,
        token,
        max_age=settings.session_ttl_days * 86400,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
        path="/",
    )


def _clear_cookie(response: Response) -> None:
    response.delete_cookie(settings.session_cookie_name, path="/")


def abrir_sessao(response: Response, user_id: int) -> None:
    """Cria uma sessão nova e grava o cookie na resposta."""
    token = _novo_token()
    expires = datetime.now(timezone.utc) + timedelta(days=settings.session_ttl_days)
    store.create_session(user_id, _hash_token(token), expires)
    _set_cookie(response, token)


def encerrar_sessao(request: Request, response: Response) -> None:
    token = request.cookies.get(settings.session_cookie_name)
    if token:
        try:
            store.delete_session(_hash_token(token))
        except Exception:
            pass
    _clear_cookie(response)


# --- Signup / login -------------------------------------------------------

def signup(nome_empresa: str, email: str, senha: str, nome: str | None = None,
           plano: str | None = None, whatsapp: str | None = None) -> dict:
    """Cria tenant + usuário owner (+ agente padrão do tenant) e envia o link de
    verificação de e-mail. NÃO abre sessão: o acesso só começa após confirmar o
    e-mail. Levanta HTTPException 400/409 em erro de validação."""
    nome_empresa = (nome_empresa or "").strip()
    email = (email or "").strip()
    if not nome_empresa:
        raise HTTPException(400, "informe o nome da empresa")
    if not email_valido(email):
        raise HTTPException(400, "e-mail inválido")
    if len(senha or "") < 8:
        raise HTTPException(400, "a senha deve ter ao menos 8 caracteres")
    whatsapp_norm = normalizar_whatsapp(whatsapp or "")
    if not whatsapp_norm:
        raise HTTPException(400, "informe um WhatsApp válido com DDD")
    if store.get_user_by_email(email):
        raise HTTPException(409, "já existe uma conta com este e-mail")

    # slug único
    base = _slug(nome_empresa)
    slug = base
    i = 1
    while store.get_tenant_by_slug(slug):
        i += 1
        slug = f"{base}-{i}"

    tenant = store.create_tenant(slug, nome_empresa)
    user = store.create_user(tenant["id"], email, hash_senha(senha), nome or None,
                             role="owner", whatsapp=whatsapp_norm)
    store.ensure_default_agent(tenant["id"])
    enviar_verificacao(user, plano)
    return {"tenant": tenant, "user": user}


# --- Verificação de e-mail ------------------------------------------------

def enviar_verificacao(user: dict, plano: str | None = None) -> None:
    """Gera um token de uso único e envia o link de confirmação por e-mail.
    `plano` (opcional) segue no link para cair direto no checkout depois."""
    token = _novo_token()
    expires = datetime.now(timezone.utc) + timedelta(hours=settings.email_verification_ttl_hours)
    store.create_email_verification(user["id"], _hash_token(token), expires)
    params = {"token": token}
    if plano:
        params["plano"] = plano
    link = f"{settings.panel_url.rstrip('/')}/verificar-email?{urlencode(params)}"
    if not settings.email_enabled:
        # Sem SMTP (dev): o link só aparece no log.
        log.warning("SMTP desligado — link de verificação de %s: %s", user["email"], link)
        return
    mailer.enviar_verificacao_email(user["email"], user.get("nome"), link)


def reenviar_verificacao(email: str, plano: str | None = None) -> None:
    """Reenvia o link. Silencioso para e-mail inexistente/já verificado (não
    revela se a conta existe) e limitado por hora para não virar spam."""
    u = store.get_user_by_email((email or "").strip())
    if not u or not u.get("ativo") or u.get("email_verificado_em"):
        return
    recentes = store.count_recent_email_verifications(u["id"], 60)
    if recentes >= settings.email_verification_max_por_hora:
        raise HTTPException(429, "muitos reenvios; tente novamente mais tarde")
    enviar_verificacao(u, plano)


def verificar_email(token: str) -> dict:
    """Consome o token e marca o e-mail como verificado. 400 se inválido/expirado."""
    u = store.consume_email_verification(_hash_token(token or ""))
    if not u:
        raise HTTPException(400, "link de verificação inválido ou expirado")
    return u


# --- Verificação de WhatsApp ----------------------------------------------

CHAVE_INSTANCIA_VERIFICACAO = "whatsapp_verificacao_instancia"


def instancia_verificacao() -> str:
    """Instância que envia os códigos: a sincronizada na central admin; a env
    WHATSAPP_VERIFICACAO_INSTANCIA fica só como reserva."""
    try:
        valor = store.get_platform_setting(CHAVE_INSTANCIA_VERIFICACAO)
    except Exception:  # pragma: no cover - banco fora não deve mascarar a env
        valor = None
    return valor or settings.whatsapp_verificacao_instancia


def _hash_codigo(user_id: int, codigo: str) -> str:
    return hashlib.sha256(f"{user_id}:{codigo}".encode("utf-8")).hexdigest()


def enviar_codigo_whatsapp(ctx: "TenantCtx", telefone: str | None = None) -> dict:
    """Gera e envia pelo WhatsApp um código de 6 dígitos. `telefone` troca o
    número informado no cadastro (enquanto não verificado). Limita intervalo e
    quantidade por hora. 400/409/429/502/503 em erro."""
    if ctx.whatsapp_verificado:
        raise HTTPException(409, "whatsapp_ja_verificado")
    numero = normalizar_whatsapp(telefone) if telefone else ctx.whatsapp
    if not numero:
        raise HTTPException(400, "informe um WhatsApp válido com DDD")
    if store.whatsapp_em_uso(numero, ctx.user_id):
        raise HTTPException(409, "este WhatsApp já está verificado em outra conta")

    rec = store.whatsapp_verifications_recentes(ctx.user_id, 60)
    if rec["ultimo"]:
        passados = (datetime.now(timezone.utc) - rec["ultimo"]).total_seconds()
        if passados < settings.whatsapp_codigo_intervalo_seg:
            espera = int(settings.whatsapp_codigo_intervalo_seg - passados) + 1
            raise HTTPException(429, f"aguarde {espera}s para pedir outro código")
    if rec["n"] >= settings.whatsapp_codigo_max_por_hora:
        raise HTTPException(429, "muitos códigos pedidos; tente novamente mais tarde")

    if numero != ctx.whatsapp:
        store.set_user_whatsapp(ctx.user_id, numero)

    codigo = f"{secrets.randbelow(1_000_000):06d}"
    expires = datetime.now(timezone.utc) + timedelta(minutes=settings.whatsapp_codigo_ttl_min)
    store.create_whatsapp_verification(ctx.user_id, numero, _hash_codigo(ctx.user_id, codigo), expires)

    texto = (f"AtentBot: seu código de verificação é {codigo}. "
             f"Vale por {settings.whatsapp_codigo_ttl_min} minutos. Não compartilhe.")
    if not settings.evolution_configured:
        # Sem Evolution (dev): o código só aparece no log.
        log.warning("Evolution desligada — código WhatsApp de %s (%s): %s", ctx.email, numero, codigo)
    elif not (instancia := instancia_verificacao()):
        raise HTTPException(503, "verificação por WhatsApp indisponível no momento")
    else:
        try:
            evolution.enviar_texto(numero, texto, instancia=instancia)
        except evolution.EvolutionError as e:
            log.warning("envio do código WhatsApp falhou (%s): %s", numero, e)
            raise HTTPException(502, "não foi possível enviar o código para este número")
    return {"enviado": True, "whatsapp": numero, "expira_em_min": settings.whatsapp_codigo_ttl_min}


def confirmar_codigo_whatsapp(ctx: "TenantCtx", codigo: str) -> dict:
    """Confere o código (tentativas limitadas) e marca o WhatsApp como verificado."""
    if ctx.whatsapp_verificado:
        return {"verificado": True, "whatsapp": ctx.whatsapp}
    v = store.get_active_whatsapp_verification(ctx.user_id)
    if not v:
        raise HTTPException(400, "código expirado; peça um novo")
    if v["tentativas"] >= settings.whatsapp_codigo_max_tentativas:
        raise HTTPException(429, "muitas tentativas; peça um novo código")
    store.increment_whatsapp_attempt(v["id"])
    codigo = re.sub(r"\D", "", codigo or "")
    if not hmac.compare_digest(v["code_hash"], _hash_codigo(ctx.user_id, codigo)):
        raise HTTPException(400, "código incorreto")
    if store.whatsapp_em_uso(v["telefone"], ctx.user_id):
        raise HTTPException(409, "este WhatsApp já está verificado em outra conta")
    store.confirm_whatsapp_verification(v["id"], ctx.user_id, v["telefone"])
    return {"verificado": True, "whatsapp": v["telefone"]}


def trocar_senha(user_id: int, atual: str, nova: str) -> None:
    """Troca a senha do usuário logado (valida a atual). 400/401 em erro."""
    if len(nova or "") < 8:
        raise HTTPException(400, "a nova senha deve ter ao menos 8 caracteres")
    h = store.get_password_hash(user_id)
    if not h or not verificar_senha(h, atual or ""):
        raise HTTPException(401, "senha atual incorreta")
    store.set_password(user_id, hash_senha(nova))


def login(email: str, senha: str) -> dict:
    """Valida credenciais e devolve o usuário (sem abrir sessão). 401 se inválido."""
    u = store.get_user_by_email((email or "").strip())
    if not u or not u.get("ativo") or not verificar_senha(u["password_hash"], senha or ""):
        raise HTTPException(401, "e-mail ou senha inválidos")
    if not u.get("email_verificado_em"):
        # Senha já conferida: dá pra dizer o motivo sem vazar existência da conta.
        raise HTTPException(403, "email_nao_verificado")
    return u


# --- Dependency de tenant (para os endpoints do painel) -------------------

@dataclass
class TenantCtx:
    tenant_id: int
    user_id: int
    email: str
    nome: str | None
    role: str
    is_staff: bool = False
    whatsapp: str | None = None
    whatsapp_verificado: bool = False


def current_tenant(request: Request) -> TenantCtx:
    """Resolve a sessão do cookie -> usuário -> tenant. 401 se ausente/expirada.
    Use como dependency nos endpoints do painel."""
    token = request.cookies.get(settings.session_cookie_name)
    if not token:
        raise HTTPException(401, "não autenticado")
    sess = store.get_session(_hash_token(token))
    if not sess:
        raise HTTPException(401, "sessão expirada")
    try:
        store.touch_session(_hash_token(token))
    except Exception:
        pass
    return TenantCtx(
        tenant_id=int(sess["tenant_id"]),
        user_id=int(sess["user_id"]),
        email=sess["email"],
        nome=sess.get("nome"),
        role=sess.get("role") or "owner",
        is_staff=bool(sess.get("is_staff")),
        whatsapp=sess.get("whatsapp"),
        whatsapp_verificado=bool(sess.get("whatsapp_verificado_em")),
    )


def current_admin(tenant: TenantCtx = Depends(current_tenant)) -> TenantCtx:
    """Dependency da central admin (equipe Dew): exige usuário staff (403 se não)."""
    if not tenant.is_staff:
        raise HTTPException(403, "acesso restrito à administração")
    return tenant
