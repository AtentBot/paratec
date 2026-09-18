"""Integração da camada de persistência contra o Postgres real (por tenant).
Pulado automaticamente quando não há banco (ver conftest)."""
from .conftest import requires_db


@requires_db
def test_fluxo_conversa_mensagens_eventos(db, tid):
    db.upsert_conversation(tid, "5511999", cliente="Marcos", telefone="5511999")
    db.add_message(tid, "5511999", "cliente", "Quero 20 hastes")
    db.log_event(tid, "mensagem_recebida", thread_id="5511999")
    db.add_message(tid, "5511999", "agente", "Registrei seu pedido", especialista="pedidos")
    db.log_event(tid, "roteou_especialista", thread_id="5511999", especialista="pedidos")

    conv = db.get_conversation(tid, "5511999")
    assert conv["cliente"] == "Marcos"
    assert conv["especialista"] == "pedidos"
    assert conv["unread"] == 1  # só a mensagem do cliente conta
    assert [m["role"] for m in conv["mensagens"]] == ["cliente", "agente"]


@requires_db
def test_lista_por_status_e_assumir(db, tid):
    db.upsert_conversation(tid, "t1", cliente="A")
    db.upsert_conversation(tid, "t2", cliente="B")
    db.assumir_conversation(tid, "t2")

    humanos = db.list_conversations(tid, status="humano")
    assert [c["thread_id"] for c in humanos] == ["t2"]
    assert db.get_conversation(tid, "t2")["status"] == "humano"


@requires_db
def test_fila_criacao_e_atualizacao(db, tid):
    item_id = db.add_queue_item(tid, "pedido", "12x captor", thread_id="t3", cliente="C")
    assert isinstance(item_id, int)

    abertos = db.list_queue(tid, status="novo")
    assert len(abertos) == 1

    atual = db.update_queue_item(tid, item_id, status="andamento", responsavel="Rafael")
    assert atual["status"] == "andamento"
    assert atual["responsavel"] == "Rafael"


@requires_db
def test_customers_por_telefones_filtra_elegiveis(db, tid):
    db.upsert_customer(tid, "5599001", razao_social="A", cnpj="1", email="a@a", nome_contato="A")
    db.upsert_customer(tid, "5599002", razao_social="B", cnpj="2", email="b@b", nome_contato="B")
    db.set_opt_out(tid, "5599002", True)
    db.upsert_customer(tid, "5599003", razao_social="C")  # pendente

    sel = db.customers_por_telefones(tid, ["5599001", "5599002", "5599003", "5599999"])
    assert {c["telefone"] for c in sel} == {"5599001"}
    assert db.customers_por_telefones(tid, []) == []


@requires_db
def test_broadcast_grava_e_lista_imagem(db, tid):
    bid = db.create_broadcast(tid, "Promo", 3, "tester", "/media/banner.png")
    assert isinstance(bid, int)
    b = db.list_broadcasts(tid)[0]
    assert b["texto"] == "Promo" and b["total"] == 3
    assert b["imagem"] == "/media/banner.png"

    db.create_broadcast(tid, "Só texto", 1)
    assert db.list_broadcasts(tid)[0]["imagem"] is None


@requires_db
def test_metricas_agregam_eventos(db, tid):
    db.upsert_conversation(tid, "m1")
    db.log_event(tid, "mensagem_recebida", thread_id="m1")
    db.log_event(tid, "roteou_especialista", thread_id="m1", especialista="produtos")
    db.log_event(tid, "handoff_humano", thread_id="m1")

    m = db.metrics_overview(tid)
    assert len(m["semana"]) == 7
    assert m["totais"]["atendimentos"] == 1
    assert m["totais"]["handoffs"] == 1
    assert m["totais"]["resolvidos_pct"] == 0
    assert {"nome": "produtos", "valor": 1} in m["especialistas"]
