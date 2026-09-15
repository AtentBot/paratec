"""Chamados de suporte: criação, mensagens, status (integração; pula sem DB)."""
from .conftest import requires_db


@requires_db
def test_fluxo_chamado(db, tid):
    t = db.create_ticket(tid, None, "Não recebo alertas", "problema_tecnico", "alta",
                         "Os vendedores não recebem o alerta de orçamento.")
    assert t["status"] == "aberto" and t["prioridade"] == "alta"

    # a descrição inicial vira a 1ª mensagem
    det = db.get_ticket(tid, t["id"])
    assert len(det["mensagens"]) == 1 and det["mensagens"][0]["autor"] == "cliente"

    # resposta do suporte move p/ em_andamento
    db.add_ticket_message(tid, t["id"], "suporte", "Estamos verificando.")
    det = db.get_ticket(tid, t["id"])
    assert det["status"] == "em_andamento"
    assert [m["autor"] for m in det["mensagens"]] == ["cliente", "suporte"]

    # cliente fecha; nova mensagem do cliente reabre
    db.set_ticket_status(tid, t["id"], "fechado")
    assert db.get_ticket(tid, t["id"])["status"] == "fechado"
    db.add_ticket_message(tid, t["id"], "cliente", "Voltou a acontecer.")
    assert db.get_ticket(tid, t["id"])["status"] == "aberto"

    # listagem só do tenant
    assert [x["id"] for x in db.list_tickets(tid)] == [t["id"]]


@requires_db
def test_chamados_isolados_por_tenant(db, tid):
    outro = int((db.get_tenant_by_slug("sup-b") or db.create_tenant("sup-b", "Sup B"))["id"])
    db.create_ticket(tid, None, "A", "duvida", "normal", "corpo A")
    db.create_ticket(outro, None, "B", "duvida", "normal", "corpo B")
    assert {t["assunto"] for t in db.list_tickets(tid)} == {"A"}
    assert {t["assunto"] for t in db.list_tickets(outro)} == {"B"}
