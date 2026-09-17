"""Central admin: número DA PLATAFORMA que envia os códigos de verificação."""
import uuid

import pytest
from fastapi.testclient import TestClient

from app import auth, evolution, main
from app.settings import settings
from .conftest import requires_db

client = TestClient(main.app)


@pytest.fixture()
def evo(monkeypatch):
    """Evolution simulada; registra as chamadas."""
    chamadas = []
    monkeypatch.setattr(settings, "evolution_api_url", "http://evo")
    monkeypatch.setattr(settings, "evolution_api_key", "k")
    monkeypatch.setattr(settings, "whatsapp_verificacao_instancia", "")
    qr = {"base64": "data:image/png;base64,x", "code": "c", "pairing_code": None}
    monkeypatch.setattr(evolution, "criar_instancia",
                        lambda nome, webhook=True: chamadas.append(("criar", nome, webhook)) or qr)
    monkeypatch.setattr(evolution, "conectar_instancia", lambda nome: qr)
    monkeypatch.setattr(evolution, "status_instancia",
                        lambda nome: {"nome": nome, "estado": "conectado", "numero": "5511900000000", "perfil": "AtentBot"})
    monkeypatch.setattr(evolution, "enviar_texto",
                        lambda tel, txt, instancia=None: chamadas.append(("enviar", tel, instancia)))
    monkeypatch.setattr(evolution, "remover_instancia", lambda nome: chamadas.append(("remover", nome)))
    monkeypatch.setattr(evolution, "listar_instancias", lambda: [
        {"nome": "atentbot-verificacao", "estado": "conectado", "numero": None, "perfil": None},
        {"nome": "cliente-x", "estado": "conectado", "numero": None, "perfil": None},
    ])
    return chamadas


@pytest.fixture()
def staff():
    ctx = auth.TenantCtx(tenant_id=1, user_id=1, email="staff@atentbot.com", nome="Staff",
                         role="owner", is_staff=True)
    main.app.dependency_overrides[auth.current_admin] = lambda: ctx
    yield ctx
    main.app.dependency_overrides.pop(auth.current_admin, None)


def test_admin_exige_staff():
    # o override autouse injeta um tenant comum (não staff)
    assert client.get("/admin/whatsapp-verificacao").status_code == 403


@requires_db
def test_sincronizar_testar_e_remover(db, evo, staff):
    r = client.get("/admin/whatsapp-verificacao").json()
    assert r["instancia"] is None and r["origem"] is None

    r = client.post("/admin/whatsapp-verificacao", json={"nome": "AtentBot Verificacao"})
    assert r.status_code == 200 and r.json()["qrcode"]["base64"]
    assert ("criar", "atentbot-verificacao", False) in evo       # sem webhook

    r = client.get("/admin/whatsapp-verificacao").json()
    assert r["instancia"] == "atentbot-verificacao" and r["origem"] == "painel"
    assert r["estado"] == "conectado"
    assert auth.instancia_verificacao() == "atentbot-verificacao"

    r = client.post("/admin/whatsapp-verificacao/teste", json={"telefone": "(11) 98888-7777"})
    assert r.status_code == 200
    assert ("enviar", "5511988887777", "atentbot-verificacao") in evo

    # clientes não veem nem operam o número da plataforma
    db.register_instance(1, "cliente-x")
    nomes = [i["nome"] for i in client.get("/whatsapp/instancias").json()]
    assert nomes == ["cliente-x"]
    assert client.get("/whatsapp/instancias/atentbot-verificacao/status").status_code == 404
    assert client.post("/whatsapp/instancias", json={"nome": "atentbot-verificacao"}).status_code == 409

    assert client.delete("/admin/whatsapp-verificacao").status_code == 200
    assert ("remover", "atentbot-verificacao") in evo
    assert auth.instancia_verificacao() == ""


@requires_db
def test_nao_usa_instancia_de_cliente(db, evo, staff):
    db.register_instance(1, "numero-do-cliente")
    r = client.post("/admin/whatsapp-verificacao", json={"nome": "numero-do-cliente"})
    assert r.status_code == 409


@requires_db
def test_env_e_reserva(db, evo, staff, monkeypatch):
    monkeypatch.setattr(settings, "whatsapp_verificacao_instancia", "via-env")
    r = client.get("/admin/whatsapp-verificacao").json()
    assert r["instancia"] == "via-env" and r["origem"] == "ambiente"
    assert client.delete("/admin/whatsapp-verificacao").status_code == 409
    db.set_platform_setting(auth.CHAVE_INSTANCIA_VERIFICACAO, "via-painel")
    assert auth.instancia_verificacao() == "via-painel"               # painel tem prioridade


@requires_db
def test_tenant_so_ve_e_opera_as_proprias_instancias(db, evo):
    outro = db.create_tenant(f"outro-wa-{uuid.uuid4().hex[:6]}", "Outro WA")
    db.register_instance(outro["id"], "cliente-x")
    # tenant 1 (override autouse) não vê instância de outro tenant nem sem dono
    assert client.get("/whatsapp/instancias").json() == []
    assert client.get("/whatsapp/instancias/cliente-x/status").status_code == 404
    assert client.get("/whatsapp/instancias/sem-dono/status").status_code == 404
    assert client.delete("/whatsapp/instancias/sem-dono").status_code == 404
    db.register_instance(1, "minha")
    assert client.get("/whatsapp/instancias/minha/status").status_code == 200
