"""Webhooks de saída: assinatura, anti-SSRF, retry, disparo e gestão."""
import hashlib
import hmac
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app import main, store, webhooks
from app.settings import settings

from .conftest import requires_db

client = TestClient(main.app)


@pytest.fixture(autouse=True)
def _sem_espera(monkeypatch):
    monkeypatch.setattr(webhooks.time, "sleep", lambda s: None)
    monkeypatch.setattr(webhooks, "_agendar", lambda fn, *a: fn(*a))  # entrega inline


# --- Funções puras ----------------------------------------------------------

def test_assinatura_hmac_verificavel():
    corpo = b'{"a":1}'
    sig = webhooks.assinar("whsec_x", 1700000000, corpo)
    esperado = hmac.new(b"whsec_x", b"1700000000." + corpo, hashlib.sha256).hexdigest()
    assert sig == "sha256=" + esperado
    assert webhooks.novo_segredo().startswith("whsec_")


@pytest.mark.parametrize("url,ok", [
    ("http://8.8.8.8/hook", False),          # só https
    ("https://user:pw@8.8.8.8/hook", False),  # credenciais na URL
    ("https://127.0.0.1/hook", False),        # loopback
    ("https://10.0.0.5/hook", False),         # rede privada
    ("https://169.254.169.254/latest", False),  # metadata de cloud
    ("https://[::ffff:192.168.0.1]/x", False),  # IPv4 privado mapeado em IPv6
    ("https://localhost/hook", False),
    ("https://8.8.8.8/hook", True),
])
def test_validar_destino_bloqueia_ssrf(url, ok):
    assert (webhooks.validar_destino(url) is None) is ok


# --- Entrega ----------------------------------------------------------------

HOOK = {"id": 9, "tenant_id": 3, "url": "https://exemplo.com/hook", "segredo": "whsec_teste"}


@pytest.fixture()
def registro(monkeypatch):
    feitos = []
    monkeypatch.setattr(webhooks, "validar_destino", lambda url: None)
    monkeypatch.setattr(store, "registrar_entrega_webhook", lambda *a: feitos.append(a))
    return feitos


def test_entrega_assinada_sucesso(monkeypatch, registro):
    enviados = []

    def fake_post(url, corpo, headers):
        enviados.append((url, corpo, headers))
        return httpx.Response(200)

    monkeypatch.setattr(webhooks, "_post", fake_post)
    payload = webhooks.envelope(3, "orcamento.criado", {"id": 1})
    r = webhooks.entregar(HOOK, payload)
    assert r["sucesso"] and r["tentativas"] == 1

    url, corpo, h = enviados[0]
    assert json.loads(corpo)["evento"] == "orcamento.criado"
    assert h["X-AtentBot-Evento"] == "orcamento.criado" and h["X-AtentBot-Entrega"] == payload["id"]
    assert h["X-AtentBot-Assinatura"] == webhooks.assinar(
        "whsec_teste", int(h["X-AtentBot-Timestamp"]), corpo)
    # (webhook_id, tenant, evento_id, evento, payload, sucesso, status, tentativas, erro, ms, max)
    assert registro[0][:9] == (9, 3, payload["id"], "orcamento.criado", payload, True, 200, 1, None)


@pytest.mark.parametrize("resposta,tentativas", [
    (httpx.Response(500), 3),          # erro do servidor: tenta de novo
    (httpx.Response(429), 3),          # rate limit: tenta de novo
    (httpx.Response(404), 1),          # erro do receptor: não adianta repetir
    (httpx.ConnectError("recusado"), 3),
])
def test_retry(monkeypatch, registro, resposta, tentativas):
    def fake_post(*a):
        if isinstance(resposta, Exception):
            raise resposta
        return resposta

    monkeypatch.setattr(webhooks, "_post", fake_post)
    r = webhooks.entregar(HOOK, webhooks.envelope(3, "mensagem.recebida", {}))
    assert not r["sucesso"] and r["tentativas"] == tentativas and r["erro"]
    assert registro[0][5] is False


def test_destino_recusado_na_entrega_nao_envia(monkeypatch):
    monkeypatch.setattr(store, "registrar_entrega_webhook", lambda *a: None)
    monkeypatch.setattr(webhooks, "_post", lambda *a: pytest.fail("não deveria enviar"))
    hook = {**HOOK, "url": "https://127.0.0.1/x"}
    r = webhooks.entregar(hook, webhooks.envelope(3, "mensagem.recebida", {}))
    assert not r["sucesso"] and "recusado" in r["erro"] and r["tentativas"] == 1


def test_disparar_so_para_assinantes(monkeypatch):
    entregues = []
    monkeypatch.setattr(store, "webhooks_do_evento",
                        lambda tid, ev: [HOOK] if (tid, ev) == (3, "orcamento.criado") else [])
    monkeypatch.setattr(webhooks, "entregar", lambda h, p: entregues.append((h["id"], p["evento"], p["tenant_id"])))
    webhooks.disparar(3, "orcamento.criado", {"id": 1})
    webhooks.disparar(4, "orcamento.criado", {"id": 2})   # outro tenant: sem assinantes
    webhooks.disparar(3, "evento.inexistente", {})
    assert entregues == [(9, "orcamento.criado", 3)]


