"""Enforcement de assinatura (puro, sem Stripe/DB — store monkeypatchado)."""
from datetime import datetime, timedelta, timezone

from app import billing, store
from app.settings import settings
from .conftest import requires_db


def test_sem_billing_libera_tudo(monkeypatch):
    monkeypatch.setattr(settings, "stripe_secret_key", "", raising=False)
    assert billing.assinatura_ativa(1) is True


def test_status_gate(monkeypatch):
    monkeypatch.setattr(settings, "stripe_secret_key", "sk_test", raising=False)
    monkeypatch.setattr(store, "get_subscription",
                        lambda t: {"status": "active", "current_period_end": None})
    assert billing.assinatura_ativa(1) is True

    monkeypatch.setattr(store, "get_subscription",
                        lambda t: {"status": "canceled", "current_period_end": None})
    assert billing.assinatura_ativa(1) is False

    monkeypatch.setattr(store, "get_subscription", lambda t: None)
    assert billing.assinatura_ativa(1) is False


def test_past_due_carencia(monkeypatch):
    monkeypatch.setattr(settings, "stripe_secret_key", "sk_test", raising=False)
    monkeypatch.setattr(settings, "past_due_grace_days", 3, raising=False)

    dentro = datetime.now(timezone.utc) - timedelta(days=1)
    fora = datetime.now(timezone.utc) - timedelta(days=5)
    monkeypatch.setattr(store, "get_subscription",
                        lambda t: {"status": "past_due", "current_period_end": dentro})
    assert billing.assinatura_ativa(1) is True
    monkeypatch.setattr(store, "get_subscription",
                        lambda t: {"status": "past_due", "current_period_end": fora})
    assert billing.assinatura_ativa(1) is False


def test_planos_lista_os_tres():
    ids = {p["id"] for p in billing.planos()}
    assert ids == {"essencial", "profissional", "escala"}


def test_custo_tokens_por_fonte(monkeypatch):
    monkeypatch.setattr(settings, "usage_preco_por_1k_tokens_embedding", 0.02, raising=False)
    monkeypatch.setattr(settings, "usage_preco_por_1k_tokens_chat", 0.20, raising=False)
    assert settings.custo_tokens("rag_ingest_documento", 1000) == 0.02
    assert settings.custo_tokens("chat", 1000) == 0.20
    assert settings.custo_tokens("chat", 500) == 0.10


def test_metered_enabled_flag(monkeypatch):
    monkeypatch.setattr(settings, "stripe_secret_key", "sk_test", raising=False)
    monkeypatch.setattr(settings, "stripe_meter_indexacao", "", raising=False)
    monkeypatch.setattr(settings, "stripe_meter_conversa", "", raising=False)
    assert settings.metered_enabled is False
    monkeypatch.setattr(settings, "stripe_meter_indexacao", "m_idx", raising=False)
    monkeypatch.setattr(settings, "stripe_meter_conversa", "m_chat", raising=False)
    assert settings.metered_enabled is True


def test_registrar_consumo_mede_sem_stripe(monkeypatch):
    # metered desligado: registra o consumo mas NÃO chama o Stripe.
    monkeypatch.setattr(settings, "stripe_secret_key", "", raising=False)
    capt = {}
    monkeypatch.setattr(store, "record_usage",
                        lambda *a, **k: capt.setdefault("args", a))
    r = billing.registrar_consumo(1, "chat", 1500)
    assert r["tokens"] == 1500 and r["custo_estimado"] > 0
    assert "args" in capt
    # tokens <= 0 é ignorado
    capt.clear()
    r0 = billing.registrar_consumo(1, "chat", 0)
    assert r0["tokens"] == 0 and "args" not in capt


@requires_db
def test_usage_registro_e_resumo(db, tid):
    db.record_usage(tid, "chat", 1000, 0.20, meta={"thread_id": "x"})
    db.record_usage(tid, "rag_ingest_documento", 2000, 0.04)
    db.record_usage(tid, "chat", 0, 0.0)  # tokens<=0 é ignorado
    r = db.usage_periodo(tid)
    assert r["tokens"] == 3000
    assert round(r["custo"], 2) == 0.24
    assert r["eventos"] == 2
    assert {t["tipo"] for t in r["por_tipo"]} == {"chat", "rag_ingest_documento"}
    assert len(db.usage_recentes(tid)) == 2


