"""Autenticação: hash de senha (puro) + signup/login/sessão (integração)."""
import uuid

import pytest
from fastapi import HTTPException

from app import auth
from .conftest import requires_db


def _wa() -> str:
    """Celular brasileiro aleatório (evita colisão entre testes)."""
    return f"119{uuid.uuid4().int % 10**8:08d}"


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
    with pytest.raises(HTTPException):
        auth.signup("Empresa", "a@b.com", "12345678", whatsapp="123")  # whatsapp inválido


def test_normalizar_whatsapp():
    assert auth.normalizar_whatsapp("(11) 98765-4321") == "5511987654321"
    assert auth.normalizar_whatsapp("+55 11 3333-4444") == "551133334444"
    assert auth.normalizar_whatsapp("5511987654321") == "5511987654321"
    assert auth.normalizar_whatsapp("12345") is None
    assert auth.normalizar_whatsapp("") is None


@requires_db
def test_signup_login_e_sessao(db, monkeypatch):
    tokens = []

    def _token():
        t = f"tok-{uuid.uuid4().hex}"
        tokens.append(t)
        return t

    monkeypatch.setattr(auth, "_novo_token", _token)
    email = f"user-{uuid.uuid4().hex[:8]}@exemplo.com"
    res = auth.signup("Empresa Teste", email, "senha-forte-1", whatsapp=_wa())
    assert res["tenant"]["id"] and res["user"]["email"].lower() == email.lower()
    # agente padrão criado para o novo tenant
    assert db.get_default_agent(res["tenant"]["id"]) is not None

    # sem confirmar o e-mail não entra (403); senha errada continua 401
    with pytest.raises(HTTPException) as e:
        auth.login(email, "senha-forte-1")
    assert e.value.status_code == 403
    with pytest.raises(HTTPException) as e:
        auth.login(email, "senha-errada")
    assert e.value.status_code == 401

    # token inválido é rejeitado; o do e-mail confirma (uso único)
    with pytest.raises(HTTPException):
        auth.verificar_email("token-que-nao-existe")
    u = auth.verificar_email(tokens[0])
    assert u["tenant_id"] == res["tenant"]["id"]
    with pytest.raises(HTTPException):
        auth.verificar_email(tokens[0])

    u = auth.login(email, "senha-forte-1")
    assert u["tenant_id"] == res["tenant"]["id"]

    # e-mail duplicado é rejeitado
    with pytest.raises(HTTPException):
        auth.signup("Outra", email, "senha-forte-2", whatsapp=_wa())


@requires_db
def test_sessao_exige_email_verificado(db):
    email = f"user-{uuid.uuid4().hex[:8]}@exemplo.com"
    res = auth.signup("Empresa Sessao", email, "senha-forte-1", whatsapp=_wa())
    uid = res["user"]["id"]
    db.create_session(uid, "hash-sessao-" + uuid.uuid4().hex,
                      auth.datetime.now(auth.timezone.utc) + auth.timedelta(days=1))
    h = db.query("SELECT token_hash FROM sessions WHERE user_id = %s", (uid,))[0]["token_hash"]
    assert db.get_session(h) is None          # não verificado: sessão não vale
    db.mark_email_verified(uid)
    assert db.get_session(h) is not None


@requires_db
def test_reenvio_limitado(db, monkeypatch):
    monkeypatch.setattr(auth.settings, "email_verification_max_por_hora", 2)
    email = f"user-{uuid.uuid4().hex[:8]}@exemplo.com"
    auth.signup("Empresa Reenvio", email, "senha-forte-1", whatsapp=_wa())   # 1º envio
    auth.reenviar_verificacao(email)                          # 2º
    with pytest.raises(HTTPException) as e:
        auth.reenviar_verificacao(email)
    assert e.value.status_code == 429
    # e-mail desconhecido não revela nada
    auth.reenviar_verificacao("ninguem-" + uuid.uuid4().hex[:6] + "@exemplo.com")


@requires_db
def test_endpoints_signup_sem_sessao_e_verificacao_abre(db, monkeypatch):
    from fastapi.testclient import TestClient
    from app import main
    from app.settings import settings

    tokens = []
    real = auth._novo_token

    def _token():
        t = real()
        tokens.append(t)
        return t

    monkeypatch.setattr(auth, "_novo_token", _token)
    client = TestClient(main.app)
    email = f"user-{uuid.uuid4().hex[:8]}@exemplo.com"
    r = client.post("/auth/signup", json={"empresa": "Empresa API", "email": email,
                                          "senha": "senha-forte-1", "plano": "xpto",
                                          "whatsapp": _wa()})
    assert r.status_code == 200 and r.json()["verificacao_enviada"] is True
    assert settings.session_cookie_name not in r.cookies        # cadastro não loga

    r = client.post("/auth/login", json={"email": email, "senha": "senha-forte-1"})
    assert r.status_code == 403

    r = client.post("/auth/verify-email", json={"token": tokens[0]})
    assert r.status_code == 200
    assert settings.session_cookie_name in r.cookies             # link confirmado loga
    assert client.post("/auth/verify-email", json={"token": tokens[0]}).status_code == 400


def _ctx(db, user_id: int):
    """TenantCtx atual do usuário (como o current_tenant montaria)."""
    u = db.query("""SELECT id, tenant_id, email, nome, role, whatsapp, whatsapp_verificado_em
                      FROM users WHERE id = %s""", (user_id,))[0]
    return auth.TenantCtx(tenant_id=u["tenant_id"], user_id=u["id"], email=u["email"],
                          nome=u["nome"], role=u["role"], whatsapp=u["whatsapp"],
                          whatsapp_verificado=bool(u["whatsapp_verificado_em"]))


