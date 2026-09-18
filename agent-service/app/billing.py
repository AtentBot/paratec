"""Assinatura SaaS via Stripe (checkout SEM trial, webhook, cancelamento).

Padrão (inspirado, sem acoplamento, em implementações .NET conhecidas):
- Checkout Session mode=subscription, SEM trial → cobra a 1ª fatura na conclusão.
- Um único webhook (`/billing/webhook`) verifica assinatura e é idempotente.
- Cancelamento = cancel_at_period_end (mantém acesso até o fim do período).
- Enforcement: só tenant com assinatura ATIVA (com carência p/ past_due) acessa
  os endpoints operacionais e o bot.
- Cota: cada plano inclui N respostas da IA por ciclo; acima disso o cliente
  compra pacotes avulsos (Checkout mode=payment, pré-pago, válidos até o fim do
  ciclo). Sem saldo, a IA para e a conversa vai para a fila humana.

O estado é espelhado na tabela `subscriptions` (store.upsert_subscription); a
Paratec tem uma assinatura "cortesia" semeada no schema, então nunca bloqueia.
"""
from __future__ import annotations

import calendar
import logging
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException

from . import store
from .auth import TenantCtx, current_tenant
from .settings import settings

log = logging.getLogger("atentbot.billing")

# Catálogo padrão dos planos. A fonte de verdade do PREÇO é a tabela `plans`
# (editável na central admin); isto é só fallback se o banco estiver fora.
PLANOS = {
    "essencial": {
        "nome": "Essencial", "preco": 99, "mensagens_incluidas": 1000,
        "descricao": "1 número · 1 agente · catálogo até 500 SKUs · 3 usuários.",
    },
    "profissional": {
        "nome": "Profissional", "preco": 249, "mensagens_incluidas": 3000,
        "descricao": "Até 3 números · multi-agente · equipe · broadcast · 8 usuários.",
    },
    "escala": {
        "nome": "Escala", "preco": 599, "mensagens_incluidas": 10000,
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


def _plain(obj):
    """Objeto do SDK do Stripe -> dict puro (recursivo). Desde o stripe-python
    v12 os StripeObject não são mais dict: `.get()`/`dict(obj)` quebram."""
    return obj.to_dict() if hasattr(obj, "to_dict") else obj


def _dt(ts) -> datetime | None:
    return datetime.fromtimestamp(ts, tz=timezone.utc) if ts else None


# --- Medição de consumo (custo interno de tokens) --------------------------

def registrar_consumo(tenant_id: int, tipo: str, tokens: int, meta: dict | None = None) -> dict:
    """Registra o consumo de tokens (usage_events). O cliente não paga por token:
    o evento 'chat' conta como 1 mensagem da cota e os tokens viram só custo
    interno. Best-effort: nunca quebra o fluxo do agente/ingestão."""
    if tokens <= 0:
        return {"tokens": 0, "custo_estimado": 0.0}
    custo = settings.custo_tokens(tipo, tokens)
    try:
        store.record_usage(tenant_id, tipo, tokens, custo, meta)
    except Exception as e:  # pragma: no cover
        log.warning("record_usage falhou: %s", e)
    return {"tokens": tokens, "custo_estimado": custo}


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


def _planos_db() -> list[dict]:
    try:
        rows = store.list_plans()
    except Exception as e:  # pragma: no cover
        log.warning("list_plans falhou, usando catálogo padrão: %s", e)
        rows = []
    if not rows:
        return [{"id": pid, **meta, "stripe_price_id": None} for pid, meta in PLANOS.items()]
    return rows


def price_id_do_plano(plano: str, plano_db: dict | None = None) -> str | None:
    """Price id vigente: o gravado pelo admin (tabela plans) ou a env STRIPE_PRICE_*."""
    if plano_db is None:
        try:
            plano_db = store.get_plan(plano)
        except Exception:  # pragma: no cover
            plano_db = None
    return (plano_db or {}).get("stripe_price_id") or settings.plan_prices.get(plano)


def _incluidas(plano_db: dict) -> int:
    n = plano_db.get("mensagens_incluidas")
    return int(n) if n is not None else PLANOS.get(plano_db["id"], {}).get("mensagens_incluidas", 0)


def _mensagens_do_plano(plano: str | None) -> int:
    pid = plano if plano in PLANOS else "essencial"
    try:
        p = store.get_plan(pid)
    except Exception:  # pragma: no cover
        p = None
    return _incluidas(p or {"id": pid})


def planos() -> list[dict]:
    """Planos com o preço vigente (só 'disponivel' os que têm price id no Stripe)."""
    return [
        {
            "id": p["id"], "nome": p["nome"], "preco": float(p["preco"]),
            "descricao": p.get("descricao") or "",
            "mensagens_incluidas": _incluidas(p),
            "disponivel": bool(price_id_do_plano(p["id"], p)),
        }
        for p in _planos_db()
    ]


# --- Cota de mensagens ------------------------------------------------------

def _menos_um_mes(dt: datetime) -> datetime:
    ano, mes = (dt.year, dt.month - 1) if dt.month > 1 else (dt.year - 1, 12)
    dia = min(dt.day, calendar.monthrange(ano, mes)[1])
    return dt.replace(year=ano, month=mes, day=dia)


def periodo_cota(sub: dict | None) -> tuple[datetime, datetime]:
    """Janela da cota: o ciclo de cobrança vigente do Stripe. Sem ciclo conhecido,
    deriva do fim do período (1 mês antes) e, em último caso, usa o mês civil."""
    agora = datetime.now(timezone.utc)
    ini, fim = (sub or {}).get("current_period_start"), (sub or {}).get("current_period_end")
    if fim and fim > agora:
        ini = ini or _menos_um_mes(fim)
        if ini <= agora:
            return ini, fim
    ini = agora.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    prox = (ini.replace(year=ini.year + 1, month=1) if ini.month == 12
            else ini.replace(month=ini.month + 1))
    return ini, prox


def cota(tenant_id: int) -> dict:
    """Situação da cota no ciclo: incluídas no plano + pacotes válidos x usadas.
    Ilimitada quando a cota está desligada, sem billing (dev) ou em assinatura
    cortesia/manual (sem assinatura no Stripe, ex.: a Paratec)."""
    sub = store.get_subscription(tenant_id)
    inicio, fim = periodo_cota(sub)
    ilimitado = (not settings.cota_mensagens_ativa or not settings.stripe_configured
                 or not sub or not sub.get("stripe_subscription_id"))
    incluidas = _mensagens_do_plano((sub or {}).get("plan"))
    pacotes = store.pacotes_validos(tenant_id)
    extra = sum(int(p["mensagens"]) for p in pacotes)
    usadas = store.mensagens_ia_desde(tenant_id, inicio)
    limite = incluidas + extra
    return {
        "ilimitado": ilimitado,
        "plano": (sub or {}).get("plan"),
        "periodo_inicio": inicio,
        "periodo_fim": fim,
        "incluidas": incluidas,
        "pacotes": extra,
        "limite": limite,
        "usadas": usadas,
        "restantes": max(limite - usadas, 0),
        "percentual": round(100 * usadas / limite, 1) if limite else 100.0,
        "esgotada": not ilimitado and usadas >= limite,
        "pacotes_ativos": pacotes,
    }


def pode_responder(tenant_id: int) -> bool:
    """A IA ainda tem saldo de mensagens neste ciclo? Falha de leitura libera
    (não derruba o atendimento por um erro de banco)."""
    try:
        return not cota(tenant_id)["esgotada"]
    except Exception as e:  # pragma: no cover
        log.warning("checagem de cota falhou (%s); libera", e)
        return True


_AVISOS = {
    80: ("Você já usou 80% das mensagens do seu plano",
         "Seu agente já respondeu {usadas} de {limite} mensagens neste ciclo "
         "(renova em {fim}).\n\nSe precisar de mais antes disso, compre um pacote "
         "extra em {link}."),
    100: ("As mensagens do seu plano acabaram",
          "Seu agente respondeu as {limite} mensagens deste ciclo. Até {fim}, as novas "
          "conversas vão direto para a fila humana do painel.\n\nPara a IA voltar a "
          "responder agora, compre um pacote extra em {link}."),
}


def verificar_alertas_cota(tenant_id: int) -> None:
    """Avisa o responsável da conta por e-mail ao atingir 80% e 100% da cota
    (uma vez por nível, ciclo e limite). Best-effort."""
    try:
        c = cota(tenant_id)
        if c["ilimitado"] or not c["limite"]:
            return
        nivel = 100 if c["usadas"] >= c["limite"] else 80 if c["percentual"] >= 80 else 0
        if not nivel or not store.registrar_alerta_cota(
                tenant_id, c["periodo_inicio"], nivel, c["limite"]):
            return
        assunto, corpo = _AVISOS[nivel]
        corpo = corpo.format(
            usadas=f"{c['usadas']:,}".replace(",", "."), limite=f"{c['limite']:,}".replace(",", "."),
            fim=c["periodo_fim"].strftime("%d/%m/%Y"),
            link=f"{settings.panel_url.rstrip('/')}/assinatura",
        )
        from . import mailer

        for email in store.emails_owners(tenant_id):
            mailer.enviar(email, assunto, corpo)
        store.log_event(tenant_id, f"cota_{nivel}")
    except Exception as e:  # pragma: no cover
        log.warning("aviso de cota falhou: %s", e)


def uso(tenant_id: int) -> dict:
    """Cota de mensagens do ciclo + pacotes à venda (tela Assinatura)."""
    return {
        **cota(tenant_id),
        "pacotes_disponiveis": [
            {"id": p["id"], "nome": p["nome"], "mensagens": int(p["mensagens"]),
             "preco": float(p["preco"])}
            for p in store.list_message_packs()
        ],
    }


# --- Checkout -------------------------------------------------------------

def _garantir_customer(stripe, tenant: TenantCtx) -> str:
    """Customer do Stripe do tenant (cria no 1º checkout)."""
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
    return customer_id


def criar_checkout(tenant: TenantCtx, plano: str) -> str:
    """Cria a Checkout Session (assinatura, SEM trial) e devolve a URL."""
    stripe = _init_stripe()
    price_id = price_id_do_plano(plano) if plano in PLANOS else None
    if not price_id:
        raise HTTPException(400, "plano inválido ou indisponível")

    customer_id = _garantir_customer(stripe, tenant)
    sess = stripe.checkout.Session.create(
        mode="subscription",
        customer=customer_id,
        client_reference_id=str(tenant.tenant_id),
        line_items=[{"price": price_id, "quantity": 1}],
        # SEM trial: omitimos subscription_data.trial_* → cobra a 1ª fatura já.
        subscription_data={"metadata": {"tenant_id": str(tenant.tenant_id)}},
        success_url=settings.billing_success_url,
        cancel_url=settings.billing_cancel_url,
    )
    return sess["url"]


TIPO_PACOTE = "pacote_mensagens"


def criar_checkout_pacote(tenant: TenantCtx, pack_id: str) -> str:
    """Checkout de pagamento único (pré-pago) de um pacote de mensagens. O saldo
    só entra quando o Stripe confirma o pagamento (webhook) e vale até o fim do
    ciclo de cobrança em que foi pago."""
    stripe = _init_stripe()
    if not assinatura_ativa(tenant.tenant_id):
        raise HTTPException(402, "subscription_required")
    pack = store.get_message_pack(pack_id)
    if not pack or not pack.get("ativo"):
        raise HTTPException(400, "pacote inválido ou indisponível")

    customer_id = _garantir_customer(stripe, tenant)
    compra_id = store.create_pack_purchase(tenant.tenant_id, pack, tenant.email)
    meta = {"tipo": TIPO_PACOTE, "tenant_id": str(tenant.tenant_id), "compra_id": str(compra_id)}
    sess = stripe.checkout.Session.create(
        mode="payment",
        customer=customer_id,
        client_reference_id=str(tenant.tenant_id),
        line_items=[{
            "quantity": 1,
            "price_data": {
                "currency": "brl",
                "unit_amount": int(round(float(pack["preco"]) * 100)),
                "product_data": {
                    "name": f"AtentBot · {pack['nome']}",
                    "description": "Mensagens extras da IA, válidas até o fim do ciclo atual da assinatura.",
                },
            },
        }],
        metadata=meta,
        payment_intent_data={"metadata": meta},
        success_url=settings.pacote_success_url,
        cancel_url=settings.pacote_cancel_url,
    )
    sess = _plain(sess)
    store.set_pack_purchase_session(compra_id, sess["id"])
    return sess["url"]


def _pacote_do_evento(obj: dict) -> tuple[int, int] | None:
    meta = obj.get("metadata") or {}
    if meta.get("tipo") != TIPO_PACOTE:
        return None
    try:
        return int(meta["tenant_id"]), int(meta["compra_id"])
    except (KeyError, TypeError, ValueError):
        log.warning("webhook: pacote sem tenant/compra na metadata (%s)", obj.get("id"))
        return None


def _confirmar_pacote(tenant_id: int, compra_id: int) -> None:
    """Credita o pacote: vale até o fim do ciclo vigente no momento do pagamento.
    Com saldo de novo, devolve à IA as conversas pausadas só pela cota."""
    inicio, fim = periodo_cota(store.get_subscription(tenant_id))
    if store.confirmar_pack_purchase(compra_id, tenant_id, fim):
        store.log_event(tenant_id, "pacote_mensagens_pago", meta={"compra_id": compra_id})
        retomar_conversas_da_cota(tenant_id, inicio)


def retomar_conversas_da_cota(tenant_id: int, desde: datetime) -> int:
    """Volta para a IA as conversas que a cota esgotada mandou para a fila humana,
    exceto aquelas em que a equipe já respondeu ou anotou algo. Best-effort."""
    try:
        threads = store.conversas_pausadas_pela_cota(tenant_id, desde)
        for th in threads:
            store.set_status(tenant_id, th, "ia")
            store.log_event(tenant_id, "cota_retomada", thread_id=th)
        return len(threads)
    except Exception as e:  # pragma: no cover
        log.warning("retomar conversas após pacote falhou: %s", e)
        return 0


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


# --- Preço base dos planos (central admin) -----------------------------

def planos_admin() -> dict:
    """Planos com dados de Stripe, nº de assinantes e histórico de preços."""
    try:
        contagem = store.contagem_assinantes_por_plano()
        historico = store.plan_price_history(limit=30)
        pacotes = store.list_message_packs(apenas_ativos=False)
    except Exception:  # pragma: no cover
        contagem, historico, pacotes = {}, [], []
    itens = [
        {
            **p,
            "preco": float(p["preco"]),
            "stripe_price_id": price_id_do_plano(p["id"], p),
            "assinantes": contagem.get(p["id"], 0),
            "mensagens_incluidas": _incluidas(p),
        }
        for p in _planos_db()
    ]
    return {"items": itens, "historico": historico, "pacotes": pacotes,
            "stripe_configurado": settings.stripe_configured}


def alterar_preco(plano: str, preco: float, aplicar_existentes: bool,
                  alterado_por: str | None) -> dict:
    """Altera o preço base de um plano em toda a cadeia de cobrança.

    Preço no Stripe é imutável, então: cria um Price novo no mesmo produto
    (herdando moeda/recorrência e o lookup_key), arquiva o anterior e grava o
    novo como vigente → próximos checkouts já usam o valor novo. Com
    `aplicar_existentes`, troca o item do plano nas assinaturas vivas SEM
    proração (o valor novo vale a partir da próxima fatura). Sem Stripe
    configurado, só atualiza o valor exibido."""
    atual = store.get_plan(plano)
    if not atual:
        raise HTTPException(404, "plano não encontrado")
    centavos = int(round(preco * 100))
    if centavos <= 0:
        raise HTTPException(422, "preço deve ser maior que zero")
    preco = centavos / 100

    price_antigo = price_id_do_plano(plano, atual)
    novo_price_id, product_id = None, atual.get("stripe_product_id")
    migradas = falhas = 0

    if settings.stripe_configured:
        stripe = _init_stripe()
        try:
            recurring = {"interval": "month"}
            moeda = "brl"
            lookup_key = f"atentbot_{plano}_mensal"
            if price_antigo:
                antigo = _plain(stripe.Price.retrieve(price_antigo))
                product_id = antigo["product"]
                moeda = antigo["currency"]
                rec = antigo.get("recurring") or {}
                recurring = {"interval": rec.get("interval", "month"),
                             "interval_count": rec.get("interval_count", 1)}
                lookup_key = antigo.get("lookup_key") or lookup_key
            if not product_id:
                prod = stripe.Product.create(name=f"AtentBot {atual['nome']}",
                                             metadata={"plan": plano})
                product_id = prod["id"]
            novo = stripe.Price.create(
                product=product_id, currency=moeda, unit_amount=centavos,
                recurring=recurring, lookup_key=lookup_key, transfer_lookup_key=True,
                metadata={"plan": plano},
            )
            novo_price_id = novo["id"]
        except HTTPException:
            raise
        except Exception as e:
            log.error("criar price do plano %s falhou: %s", plano, e)
            raise HTTPException(502, f"Stripe recusou o novo preço: {e}")

        if aplicar_existentes:
            for sub in store.assinaturas_do_plano(plano):
                try:
                    full = _plain(stripe.Subscription.retrieve(sub["stripe_subscription_id"]))
                    item = next(
                        (it for it in full["items"]["data"]
                         if _plan_do_price(it["price"]["id"]) == plano), None)
                    if not item:
                        falhas += 1
                        continue
                    if item["price"]["id"] != novo_price_id:
                        stripe.Subscription.modify(
                            full["id"],
                            items=[{"id": item["id"], "price": novo_price_id}],
                            proration_behavior="none",
                        )
                    store.upsert_subscription(sub["tenant_id"], stripe_price_id=novo_price_id)
                    migradas += 1
                except Exception as e:
                    falhas += 1
                    log.warning("migrar assinatura %s p/ novo preço falhou: %s",
                                sub["stripe_subscription_id"], e)

        # Arquiva o preço antigo só depois de migrar (assinaturas que ficaram
        # nele continuam sendo cobradas normalmente; só some de novos checkouts).
        if price_antigo and price_antigo != novo_price_id:
            try:
                stripe.Price.modify(price_antigo, active=False)
            except Exception as e:  # pragma: no cover
                log.warning("arquivar price %s falhou: %s", price_antigo, e)

    store.update_plan_price(
        plano, preco, stripe_price_id=novo_price_id, stripe_product_id=product_id,
        preco_anterior=float(atual["preco"]), stripe_price_id_anterior=price_antigo,
        migradas=migradas, falhas=falhas, alterado_por=alterado_por,
    )
    return {**planos_admin(), "resultado": {
        "plano": plano, "preco": preco, "stripe_price_id": novo_price_id,
        "assinaturas_migradas": migradas, "assinaturas_falhas": falhas,
    }}


# --- Webhook --------------------------------------------------------------

def _plan_do_price(price_id: str | None) -> str | None:
    if not price_id:
        return None
    try:
        plano = store.plan_by_price_id(price_id)
    except Exception:  # pragma: no cover
        plano = None
    return plano or settings.price_to_plan.get(price_id)


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
    # API Stripe >= 2025-03 moveu current_period_end p/ os itens da assinatura.
    period_end = sub_obj.get("current_period_end") or max(
        (it.get("current_period_end") or 0 for it in items), default=0) or None
    period_start = sub_obj.get("current_period_start") or max(
        (it.get("current_period_start") or 0 for it in items), default=0) or None
    # O item do plano base é o que mapeia p/ um plano (assinaturas antigas ainda podem ter itens metered).
    price_id, plano = None, None
    for it in items:
        pid = it["price"]["id"]
        plano = _plan_do_price(pid)
        if plano:
            price_id = pid
            break
    if not price_id and items:
        price_id = items[0]["price"]["id"]
    store.upsert_subscription(
        tenant_id,
        stripe_subscription_id=sub_obj.get("id"),
        stripe_customer_id=customer_id,
        plan=plano,
        stripe_price_id=price_id,
        status=sub_obj.get("status"),
        cancel_at_period_end=bool(sub_obj.get("cancel_at_period_end")),
        current_period_end=_dt(period_end),
        current_period_start=_dt(period_start),
    )


def alterar_cota(plano: str, mensagens: int, alterado_por: str | None) -> dict:
    """Muda quantas mensagens o plano inclui por ciclo. Vale na hora para todos
    os assinantes do plano (não mexe no Stripe)."""
    if not store.get_plan(plano):
        raise HTTPException(404, "plano não encontrado")
    store.set_plan_mensagens(plano, mensagens, alterado_por)
    return planos_admin()


def alterar_pacote(pack_id: str, *, mensagens: int | None, preco: float | None,
                   ativo: bool | None, alterado_por: str | None) -> dict:
    """Edita um pacote avulso. O preço vai inline no checkout, então vale para as
    próximas compras sem criar nada no Stripe."""
    if not store.get_message_pack(pack_id):
        raise HTTPException(404, "pacote não encontrado")
    if preco is not None:
        preco = int(round(preco * 100)) / 100
    # O nome acompanha a quantidade ("+1.000 mensagens"), p/ nunca divergir dela.
    nome = f"+{mensagens:,} mensagens".replace(",", ".") if mensagens else None
    store.update_message_pack(pack_id, nome=nome, mensagens=mensagens, preco=preco,
                              ativo=ativo, alterado_por=alterado_por)
    return planos_admin()


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

    event = _plain(event)

    # Idempotência: cada evento é processado uma única vez.
    try:
        if store.stripe_event_seen(event["id"], event.get("type")):
            return {"ignored": True}
    except Exception:  # pragma: no cover
        pass

    tipo = event["type"]
    obj = event["data"]["object"]

    pacote = _pacote_do_evento(obj) if tipo.startswith("checkout.session.") else None
    if pacote:
        # Pacote avulso (mode=payment). Cartão confirma no `completed`; Pix/boleto
        # confirmam depois, no `async_payment_succeeded`.
        if tipo in ("checkout.session.completed", "checkout.session.async_payment_succeeded"):
            if obj.get("payment_status") == "paid":
                _confirmar_pacote(*pacote)
        elif tipo == "checkout.session.async_payment_failed":
            store.falhar_pack_purchase(pacote[1], pacote[0])
    elif tipo == "checkout.session.completed":
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
                    _sync_subscription(_plain(full))
                except Exception as e:  # pragma: no cover
                    log.warning("retrieve subscription %s falhou: %s", sub_id, e)
                    store.upsert_subscription(
                        tid, stripe_subscription_id=sub_id,
                        stripe_customer_id=customer_id, status="active",
                    )
    elif tipo in ("customer.subscription.created", "customer.subscription.updated",
                  "customer.subscription.deleted"):
        _sync_subscription(obj)
    elif tipo in ("invoice.paid", "invoice.payment_succeeded", "invoice.payment_failed"):
        # O status vem via customer.subscription.updated; aqui reforçamos o período
        # quando a fatura tem a assinatura embutida.
        # API Stripe >= 2025-03: a assinatura da fatura fica em parent.subscription_details.
        sub_id = obj.get("subscription") or (
            ((obj.get("parent") or {}).get("subscription_details") or {}).get("subscription"))
        if sub_id:
            try:
                full = stripe.Subscription.retrieve(sub_id)
                _sync_subscription(_plain(full))
            except Exception as e:  # pragma: no cover
                log.warning("retrieve subscription (invoice) %s falhou: %s", sub_id, e)

    return {"ok": True, "type": tipo}