# --- Gestão -----------------------------------------------------------------

def test_criar_valida_url_e_eventos(monkeypatch):
    monkeypatch.setattr(store, "count_webhooks", lambda tid: 0)
    monkeypatch.setattr(store, "create_webhook",
                        lambda tid, url, desc, ev, seg, uid: {"id": 1, "tenant_id": tid, "url": url, "eventos": ev})
    r = client.post("/integracoes/webhooks", json={"url": "https://10.0.0.1/x", "eventos": ["orcamento.criado"]})
    assert r.status_code == 422 and "privada" in r.json()["detail"]
    r = client.post("/integracoes/webhooks", json={"url": "https://8.8.8.8/x", "eventos": ["nada"]})
    assert r.status_code == 422

    r = client.post("/integracoes/webhooks",
                    json={"url": "https://8.8.8.8/x", "eventos": ["orcamento.criado", "mensagem.recebida"]})
    assert r.status_code == 201
    assert r.json()["segredo"].startswith("whsec_") and r.json()["tenant_id"] == 1


def test_limite_de_webhooks(monkeypatch):
    monkeypatch.setattr(store, "count_webhooks", lambda tid: settings.webhook_max_por_tenant)
    r = client.post("/integracoes/webhooks", json={"url": "https://8.8.8.8/x", "eventos": ["orcamento.criado"]})
    assert r.status_code == 409


def test_testar_404_de_outro_tenant(monkeypatch):
    monkeypatch.setattr(store, "get_webhook", lambda tid, wid: None)
    monkeypatch.setattr(store, "get_webhook_segredo", lambda tid, wid: None)
    assert client.post("/integracoes/webhooks/77/testar").status_code == 404


# --- Integração com DB ------------------------------------------------------

@requires_db
def test_eventos_reais_e_autodesativacao(db, tid, monkeypatch):
    from app.db import execute

    execute("TRUNCATE webhook_entregas, webhooks RESTART IDENTITY CASCADE")
    monkeypatch.setattr(webhooks, "validar_destino", lambda url: None)
    recebidos = []
    status = {"code": 200}

    def fake_post(url, corpo, headers):
        recebidos.append(json.loads(corpo)["evento"])
        return httpx.Response(status["code"])

    monkeypatch.setattr(webhooks, "_post", fake_post)

    r = client.post("/integracoes/webhooks", json={
        "url": "https://erp.exemplo.com/hook",
        "eventos": ["orcamento.criado", "conversa.transferida_humano", "cliente.cadastro_completo"]})
    assert r.status_code == 201
    wid = r.json()["id"]

    db.upsert_conversation(tid, "5511911110000", "Cliente", "5511911110000", None)
    db.add_message(tid, "5511911110000", "cliente", "oi")            # não assinado
    db.add_queue_item(tid, "pedido", "orçamento de cabos", "5511911110000")
    db.add_queue_item(tid, "boleto", "2ª via", "5511911110000")        # fila.item_criado: não assinado
    db.set_status(tid, "5511911110000", "humano")
    db.set_status(tid, "5511911110000", "humano")                    # sem transição: não emite
    db.upsert_customer(tid, "5511911110000", razao_social="ACME", cnpj="11222333000181")
    db.upsert_customer(tid, "5511911110000", email="a@acme.com", nome_contato="Ana")
    db.upsert_customer(tid, "5511911110000", nome_contato="Ana Maria")  # já ativo: não emite
    assert recebidos == ["orcamento.criado", "conversa.transferida_humano", "cliente.cadastro_completo"]

    ent = client.get(f"/integracoes/webhooks/entregas?webhook_id={wid}").json()
    assert ent["total"] == 3 and all(e["sucesso"] for e in ent["items"])

    # reenvio mantém o id do evento
    primeira = ent["items"][-1]
    r = client.post(f"/integracoes/webhooks/entregas/{primeira['id']}/reenviar")
    assert r.status_code == 200 and r.json()["sucesso"]

    # falhas seguidas desativam o webhook
    monkeypatch.setattr(settings, "webhook_max_falhas", 2)
    status["code"] = 500
    db.add_queue_item(tid, "pedido", "x", "5511911110000")
    db.add_queue_item(tid, "pedido", "y", "5511911110000")
    h = db.get_webhook(tid, wid)
    assert h["ativo"] is False and "2 falhas" in h["desativado_motivo"]

    # reativar manualmente zera as falhas
    r = client.patch(f"/integracoes/webhooks/{wid}", json={"ativo": True})
    assert r.json()["ativo"] and r.json()["falhas_consecutivas"] == 0 and r.json()["desativado_motivo"] is None

    # isolamento: outro tenant não vê nem dispara este webhook
    outro = int((db.get_tenant_by_slug("wh-b") or db.create_tenant("wh-b", "WH B"))["id"])
    assert db.list_webhooks(outro) == [] and db.webhooks_do_evento(outro, "orcamento.criado") == []
