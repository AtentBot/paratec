#!/usr/bin/env python
"""Cria (idempotente) um usuário OWNER para um tenant — necessário para logar no
painel após a virada SaaS (substitui o Authentik).

Uso (a partir de agent-service/, com o venv):
    .venv/bin/python seed_owner.py --slug paratec --email voce@paratec.com --senha 'ForteAqui123'
    # --nome opcional; --tenant-nome cria o tenant se o slug ainda não existir

Lê a conexão do Postgres das mesmas variáveis do serviço (PGHOST/PGPORT/...).
Se o usuário (e-mail) já existir, apenas informa e sai sem alterar a senha.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Permite rodar de qualquer diretório: garante que o pacote `app` esteja no path.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app import auth, store  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Cria um usuário owner para um tenant.")
    ap.add_argument("--slug", required=True, help="slug do tenant (ex.: paratec)")
    ap.add_argument("--email", required=True, help="e-mail de login do owner")
    ap.add_argument("--senha", required=True, help="senha (mín. 8 caracteres)")
    ap.add_argument("--nome", default=None, help="nome do usuário (opcional)")
    ap.add_argument("--tenant-nome", default=None,
                    help="cria o tenant com este nome se o slug não existir")
    args = ap.parse_args()

    if len(args.senha) < 8:
        print("erro: a senha deve ter ao menos 8 caracteres", file=sys.stderr)
        return 2
    if not auth.email_valido(args.email):
        print("erro: e-mail inválido", file=sys.stderr)
        return 2

    # Garante o schema (idempotente) — cria as tabelas de conta se faltarem.
    store.ensure_schema()

    tenant = store.get_tenant_by_slug(args.slug)
    if not tenant:
        if not args.tenant_nome:
            print(f"erro: tenant '{args.slug}' não existe. "
                  f"Passe --tenant-nome para criá-lo.", file=sys.stderr)
            return 3
        tenant = store.create_tenant(args.slug, args.tenant_nome)
        store.ensure_default_agent(tenant["id"])
        print(f"tenant criado: {args.slug} (id={tenant['id']})")

    existente = store.get_user_by_email(args.email)
    if existente:
        print(f"usuário já existe: {args.email} "
              f"(tenant_id={existente['tenant_id']}) — nada alterado.")
        return 0

    user = store.create_user(
        tenant["id"], args.email, auth.hash_senha(args.senha), args.nome, role="owner"
    )
    store.ensure_default_agent(tenant["id"])
    print(f"owner criado: {user['email']} para o tenant '{args.slug}' "
          f"(id={tenant['id']}). Já é possível logar no painel.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
