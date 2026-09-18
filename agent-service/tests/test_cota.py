"""Cota de mensagens por plano + pacotes avulsos pré-pagos."""
from datetime import datetime, timedelta, timezone

import pytest

from app import agents, billing, store
from app.settings import settings
from .conftest import requires_db

AGORA = datetime.now(timezone.utc)


# --- Janela do ciclo -----------------------------------------------------------

def test_periodo_usa_ciclo_do_stripe():
    ini, fim = AGORA - timedelta(days=10), AGORA + timedelta(days=20)
    assert billing.periodo_cota({"current_period_start": ini, "current_period_end": fim}) == (ini, fim)


def test_periodo_sem_inicio_deriva_um_mes_antes_do_fim():
    fim = AGORA + timedelta(days=5)
    ini, f = billing.periodo_cota({"current_period_end": fim})
    assert f == fim and ini <= AGORA and (fim - ini).days in (28, 29, 30, 31)


@pytest.mark.parametrize("sub", [None, {}, {"current_period_end": AGORA + timedelta(days=36500)}])
def test_periodo_sem_ciclo_conhecido_usa_mes_civil(sub):
    ini, fim = billing.periodo_cota(sub)
    assert ini.day == 1 and ini.hour == 0 and ini <= AGORA < fim and fim.day == 1


def test_menos_um_mes_ajusta_fim_de_mes():
    assert billing._menos_um_mes(datetime(2026, 3, 31, tzinfo=timezone.utc)).day == 28
    assert billing._menos_um_mes(datetime(2026, 1, 15, tzinfo=timezone.utc)).month == 12


# --- Cálculo da cota (store monkeypatchado) -----------------------------------

def _cota(monkeypatch, *, usadas, pacotes=(), sub_id="sub_1", plano="essencial", ativa=True):
    monkeypatch.setattr(settings, "stripe_secret_key", "sk_test", raising=False)
    monkeypatch.setattr(settings, "cota_mensagens_ativa", ativa, raising=False)
    monkeypatch.setattr(store, "get_subscription", lambda t: {
        "plan": plano, "stripe_subscription_id": sub_id,
        "current_period_start": AGORA - timedelta(days=3),
        "current_period_end": AGORA + timedelta(days=27)})
    monkeypatch.setattr(store, "get_plan", lambda p: {"id": p, "mensagens_incluidas": 1000})
    monkeypatch.setattr(store, "pacotes_validos",
                        lambda t: [{"mensagens": m, "valido_ate": AGORA} for m in pacotes])
    monkeypatch.setattr(store, "mensagens_ia_desde", lambda t, ini: usadas)
    return billing.cota(1)


def test_cota_dentro_do_limite(monkeypatch):
    c = _cota(monkeypatch, usadas=999)
    assert c["limite"] == 1000 and c["restantes"] == 1 and not c["esgotada"]


def test_cota_esgota_no_limite(monkeypatch):
    c = _cota(monkeypatch, usadas=1000)
    assert c["esgotada"] and c["restantes"] == 0 and c["percentual"] == 100.0
    assert billing.pode_responder(1) is False


def test_pacote_soma_ao_limite(monkeypatch):
    c = _cota(monkeypatch, usadas=1200, pacotes=(500,))
    assert c["limite"] == 1500 and c["pacotes"] == 500 and not c["esgotada"]


def test_cortesia_sem_stripe_e_ilimitada(monkeypatch):
    c = _cota(monkeypatch, usadas=50_000, sub_id=None)
    assert c["ilimitado"] and not c["esgotada"]


def test_cota_desligada_libera(monkeypatch):
    assert not _cota(monkeypatch, usadas=50_000, ativa=False)["esgotada"]


def test_plano_com_cota_zero_esgota(monkeypatch):
    monkeypatch.setattr(settings, "stripe_secret_key", "sk_test", raising=False)
    monkeypatch.setattr(store, "get_plan", lambda p: {"id": p, "mensagens_incluidas": 0})
    assert billing._mensagens_do_plano("essencial") == 0


# --- Avisos de 80% / 100% ----------------------------------------------------

def test_aviso_dispara_uma_vez_por_nivel(monkeypatch):
    from app import mailer

    enviados, vistos = [], set()
    monkeypatch.setattr(billing, "cota", lambda t: {
        "ilimitado": False, "limite": 1000, "usadas": 820, "percentual": 82.0,
        "periodo_inicio": AGORA, "periodo_fim": AGORA + timedelta(days=9)})

    def registrar(t, ini, nivel, limite):
        novo = (nivel, limite) not in vistos
        vistos.add((nivel, limite))
        return novo

    monkeypatch.setattr(store, "registrar_alerta_cota", registrar)
    monkeypatch.setattr(store, "emails_owners", lambda t: ["dono@loja.com"])
    monkeypatch.setattr(store, "log_event", lambda *a, **k: None)
    monkeypatch.setattr(mailer, "enviar", lambda to, assunto, corpo: enviados.append((to, assunto, corpo)))

    billing.verificar_alertas_cota(1)
    billing.verificar_alertas_cota(1)
    assert len(enviados) == 1
    assert "80%" in enviados[0][1] and "820 de 1.000" in enviados[0][2]


