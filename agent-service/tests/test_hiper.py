"""Hiperpersonalização: contexto compacto do cliente + flag por agente."""
from app import agents
from .conftest import requires_db


@requires_db
def test_contexto_compacto_e_vazio(db, tid):
    db.upsert_customer(tid, "5511", razao_social="Alfa Ltda", cnpj="11.222.333/0001-81",
                       email="a@a.com", nome_contato="Ana")
    db.add_queue_item(tid, "pedido", "20 hastes de aterramento", thread_id="5511", telefone="5511")

    ctx = agents._montar_contexto(tid, "5511")
    assert "Alfa Ltda" in ctx
    assert "hastes" in ctx
    assert "CONTEXTO DO CLIENTE" in ctx

    # número sem histórico -> contexto vazio (não injeta nada, não gasta tokens)
    assert agents._montar_contexto(tid, "5599999") == ""


@requires_db
def test_flag_hiperpersonalizacao_no_agente(db, tid):
    a = db.create_agent(tid, "Comercial", None, None, None, ["catalogo", "pedidos"], True, True)
    assert a["hiperpersonalizacao"] is True
    upd = db.update_agent(tid, a["id"], hiperpersonalizacao=False)
    assert upd["hiperpersonalizacao"] is False


@requires_db
def test_contexto_isolado_por_tenant(db, tid):
    outro = int((db.get_tenant_by_slug("hp-b") or db.create_tenant("hp-b", "HP B"))["id"])
    db.upsert_customer(tid, "5511", razao_social="Empresa A", cnpj="1", email="a@a", nome_contato="A")
    db.add_queue_item(tid, "pedido", "pedido do A", thread_id="5511", telefone="5511")
    # mesmo número no outro tenant, sem histórico
    assert "pedido do A" in agents._montar_contexto(tid, "5511")
    assert agents._montar_contexto(outro, "5511") == ""