# --- Preço base parametrizável (central admin) ------------------------------

class _FakeStripe:
    """Stripe mínimo p/ alterar_preco: registra as chamadas."""

    def __init__(self, sub_items):
        fake = self
        self.calls = []

        class Price:
            @staticmethod
            def retrieve(pid):
                return {"id": pid, "product": "prod_1", "currency": "brl",
                        "recurring": {"interval": "month", "interval_count": 1},
                        "lookup_key": "atentbot_essencial_mensal"}

            @staticmethod
            def create(**kw):
                fake.calls.append(("price.create", kw))
                return {"id": "price_novo"}

            @staticmethod
            def modify(pid, **kw):
                fake.calls.append(("price.modify", pid, kw))

        class Subscription:
            @staticmethod
            def retrieve(sid):
                return {"id": sid, "items": {"data": sub_items}}

            @staticmethod
            def modify(sid, **kw):
                fake.calls.append(("sub.modify", sid, kw))

        self.Price, self.Subscription = Price, Subscription


def _setup_alterar(monkeypatch, sub_items, subs):
    fake = _FakeStripe(sub_items)
    gravado = {}
    monkeypatch.setattr(settings, "stripe_secret_key", "sk_test", raising=False)
    monkeypatch.setattr(billing, "_init_stripe", lambda: fake)
    monkeypatch.setattr(store, "get_plan", lambda p: {
        "id": p, "nome": "Essencial", "preco": 690.0, "stripe_price_id": "price_velho",
        "stripe_product_id": None})
    monkeypatch.setattr(store, "plan_by_price_id",
                        lambda pid: "essencial" if pid in ("price_velho", "price_novo") else None)
    monkeypatch.setattr(store, "assinaturas_do_plano", lambda p: subs)
    monkeypatch.setattr(store, "upsert_subscription", lambda *a, **k: None)
    monkeypatch.setattr(store, "update_plan_price",
                        lambda plano, preco, **kw: gravado.update(plano=plano, preco=preco, **kw))
    monkeypatch.setattr(billing, "planos_admin", lambda: {"items": []})
    return fake, gravado


def test_alterar_preco_so_novos_checkouts(monkeypatch):
    fake, gravado = _setup_alterar(monkeypatch, [], [{"tenant_id": 5, "stripe_subscription_id": "sub_1"}])
    r = billing.alterar_preco("essencial", 790.5, False, "staff@dew")

    criado = [c for c in fake.calls if c[0] == "price.create"][0][1]
    assert criado["unit_amount"] == 79050 and criado["product"] == "prod_1"
    assert criado["transfer_lookup_key"] is True
    assert ("price.modify", "price_velho", {"active": False}) in fake.calls
    assert not any(c[0] == "sub.modify" for c in fake.calls)  # assinantes intocados
    assert gravado["stripe_price_id"] == "price_novo" and gravado["preco"] == 790.5
    assert gravado["stripe_price_id_anterior"] == "price_velho"
    assert r["resultado"]["assinaturas_migradas"] == 0


def test_alterar_preco_migra_existentes_sem_proracao(monkeypatch):
    items = [{"id": "si_meter", "price": {"id": "price_meter"}},
             {"id": "si_base", "price": {"id": "price_velho"}}]
    fake, gravado = _setup_alterar(monkeypatch, items, [{"tenant_id": 5, "stripe_subscription_id": "sub_1"}])
    r = billing.alterar_preco("essencial", 790, True, "staff@dew")

    mods = [c for c in fake.calls if c[0] == "sub.modify"]
    assert mods == [("sub.modify", "sub_1", {
        "items": [{"id": "si_base", "price": "price_novo"}], "proration_behavior": "none"})]
    assert r["resultado"]["assinaturas_migradas"] == 1 and gravado["migradas"] == 1