# --- Webhook de pacote --------------------------------------------------------

def _webhook(monkeypatch, tipo, obj):
    import stripe

    monkeypatch.setattr(settings, "stripe_secret_key", "sk_test", raising=False)
    monkeypatch.setattr(settings, "stripe_webhook_secret", "whsec", raising=False)
    evento = stripe.StripeObject.construct_from(
        {"id": "evt_p", "type": tipo, "data": {"object": obj}}, "k")
    monkeypatch.setattr(stripe.Webhook, "construct_event", lambda *a, **k: evento)
    monkeypatch.setattr(store, "stripe_event_seen", lambda *a: False)
    fim = AGORA + timedelta(days=12)
    monkeypatch.setattr(store, "get_subscription", lambda t: {
        "current_period_start": AGORA - timedelta(days=18), "current_period_end": fim})
    capt = {}
    monkeypatch.setattr(store, "confirmar_pack_purchase",
                        lambda cid, t, ate: capt.update(compra=cid, tenant=t, ate=ate) or {"id": cid})
    monkeypatch.setattr(store, "falhar_pack_purchase", lambda cid, t: capt.update(falhou=cid))
    monkeypatch.setattr(store, "log_event", lambda *a, **k: None)
    monkeypatch.setattr(store, "upsert_subscription",
                        lambda *a, **k: pytest.fail("pacote não mexe na assinatura"))
    billing.processar_webhook(b"{}", "sig")
    return capt, fim


_SESSAO = {"object": "checkout.session", "id": "cs_1", "mode": "payment", "customer": "cus_1",
           "client_reference_id": "4",
           "metadata": {"tipo": billing.TIPO_PACOTE, "tenant_id": "4", "compra_id": "77"}}


def test_webhook_pacote_pago_credita_ate_o_fim_do_ciclo(monkeypatch):
    capt, fim = _webhook(monkeypatch, "checkout.session.completed",
                         {**_SESSAO, "payment_status": "paid"})
    assert capt == {"compra": 77, "tenant": 4, "ate": fim}


def test_webhook_pix_pendente_so_credita_na_confirmacao(monkeypatch):
    capt, _ = _webhook(monkeypatch, "checkout.session.completed",
                       {**_SESSAO, "payment_status": "unpaid"})
    assert capt == {}
    capt, _ = _webhook(monkeypatch, "checkout.session.async_payment_succeeded",
                       {**_SESSAO, "payment_status": "paid"})
    assert capt["compra"] == 77


def test_webhook_pix_falhou(monkeypatch):
    capt, _ = _webhook(monkeypatch, "checkout.session.async_payment_failed",
                       {**_SESSAO, "payment_status": "unpaid"})
    assert capt == {"falhou": 77}


# --- Checkout de pacote -------------------------------------------------------

def test_checkout_pacote_preco_inline_e_metadata(monkeypatch):
    from app.auth import TenantCtx

    criado = {}

    class _Stripe:
        class checkout:
            class Session:
                @staticmethod
                def create(**kw):
                    criado.update(kw)
                    return {"id": "cs_9", "url": "https://checkout/cs_9"}

    monkeypatch.setattr(billing, "_init_stripe", lambda: _Stripe)
    monkeypatch.setattr(billing, "assinatura_ativa", lambda t: True)
    monkeypatch.setattr(billing, "_garantir_customer", lambda s, t: "cus_1")
    monkeypatch.setattr(store, "get_message_pack", lambda pid: {
        "id": pid, "nome": "+1.000 mensagens", "mensagens": 1000, "preco": 69.0, "ativo": True})
    monkeypatch.setattr(store, "create_pack_purchase", lambda t, p, por: 42)
    sess = {}
    monkeypatch.setattr(store, "set_pack_purchase_session", lambda cid, sid: sess.update({cid: sid}))

    t = TenantCtx(tenant_id=4, user_id=1, email="dono@loja.com", nome=None, role="owner")
    assert billing.criar_checkout_pacote(t, "p1000") == "https://checkout/cs_9"
    assert criado["mode"] == "payment"
    assert criado["line_items"][0]["price_data"]["unit_amount"] == 6900
    assert criado["metadata"] == {"tipo": billing.TIPO_PACOTE, "tenant_id": "4", "compra_id": "42"}
    assert sess == {42: "cs_9"}