def _novo_usuario(db, whatsapp=None):
    email = f"user-{uuid.uuid4().hex[:8]}@exemplo.com"
    res = auth.signup("Empresa WA", email, "senha-forte-1", whatsapp=whatsapp or _wa())
    db.mark_email_verified(res["user"]["id"])
    return res["user"]["id"]


@requires_db
def test_whatsapp_codigo_fluxo(db, monkeypatch):
    from app import evolution
    enviados = []
    monkeypatch.setattr(auth.settings, "evolution_api_url", "http://evo")
    monkeypatch.setattr(auth.settings, "evolution_api_key", "k")
    monkeypatch.setattr(auth.settings, "whatsapp_verificacao_instancia", "atentbot")
    monkeypatch.setattr(evolution, "enviar_texto",
                        lambda tel, txt, instancia=None: enviados.append((tel, txt, instancia)))
    monkeypatch.setattr(auth.secrets, "randbelow", lambda n: 123456)

    uid = _novo_usuario(db)
    r = auth.enviar_codigo_whatsapp(_ctx(db, uid))
    assert r["enviado"] and enviados[0][2] == "atentbot" and "123456" in enviados[0][1]

    # intervalo mínimo entre pedidos
    with pytest.raises(HTTPException) as e:
        auth.enviar_codigo_whatsapp(_ctx(db, uid))
    assert e.value.status_code == 429

    with pytest.raises(HTTPException) as e:
        auth.confirmar_codigo_whatsapp(_ctx(db, uid), "000000")
    assert e.value.status_code == 400
    assert auth.confirmar_codigo_whatsapp(_ctx(db, uid), "123 456")["verificado"] is True
    assert _ctx(db, uid).whatsapp_verificado is True

    # o mesmo número não confirma outra conta
    outro = _novo_usuario(db, whatsapp=_ctx(db, uid).whatsapp)
    with pytest.raises(HTTPException) as e:
        auth.enviar_codigo_whatsapp(_ctx(db, outro))
    assert e.value.status_code == 409


@requires_db
def test_whatsapp_tentativas_limitadas(db, monkeypatch):
    monkeypatch.setattr(auth.settings, "evolution_api_url", "")   # dev: código só no log
    monkeypatch.setattr(auth.secrets, "randbelow", lambda n: 654321)
    monkeypatch.setattr(auth.settings, "whatsapp_codigo_max_tentativas", 2)
    uid = _novo_usuario(db)
    auth.enviar_codigo_whatsapp(_ctx(db, uid))
    for _ in range(2):
        with pytest.raises(HTTPException):
            auth.confirmar_codigo_whatsapp(_ctx(db, uid), "111111")
    with pytest.raises(HTTPException) as e:            # até o código certo é recusado
        auth.confirmar_codigo_whatsapp(_ctx(db, uid), "654321")
    assert e.value.status_code == 429


@requires_db
def test_whatsapp_indisponivel_sem_instancia(db, monkeypatch):
    monkeypatch.setattr(auth.settings, "evolution_api_url", "http://evo")
    monkeypatch.setattr(auth.settings, "evolution_api_key", "k")
    monkeypatch.setattr(auth.settings, "whatsapp_verificacao_instancia", "")
    uid = _novo_usuario(db)
    with pytest.raises(HTTPException) as e:
        auth.enviar_codigo_whatsapp(_ctx(db, uid))
    assert e.value.status_code == 503


def test_checkout_exige_whatsapp_verificado():
    from fastapi.testclient import TestClient
    from app import main
    ctx = auth.TenantCtx(tenant_id=1, user_id=1, email="t@x.com", nome=None, role="owner",
                         whatsapp="5511999998888", whatsapp_verificado=False)
    main.app.dependency_overrides[auth.current_tenant] = lambda: ctx
    try:
        r = TestClient(main.app).post("/billing/checkout", json={"plano": "essencial"})
        assert r.status_code == 403 and r.json()["detail"] == "whatsapp_nao_verificado"
    finally:
        main.app.dependency_overrides.pop(auth.current_tenant, None)


def test_login_lockout_apos_muitas_tentativas(monkeypatch):
    """Após login_max_tentativas falhas do mesmo (email, ip), o login é
    bloqueado com 423 (Locked) — anti-brute-force / anti-spray."""
    # Sem DB: força o caminho de credencial inválida (usuário inexistente).
    monkeypatch.setattr(auth.store, "get_user_by_email", lambda _e: None)
    # Isola o estado em memória deste teste.
    auth._login_falhas.clear()
    auth._login_ate.clear()

    email, ip = "alvo@empresa.com", "203.0.113.7"
    for _ in range(auth.settings.login_max_tentativas):
        with pytest.raises(HTTPException) as ei:
            auth.login(email, "senha-errada", ip=ip)
        assert ei.value.status_code == 401

    # A próxima já vem bloqueada (423), mesmo com a "senha certa".
    with pytest.raises(HTTPException) as ei:
        auth.login(email, "qualquer", ip=ip)
    assert ei.value.status_code == 423
    assert "Retry-After" in ei.value.headers

    # Outro IP não é afetado pelo bloqueio do primeiro.
    with pytest.raises(HTTPException) as ei:
        auth.login(email, "senha-errada", ip="198.51.100.1")
    assert ei.value.status_code == 401

    auth._login_falhas.clear()
    auth._login_ate.clear()
