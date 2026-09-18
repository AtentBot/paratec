"""Isolamento multi-tenant: dois tenants NUNCA enxergam os dados um do outro,
mesmo compartilhando o mesmo número de WhatsApp (thread_id). Pula sem DB."""
from .conftest import requires_db


def _tenant_b(db):
    t = db.get_tenant_by_slug("tenant-b") or db.create_tenant("tenant-b", "Tenant B")
    return int(t["id"])


@requires_db
def test_conversas_e_mensagens_isoladas(db, tid):
    ob = _tenant_b(db)
    # Mesmo número em dois tenants (PK composta permite).
    db.upsert_conversation(tid, "5511", cliente="Cliente A")
    db.upsert_conversation(ob, "5511", cliente="Cliente B")
    db.add_message(tid, "5511", "cliente", "oi A")
    db.add_message(ob, "5511", "cliente", "oi B")

    a = db.get_conversation(tid, "5511")
    b = db.get_conversation(ob, "5511")
    assert a["cliente"] == "Cliente A" and b["cliente"] == "Cliente B"
    assert [m["content"] for m in a["mensagens"]] == ["oi A"]
    assert [m["content"] for m in b["mensagens"]] == ["oi B"]


@requires_db
def test_customers_e_fila_isolados(db, tid):
    ob = _tenant_b(db)
    db.upsert_customer(tid, "5511", razao_social="Empresa A", cnpj="1", email="a@a", nome_contato="A")
    db.upsert_customer(ob, "5511", razao_social="Empresa B", cnpj="2", email="b@b", nome_contato="B")
    db.add_queue_item(tid, "pedido", "pedido A", thread_id="5511")
    db.add_queue_item(ob, "pedido", "pedido B", thread_id="5511")

    assert db.get_customer(tid, "5511")["razao_social"] == "Empresa A"
    assert db.get_customer(ob, "5511")["razao_social"] == "Empresa B"
    assert [i["resumo"] for i in db.list_queue(tid)] == ["pedido A"]
    assert [i["resumo"] for i in db.list_queue(ob)] == ["pedido B"]
    # listagem de clientes não cruza
    assert {c["telefone"] for c in db.list_customers(tid)} == {"5511"}
    assert len(db.list_customers(tid)) == 1 and len(db.list_customers(ob)) == 1
