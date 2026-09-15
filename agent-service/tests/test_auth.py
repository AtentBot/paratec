"""Autenticação: hash de senha (puro) + signup/login/sessão (integração)."""
import uuid

import pytest
from fastapi import HTTPException

from app import auth
from .conftest import requires_db


def test_hash_e_verificacao():
    h = auth.hash_senha("segredo-forte-123")
    assert h != "segredo-forte-123"
    assert auth.verificar_senha(h, "segredo-forte-123") is True
    assert auth.verificar_senha(h, "errado") is False


def test_email_valido():
    assert auth.email_valido("contato@empresa.com.br")
    assert not auth.email_valido("contato@empresa")
    assert not auth.email_valido("")


def test_signup_valida_entradas():
    with pytest.raises(HTTPException):
        auth.signup("", "a@b.com", "12345678")          # empresa vazia
    with pytest.raises(HTTPException):
        auth.signup("Empresa", "invalido", "12345678")  # email inválido
    with pytest.raises(HTTPException):
        auth.signup("Empresa", "a@b.com", "123")        # senha curta


@requires_db
def test_signup_login_e_sessao(db):
    email = f"user-{uuid.uuid4().hex[:8]}@exemplo.com"
    res = auth.signup("Empresa Teste", email, "senha-forte-1")
    assert res["tenant"]["id"] and res["user"]["email"].lower() == email.lower()
    # agente padrão criado para o novo tenant
    assert db.get_default_agent(res["tenant"]["id"]) is not None

    u = auth.login(email, "senha-forte-1")
    assert u["tenant_id"] == res["tenant"]["id"]
    with pytest.raises(HTTPException):
        auth.login(email, "senha-errada")

    # e-mail duplicado é rejeitado
    with pytest.raises(HTTPException):
        auth.signup("Outra", email, "senha-forte-2")
