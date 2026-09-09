"""Wiring HTTP dos endpoints da tela adm. Sem DB: monkeypatcha a camada
`store`, validando apenas roteamento, parâmetros e serialização."""
import base64

from fastapi.testclient import TestClient

from app import evolution, main, store
from app.settings import settings

client = TestClient(main.app)

# PNG 1x1 válido, usado nos testes de banner.
_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+M8AAAMBAQDJ/pLvAAAAAElFTkSuQmCC"
)


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


# --- Promoções: upload de banner + broadcast --------------------------------

def test_broadcast_upload_salva_e_serve_imagem():
    up = client.post("/broadcast/upload", files={"file": ("b.png", _PNG, "image/png")})
    assert up.status_code == 200
    body = up.json()
    assert body["url"].startswith("/media/") and body["arquivo"].endswith(".png")
    # o arquivo é servido de volta idêntico pelo mount estático /media
    got = client.get(body["url"])
    assert got.status_code == 200 and got.content == _PNG


def test_broadcast_upload_rejeita_nao_imagem():
    r = client.post("/broadcast/upload", files={"file": ("x.txt", b"oi", "text/plain")})
    assert r.status_code == 422


def test_broadcast_422_sem_texto_e_sem_imagem():
    r = client.post("/broadcast", json={})
    assert r.status_code == 422


def test_broadcast_503_sem_evolution(monkeypatch):
    monkeypatch.setattr(settings, "evolution_api_url", "", raising=False)
    monkeypatch.setattr(settings, "evolution_api_key", "", raising=False)
    r = client.post("/broadcast", json={"texto": "oi"})
    assert r.status_code == 503


def test_broadcast_manual_com_banner_envia_midia(monkeypatch):
    """Seleção manual (telefones) + banner: envia mídia com o texto como legenda
    e grava a referência da imagem na campanha."""
    monkeypatch.setattr(settings, "evolution_api_url", "http://evo:8080", raising=False)
    monkeypatch.setattr(settings, "evolution_api_key", "k", raising=False)

    up = client.post("/broadcast/upload", files={"file": ("b.png", _PNG, "image/png")})
    url = up.json()["url"]

    capturado = {}
    monkeypatch.setattr(
        store, "customers_por_telefones",
        lambda tels: [{"telefone": "5511", "razao_social": "ACME", "nome_contato": "Ana"}],
    )
    monkeypatch.setattr(
        store, "create_broadcast",
        lambda texto, total, criado_por=None, imagem=None: capturado.update(
            texto=texto, total=total, imagem=imagem
        ) or 7,
    )
    monkeypatch.setattr(store, "bump_broadcast", lambda *a, **k: None)
    monkeypatch.setattr(store, "finish_broadcast", lambda *a, **k: None)

    envios = []
    monkeypatch.setattr(
        evolution, "enviar_midia",
        lambda tel, b64, **kw: envios.append((tel, kw.get("caption"), b64)) or {},
    )
    # garante que NÃO caiu no caminho de texto puro
    monkeypatch.setattr(evolution, "enviar_texto", lambda *a, **k: (_ for _ in ()).throw(AssertionError("deveria enviar mídia")))

    r = client.post(
        "/broadcast",
        json={"texto": "Promo", "imagem": url, "telefones": ["5511"]},
    )
    assert r.status_code == 200
    assert r.json()["total"] == 1
    # imagem gravada na campanha e mídia enviada com legenda == texto
    assert capturado["imagem"] == url and capturado["total"] == 1
    assert len(envios) == 1
    tel, caption, b64 = envios[0]
    assert tel == "5511" and caption == "Promo"
    assert base64.b64decode(b64) == _PNG


def test_broadcast_segmento_sem_imagem_envia_texto(monkeypatch):
    monkeypatch.setattr(settings, "evolution_api_url", "http://evo:8080", raising=False)
    monkeypatch.setattr(settings, "evolution_api_key", "k", raising=False)
    monkeypatch.setattr(
        store, "customers_para_broadcast",
        lambda seg: [{"telefone": "5522", "razao_social": "X", "nome_contato": "Y"}],
    )
    monkeypatch.setattr(store, "create_broadcast", lambda *a, **k: 8)
    monkeypatch.setattr(store, "bump_broadcast", lambda *a, **k: None)
    monkeypatch.setattr(store, "finish_broadcast", lambda *a, **k: None)

    envios = []
    monkeypatch.setattr(evolution, "enviar_texto", lambda tel, txt: envios.append((tel, txt)) or {})
    r = client.post("/broadcast", json={"texto": "Oferta", "segmento": "todos"})
    assert r.status_code == 200
    assert envios == [("5522", "Oferta")]
