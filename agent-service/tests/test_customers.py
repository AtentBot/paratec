"""Cadastro de clientes: store + ferramentas (integração; pula sem DB)."""
import json

from .conftest import requires_db


@requires_db
def test_cadastro_incremental_ativa_quando_completo(db):
    c = db.upsert_customer("5511", razao_social="Alvorada Ltda")
    assert c["status"] == "pendente"
    db.upsert_customer("5511", cnpj="11.222.333/0001-81")
    db.upsert_customer("5511", email="compras@alvorada.com")
    c = db.upsert_customer("5511", nome_contato="Patrícia")
    assert c["status"] == "ativo"
    assert db.cliente_ativo("5511") is True
    assert db.get_customer("5511")["razao_social"] == "Alvorada Ltda"


@requires_db
def test_lista_por_status(db):
    db.upsert_customer("a", razao_social="A")  # pendente
    db.upsert_customer(
        "b", razao_social="B", cnpj="11.222.333/0001-81",
        email="b@b.com", nome_contato="Bea",
    )  # ativo
    assert [c["telefone"] for c in db.list_customers(status="ativo")] == ["b"]


@requires_db
def test_ferramenta_cadastrar_valida_cnpj(db):
    from app.tools import cadastrar_cliente, verificar_cliente

    cfg = {"configurable": {"thread_id": "5599"}}

    v = json.loads(verificar_cliente.invoke({}, config=cfg))
    assert v["cadastrado"] is False and "cnpj" in v["faltam"]

    r = json.loads(cadastrar_cliente.invoke({"cnpj": "11.222.333/0001-80"}, config=cfg))
    assert r["ok"] is False and r["campo"] == "cnpj"  # DV inválido

    r = json.loads(cadastrar_cliente.invoke(
        {
            "razao_social": "São Jorge",
            "cnpj": "11222333000181",
            "email": "dep@sj.com",
            "nome_contato": "João",
        },
        config=cfg,
    ))
    assert r["concluido"] is True and r["status"] == "ativo"
    assert db.cliente_ativo("5599") is True
