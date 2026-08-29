"""Wiring HTTP dos endpoints da tela adm. Sem DB: monkeypatcha a camada
`store`, validando apenas roteamento, parâmetros e serialização."""
from fastapi.testclient import TestClient

from app import main, store

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
