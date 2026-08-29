"""Integração da camada de persistência contra o Postgres real.
Pulado automaticamente quando não há banco (ver conftest)."""
from .conftest import requires_db


@requires_db
def test_fluxo_conversa_mensagens_eventos(db):
    db.upsert_conversation("5511999", cliente="Marcos", telefone="5511999")
    db.add_message("5511999", "cliente", "Quero 20 hastes")
    db.log_event("mensagem_recebida", thread_id="5511999")
    db.add_message("5511999", "agente", "Registrei seu pedido", especialista="pedidos")
    db.log_event("roteou_especialista", thread_id="5511999", especialista="pedidos")

    conv = db.get_conversation("5511999")
    assert conv["cliente"] == "Marcos"
    assert conv["especialista"] == "pedidos"
    assert conv["unread"] == 1  # só a mensagem do cliente conta
    assert [m["role"] for m in conv["mensagens"]] == ["cliente", "agente"]


@requires_db
def test_lista_por_status_e_assumir(db):
    db.upsert_conversation("t1", cliente="A")
    db.upsert_conversation("t2", cliente="B")
    db.assumir_conversation("t2")

    humanos = db.list_conversations(status="humano")
    assert [c["thread_id"] for c in humanos] == ["t2"]
    assert db.get_conversation("t2")["status"] == "humano"


@requires_db
def test_fila_criacao_e_atualizacao(db):
    item_id = db.add_queue_item("pedido", "12x captor", thread_id="t3", cliente="C")
    assert isinstance(item_id, int)

    abertos = db.list_queue(status="novo")
    assert len(abertos) == 1

    atual = db.update_queue_item(item_id, status="andamento", responsavel="Rafael")
    assert atual["status"] == "andamento"
    assert atual["responsavel"] == "Rafael"


@requires_db
def test_metricas_agregam_eventos(db):
    db.upsert_conversation("m1")
    db.log_event("mensagem_recebida", thread_id="m1")
    db.log_event("roteou_especialista", thread_id="m1", especialista="produtos")
    db.log_event("handoff_humano", thread_id="m1")

    m = db.metrics_overview()
    assert len(m["semana"]) == 7  # sempre 7 dias
    assert m["totais"]["atendimentos"] == 1
    assert m["totais"]["handoffs"] == 1
    assert m["totais"]["resolvidos_pct"] == 0  # 1 atendimento, 1 handoff
    assert {"nome": "produtos", "valor": 1} in m["especialistas"]
