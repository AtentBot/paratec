"""Autenticação de aplicação (multi-tenant) por cookie de sessão.

Cada cliente (tenant) tem um ou mais usuários. O login cria uma sessão opaca
(token aleatório); guardamos apenas o SHA-256 do token no banco. O cookie viaja
pelo proxy same-origin `/agent/*` do Next, então o painel autentica sem CORS.

Substitui o Authentik (forward-auth) que era usado na infra.
"""
from __future__ import annotations

import hashlib
import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import Depends, HTTPException, Request, Response

from . import store
from .settings import settings

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

def signup(nome_empresa: str, email: str, senha: str, nome: str | None = None) -> dict:
    """Cria tenant + usuário owner (+ agente padrão do tenant). Não abre sessão
    (o chamador decide). Levanta HTTPException 400/409 em erro de validação."""
    nome_empresa = (nome_empresa or "").strip()
    email = (email or "").strip()
    if not nome_empresa:
        raise HTTPException(400, "informe o nome da empresa")
    if not email_valido(email):
        raise HTTPException(400, "e-mail inválido")
    if len(senha or "") < 8:
        raise HTTPException(400, "a senha deve ter ao menos 8 caracteres")
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
    user = store.create_user(tenant["id"], email, hash_senha(senha), nome or None, role="owner")
    store.ensure_default_agent(tenant["id"])
    return {"tenant": tenant, "user": user}


def login(email: str, senha: str) -> dict:
    """Valida credenciais e devolve o usuário (sem abrir sessão). 401 se inválido."""
    u = store.get_user_by_email((email or "").strip())
    if not u or not u.get("ativo") or not verificar_senha(u["password_hash"], senha or ""):
        raise HTTPException(401, "e-mail ou senha inválidos")
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
    )


def current_admin(tenant: TenantCtx = Depends(current_tenant)) -> TenantCtx:
    """Dependency da central admin (equipe Dew): exige usuário staff (403 se não)."""
    if not tenant.is_staff:
        raise HTTPException(403, "acesso restrito à administração")
    return tenant
