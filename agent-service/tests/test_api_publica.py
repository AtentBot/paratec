"""API pública (/v1) e gestão de chaves (/integracoes).

Wiring sem DB: a camada `store` é substituída por um fake em memória, validando
autenticação por chave, escopos, revogação/validade, allowlist de IP, rate limit,
auditoria e isolamento por tenant. O teste com DB fecha o ciclo real."""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app import api_publica, main, store

from .conftest import requires_db

client = TestClient(main.app)


# --- Funções puras ----------------------------------------------------------

def test_gerar_chave_formato_e_hash():
    texto, prefixo, h = api_publica.gerar_chave()
    assert texto.startswith("atb_live_") and len(texto) > 40
    assert texto.startswith(prefixo) and len(prefixo) == len("atb_live_") + 6
    assert h == api_publica.hash_chave(texto) and texto not in h


def test_normalizar_ips():
    assert api_publica.normalizar_ips([" 10.0.0.1 ", "192.168.0.0/24", ""]) == [
        "10.0.0.1/32", "192.168.0.0/24"]
    with pytest.raises(Exception):
        api_publica.normalizar_ips(["999.1.1.1"])


def test_ip_permitido():
    assert api_publica.ip_permitido("1.2.3.4", [])  # sem allowlist = qualquer IP
    assert api_publica.ip_permitido("192.168.0.9", ["192.168.0.0/24"])
    assert not api_publica.ip_permitido("192.168.1.9", ["192.168.0.0/24"])
    assert not api_publica.ip_permitido(None, ["192.168.0.0/24"])


def test_rate_limiter_janela():
    rl = api_publica._RateLimiter()
    assert rl.consumir(1, 2)[0] and rl.consumir(1, 2)[0]
    ok, restantes, espera = rl.consumir(1, 2)
    assert not ok and restantes == 0 and espera >= 1
    assert rl.consumir(2, 2)[0]  # contador é por chave


# --- Fake de store ----------------------------------------------------------

class FakeStore:
    def __init__(self):
        self.keys: dict[str, dict] = {}
        self.logs: list[tuple] = []

    def add(self, tenant_id=1, escopos=("catalogo:ler",), **extra):
        texto, prefixo, h = api_publica.gerar_chave()
        self.keys[h] = {
            "id": len(self.keys) + 1, "tenant_id": tenant_id, "nome": "ERP",
            "prefixo": prefixo, "escopos": list(escopos), "ips_permitidos": [],
            "rate_limit_min": 60, "expires_at": None, "revoked_at": None,
            "tenant_status": "ativa", **extra,
        }
        return texto, self.keys[h]


@pytest.fixture()
def fake(monkeypatch):
    f = FakeStore()
    api_publica.rate_limiter.limpar()
    monkeypatch.setattr(store, "get_api_key_by_hash", lambda h: f.keys.get(h))
    monkeypatch.setattr(store, "touch_api_key", lambda *a: None)
    monkeypatch.setattr(store, "log_api_request", lambda *a: f.logs.append(a))
    monkeypatch.setattr(store, "get_tenant", lambda tid: {"id": tid, "nome": f"T{tid}", "slug": f"t{tid}"})
    return f


def _h(chave):
    return {"Authorization": f"Bearer {chave}"}


def test_sem_chave_401(fake):
    r = client.get("/v1/me")
    assert r.status_code == 401 and r.headers.get("www-authenticate") == "Bearer"
    assert fake.logs == []  # sem tenant identificado, não há o que auditar


def test_chave_invalida_401(fake):
    assert client.get("/v1/me", headers=_h("atb_live_naoexiste")).status_code == 401


def test_me_aceita_bearer_e_x_api_key(fake):
    chave, k = fake.add(tenant_id=7)
    r = client.get("/v1/me", headers=_h(chave))
    assert r.status_code == 200
    assert r.json()["tenant"]["id"] == 7 and r.json()["chave"]["escopos"] == ["catalogo:ler"]
    assert r.headers["x-ratelimit-limit"] == "60"
    assert client.get("/v1/me", headers={"X-API-Key": chave}).status_code == 200
    # auditoria: (tenant, chave, método, rota, status, ms, ip)
    assert fake.logs[0][:5] == (7, k["id"], "GET", "/v1/me", 200)


def test_escopo_ausente_403_e_isolamento_por_tenant(fake, monkeypatch):
    chave, _ = fake.add(tenant_id=42, escopos=["catalogo:ler"])
    assert client.get("/v1/clientes", headers=_h(chave)).status_code == 403

    capturado = {}
    monkeypatch.setattr(api_publica.catalog, "listar_produtos",
                        lambda tid, *a: capturado.setdefault("tid", tid) and [])
    r = client.get("/v1/catalogo/produtos?q=cabo", headers=_h(chave))
    assert r.status_code == 200
    assert capturado["tid"] == 42  # o tenant vem SEMPRE da chave


def test_revogada_e_expirada_401(fake):
    rev, _ = fake.add(revoked_at=datetime.now(timezone.utc))
    exp, _ = fake.add(expires_at=datetime.now(timezone.utc) - timedelta(days=1))
    assert client.get("/v1/me", headers=_h(rev)).status_code == 401
    assert client.get("/v1/me", headers=_h(exp)).status_code == 401
    assert [log[4] for log in fake.logs] == [401, 401]


def test_tenant_suspenso_403(fake):
    chave, _ = fake.add(tenant_status="suspensa")
    assert client.get("/v1/me", headers=_h(chave)).status_code == 403