def test_checkout_pacote_inativo_recusa(monkeypatch):
    from fastapi import HTTPException

    monkeypatch.setattr(billing, "_init_stripe", lambda: object())
    monkeypatch.setattr(billing, "assinatura_ativa", lambda t: True)
    monkeypatch.setattr(store, "get_message_pack", lambda pid: {"id": pid, "ativo": False})

    class T:
        tenant_id, email = 4, "x@y"

    with pytest.raises(HTTPException) as e:
        billing.criar_checkout_pacote(T, "p500")
    assert e.value.status_code == 400


# --- Agente com cota esgotada -------------------------------------------------

def test_agente_com_cota_esgotada_nao_chama_ia(monkeypatch):
    chamadas = []
    monkeypatch.setattr(agents, "_resolver_tenant", lambda inst: (4, "Loja"))
    monkeypatch.setattr(billing, "assinatura_ativa", lambda t: True)
    monkeypatch.setattr(billing, "pode_responder", lambda t: False)
    monkeypatch.setattr(billing, "verificar_alertas_cota", lambda t: chamadas.append("alerta"))
    for fn in ("upsert_conversation", "add_message", "log_event"):
        monkeypatch.setattr(store, fn, lambda *a, _fn=fn, **k: chamadas.append((_fn, a[2:4])))
    monkeypatch.setattr(store, "get_status", lambda t, th: "ia")
    monkeypatch.setattr(store, "set_status", lambda t, th, st: chamadas.append(("status", st)))
    monkeypatch.setattr(agents, "_cfg_para", lambda *a: pytest.fail("não deveria chamar a IA"))

    resp = agents.responder("oi, tem cabo?", "5511999990000", instancia="loja")
    assert resp == settings.cota_esgotada_mensagem
    assert ("status", "humano") in chamadas and "alerta" in chamadas
    assert ("add_message", ("agente", settings.cota_esgotada_mensagem)) in chamadas


# --- Persistência (Postgres) ---------------------------------------------------

@requires_db
def test_seed_de_planos_e_pacotes(db):
    cotas = {p["id"]: p["mensagens_incluidas"] for p in db.list_plans()}
    assert cotas == {"essencial": 1000, "profissional": 3000, "escala": 10000}
    assert [p["id"] for p in db.list_message_packs()] == ["p500", "p1000", "p3000"]


@requires_db
def test_compra_de_pacote_ponta_a_ponta(db, tid):
    db.execute("DELETE FROM message_pack_purchases")
    pack = db.get_message_pack("p500")
    cid = db.create_pack_purchase(tid, pack, "dono@loja.com")
    db.set_pack_purchase_session(cid, "cs_teste")
    assert db.pacotes_validos(tid) == []          # pendente não conta
    ate = AGORA + timedelta(days=10)
    assert db.confirmar_pack_purchase(cid, tid, ate)
    assert db.confirmar_pack_purchase(cid, tid, ate) is None   # idempotente
    assert db.confirmar_pack_purchase(cid, tid + 999, ate) is None  # outro tenant
    validos = db.pacotes_validos(tid)
    assert [p["mensagens"] for p in validos] == [500]
    db.execute("UPDATE message_pack_purchases SET valido_ate = now() - interval '1 second'")
    assert db.pacotes_validos(tid) == []          # expirou com o ciclo
    db.execute("DELETE FROM message_pack_purchases")


@requires_db
def test_contagem_de_mensagens_e_alerta_unico(db, tid):
    inicio = AGORA - timedelta(minutes=1)
    db.record_usage(tid, "chat", 900, 0.01)
    db.record_usage(tid, "chat", 1200, 0.01)
    db.record_usage(tid, "rag_ingest_documento", 5000, 0.01)   # indexação não conta
    assert db.mensagens_ia_desde(tid, inicio) == 2
    db.execute("DELETE FROM message_quota_alerts")
    assert db.registrar_alerta_cota(tid, inicio, 80, 1000) is True
    assert db.registrar_alerta_cota(tid, inicio, 80, 1000) is False
    assert db.registrar_alerta_cota(tid, inicio, 80, 1500) is True  # comprou pacote: rearma
    db.execute("DELETE FROM message_quota_alerts")


@requires_db
def test_editar_cota_e_pacote(db):
    antes = db.get_plan("essencial")["mensagens_incluidas"]
    db.set_plan_mensagens("essencial", 1234, "staff@dew")
    assert db.get_plan("essencial")["mensagens_incluidas"] == 1234
    db.set_plan_mensagens("essencial", antes, None)
    p = billing.alterar_pacote("p500", mensagens=600, preco=45.5, ativo=None, alterado_por="staff")
    k = next(x for x in p["pacotes"] if x["id"] == "p500")
    assert (k["nome"], k["mensagens"], k["preco"]) == ("+600 mensagens", 600, 45.5)
    billing.alterar_pacote("p500", mensagens=500, preco=39, ativo=None, alterado_por=None)
