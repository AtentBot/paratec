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
