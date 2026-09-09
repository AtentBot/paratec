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
def test_customers_por_telefones_filtra_elegiveis(db):
    # ativo elegível
    db.upsert_customer("5599001", razao_social="A", cnpj="1", email="a@a", nome_contato="A")
    # ativo, mas com opt-out
    db.upsert_customer("5599002", razao_social="B", cnpj="2", email="b@b", nome_contato="B")
    db.set_opt_out("5599002", True)
    # cadastro pendente (faltam campos -> status 'pendente')
    db.upsert_customer("5599003", razao_social="C")

    sel = db.customers_por_telefones(
        ["5599001", "5599002", "5599003", "5599999"]  # último nem existe
    )
    assert {c["telefone"] for c in sel} == {"5599001"}
    assert db.customers_por_telefones([]) == []


@requires_db
def test_broadcast_grava_e_lista_imagem(db):
    bid = db.create_broadcast("Promo", 3, "tester", "/media/banner.png")
    assert isinstance(bid, int)
    b = db.list_broadcasts()[0]
    assert b["texto"] == "Promo" and b["total"] == 3
    assert b["imagem"] == "/media/banner.png"

    # campanha só de texto: imagem NULL
    db.create_broadcast("Só texto", 1)
    assert db.list_broadcasts()[0]["imagem"] is None


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