def test_allowlist_de_ip(fake):
    chave, _ = fake.add(ips_permitidos=["200.10.0.0/16"])
    ok = client.get("/v1/me", headers={**_h(chave), "X-Forwarded-For": "200.10.5.5, 10.0.0.2"})
    fora = client.get("/v1/me", headers={**_h(chave), "X-Forwarded-For": "8.8.8.8"})
    assert ok.status_code == 200 and fora.status_code == 403


def test_rate_limit_429(fake):
    chave, _ = fake.add(rate_limit_min=2)
    assert client.get("/v1/me", headers=_h(chave)).status_code == 200
    assert client.get("/v1/me", headers=_h(chave)).status_code == 200
    r = client.get("/v1/me", headers=_h(chave))
    assert r.status_code == 429 and int(r.headers["retry-after"]) >= 1


def test_assinatura_inativa_402(fake, monkeypatch):
    chave, _ = fake.add()
    monkeypatch.setattr(api_publica.billing, "assinatura_ativa", lambda tid: False)
    assert client.get("/v1/me", headers=_h(chave)).status_code == 402


def test_upsert_cliente_valida(fake, monkeypatch):
    chave, _ = fake.add(escopos=["clientes:escrever"])
    monkeypatch.setattr(store, "upsert_customer", lambda tid, tel, **d: {"telefone": tel, **d})
    assert client.put("/v1/clientes/5511999998888", json={"cnpj": "123"},
                      headers=_h(chave)).status_code == 422
    r = client.put("/v1/clientes/+55 (11) 99999-8888", json={"email": "a@b.com"},
                   headers=_h(chave))
    assert r.status_code == 200 and r.json() == {"telefone": "5511999998888", "email": "a@b.com"}


def test_fila_status_invalido_422(fake):
    chave, _ = fake.add(escopos=["fila:escrever"])
    r = client.patch("/v1/fila/1", json={"status": "xyz"}, headers=_h(chave))
    assert r.status_code == 422


# --- Gestão (painel) --------------------------------------------------------

def test_criar_chave_valida_escopos_e_ips(monkeypatch):
    monkeypatch.setattr(store, "api_uso_resumo", lambda tid: {"chaves_ativas": 0})
    criadas = []

    def fake_create(tid, nome, prefixo, h, escopos, ips, rate, exp, uid):
        criadas.append(h)
        return {"id": 1, "tenant_id": tid, "nome": nome, "prefixo": prefixo,
                "escopos": escopos, "ips_permitidos": ips}

    monkeypatch.setattr(store, "create_api_key", fake_create)
    assert client.post("/integracoes/chaves", json={"nome": "x", "escopos": ["nada"]}).status_code == 422
    assert client.post("/integracoes/chaves", json={"nome": "x", "escopos": []}).status_code == 422
    assert client.post("/integracoes/chaves", json={
        "nome": "x", "escopos": ["catalogo:ler"], "ips_permitidos": ["abc"]}).status_code == 422

    r = client.post("/integracoes/chaves", json={
        "nome": "ERP", "escopos": ["clientes:ler", "catalogo:ler", "catalogo:ler"],
        "ips_permitidos": ["10.0.0.1"], "expira_em_dias": 30})
    assert r.status_code == 201
    body = r.json()
    assert body["chave"].startswith("atb_live_") and body["tenant_id"] == 1
    assert body["escopos"] == ["catalogo:ler", "clientes:ler"]
    assert criadas == [api_publica.hash_chave(body["chave"])]  # só o hash persiste


def test_limite_de_chaves_409(monkeypatch):
    monkeypatch.setattr(store, "api_uso_resumo", lambda tid: {"chaves_ativas": 999})
    r = client.post("/integracoes/chaves", json={"nome": "x", "escopos": ["catalogo:ler"]})
    assert r.status_code == 409


def test_admin_integracoes_exige_staff():
    assert client.get("/admin/integracoes").status_code == 403


# --- Integração com DB ------------------------------------------------------

@requires_db
def test_ciclo_completo_com_db(db, tid):
    from app.db import execute

    execute("TRUNCATE api_request_log, api_keys RESTART IDENTITY CASCADE")
    api_publica.rate_limiter.limpar()
    outro = int((db.get_tenant_by_slug("api-b") or db.create_tenant("api-b", "API B"))["id"])
    db.upsert_customer(tid, "5511900000001", razao_social="Do tenant A")
    db.upsert_customer(outro, "5511900000002", razao_social="Do tenant B")

    r = client.post("/integracoes/chaves", json={"nome": "ERP", "escopos": ["clientes:ler"]})
    assert r.status_code == 201
    chave, key_id = r.json()["chave"], r.json()["id"]
    listadas = client.get("/integracoes/chaves").json()
    assert [k["id"] for k in listadas] == [key_id] and "key_hash" not in listadas[0]

    r = client.get("/v1/clientes", headers=_h(chave))
    assert r.status_code == 200
    assert [c["telefone"] for c in r.json()["items"]] == ["5511900000001"]
    assert client.get("/v1/clientes/5511900000002", headers=_h(chave)).status_code == 404

    # rotação: a antiga para de funcionar, a nova herda a configuração
    nova = client.post(f"/integracoes/chaves/{key_id}/rotacionar").json()
    assert nova["escopos"] == ["clientes:ler"]
    assert client.get("/v1/me", headers=_h(chave)).status_code == 401
    assert client.get("/v1/me", headers=_h(nova["chave"])).status_code == 200

    assert client.delete(f"/integracoes/chaves/{nova['id']}").status_code == 200
    assert client.get("/v1/me", headers=_h(nova["chave"])).status_code == 401

    logs = client.get("/integracoes/logs").json()
    assert logs["total"] >= 5 and {x["status"] for x in logs["items"]} >= {200, 401, 404}
    assert db.list_api_logs(outro)["total"] == 0
