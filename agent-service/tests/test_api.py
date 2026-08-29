"""Wiring HTTP dos endpoints da tela adm. Sem DB: monkeypatcha a camada
`store`, validando apenas roteamento, parâmetros e serialização."""
from fastapi.testclient import TestClient

from app import evolution, main, store

client = TestClient(main.app)


def test_fila_repassa_filtros(monkeypatch):
    capturado = {}

    def fake_list_queue(tipo=None, status=None):
        capturado["tipo"] = tipo
        capturado["status"] = status
        return [{"id": 1, "tipo": "pedido", "resumo": "x", "status": "novo"}]

    monkeypatch.setattr(store, "list_queue", fake_list_queue)
    r = client.get("/fila?tipo=pedido&status=novo")
    assert r.status_code == 200
    assert r.json()[0]["id"] == 1
    assert capturado == {"tipo": "pedido", "status": "novo"}


def test_patch_fila_404(monkeypatch):
    monkeypatch.setattr(store, "update_queue_item", lambda *a, **k: None)
    r = client.patch("/fila/999", json={"status": "andamento"})
    assert r.status_code == 404


def test_conversa_404(monkeypatch):
    monkeypatch.setattr(store, "get_conversation", lambda tid: None)
    r = client.get("/conversas/inexistente")
    assert r.status_code == 404


def test_metrics_overview(monkeypatch):
    payload = {"semana": [], "especialistas": [], "totais": {"na_fila": 0}}
    monkeypatch.setattr(store, "metrics_overview", lambda: payload)
    r = client.get("/metrics/overview")
    assert r.status_code == 200
    assert r.json() == payload


def test_assumir_conversa(monkeypatch):
    monkeypatch.setattr(
        store, "assumir_conversation",
        lambda tid: {"thread_id": tid, "status": "humano", "mensagens": []},
    )
    r = client.post("/conversas/5511/assumir")
    assert r.status_code == 200
    assert r.json()["status"] == "humano"


def test_responder_envia_e_persiste(monkeypatch):
    enviados = {}
    monkeypatch.setattr(store, "get_conversation", lambda tid: {"thread_id": tid, "mensagens": []})
    monkeypatch.setattr(store, "add_message", lambda *a, **k: enviados.setdefault("msg", a))
    monkeypatch.setattr(store, "set_status", lambda *a, **k: None)
    monkeypatch.setattr(evolution, "enviar_texto", lambda tel, txt: enviados.update(tel=tel, txt=txt) or {})
    r = client.post("/conversas/5511/responder", json={"texto": "Olá!"})
    assert r.status_code == 200
    assert enviados["tel"] == "5511" and enviados["txt"] == "Olá!"


def test_responder_503_quando_evolution_off(monkeypatch):
    monkeypatch.setattr(store, "get_conversation", lambda tid: {"thread_id": tid, "mensagens": []})

    def boom(tel, txt):
        raise evolution.EvolutionError("não configurada")

    monkeypatch.setattr(evolution, "enviar_texto", boom)
    r = client.post("/conversas/5511/responder", json={"texto": "oi"})
    assert r.status_code == 503


def test_clientes_csv(monkeypatch):
    monkeypatch.setattr(
        store, "list_customers",
        lambda status=None, limit=100000: [
            {"telefone": "5511", "razao_social": "ACME", "cnpj": "1", "email": "a@a",
             "nome_contato": "Ana", "status": "ativo", "created_at": "2026-08-29"},
        ],
    )
    r = client.get("/clientes.csv")
    assert r.status_code == 200
    assert "text/csv" in r.headers["content-type"]
    assert "attachment" in r.headers.get("content-disposition", "")
    assert "razao_social" in r.text and "ACME" in r.text