def test_alterar_preco_rejeita_zero(monkeypatch):
    import pytest
    from fastapi import HTTPException

    _setup_alterar(monkeypatch, [], [])
    with pytest.raises(HTTPException):
        billing.alterar_preco("essencial", 0, False, None)


def test_sync_subscription_usa_item_do_plano(monkeypatch):
    capt = {}
    monkeypatch.setattr(store, "get_subscription_tenant_by_customer", lambda c: 7)
    monkeypatch.setattr(store, "plan_by_price_id",
                        lambda pid: "escala" if pid == "price_escala_novo" else None)
    monkeypatch.setattr(store, "upsert_subscription", lambda t, **kw: capt.update(kw))
    billing._sync_subscription({
        "id": "sub_1", "customer": "cus_1", "status": "active",
        "items": {"data": [{"price": {"id": "price_meter"}},
                           {"price": {"id": "price_escala_novo"}}]},
    })
    assert capt["plan"] == "escala" and capt["stripe_price_id"] == "price_escala_novo"


@requires_db
def test_plans_store_e_historico():
    store.execute("DELETE FROM plan_price_history")
    store.execute("UPDATE plans SET preco = 690, stripe_price_id = NULL WHERE id = 'essencial'")
    assert [p["id"] for p in store.list_plans()] == ["essencial", "profissional", "escala"]
    p = store.update_plan_price(
        "essencial", 790.5, stripe_price_id="price_novo", stripe_product_id="prod_1",
        preco_anterior=690, stripe_price_id_anterior="price_velho",
        migradas=2, falhas=0, alterado_por="staff@dew")
    assert p["preco"] == 790.5 and p["stripe_price_id"] == "price_novo"
    assert store.plan_by_price_id("price_novo") == "essencial"
    assert store.plan_by_price_id("price_velho") == "essencial"   # antigo, via histórico
    assert store.plan_by_price_id("price_x") is None
    h = store.plan_price_history("essencial")
    assert h[0]["preco_anterior"] == 690 and h[0]["assinaturas_migradas"] == 2
    # a vitrine pública reflete o preço novo
    assert {x["id"]: x["preco"] for x in billing.planos()}["essencial"] == 790.5
    store.execute("DELETE FROM plan_price_history")
    store.execute("UPDATE plans SET preco = 690, stripe_price_id = NULL WHERE id = 'essencial'")


def test_webhook_aceita_objetos_do_sdk_stripe(monkeypatch):
    """stripe-python >= 12: StripeObject não é dict (regressão de dict(obj)/.get)."""
    import stripe

    monkeypatch.setattr(settings, "stripe_secret_key", "sk_test", raising=False)
    monkeypatch.setattr(settings, "stripe_webhook_secret", "whsec", raising=False)
    sub = {"object": "subscription", "id": "sub_1", "customer": "cus_1", "status": "active",
           "cancel_at_period_end": False, "metadata": {},
           "items": {"object": "list", "data": [
               {"id": "si_1", "current_period_end": 1_900_000_000,
                "price": {"object": "price", "id": "price_velho"}}]}}
    evento = stripe.StripeObject.construct_from(
        {"id": "evt_1", "type": "customer.subscription.updated", "data": {"object": sub}}, "k")
    monkeypatch.setattr(stripe.Webhook, "construct_event", lambda *a, **k: evento)
    monkeypatch.setattr(store, "stripe_event_seen", lambda *a: False)
    monkeypatch.setattr(store, "get_subscription_tenant_by_customer", lambda c: 3)
    monkeypatch.setattr(store, "plan_by_price_id", lambda pid: "essencial")
    capt = {}
    monkeypatch.setattr(store, "upsert_subscription", lambda t, **kw: capt.update(kw, tenant=t))

    assert billing.processar_webhook(b"{}", "sig")["ok"]
    assert capt["tenant"] == 3 and capt["plan"] == "essencial" and capt["status"] == "active"
    assert capt["current_period_end"] is not None  # veio do item (API nova)
