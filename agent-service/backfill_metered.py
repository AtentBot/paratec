#!/usr/bin/env python
"""Adiciona os itens metered (consumo) às assinaturas Stripe JÁ existentes.

Novas assinaturas já entram com os itens metered no checkout; as antigas não os
têm retroativamente. Este utilitário percorre as assinaturas com
stripe_subscription_id e adiciona os preços metered que faltarem (idempotente).

Uso (em agent-service/, com o venv e as envs do Stripe/DB carregadas):
    .venv/bin/python backfill_metered.py            # DRY-RUN (só mostra)
    .venv/bin/python backfill_metered.py --apply    # aplica de verdade

Requer STRIPE_SECRET_KEY + STRIPE_PRICE_METER_* configurados (metered ligado).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.db import query  # noqa: E402
from app.settings import settings  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Backfill de itens metered nas assinaturas.")
    ap.add_argument("--apply", action="store_true", help="aplica (sem isto, é dry-run)")
    args = ap.parse_args()

    precos = settings.metered_price_ids
    if not settings.stripe_secret_key or not precos:
        print("erro: configure STRIPE_SECRET_KEY e os STRIPE_PRICE_METER_* antes.",
              file=sys.stderr)
        return 2

    import stripe

    stripe.api_key = settings.stripe_secret_key

    subs = query(
        "SELECT tenant_id, stripe_subscription_id FROM subscriptions "
        "WHERE stripe_subscription_id IS NOT NULL"
    )
    if not subs:
        print("nenhuma assinatura com stripe_subscription_id.")
        return 0

    total_add = 0
    for s in subs:
        sid = s["stripe_subscription_id"]
        try:
            sub = stripe.Subscription.retrieve(sid, expand=["items.data.price"])
        except Exception as e:
            print(f"[skip] {sid}: falha ao buscar ({e})")
            continue
        existentes = {it["price"]["id"] for it in sub["items"]["data"]}
        faltam = [p for p in precos if p not in existentes]
        if not faltam:
            print(f"[ok]   tenant {s['tenant_id']} {sid}: já tem os itens metered")
            continue
        print(f"[add]  tenant {s['tenant_id']} {sid}: faltam {faltam}"
              + ("" if args.apply else "  (dry-run)"))
        if args.apply:
            for p in faltam:
                # item metered: sem 'quantity'
                stripe.SubscriptionItem.create(subscription=sid, price=p)
                total_add += 1

    print(f"\n{'aplicado' if args.apply else 'dry-run'}: "
          f"{total_add if args.apply else 'nenhuma alteração feita'}")
    if not args.apply:
        print("rode de novo com --apply para efetivar.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
