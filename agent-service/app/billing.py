"""Assinatura SaaS via Stripe (checkout SEM trial, webhook, cancelamento).

Padrão (inspirado, sem acoplamento, em implementações .NET conhecidas):
- Checkout Session mode=subscription, SEM trial → cobra a 1ª fatura na conclusão.
- Um único webhook (`/billing/webhook`) verifica assinatura e é idempotente.
- Cancelamento = cancel_at_period_end (mantém acesso até o fim do período).
- Enforcement: só tenant com assinatura ATIVA (com carência p/ past_due) acessa
  os endpoints operacionais e o bot.

O estado é espelhado na tabela `subscriptions` (store.upsert_subscription); a
Paratec tem uma assinatura "cortesia" semeada no schema, então nunca bloqueia.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException

from . import store
from .auth import TenantCtx, current_tenant
from .settings import settings

log = logging.getLogger("atentbot.billing")

# Catálogo de planos exibido na tela (valores do plano de negócios).
PLANOS = {
    "essencial": {
        "nome": "Essencial", "preco": 690,
        "descricao": "1 número · 1 agente · catálogo até 500 SKUs · 3 usuários.",
    },
    "profissional": {
        "nome": "Profissional", "preco": 1690,
        "descricao": "Até 3 números · multi-agente · equipe · broadcast · 8 usuários.",
    },
    "escala": {
        "nome": "Escala", "preco": 3900,
        "descricao": "Números ilimitados · WhatsApp API oficial · ERP · SLA.",
    },
}

STATUS_ATIVOS = {"active", "trialing"}


def _init_stripe():
    if not settings.stripe_configured:
        raise HTTPException(503, "billing não configurado")
    import stripe

    stripe.api_key = settings.stripe_secret_key
    return stripe


def _dt(ts) -> datetime | None:
    return datetime.fromtimestamp(ts, tz=timezone.utc) if ts else None


# --- Medição + reporte de consumo (pay-per-use) ---------------------------

def registrar_consumo(tenant_id: int, tipo: str, tokens: int, meta: dict | None = None) -> dict:
    """Registra o consumo (usage_events) e, se a cobrança metered estiver ligada,
    reporta ao Stripe. Best-effort: nunca quebra o fluxo do agente/ingestão.
    Retorna {tokens, custo_estimado}."""
    if tokens <= 0:
        return {"tokens": 0, "custo_estimado": 0.0}
    custo = settings.custo_tokens(tipo, tokens)
    try:
        store.record_usage(tenant_id, tipo, tokens, custo, meta)
    except Exception as e:  # pragma: no cover
        log.warning("record_usage falhou: %s", e)
    _reportar_stripe(tenant_id, tipo, tokens)
    return {"tokens": tokens, "custo_estimado": custo}


def _reportar_stripe(tenant_id: int, tipo: str, tokens: int) -> None:
    """Envia um evento de medidor ao Stripe (Billing Meters). Só roda se metered
    estiver configurado e o tenant tiver stripe_customer_id."""
    if not settings.metered_enabled:
        return
    event_name = settings.meter_event_name(tipo)
    if not event_name:
        return
    try:
        import stripe

        stripe.api_key = settings.stripe_secret_key
        t = store.get_tenant(tenant_id)
        cust = (t or {}).get("stripe_customer_id")
        if not cust:
            return  # sem customer no Stripe ainda (ex.: cortesia) — não reporta
        # value = tokens; o preço metered define o valor por token (unit_amount_decimal).
        stripe.billing.MeterEvent.create(
            event_name=event_name,
            payload={"stripe_customer_id": cust, "value": str(int(tokens))},
        )
    except Exception as e:  # pragma: no cover
        log.warning("reporte de consumo ao Stripe falhou (%s): %s", event_name, e)


# --- Enforcement ----------------------------------------------------------

def assinatura_ativa(tenant_id: int) -> bool:
    """True se o tenant pode operar (assinatura active/trialing, ou past_due
    dentro da carência). Sem billing configurado, tudo é liberado (dev)."""
    if not settings.stripe_configured:
        return True
    try:
        sub = store.get_subscription(tenant_id)
    except Exception:  # pragma: no cover
        return True  # falha de leitura não deve derrubar o serviço
    if not sub:
        return False
    status = (sub.get("status") or "").lower()
    if status in STATUS_ATIVOS:
        return True
    if status == "past_due":
        fim = sub.get("current_period_end")
        if fim:
            limite = fim + timedelta(days=settings.past_due_grace_days)
            return datetime.now(timezone.utc) <= limite
    return False


def require_active_subscription(tenant: TenantCtx = Depends(current_tenant)) -> TenantCtx:
    """Dependency dos endpoints operacionais: exige assinatura ativa (402)."""
    if not assinatura_ativa(tenant.tenant_id):
        raise HTTPException(402, "subscription_required")
    return tenant


# --- Consulta -------------------------------------------------------------

def status(tenant_id: int) -> dict:
    sub = None
    try:
        sub = store.get_subscription(tenant_id)
    except Exception:  # pragma: no cover
        pass
    if not sub:
        return {"tem_assinatura": False, "ativa": False, "status": "sem_assinatura",
                "plan": None, "cancel_at_period_end": False, "current_period_end": None}
    return {
        "tem_assinatura": True,
        "ativa": assinatura_ativa(tenant_id),
        "status": sub.get("status"),
        "plan": sub.get("plan"),
        "cancel_at_period_end": sub.get("cancel_at_period_end"),
        "current_period_end": sub.get("current_period_end"),
    }


def planos() -> list[dict]:
    """Planos disponíveis (só os que têm price id configurado no Stripe)."""
    disponiveis = settings.plan_prices
    return [
        {"id": pid, **meta, "disponivel": pid in disponiveis}
        for pid, meta in PLANOS.items()
    ]


def uso(tenant_id: int) -> dict:
    """Consumo pay-per-use do mês corrente (tokens + custo estimado em BRL) +
    eventos recentes + as tarifas usadas. Hoje é 'medir e mostrar' (não cobrado
    automaticamente ainda)."""
    from datetime import datetime, timezone

    resumo = store.usage_periodo(tenant_id)
    LABELS = {
        "chat": "Conversas (IA)",
        "rag_ingest_documento": "Indexação de documentos",
        "rag_ingest_catalogo": "Indexação de catálogo",
    }
    por_tipo = [
        {**t, "label": LABELS.get(t["tipo"], t["tipo"])}
        for t in resumo.get("por_tipo", [])
    ]
    return {
        "mes": datetime.now(timezone.utc).strftime("%Y-%m"),
        "tokens": resumo["tokens"],
        "custo": resumo["custo"],
        "eventos": resumo["eventos"],
        "por_tipo": por_tipo,
        "recentes": store.usage_recentes(tenant_id, 15),
        "cobranca_automatica": settings.metered_enabled,
        "precos": {
            "embedding_por_1k": settings.usage_preco_por_1k_tokens_embedding,
            "chat_por_1k": settings.usage_preco_por_1k_tokens_chat,
        },
    }


# --- Checkout -------------------------------------------------------------

def criar_checkout(tenant: TenantCtx, plano: str) -> str:
    """Cria a Checkout Session (assinatura, SEM trial) e devolve a URL."""
    stripe = _init_stripe()
    price_id = settings.plan_prices.get(plano)
    if not price_id:
        raise HTTPException(400, "plano inválido ou indisponível")

    t = store.get_tenant(tenant.tenant_id)
    if not t:
        raise HTTPException(404, "tenant não encontrado")

    customer_id = t.get("stripe_customer_id")
    if not customer_id:
        cust = stripe.Customer.create(
            email=tenant.email,
            name=t.get("nome"),
            metadata={"tenant_id": str(tenant.tenant_id)},
        )
        customer_id = cust["id"]
        store.set_tenant_stripe_customer(tenant.tenant_id, customer_id)

    # Plano base (quantidade 1) + itens metered (consumo, sem quantity) quando a
    # cobrança automática de extras está configurada.
    line_items = [{"price": price_id, "quantity": 1}]
    for mp in settings.metered_price_ids:
        line_items.append({"price": mp})

    sess = stripe.checkout.Session.create(
        mode="subscription",
        customer=customer_id,
        client_reference_id=str(tenant.tenant_id),
        line_items=line_items,
        # SEM trial: omitimos subscription_data.trial_* → cobra a 1ª fatura já.
        subscription_data={"metadata": {"tenant_id": str(tenant.tenant_id)}},
        success_url=settings.billing_success_url,
        cancel_url=settings.billing_cancel_url,
    )
    return sess["url"]


def cancelar(tenant_id: int, respostas: dict | None = None, comentario: str | None = None) -> dict:
    """Cancela ao fim do período (mantém acesso até current_period_end).
    Guarda a pesquisa de cancelamento (motivos + relato) antes de cancelar."""
    # Registra a pesquisa primeiro (não perde o feedback mesmo se algo falhar).
    try:
        store.record_cancellation_feedback(tenant_id, respostas, comentario)
    except Exception as e:  # pragma: no cover
        log.warning("registro da pesquisa de cancelamento falhou: %s", e)

    stripe = _init_stripe()
    sub = store.get_subscription(tenant_id)
    if not sub or not sub.get("stripe_subscription_id"):
        raise HTTPException(404, "sem assinatura ativa")
    stripe.Subscription.modify(sub["stripe_subscription_id"], cancel_at_period_end=True)
    store.upsert_subscription(tenant_id, cancel_at_period_end=True)
    return status(tenant_id)


def reativar(tenant_id: int) -> dict:
    """Desfaz um cancelamento agendado."""
    stripe = _init_stripe()
    sub = store.get_subscription(tenant_id)
    if not sub or not sub.get("stripe_subscription_id"):
        raise HTTPException(404, "sem assinatura")
    stripe.Subscription.modify(sub["stripe_subscription_id"], cancel_at_period_end=False)
    store.upsert_subscription(tenant_id, cancel_at_period_end=False)
    return status(tenant_id)


# --- Webhook --------------------------------------------------------------

def _plan_do_price(price_id: str | None) -> str | None:
    return settings.price_to_plan.get(price_id) if price_id else None


def _sync_subscription(sub_obj: dict) -> None:
    """Espelha um objeto de assinatura do Stripe na tabela subscriptions."""
    customer_id = sub_obj.get("customer")
    tenant_id = store.get_subscription_tenant_by_customer(customer_id) if customer_id else None
    if tenant_id is None:
        meta = sub_obj.get("metadata") or {}
        if meta.get("tenant_id"):
            tenant_id = int(meta["tenant_id"])
    if tenant_id is None:
        log.warning("webhook: assinatura sem tenant resolvível (customer=%s)", customer_id)
        return
    items = (sub_obj.get("items") or {}).get("data") or []
    price_id = items[0]["price"]["id"] if items else None
    store.upsert_subscription(
        tenant_id,
        stripe_subscription_id=sub_obj.get("id"),
        stripe_customer_id=customer_id,
        plan=_plan_do_price(price_id),
        stripe_price_id=price_id,
        status=sub_obj.get("status"),
        cancel_at_period_end=bool(sub_obj.get("cancel_at_period_end")),
        current_period_end=_dt(sub_obj.get("current_period_end")),
    )


def processar_webhook(payload: bytes, sig_header: str | None) -> dict:
    """Verifica a assinatura, ignora duplicados e processa o evento."""
    stripe = _init_stripe()
    if not settings.stripe_webhook_secret:
        raise HTTPException(503, "webhook secret não configurado")
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.stripe_webhook_secret
        )
    except Exception as e:
        raise HTTPException(400, f"assinatura inválida: {e}")

    # Idempotência: cada evento é processado uma única vez.
    try:
        if store.stripe_event_seen(event["id"], event.get("type")):
            return {"ignored": True}
    except Exception:  # pragma: no cover
        pass

    tipo = event["type"]
    obj = event["data"]["object"]

    if tipo == "checkout.session.completed":
        tenant_id = obj.get("client_reference_id")
        customer_id = obj.get("customer")
        sub_id = obj.get("subscription")
        if tenant_id:
            tid = int(tenant_id)
            if customer_id:
                store.set_tenant_stripe_customer(tid, customer_id)
            # Busca a assinatura completa p/ ter status/price/período.
            if sub_id:
                try:
                    full = stripe.Subscription.retrieve(sub_id)
                    _sync_subscription(dict(full))
                except Exception as e:  # pragma: no cover
                    log.warning("retrieve subscription %s falhou: %s", sub_id, e)
                    store.upsert_subscription(
                        tid, stripe_subscription_id=sub_id,
                        stripe_customer_id=customer_id, status="active",
                    )
    elif tipo in ("customer.subscription.created", "customer.subscription.updated",
                  "customer.subscription.deleted"):
        _sync_subscription(dict(obj))
    elif tipo in ("invoice.paid", "invoice.payment_succeeded", "invoice.payment_failed"):
        # O status vem via customer.subscription.updated; aqui reforçamos o período
        # quando a fatura tem a assinatura embutida.
        sub_id = obj.get("subscription")
        if sub_id:
            try:
                full = stripe.Subscription.retrieve(sub_id)
                _sync_subscription(dict(full))
            except Exception as e:  # pragma: no cover
                log.warning("retrieve subscription (invoice) %s falhou: %s", sub_id, e)

    return {"ok": True, "type": tipo}
